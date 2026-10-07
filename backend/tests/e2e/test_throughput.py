"""Burst of webhooks through a concurrent worker: no lost/duplicate work, per-PR serialization, jobs/sec."""

from __future__ import annotations

import asyncio
import time

from app.core.config import reload_settings
from app.services import reviewer, worker
from tests.conftest import post_webhook
from tests.e2e.diffs import PLANTED_SCENARIOS
from tests.e2e.harness import LoopHttpClient, pending_jobs, percentile, pr_opened_payload

PRS = 5
COMMENTS_PER_PR = 3
DUPLICATES = 5  # replayed deliveries on top of the 20 unique ones → 25 webhooks
CONCURRENCY = 4
LLM_DELAY_S = 0.02
PR_BUSY_DELAY_S = 0.05  # production uses 5 s; shortened so the burst finishes quickly
DRAIN_TIMEOUT_S = 30.0


async def test_burst_is_processed_once_with_per_pr_serialization(pipeline, monkeypatch, e2e_report):
    monkeypatch.setenv("WORKER_CONCURRENCY", str(CONCURRENCY))
    monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "0.01")
    reload_settings()
    monkeypatch.setattr(worker, "PR_BUSY_DELAY_SECONDS", PR_BUSY_DELAY_S)
    pipeline.llm.delay_s = LLM_DELAY_S

    # Fail if two review jobs for the same PR ever run at the same time.
    active: set[tuple[str, int]] = set()
    overlaps: list[tuple[str, int]] = []
    max_parallel = 0
    review_handler = reviewer.HANDLERS["review"]

    async def guarded(ctx: reviewer.JobContext) -> None:
        nonlocal max_parallel
        key = (ctx.repo_full_name, ctx.pr_number)
        if key in active:
            overlaps.append(key)
        active.add(key)
        max_parallel = max(max_parallel, len(active))
        try:
            await review_handler(ctx)
        finally:
            active.discard(key)

    monkeypatch.setitem(reviewer.HANDLERS, "review", guarded)
    deferrals = 0
    original_defer = worker.defer_job

    def counting_defer(job_id: int, delay: float) -> None:
        nonlocal deferrals
        deferrals += 1
        original_defer(job_id, delay)

    monkeypatch.setattr(worker, "defer_job", counting_defer)

    # Round-robin across PRs so concurrent workers mostly pick different PRs (like real traffic).
    scenarios = list(PLANTED_SCENARIOS.values())
    numbers = [80 + i for i in range(PRS)]
    opened: dict[int, str] = {}
    for number in numbers:
        opened[number] = pipeline.open_pr(number, scenarios[number % len(scenarios)])
    for _ in range(COMMENTS_PER_PR):
        for number in numbers:
            pipeline.comment(number, "@review")
    for number in numbers[:DUPLICATES]:
        scenario = scenarios[number % len(scenarios)]
        replay = post_webhook(pipeline.client, "pull_request", pr_opened_payload(number, scenario), opened[number])
        assert replay.json()["status"] == "duplicate"

    unique_jobs = PRS * (1 + COMMENTS_PER_PR)
    assert len(pipeline.jobs()) == unique_jobs

    w = worker.Worker()
    start = time.perf_counter()
    async with LoopHttpClient():
        await w.start()
        try:
            while pending_jobs():
                assert time.perf_counter() - start < DRAIN_TIMEOUT_S, "burst did not drain in time"
                await asyncio.sleep(0.01)
        finally:
            await w.stop()
    wall = time.perf_counter() - start

    jobs = pipeline.jobs()
    assert [j.status for j in jobs] == ["succeeded"] * unique_jobs
    assert overlaps == [], f"same PR processed concurrently: {overlaps}"
    reviews = pipeline.reviews()
    assert len(reviews) == unique_jobs
    assert len({j.review_id for j in jobs}) == unique_jobs, "every job owns exactly one review"
    assert len(pipeline.github.comments) == unique_jobs
    for number in numbers:
        assert len(pipeline.github.comments_for(number)) == 1 + COMMENTS_PER_PR
    assert pipeline.llm.generate_calls == unique_jobs

    exec_s = [pipeline.timer.totals[j.id] for j in jobs]
    queue_to_done_s = [(j.updated_at - j.created_at).total_seconds() for j in jobs]
    e2e_report.add_throughput(
        webhooks=unique_jobs + DUPLICATES,
        jobs=unique_jobs,
        concurrency=CONCURRENCY,
        llm_delay_ms=int(LLM_DELAY_S * 1000),
        wall_s=round(wall, 3),
        jobs_per_s=round(unique_jobs / wall, 1),
        exec_p50_ms=round(percentile(exec_s, 50) * 1000, 1),
        exec_p95_ms=round(percentile(exec_s, 95) * 1000, 1),
        queue_to_done_p95_ms=round(percentile(queue_to_done_s, 95) * 1000, 1),
        max_parallel_prs=max_parallel,
        pr_busy_deferrals=deferrals,
    )
    assert max_parallel > 1, "the worker should process different PRs in parallel"
