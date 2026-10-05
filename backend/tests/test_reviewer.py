from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select

from app.models import Job, PRReview, WebhookEvent
from app.services import reviewer
from app.services.errors import DiffFetchError, GeminiPermanentError
from app.services.reviewer import JobContext, count_changed_lines, truncate_diff
from app.services.rules import upsert_rule
from tests.conftest import FIXTURES, GEMINI_API, GITHUB_API

DIFF = (FIXTURES / "sample.diff").read_text(encoding="utf-8")
LLM_OUTPUT = (FIXTURES / "gemini_review.md").read_text(encoding="utf-8")
PR_JSON = {
    "number": 7,
    "title": "Add payment retries",
    "body": "Adds retries",
    "user": {"login": "bob"},
    "base": {"ref": "main"},
    "head": {"ref": "feat"},
    "state": "open",
    "additions": 5,
    "deletions": 2,
    "changed_files": 1,
}
GEMINI_URL = f"{GEMINI_API}/models/gemini-2.0-flash:generateContent"
COMMENTS_URL = f"{GITHUB_API}/repos/acme/api/issues/7/comments"


def gemini_response(text: str = LLM_OUTPUT) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


@pytest.fixture
def github(mock_http):
    mock_http.post(f"{GITHUB_API}/app/installations/99/access_tokens").respond(201, json={"token": "t"})
    mock_http.get(f"{GITHUB_API}/repos/acme/api/pulls/7").mock(
        side_effect=lambda request: (
            httpx.Response(200, text=DIFF)
            if request.headers["Accept"] == "application/vnd.github.v3.diff"
            else httpx.Response(200, json=PR_JSON)
        )
    )
    mock_http.post(f"{GITHUB_API}/repos/acme/api/issues/comments/555/reactions").respond(201, json={})
    return mock_http


def make_job(db, kind: str = "review", **overrides) -> JobContext:
    data = {
        "installation_id": 99,
        "owner": "acme",
        "repo": "api",
        "pr_number": 7,
        "author": "bob",
        "trigger": "comment",
        "requester": "alice",
        "requester_note": "focus on auth boundaries",
        "comment_id": 555,
    }
    data.update(overrides)
    event = WebhookEvent(event="issue_comment", status="queued", payload_preview="{}")
    db.add(event)
    db.flush()
    job = Job(event_id=event.id, kind=kind, payload=json.dumps(data), status="running", attempts=1)
    db.add(job)
    db.commit()
    return JobContext(job.id, kind, data, None, 1, 3)


def test_truncate_diff_on_line_boundary():
    diff = "line1\nline2\nline3\n"
    out, truncated = truncate_diff(diff, 9)
    assert truncated and out.startswith("line1\n") and "DIFF TRUNCATED" in out
    assert truncate_diff(diff, 1000) == (diff, False)


def test_count_changed_lines_ignores_headers():
    assert count_changed_lines(DIFF) == 7


async def test_happy_path_persists_and_posts(github, db):
    gemini_route = github.post(GEMINI_URL).respond(200, json=gemini_response())
    comment_route = github.post(COMMENTS_URL).respond(201, json={"id": 777})
    upsert_rule(
        db,
        "acme/api",
        custom_instructions="Strict idempotency keys in payment flows",
        verbosity="detailed",
        review_mode="auto",
        enable_security=True,
        user_id=None,
    )
    ctx = make_job(db)

    await reviewer.handle_review(ctx)

    sent = json.loads(gemini_route.calls[0].request.content)
    system = sent["systemInstruction"]["parts"][0]["text"]
    assert "Strict idempotency keys in payment flows" in system
    assert "Be detailed" in system and "SECURITY MODE ENABLED" in system
    assert "focus on auth boundaries" in system
    assert gemini_route.calls[0].request.headers["x-goog-api-key"] == "gemini-key-1234"
    assert "key=" not in str(gemini_route.calls[0].request.url)

    body = json.loads(comment_route.calls[0].request.content)["body"]
    assert body.startswith("## ✈️ ReviewPilot Architectural Audit")
    assert body.rstrip().endswith("_Triggered via ReviewPilot · Architecture Gatekeeper_")
    assert "🔴 Critical Risk" in body and "3.5/10" in body
    assert "_Requested by @alice: “focus on auth boundaries”_" in body
    assert "reviewpilot-meta" not in body

    db.expire_all()
    review = db.scalars(select(PRReview)).one()
    assert (review.verdict, review.score, review.lines_reviewed) == ("critical", 3.5, 7)
    assert review.github_comment_id == 777 and review.full_markdown == body
    assert review.repo_full_name == "acme/api" and review.author == "bob"
    assert db.get(Job, ctx.job_id).review_id == review.id


async def test_default_rules_used_when_none_stored(github, db):
    gemini_route = github.post(GEMINI_URL).respond(200, json=gemini_response())
    github.post(COMMENTS_URL).respond(201, json={"id": 1})
    await reviewer.handle_review(make_job(db))
    system = json.loads(gemini_route.calls[0].request.content)["systemInstruction"]["parts"][0]["text"]
    assert "Be concise" in system and "(none — apply general architectural standards)" in system


async def test_retry_with_saved_review_does_not_call_llm(github, db):
    gemini_route = github.post(GEMINI_URL).respond(200, json=gemini_response())
    comment_route = github.post(COMMENTS_URL).mock(
        side_effect=[httpx.Response(502), httpx.Response(201, json={"id": 9})]
    )
    ctx = make_job(db)
    with pytest.raises(Exception):  # noqa: B017 - first post fails transiently
        await reviewer.handle_review(ctx)
    review_id = db.get(Job, ctx.job_id).review_id
    assert review_id is not None

    retry = JobContext(ctx.job_id, "review", ctx.data, review_id, 2, 3)
    await reviewer.handle_review(retry)
    assert gemini_route.call_count == 1
    assert comment_route.call_count == 2
    db.expire_all()
    assert db.get(PRReview, review_id).github_comment_id == 9


