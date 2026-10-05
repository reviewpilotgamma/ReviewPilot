from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.database import utcnow
from app.models import Job, WebhookEvent
from app.services import reviewer, worker
from app.services.errors import GeminiPermanentError, GitHubRateLimited, GitHubTransientError

PAYLOAD = {"installation_id": 99, "owner": "acme", "repo": "api", "pr_number": 7}


def add_job(db, kind: str = "review", status: str = "queued", **payload) -> Job:
    event = WebhookEvent(event="pull_request", status="queued", payload_preview="{}", repo="acme/api")
    db.add(event)
    db.flush()
    job = Job(
        event_id=event.id,
        kind=kind,
        payload=json.dumps({**PAYLOAD, **payload}),
        status=status,
        max_attempts=3,
        next_run_at=utcnow(),
    )
    db.add(job)
    db.commit()
    return job


@pytest.fixture
def handlers(monkeypatch):
    calls: list[tuple[str, int]] = []
    outcome: dict = {"error": None}

    async def fake(ctx):
        calls.append((ctx.kind, ctx.attempts))
        if outcome["error"] is not None:
            raise outcome["error"]

    failures: list[BaseException] = []

    async def fake_failure_comment(ctx, exc):
        failures.append(exc)

    monkeypatch.setitem(reviewer.HANDLERS, "review", fake)
    monkeypatch.setitem(reviewer.HANDLERS, "plan", fake)
    monkeypatch.setattr(worker, "post_failure_comment", fake_failure_comment)
    return calls, outcome, failures


def reload(db, job_id: int) -> Job:
    db.expire_all()
    return db.get(Job, job_id)


async def test_success_marks_job_and_event(db, handlers):
    calls, _, _ = handlers
    job = add_job(db)
    assert await worker.Worker().run_once()
    job = reload(db, job.id)
    assert job.status == "succeeded" and job.attempts == 1
    assert db.get(WebhookEvent, job.event_id).status == "processed"
    assert calls == [("review", 1)]


async def test_no_job_returns_false(db):
    assert not await worker.Worker().run_once()


async def test_future_job_not_claimed(db, handlers):
    job = add_job(db)
    job.next_run_at = utcnow() + timedelta(minutes=5)
    db.commit()
    assert not await worker.Worker().run_once()


async def test_transient_error_requeued_with_backoff(db, handlers):
    _, outcome, failures = handlers
    outcome["error"] = GitHubTransientError("boom")
    job = add_job(db)
    await worker.Worker().run_once()
    job = reload(db, job.id)
    assert job.status == "queued" and job.attempts == 1
    assert "boom" in job.last_error
    assert job.next_run_at > utcnow() + timedelta(seconds=25)
    assert db.get(WebhookEvent, job.event_id).status == "queued"
    assert failures == []


async def test_rate_limit_respects_retry_after(db, handlers):
    _, outcome, _ = handlers
    outcome["error"] = GitHubRateLimited("slow down", retry_after=900)
    job = add_job(db)
    await worker.Worker().run_once()
    assert reload(db, job.id).next_run_at > utcnow() + timedelta(seconds=850)


async def test_exhausted_retries_fail_and_post_comment_once(db, handlers):
    _, outcome, failures = handlers
    outcome["error"] = GitHubTransientError("down")
    job = add_job(db)
    job.attempts = 2  # next claim is the final (3rd) attempt
    db.commit()
    await worker.Worker().run_once()
    job = reload(db, job.id)
    assert job.status == "failed" and job.attempts == 3
    event = db.get(WebhookEvent, job.event_id)
    assert event.status == "failed" and "down" in event.error_message
    assert len(failures) == 1


async def test_permanent_error_fails_immediately(db, handlers):
    _, outcome, failures = handlers
    outcome["error"] = GeminiPermanentError("blocked")
    job = add_job(db)
    await worker.Worker().run_once()
    assert reload(db, job.id).status == "failed"
    assert len(failures) == 1


async def test_recover_interrupted_jobs(db):
    job = add_job(db, status="running")
    assert worker.recover_interrupted_jobs() == 1
    assert reload(db, job.id).status == "queued"


async def test_busy_pr_is_deferred_without_consuming_attempt(db, handlers):
    calls, _, _ = handlers
    job = add_job(db)
    w = worker.Worker()
    w._running_prs.add(("acme/api", 7))
    await w.run_once()
    job = reload(db, job.id)
    assert calls == []
    assert job.status == "queued" and job.attempts == 0 and job.next_run_at > utcnow()


async def test_event_rollup_with_multiple_jobs(db, handlers):
    job = add_job(db)
    second = Job(event_id=job.event_id, kind="plan", payload=job.payload, status="queued", next_run_at=utcnow())
    db.add(second)
    db.commit()
    w = worker.Worker()
    await w.run_once()
    assert db.get(WebhookEvent, job.event_id).status == "queued"
    await w.run_once()
    db.expire_all()
    assert db.get(WebhookEvent, job.event_id).status == "processed"
    statuses = db.scalars(select(Job.status).where(Job.event_id == job.event_id)).all()
    assert statuses == ["succeeded", "succeeded"]


async def test_worker_start_and_stop(db, handlers):
    add_job(db)
    w = worker.Worker()
    await w.start()
    assert w.running
    for _ in range(50):
        if db.scalar(select(Job.status)) == "succeeded":
            break
        import asyncio

        await asyncio.sleep(0.05)
        db.expire_all()
    await w.stop()
    assert not w.running
    assert db.scalar(select(Job.status)) == "succeeded"


def test_backoff_schedule():
    err = GitHubTransientError("x")
    assert [worker.backoff_for(n, err) for n in (1, 2, 3)] == [30, 120, 600]
