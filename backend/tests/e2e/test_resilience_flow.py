"""Failure handling end to end: retries with backoff, permanent failures, idempotent re-post, crash recovery."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import update

from app.core.config import reload_settings
from app.core.database import SessionLocal, utcnow
from app.models import Job
from app.services import worker
from tests.e2e.diffs import PLANTED_SCENARIOS

FAILURE_PREFIX = "⚠️ ReviewPilot couldn't complete the architectural review"
SCENARIO = PLANTED_SCENARIOS["no_timeout_retry"]


@pytest.mark.parametrize("status", [503, 429])
async def test_transient_gemini_error_is_retried_then_succeeds(pipeline, status):
    pipeline.llm.fail_next(status)
    delivery = pipeline.open_pr(60, SCENARIO)

    assert await pipeline.run_once()
    [job] = pipeline.jobs(delivery)
    assert (job.status, job.attempts) == ("queued", 1)
    assert f"Gemini {status}" in job.last_error
    assert job.next_run_at > utcnow() + timedelta(seconds=25)  # first backoff step is 30 s
    assert pipeline.event(delivery).status == "queued"
    assert pipeline.github.comments == []
    assert not await pipeline.run_once(), "a backed-off job must not run early"

    await pipeline.drain()  # fast-forwards the backoff

    [job] = pipeline.jobs(delivery)
    assert (job.status, job.attempts) == ("succeeded", 2)
    assert pipeline.llm.generate_calls == 2
    assert len(pipeline.reviews()) == 1 and len(pipeline.github.comments_for(60)) == 1
    assert pipeline.event(delivery).status == "processed"
    pipeline.record(SCENARIO, delivery, retries=1, injected=status)


async def test_permanent_gemini_error_fails_with_one_comment(pipeline):
    pipeline.llm.fail_next(400)
    delivery = pipeline.open_pr(61, SCENARIO)

    await pipeline.drain()

    [job] = pipeline.jobs(delivery)
    assert (job.status, job.attempts) == ("failed", 1)
    [comment] = pipeline.github.comments_for(61)
    assert comment.startswith(FAILURE_PREFIX)
    assert pipeline.reviews() == []
    event = pipeline.event(delivery)
    assert event.status == "failed" and "Gemini 400" in event.error_message


async def test_comment_post_failure_reposts_stored_review_without_second_llm_call(pipeline):
    pipeline.github.fail_next("comment", 502)
    delivery = pipeline.open_pr(62, SCENARIO)

    assert await pipeline.run_once()
    [review] = pipeline.reviews()
    assert review.github_comment_id is None
    [job] = pipeline.jobs(delivery)
    assert job.status == "queued" and job.review_id == review.id

    await pipeline.drain()

    assert pipeline.llm.generate_calls == 1, "retry must reuse the stored review, not call the LLM again"
    [review] = pipeline.reviews()
    [comment] = pipeline.github.comments_for(62)
    assert comment == review.full_markdown
    assert review.github_comment_id == pipeline.github.comments[-1].id
    assert pipeline.jobs(delivery)[0].status == "succeeded"


@pytest.mark.parametrize("status", [404, 406])
async def test_diff_fetch_failure_posts_failure_comment(pipeline, status):
    pipeline.github.fail_next("diff", status)
    delivery = pipeline.open_pr(63, SCENARIO)

    await pipeline.drain()

    [job] = pipeline.jobs(delivery)
    assert job.status == "failed" and "DiffFetchError" in job.last_error
    [comment] = pipeline.github.comments_for(63)
    assert comment.startswith(FAILURE_PREFIX)
    assert pipeline.llm.generate_calls == 0


async def test_exhausted_retries_fail_with_one_comment(pipeline, monkeypatch):
    monkeypatch.setenv("JOB_MAX_ATTEMPTS", "2")
    reload_settings()
    pipeline.llm.fail_next(503, times=5)
    delivery = pipeline.open_pr(64, SCENARIO)

    await pipeline.drain()

    [job] = pipeline.jobs(delivery)
    assert (job.status, job.attempts, job.max_attempts) == ("failed", 2, 2)
    assert pipeline.llm.generate_calls == 2
    [comment] = pipeline.github.comments_for(64)
    assert comment.startswith(FAILURE_PREFIX)


async def test_github_outage_on_pr_fetch_recovers(pipeline):
    pipeline.github.fail_next("pull", 502, times=2)
    delivery = pipeline.open_pr(65, SCENARIO)

    await pipeline.drain()

    [job] = pipeline.jobs(delivery)
    assert (job.status, job.attempts) == ("succeeded", 3)
    assert len(pipeline.github.comments_for(65)) == 1


async def test_interrupted_job_is_recovered_after_restart(pipeline):
    delivery = pipeline.open_pr(66, SCENARIO)
    with SessionLocal() as db:  # simulate a crash mid-job
        db.execute(update(Job).values(status="running", attempts=1))
        db.commit()

    assert not await pipeline.run_once(), "a running job is never claimed twice"
    assert worker.recover_interrupted_jobs() == 1
    await pipeline.drain()

    [job] = pipeline.jobs(delivery)
    assert (job.status, job.attempts) == ("succeeded", 2)
    assert len(pipeline.reviews()) == 1 and len(pipeline.github.comments_for(66)) == 1