async def test_empty_diff_posts_notice(mock_http, db):
    mock_http.post(f"{GITHUB_API}/app/installations/99/access_tokens").respond(201, json={"token": "t"})
    mock_http.get(f"{GITHUB_API}/repos/acme/api/pulls/7").mock(
        side_effect=lambda r: (
            httpx.Response(200, text="") if "diff" in r.headers["Accept"] else httpx.Response(200, json=PR_JSON)
        )
    )
    comment = mock_http.post(COMMENTS_URL).respond(201, json={"id": 1})
    await reviewer.handle_review(make_job(db, comment_id=None))
    assert "no file changes" in json.loads(comment.calls[0].request.content)["body"]
    assert db.scalars(select(PRReview)).all() == []


async def test_closed_pr_skipped(mock_http, db):
    mock_http.post(f"{GITHUB_API}/app/installations/99/access_tokens").respond(201, json={"token": "t"})
    mock_http.get(f"{GITHUB_API}/repos/acme/api/pulls/7").respond(200, json={**PR_JSON, "state": "closed"})
    comment = mock_http.post(COMMENTS_URL).respond(201, json={"id": 1})
    await reviewer.handle_review(make_job(db, comment_id=None))
    assert comment.call_count == 0


async def test_diff_fetch_failure_maps_to_diff_error(mock_http, db):
    mock_http.post(f"{GITHUB_API}/app/installations/99/access_tokens").respond(201, json={"token": "t"})
    mock_http.get(f"{GITHUB_API}/repos/acme/api/pulls/7").mock(
        side_effect=lambda r: (
            httpx.Response(406, json={"message": "too large"})
            if "diff" in r.headers["Accept"]
            else httpx.Response(200, json=PR_JSON)
        )
    )
    with pytest.raises(DiffFetchError):
        await reviewer.handle_review(make_job(db, comment_id=None))


async def test_large_diff_truncated_and_flagged(github, db, monkeypatch):
    from app.core.config import reload_settings

    monkeypatch.setenv("MAX_DIFF_CHARS", "100")
    reload_settings()
    github.post(GEMINI_URL).respond(200, json=gemini_response())
    comment = github.post(COMMENTS_URL).respond(201, json={"id": 1})
    await reviewer.handle_review(make_job(db))
    body = json.loads(comment.calls[0].request.content)["body"]
    assert "exceeded 100 characters" in body
    assert db.scalars(select(PRReview)).one().diff_truncated


async def test_comment_over_limit_truncated(github, db, monkeypatch):
    from app.core.config import reload_settings

    monkeypatch.setenv("MAX_COMMENT_CHARS", "2000")
    reload_settings()
    long_output = LLM_OUTPUT.replace("### What Looks Solid", "### What Looks Solid\n" + "- solid line\n" * 500)
    github.post(GEMINI_URL).respond(200, json=gemini_response(long_output))
    comment = github.post(COMMENTS_URL).respond(201, json={"id": 1})
    await reviewer.handle_review(make_job(db))
    body = json.loads(comment.calls[0].request.content)["body"]
    assert len(body) <= 2000
    assert "review truncated" in body and body.endswith("Architecture Gatekeeper_")


async def test_gemini_blocked_response_is_permanent(github, db):
    github.post(GEMINI_URL).respond(200, json={"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(GeminiPermanentError):
        await reviewer.handle_review(make_job(db))


async def test_welcome_comment(mock_http, db):
    mock_http.post(f"{GITHUB_API}/app/installations/99/access_tokens").respond(201, json={"token": "t"})
    comment = mock_http.post(COMMENTS_URL).respond(201, json={"id": 1})
    await reviewer.handle_welcome(make_job(db, "welcome"))
    body = json.loads(comment.calls[0].request.content)["body"]
    assert "@bob" in body and "`@review`" in body


async def test_plan_uses_llm(github, db):
    github.post(GEMINI_URL).respond(200, json=gemini_response("- [ ] Run migrations\n- [ ] Add tests"))
    comment = github.post(COMMENTS_URL).respond(201, json={"id": 1})
    await reviewer.handle_plan(make_job(db, "plan"))
    body = json.loads(comment.calls[0].request.content)["body"]
    assert body.startswith("## 🧭 ReviewPilot Execution Plan") and "- [ ] Run migrations" in body


async def test_plan_falls_back_to_canned_on_permanent_error(github, db):
    github.post(GEMINI_URL).respond(400, json={"error": {"message": "bad request"}})
    comment = github.post(COMMENTS_URL).respond(201, json={"id": 1})
    await reviewer.handle_plan(make_job(db, "plan"))
    assert "Verify the change against the PR description" in json.loads(comment.calls[0].request.content)["body"]


async def test_failure_comment_uses_safe_reason(mock_http, db):
    mock_http.post(f"{GITHUB_API}/app/installations/99/access_tokens").respond(201, json={"token": "t"})
    comment = mock_http.post(COMMENTS_URL).respond(201, json={"id": 1})
    await reviewer.post_failure_comment(make_job(db), GeminiPermanentError("Gemini 400: secret detail"))
    body = json.loads(comment.calls[0].request.content)["body"]
    assert "(AI model unavailable)" in body and "secret detail" not in body
