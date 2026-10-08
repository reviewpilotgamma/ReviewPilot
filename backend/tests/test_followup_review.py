"""Follow-up reviews: a PR that changed since its last posted review gets a new Follow-up comment."""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select

from app.core.config import reload_settings
from app.models import PRReview
from app.services import reviewer
from app.services.prompts import FOLLOWUP_DIRECTIVE
from tests.conftest import GITHUB_API
from tests.test_batched_review import file_diff, is_merge, ok, review_md
from tests.test_reviewer import COMMENTS_URL, DIFF, GEMINI_URL, PR_JSON, gemini_response, make_job

OLD_SHA = "a" * 40
NEW_SHA = "b" * 40
COMPARE_URL = f"{GITHUB_API}/repos/acme/api/compare/{OLD_SHA}...{NEW_SHA}"
PREVIOUS_MD = (
    "## ReviewPilot Architectural Audit\n\n### Architectural Findings\n"
    "- **Critical** · **Hardcoded secret**\n  - **File(s):** `app/config.py`\n"
)


@pytest.fixture
def small_batches(monkeypatch):
    monkeypatch.setenv("DIFF_BATCH_TOKENS", "1000")
    monkeypatch.setattr(reviewer, "BATCH_RETRY_DELAYS", (0.0,))
    reload_settings()


def serve(mock_http, diff: str = DIFF, head_sha: str = NEW_SHA):
    mock_http.post(f"{GITHUB_API}/app/installations/99/access_tokens").respond(201, json={"token": "t"})
    pr = {**PR_JSON, "head": {"ref": "feat", "sha": head_sha}, "changed_files": max(1, diff.count("diff --git"))}
    mock_http.get(f"{GITHUB_API}/repos/acme/api/pulls/7").mock(
        side_effect=lambda r: (
            httpx.Response(200, text=diff) if "diff" in r.headers["Accept"] else httpx.Response(200, json=pr)
        )
    )
    return mock_http.post(COMMENTS_URL).respond(201, json={"id": 900})


def add_previous(db, *, head_sha: str | None = OLD_SHA, comment_id: int | None = 111) -> int:
    review = PRReview(
        repo_full_name="acme/api",
        pr_number=7,
        pr_title="Add payment retries",
        author="bob",
        summary="",
        full_markdown=PREVIOUS_MD,
        verdict="critical",
        score=3.5,
        lines_reviewed=10,
        trigger="auto",
        github_comment_id=comment_id,
        head_sha=head_sha,
    )
    db.add(review)
    db.commit()
    return review.id


def sent(route, index: int = 0) -> tuple[str, str]:
    body = json.loads(route.calls[index].request.content)
    return body["systemInstruction"]["parts"][0]["text"], body["contents"][0]["parts"][0]["text"]


def posted(comment) -> str:
    return json.loads(comment.calls[0].request.content)["body"]


def newest(db) -> PRReview:
    db.expire_all()
    return db.scalars(select(PRReview).order_by(PRReview.id.desc())).first()


async def test_first_review_stores_head_sha(mock_http, db):
    comment = serve(mock_http)
    gemini = mock_http.post(GEMINI_URL).respond(200, json=gemini_response())

    await reviewer.handle_review(make_job(db, comment_id=None))

    assert posted(comment).startswith(reviewer.BANNER)
    assert FOLLOWUP_DIRECTIVE not in sent(gemini)[0]
    review = newest(db)
    assert review.head_sha == NEW_SHA and review.previous_review_id is None


async def test_followup_posts_new_comment_with_status_context(mock_http, db):
    previous_id = add_previous(db)
    comment = serve(mock_http)
    mock_http.get(COMPARE_URL).respond(200, json={"files": [{"filename": "app/config.py", "additions": 2}]})
    gemini = mock_http.post(GEMINI_URL).respond(200, json=gemini_response())

    await reviewer.handle_review(make_job(db, comment_id=None, trigger="push", requester=None))

    system, context = sent(gemini)
    assert system.endswith(FOLLOWUP_DIRECTIVE)
    assert "Previous ReviewPilot review of commit aaaaaaa (verdict critical, score 3.5/10)" in context
    assert "**Hardcoded secret**" in context
    assert "Files changed since the previous review:\n- app/config.py (+2/-0)" in context
    assert context.index("Previous ReviewPilot review") < context.index("Diff:")

    body = posted(comment)
    assert body.startswith(
        f"{reviewer.FOLLOWUP_BANNER}\n\n_Follow-up to the review of `aaaaaaa` (🔴 Critical Risk, 3.5/10)"
        " · 1 file changed since_\n\n**Verdict:**"
    )
    assert comment.call_count == 1  # a new comment; earlier comments are never edited
    review = newest(db)
    assert review.previous_review_id == previous_id and review.head_sha == NEW_SHA
    assert review.trigger == "push"


