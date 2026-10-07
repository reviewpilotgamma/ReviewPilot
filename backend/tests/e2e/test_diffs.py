"""Self-tests for the dummy diff generator: determinism, valid hunks, sizes, canned reviews."""

from __future__ import annotations

import re

import pytest

from app.services.review_parser import parse_review
from app.services.reviewer import count_changed_lines
from tests.e2e.diffs import (
    EDGE_SCENARIOS,
    PLANTED_SCENARIOS,
    SIZE_TIERS,
    generate_diff,
    scenario_for_tier,
)

HUNK_RE = re.compile(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@")


def assert_valid_hunks(diff: str) -> int:
    """Check every hunk header's line counts against its body. Returns the number of hunks."""
    lines = diff.splitlines()
    hunks = 0
    i = 0
    while i < len(lines):
        match = HUNK_RE.match(lines[i])
        if not match:
            i += 1
            continue
        hunks += 1
        old_expected, new_expected = int(match.group(2)), int(match.group(4))
        old = new = 0
        i += 1
        while i < len(lines) and lines[i][:1] in (" ", "+", "-") and not lines[i].startswith(("---", "+++")):
            old += lines[i][0] in (" ", "-")
            new += lines[i][0] in (" ", "+")
            i += 1
        assert (old, new) == (old_expected, new_expected), f"hunk {hunks}: {(old, new)} != header"
    return hunks


def test_same_seed_is_deterministic():
    assert generate_diff(files=3, lines_per_file=50, seed=1) == generate_diff(files=3, lines_per_file=50, seed=1)


def test_different_seed_differs():
    assert generate_diff(files=3, lines_per_file=50, seed=1) != generate_diff(files=3, lines_per_file=50, seed=2)


def test_generated_hunks_are_valid():
    diff = generate_diff(files=4, lines_per_file=130, seed=3)
    assert diff.count("diff --git ") == 4
    assert assert_valid_hunks(diff) == 4 * 4  # 130 lines → hunks of 40, 40, 40, 10


@pytest.mark.parametrize("tier", list(SIZE_TIERS))
def test_tier_sizes_within_tolerance(tier):
    scenario = scenario_for_tier(tier)
    target = SIZE_TIERS[tier].target_bytes
    assert 0.8 * target <= scenario.diff_bytes <= 1.2 * target
    assert count_changed_lines(scenario.diff) > 0


@pytest.mark.parametrize("name", list(PLANTED_SCENARIOS))
def test_planted_scenarios_are_valid_and_parse_to_expected_verdict(name):
    scenario = PLANTED_SCENARIOS[name]
    assert assert_valid_hunks(scenario.diff) >= 1
    assert f"[{name}]" in scenario.title
    parsed = parse_review(scenario.mock_review_markdown)
    assert parsed.meta_found
    assert parsed.verdict == scenario.expected_verdict
    assert scenario.expected_keywords


def test_live_expectations_cover_critical_and_clean():
    assert "passed" in PLANTED_SCENARIOS["sql_injection"].live_forbidden_verdicts
    assert "passed" in PLANTED_SCENARIOS["hardcoded_secret"].live_forbidden_verdicts
    assert "critical" in PLANTED_SCENARIOS["clean"].live_forbidden_verdicts


@pytest.mark.parametrize("name", ["binary", "rename_only", "unicode"])
def test_edge_scenarios_have_reviewable_content(name):
    scenario = EDGE_SCENARIOS[name]
    assert scenario.diff.strip()
    assert parse_review(scenario.mock_review_markdown).verdict == "passed"


def test_empty_edge_scenarios_are_blank():
    assert not EDGE_SCENARIOS["empty"].diff.strip()
    assert not EDGE_SCENARIOS["whitespace"].diff.strip()
