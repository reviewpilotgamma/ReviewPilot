"""Batched reviews of large diffs: batching, merge, partial reviews, verdict floor, time limit and limits."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.core.config import reload_settings
from app.models import Job, PRReview
from app.schemas.events import JobOut
from app.services import reviewer
from app.services.errors import (
    ContextTooLargeError,
    DiffFetchError,
    DiffTooLargeError,
    GeminiPermanentError,
    GeminiTransientError,
    error_code_for,
)
from app.services.review_parser import parse_review
from tests.conftest import GITHUB_API
from tests.test_reviewer import COMMENTS_URL, GEMINI_URL, PR_JSON, make_job

MERGE_MARKER = "Merge them into ONE review"
FILE_CHARS = 2_500  # with DIFF_BATCH_TOKENS=1000 (3,000 chars) every file lands in its own batch


def file_diff(path: str, chars: int = FILE_CHARS) -> str:
    head = f"diff --git a/{path} b/{path}\nindex 1..2 100644\n--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,40 @@\n"
    lines, size = [], len(head)
    while size < chars:
        line = f"+{path} line {len(lines)}\n"
        lines.append(line)
        size += len(line)
    return head + "".join(lines)


def review_md(verdict: str = "warning", score: float = 6.5, title: str = "Batch finding") -> str:
    tag = {"critical": "Critical", "warning": "Warning", "passed": "Passed"}[verdict]
    return (
        f"### Executive Summary\nSummary for {title}.\n"
        f"### Architectural Findings\n- **{tag}** {title} — `x.py`: details.\n"
        "### Specific Recommendations\n1. Do the thing.\n"
        "### What Looks Solid\n- Tests.\n"
        f'<!-- reviewpilot-meta: {{"score": {score}, "verdict": "{verdict}"}} -->'
    )


def ok(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


def is_merge(request: httpx.Request) -> bool:
    body = json.loads(request.content)
    return MERGE_MARKER in body["systemInstruction"]["parts"][0]["text"]


def batch_number(request: httpx.Request) -> int:
    content = json.loads(request.content)["contents"][0]["parts"][0]["text"]
    return int(content.split("This is batch ", 1)[1].split(" ", 1)[0])


@pytest.fixture
def small_batches(monkeypatch):
    monkeypatch.setenv("DIFF_BATCH_TOKENS", "1000")
    monkeypatch.setattr(reviewer, "BATCH_RETRY_DELAYS", (0.0,))
    reload_settings()


def serve(mock_http, diff: str, *, diff_status: int = 200):
    mock_http.post(f"{GITHUB_API}/app/installations/99/access_tokens").respond(201, json={"token": "t"})
    mock_http.get(f"{GITHUB_API}/repos/acme/api/pulls/7").mock(
        side_effect=lambda r: (
            httpx.Response(diff_status, text=diff, json=None if diff_status == 200 else {"message": "too large"})
            if "diff" in r.headers["Accept"]
            else httpx.Response(200, json={**PR_JSON, "changed_files": diff.count("diff --git")})
        )
    )
    return mock_http.post(COMMENTS_URL).respond(201, json={"id": 1})


def three_files() -> str:
    return file_diff("a.py") + file_diff("b.py") + file_diff("c.py")


def posted(comment) -> str:
    return json.loads(comment.calls[0].request.content)["body"]


def stored(db) -> PRReview:
    db.expire_all()
    return db.scalars(select(PRReview)).one()


# --------------------------------------------------------------------------- happy path
async def test_large_diff_is_batched_then_merged(mock_http, db, small_batches):
    diff = three_files()
    comment = serve(mock_http, diff)
    gemini = mock_http.post(GEMINI_URL).mock(
        side_effect=lambda r: ok(review_md("warning", 6.0, "Merged")) if is_merge(r) else ok(review_md())
    )

    await reviewer.handle_review(make_job(db, comment_id=None))

    requests = [c.request for c in gemini.calls]
    assert len(requests) == 4 and is_merge(requests[-1])
    assert sorted(batch_number(r) for r in requests[:-1]) == [1, 2, 3]
    first = json.loads(requests[0].content)["contents"][0]["parts"][0]["text"]
    assert "- a.py (+" in first and "- c.py (+" in first  # full file list for reference
    merge_content = json.loads(requests[-1].content)["contents"][0]["parts"][0]["text"]
    assert "Part 3 of 3" in merge_content and "Files: c.py" in merge_content

    body = posted(comment)
    assert "Summary for Merged." in body and "Partially reviewed" not in body
    review = stored(db)
    assert review.verdict == "warning" and review.score == 6.0
    assert review.lines_reviewed == reviewer.count_changed_lines(diff)
    assert not review.diff_truncated


async def test_batches_respect_concurrency_limit(mock_http, db, small_batches, monkeypatch):
    monkeypatch.setenv("DIFF_BATCH_CONCURRENCY", "2")
    reload_settings()
    serve(mock_http, "".join(file_diff(f"f{i}.py") for i in range(6)))
    in_flight = peak = 0

    async def slow(request):
        nonlocal in_flight, peak
        if is_merge(request):
            return ok(review_md())
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return ok(review_md())

    mock_http.post(GEMINI_URL).mock(side_effect=slow)
    await reviewer.handle_review(make_job(db, comment_id=None))
    assert peak == 2


# --------------------------------------------------------------------------- partial reviews
async def test_transient_batch_failure_gives_partial_review(mock_http, db, small_batches):
    comment = serve(mock_http, three_files())
    gemini = mock_http.post(GEMINI_URL).mock(
        side_effect=lambda r: (
            ok(review_md())
            if is_merge(r) or batch_number(r) != 2
            else httpx.Response(503, json={"error": {"message": "busy"}})
        )
    )

    await reviewer.handle_review(make_job(db, comment_id=None))

    assert gemini.call_count == 3 + 1 + 1  # three batches, one retry of batch 2, one merge
    body = posted(comment)
    assert "Partially reviewed: 2 of 3 files. Not reviewed: `b.py`" in body
    review = stored(db)
    assert review.diff_truncated
    assert review.lines_reviewed == reviewer.count_changed_lines(file_diff("a.py") + file_diff("c.py"))


async def test_permanent_batch_failure_is_not_retried(mock_http, db, small_batches):
    comment = serve(mock_http, three_files())
    blocked = {"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []}
    gemini = mock_http.post(GEMINI_URL).mock(
        side_effect=lambda r: (
            httpx.Response(200, json=blocked) if not is_merge(r) and batch_number(r) == 1 else ok(review_md())
        )
    )

    await reviewer.handle_review(make_job(db, comment_id=None))

    assert gemini.call_count == 4
    assert "Not reviewed: `a.py`" in posted(comment)


async def test_all_batches_failing_raises(mock_http, db, small_batches):
    serve(mock_http, three_files())
    mock_http.post(GEMINI_URL).respond(400, json={"error": {"message": "bad"}})
    with pytest.raises(GeminiPermanentError):
        await reviewer.handle_review(make_job(db, comment_id=None))
    assert db.scalars(select(PRReview)).all() == []


async def test_all_batches_transient_raises_retryable(mock_http, db, small_batches):
    serve(mock_http, three_files())
    gemini = mock_http.post(GEMINI_URL).respond(503, json={"error": {"message": "busy"}})
    with pytest.raises(GeminiTransientError):
        await reviewer.handle_review(make_job(db, comment_id=None))
    assert gemini.call_count == 3 * reviewer.BATCH_ATTEMPTS


async def test_time_limit_lists_unfinished_batches(mock_http, db, small_batches, monkeypatch):
    monkeypatch.setenv("JOB_TIMEOUT_SECONDS", "1")
    reload_settings()
    comment = serve(mock_http, three_files())

    async def third_is_slow(request):
        if not is_merge(request) and batch_number(request) == 3:
            await asyncio.sleep(5)
        return ok(review_md())

    mock_http.post(GEMINI_URL).mock(side_effect=third_is_slow)
    await reviewer.handle_review(make_job(db, comment_id=None))
    assert "Partially reviewed: 2 of 3 files. Not reviewed: `c.py`" in posted(comment)


# --------------------------------------------------------------------------- merge
async def test_merge_failure_joins_batch_reviews_in_code(mock_http, db, small_batches):
    comment = serve(mock_http, three_files())
    mock_http.post(GEMINI_URL).mock(
        side_effect=lambda r: (
            httpx.Response(500, json={"error": {"message": "down"}})
            if is_merge(r)
            else ok(review_md(title=f"Batch {batch_number(r)}"))
        )
    )

    await reviewer.handle_review(make_job(db, comment_id=None))

    body = posted(comment)
    assert "reviewed in 3 parts" in body
    assert "_Part 1 of 3_" in body and "Batch 3 —" in body
    assert stored(db).verdict == "warning"


async def test_merged_verdict_never_better_than_worst_batch(mock_http, db, small_batches):
    serve(mock_http, three_files())
    mock_http.post(GEMINI_URL).mock(
        side_effect=lambda r: (
            ok(review_md("passed", 9.0, "All good"))
            if is_merge(r)
            else ok(review_md("critical", 3.0) if batch_number(r) == 2 else review_md("passed", 9.0))
        )
    )
    await reviewer.handle_review(make_job(db, comment_id=None))
    review = stored(db)
    assert review.verdict == "critical" and review.score <= 4.9


def test_enforce_verdict_floor_and_fallback_merge():
    merged = parse_review(review_md("passed", 9.5))
    floored = reviewer.enforce_verdict_floor(merged, ["passed", "warning"])
    assert (floored.verdict, floored.score) == ("warning", 7.9)
    joined = reviewer.fallback_merge([(1, parse_review(review_md())), (2, parse_review(review_md("critical", 2)))], 2)
    assert joined.verdict == "critical" and joined.score == 2.0
    assert joined.body.count("### ") == 4


# --------------------------------------------------------------------------- filtering and limits
async def test_lockfiles_never_reach_the_prompt(mock_http, db, small_batches):
    comment = serve(mock_http, file_diff("src/app.py", 500) + file_diff("package-lock.json") + file_diff("dist/x.js"))
    gemini = mock_http.post(GEMINI_URL).mock(return_value=ok(review_md()))

    await reviewer.handle_review(make_job(db, comment_id=None))

    assert gemini.call_count == 1
    sent = gemini.calls[0].request.content.decode()
    assert "package-lock.json" not in sent and "dist/x.js" not in sent
    assert "Not reviewed (generated or lockfiles): `package-lock.json`, `dist/x.js`" in posted(comment)


async def test_only_filtered_files_posts_empty_notice(mock_http, db, small_batches):
    comment = serve(mock_http, file_diff("yarn.lock"))
    gemini = mock_http.post(GEMINI_URL).mock(return_value=ok(review_md()))
    await reviewer.handle_review(make_job(db, comment_id=None))
    assert gemini.call_count == 0
    body = posted(comment)
    assert "no file changes" in body and "`yarn.lock`" in body


async def test_documents_filling_the_context_fail_without_llm_call(mock_http, db, monkeypatch):
    monkeypatch.setenv("GEMINI_CONTEXT_TOKENS", "8192")
    reload_settings()
    serve(mock_http, three_files())
    gemini = mock_http.post(GEMINI_URL).mock(return_value=ok(review_md()))
    with pytest.raises(ContextTooLargeError) as info:
        await reviewer.handle_review(make_job(db, comment_id=None))
    assert not info.value.retryable and gemini.call_count == 0


@pytest.mark.parametrize(("status", "error"), [(406, DiffTooLargeError), (404, DiffFetchError)])
async def test_diff_fetch_errors(mock_http, db, status, error):
    serve(mock_http, "", diff_status=status)
    with pytest.raises(error) as info:
        await reviewer.handle_review(make_job(db, comment_id=None))
    assert type(info.value) is error and not info.value.retryable


async def test_plan_job_maps_406_too(mock_http, db):
    serve(mock_http, "", diff_status=406)
    with pytest.raises(DiffTooLargeError):
        await reviewer.handle_plan(make_job(db, kind="plan", comment_id=None))


def test_error_code_on_job_api():
    assert error_code_for("DiffTooLargeError: GitHub 406: too large") == "diff_too_large"
    assert error_code_for("DiffFetchError: GitHub 404") is None
    assert error_code_for(None) is None
    now = datetime.now(UTC)
    job = Job(id=1, kind="review", status="failed", attempts=1, max_attempts=3, next_run_at=now, updated_at=now)
    job.last_error = "DiffTooLargeError: GitHub 406"
    assert JobOut.model_validate(job).model_dump()["error_code"] == "diff_too_large"


def test_file_lists_are_capped():
    paths = [f"f{i}.py" for i in range(60)]
    assert reviewer.list_files(paths).endswith("`f49.py` and 10 more")
