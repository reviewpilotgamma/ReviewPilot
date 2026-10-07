"""Pipeline overhead by diff size (mocked LLM): per-stage timings, budgets, truncated vs. unlimited."""

from __future__ import annotations

import pytest

from app.core.config import reload_settings
from app.services.diff_batching import CHARS_PER_TOKEN
from app.services.reviewer import count_changed_lines
from tests.e2e.diffs import SIZE_TIERS, scenario_for_tier
from tests.e2e.harness import budget_scale

# Seconds for the whole pipeline (ingest → comment posted) with Gemini mocked. Generous on purpose.
PERF_BUDGETS = {"small": 1.0, "medium": 2.0, "large": 5.0, "very_large": 15.0}
TRUNCATED_LIMIT = 200_000
BATCH_CHARS = 100_000 * CHARS_PER_TOKEN  # DIFF_BATCH_TOKENS default


def assert_within_budget(tier: str, result) -> None:
    budget = PERF_BUDGETS[tier] * budget_scale()
    slowest = max(result.stages, key=result.stages.get)
    assert result.total_s <= budget, (
        f"{tier}: {result.total_s:.2f}s > budget {budget:.2f}s (slowest stage {slowest}={result.stages[slowest]:.2f}s)"
    )


@pytest.mark.parametrize("tier", list(SIZE_TIERS))
async def test_pipeline_scales_with_diff_size(pipeline, tier):
    scenario = scenario_for_tier(tier)
    delivery = pipeline.open_pr(70, scenario)

    assert await pipeline.drain() == 1

    [review] = pipeline.reviews()
    assert review.lines_reviewed == count_changed_lines(scenario.diff)
    assert not review.diff_truncated
    contents = [pipeline.llm.user_content(r) for r in pipeline.llm.requests]
    if len(scenario.diff) <= BATCH_CHARS:
        assert len(contents) == 1  # one request, whole diff (MAX_DIFF_CHARS=0)
        batch_contents = contents
    else:
        batch_contents = contents[:-1]  # the last request merges the batch reviews
        assert len(batch_contents) > 1
        assert all(len(c) < BATCH_CHARS + 20_000 for c in batch_contents)
        assert "partial reviews follow" in contents[-1]
    prompt_chars = sum(len(c) for c in batch_contents)
    assert prompt_chars > len(scenario.diff)  # every line of the diff reached the model
    result = pipeline.record(scenario, delivery, label=f"tier_{tier}", prompt_chars=prompt_chars, max_diff_chars=0)
    assert_within_budget(tier, result)


async def test_very_large_diff_truncated_vs_unlimited(pipeline, monkeypatch):
    monkeypatch.setenv("MAX_DIFF_CHARS", str(TRUNCATED_LIMIT))
    reload_settings()
    scenario = scenario_for_tier("very_large")
    delivery = pipeline.open_pr(71, scenario)

    await pipeline.drain()

    [review] = pipeline.reviews()
    assert review.diff_truncated
    assert review.lines_reviewed == count_changed_lines(scenario.diff)  # counts the full diff, reviews a prefix
    prompt_chars = len(pipeline.llm.user_content(pipeline.llm.requests[-1]))
    assert prompt_chars < TRUNCATED_LIMIT + 5_000
    result = pipeline.record(
        scenario, delivery, label="tier_very_large_truncated", prompt_chars=prompt_chars, max_diff_chars=TRUNCATED_LIMIT
    )
    assert_within_budget("very_large", result)
