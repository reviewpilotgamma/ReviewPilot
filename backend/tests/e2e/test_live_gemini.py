"""Opt-in: the same dummy diffs through the full pipeline against the real Gemini API (GitHub stays mocked).

Run with ``REVIEWPILOT_E2E_LIVE=1 REVIEWPILOT_E2E_GEMINI_API_KEY=... pytest -m live``. Skipped otherwise.
Optional: ``REVIEWPILOT_E2E_GEMINI_MODEL`` overrides the model.
"""

from __future__ import annotations

import pytest

from tests.e2e.diffs import PLANTED_SCENARIOS, DiffScenario, scenario_for_tier

pytestmark = pytest.mark.live

# The very_large tier (~5 MB) exceeds the model context window, so it is excluded.
LIVE_TIERS = ("small", "medium", "large")
LIVE_CASES = [*PLANTED_SCENARIOS, *(f"tier_{tier}" for tier in LIVE_TIERS)]
MAX_ERROR_CHARS = 300


def resolve(name: str) -> DiffScenario:
    return scenario_for_tier(name.removeprefix("tier_")) if name.startswith("tier_") else PLANTED_SCENARIOS[name]


def keyword_hit_rate(scenario: DiffScenario, markdown: str) -> float | None:
    if not scenario.expected_keywords:
        return None
    text = markdown.lower()
    return sum(keyword.lower() in text for keyword in scenario.expected_keywords) / len(scenario.expected_keywords)


@pytest.mark.parametrize("name", LIVE_CASES)
async def test_live_gemini_review(live_pipeline, live_gemini, name):
    scenario = resolve(name)
    delivery = live_pipeline.open_pr(90, scenario)

    await live_pipeline.drain()

    [job] = live_pipeline.jobs(delivery)
    reviews = live_pipeline.reviews()
    review = reviews[0] if reviews else None
    error = None if job.status == "succeeded" else (job.last_error or job.status)[:MAX_ERROR_CHARS]
    ok = review is not None and review.verdict not in scenario.live_forbidden_verdicts
    live_pipeline.record(
        scenario,
        delivery,
        mode="live",
        label=name,
        model=live_gemini,
        keyword_hit_rate=keyword_hit_rate(scenario, review.full_markdown if review else ""),
        ok=ok,
        error=error,
        attempts=job.attempts,
    )

    assert job.status == "succeeded", f"live review failed: {error}"
    assert review is not None and live_pipeline.github.comments_for(90) == [review.full_markdown]
    assert review.verdict not in scenario.live_forbidden_verdicts, (
        f"{name}: model returned '{review.verdict}', which means it missed the planted issue"
    )
