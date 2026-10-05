"""In-process, SQLite-backed job worker with retries, crash recovery and per-PR serialization."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, utcnow
from app.core.logging import job_id_var
from app.models import Job, WebhookEvent
from app.services.errors import GitHubRateLimited, ServiceError
from app.services.reviewer import HANDLERS, JobContext, post_failure_comment

logger = logging.getLogger(__name__)

BACKOFF_SECONDS = (30, 120, 600)
PR_BUSY_DELAY_SECONDS = 5
MAX_ERROR_CHARS = 2_000


def backoff_for(attempt: int, exc: BaseException) -> float:
    delay = float(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS)) - 1])
    if isinstance(exc, GitHubRateLimited):
        delay = max(delay, exc.retry_after)
    return delay


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ServiceError):
        return exc.retryable
    return isinstance(exc, asyncio.TimeoutError)


# --------------------------------------------------------------------------- DB operations (sync)
def recover_interrupted_jobs() -> int:
    with SessionLocal() as db:
        result = db.execute(
            update(Job)
            .where(Job.status == "running")
            .values(status="queued", updated_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return result.rowcount or 0


def claim_next_job() -> JobContext | None:
    """Atomically move the next due job from ``queued`` to ``running``."""
    now = utcnow()
    with SessionLocal() as db:
        next_id = (
            select(Job.id)
            .where(Job.status == "queued", Job.next_run_at <= now)
            .order_by(Job.next_run_at, Job.id)
            .limit(1)
            .scalar_subquery()
        )
        row = db.execute(
            update(Job)
            .where(Job.id == next_id, Job.status == "queued")
            .values(status="running", attempts=Job.attempts + 1, updated_at=now)
            .returning(Job.id, Job.kind, Job.payload, Job.review_id, Job.attempts, Job.max_attempts)
            .execution_options(synchronize_session=False)
        ).first()
        db.commit()
    if row is None:
        return None
    return JobContext(
        job_id=row.id,
        kind=row.kind,
        data=json.loads(row.payload),
        review_id=row.review_id,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
    )


def _rollup_event(db: Session, event_id: int) -> None:
    event = db.get(WebhookEvent, event_id)
    if event is None:
        return
    jobs = db.scalars(select(Job).where(Job.event_id == event_id).order_by(Job.id)).all()
    statuses = {job.status for job in jobs}
    if statuses & {"queued", "running"}:
        event.status, event.error_message = "queued", None
    elif "failed" in statuses:
        first_failed = next(job for job in jobs if job.status == "failed")
        event.status, event.error_message = "failed", first_failed.last_error
    else:
        event.status, event.error_message = "processed", None


def finish_job(job_id: int, *, status: str, error: str | None = None, retry_in: float | None = None) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = status
        job.last_error = error[:MAX_ERROR_CHARS] if error else job.last_error
        if retry_in is not None:
            job.next_run_at = utcnow() + timedelta(seconds=retry_in)
        db.flush()
        _rollup_event(db, job.event_id)
        db.commit()


def defer_job(job_id: int, delay: float) -> None:
    """Put a claimed job back without consuming an attempt (used when its PR is busy)."""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = "queued"
        job.attempts = max(0, job.attempts - 1)
        job.next_run_at = utcnow() + timedelta(seconds=delay)
        db.commit()


# --------------------------------------------------------------------------- execution
async def execute_job(ctx: JobContext) -> None:
    """Run one claimed job to completion, applying the retry policy."""
    settings = get_settings()
    token = job_id_var.set(str(ctx.job_id))
    try:
        handler = HANDLERS[ctx.kind]
        try:
            await asyncio.wait_for(handler(ctx), timeout=settings.JOB_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - classified below
            message = f"{exc.__class__.__name__}: {exc}"
            if is_retryable(exc) and ctx.attempts < ctx.max_attempts:
                delay = backoff_for(ctx.attempts, exc)
                logger.warning(
                    "Job %s failed (attempt %s), retrying in %ss: %s", ctx.job_id, ctx.attempts, delay, message
                )
                await asyncio.to_thread(finish_job, ctx.job_id, status="queued", error=message, retry_in=delay)
            else:
                logger.error("Job %s failed permanently: %s", ctx.job_id, message)
                await asyncio.to_thread(finish_job, ctx.job_id, status="failed", error=message)
                await post_failure_comment(ctx, exc)
            return
        await asyncio.to_thread(finish_job, ctx.job_id, status="succeeded")
    finally:
        job_id_var.reset(token)


class Worker:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()
        self._running_prs: set[tuple[str, int]] = set()

    @property
    def running(self) -> bool:
        return any(not task.done() for task in self._tasks)

    async def start(self) -> None:
        recovered = await asyncio.to_thread(recover_interrupted_jobs)
        if recovered:
            logger.info("Re-queued %s interrupted job(s)", recovered)
        self._stop.clear()
        concurrency = get_settings().WORKER_CONCURRENCY
        self._tasks = [asyncio.create_task(self._loop(i), name=f"worker-{i}") for i in range(concurrency)]
        logger.info("Worker started with concurrency=%s", concurrency)

    async def stop(self, grace_seconds: float = 10.0) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            with contextlib.suppress(Exception):
                await asyncio.wait(self._tasks, timeout=grace_seconds)
        self._tasks = []

    async def run_once(self) -> bool:
        """Claim and execute a single job. Returns ``False`` when nothing was due."""
        ctx = await asyncio.to_thread(claim_next_job)
        if ctx is None:
            return False
        key = (ctx.repo_full_name, ctx.pr_number)
        if key in self._running_prs:
            await asyncio.to_thread(defer_job, ctx.job_id, PR_BUSY_DELAY_SECONDS)
            return True
        self._running_prs.add(key)
        try:
            await execute_job(ctx)
        finally:
            self._running_prs.discard(key)
        return True

    async def _loop(self, index: int) -> None:
        poll = get_settings().WORKER_POLL_INTERVAL_SECONDS
        while not self._stop.is_set():
            try:
                worked = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep the loop alive
                logger.exception("Worker %s loop error", index)
                worked = False
            if not worked:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=poll)


worker = Worker()