async def test_followup_without_compare_history(mock_http, db):
    add_previous(db)
    comment = serve(mock_http)
    mock_http.get(COMPARE_URL).respond(404, json={"message": "No common ancestor"})
    gemini = mock_http.post(GEMINI_URL).respond(200, json=gemini_response())

    await reviewer.handle_review(make_job(db, comment_id=None))

    assert "Files changed since the previous review: unknown." in sent(gemini)[1]
    headline = posted(comment).split("\n")[2]
    assert headline == "_Follow-up to the review of `aaaaaaa` (🔴 Critical Risk, 3.5/10)_"


async def test_previous_review_without_sha_is_followed_up_without_compare(mock_http, db):
    add_previous(db, head_sha=None)
    comment = serve(mock_http)
    mock_http.post(GEMINI_URL).respond(200, json=gemini_response())

    await reviewer.handle_review(make_job(db, comment_id=None))

    assert posted(comment).split("\n")[2] == "_Follow-up to the previous review (🔴 Critical Risk, 3.5/10)_"


async def test_unposted_previous_review_is_ignored(mock_http, db):
    add_previous(db, comment_id=None)
    comment = serve(mock_http)
    mock_http.post(GEMINI_URL).respond(200, json=gemini_response())

    await reviewer.handle_review(make_job(db, comment_id=None))

    assert posted(comment).startswith(reviewer.BANNER)
    assert newest(db).previous_review_id is None


async def test_same_commit_review_request_runs_full_review(mock_http, db):
    add_previous(db, head_sha=NEW_SHA)
    comment = serve(mock_http)
    gemini = mock_http.post(GEMINI_URL).respond(200, json=gemini_response())

    await reviewer.handle_review(make_job(db, comment_id=None))

    assert FOLLOWUP_DIRECTIVE not in sent(gemini)[0]
    assert posted(comment).startswith(reviewer.BANNER)


async def test_push_for_already_reviewed_commit_is_skipped(mock_http, db):
    add_previous(db, head_sha=NEW_SHA)
    comment = serve(mock_http)
    gemini = mock_http.post(GEMINI_URL).respond(200, json=gemini_response())

    await reviewer.handle_review(make_job(db, comment_id=None, trigger="push", requester=None))

    assert gemini.call_count == 0 and comment.call_count == 0


async def test_batched_followup_gives_previous_review_to_merge_only(mock_http, db, small_batches):
    add_previous(db)
    comment = serve(mock_http, file_diff("a.py") + file_diff("b.py") + file_diff("c.py"))
    mock_http.get(COMPARE_URL).respond(200, json={"files": []})
    gemini = mock_http.post(GEMINI_URL).mock(side_effect=lambda r: ok(review_md()))

    await reviewer.handle_review(make_job(db, comment_id=None))

    calls = [c.request for c in gemini.calls]
    batches = [r for r in calls if not is_merge(r)]
    merges = [r for r in calls if is_merge(r)]
    assert len(batches) == 3 and len(merges) == 1
    for request in batches:
        system = json.loads(request.content)["systemInstruction"]["parts"][0]["text"]
        content = json.loads(request.content)["contents"][0]["parts"][0]["text"]
        assert FOLLOWUP_DIRECTIVE not in system and "Previous ReviewPilot review" not in content
    merge_system = json.loads(merges[0].content)["systemInstruction"]["parts"][0]["text"]
    merge_content = json.loads(merges[0].content)["contents"][0]["parts"][0]["text"]
    assert merge_system.endswith(FOLLOWUP_DIRECTIVE) and "Previous ReviewPilot review" in merge_content
    body = posted(comment)
    assert body.startswith(reviewer.FOLLOWUP_BANNER) and reviewer.FOLLOWUP_UNAVAILABLE_NOTE not in body


async def test_batched_followup_merged_in_code_notes_missing_status(mock_http, db, small_batches):
    add_previous(db)
    comment = serve(mock_http, file_diff("a.py") + file_diff("b.py") + file_diff("c.py"))
    mock_http.get(COMPARE_URL).respond(200, json={"files": []})
    mock_http.post(GEMINI_URL).mock(
        side_effect=lambda r: (
            httpx.Response(500, json={"error": {"message": "down"}}) if is_merge(r) else ok(review_md())
        )
    )

    await reviewer.handle_review(make_job(db, comment_id=None))

    assert reviewer.FOLLOWUP_UNAVAILABLE_NOTE in posted(comment)


@pytest.mark.parametrize(("changed", "suffix"), [(None, ")_"), ([], ") · 0 files changed since_")])
def test_headline_variants(changed, suffix):
    followup = reviewer.FollowUp(1, OLD_SHA, "passed", 9.0, changed, "")
    assert followup.headline() == f"_Follow-up to the review of `aaaaaaa` (🟢 Passed, 9.0/10{suffix}"
