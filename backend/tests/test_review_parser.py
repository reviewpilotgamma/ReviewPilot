from __future__ import annotations

from app.services.review_parser import extract_summary, findings_excerpt, parse_review
from tests.conftest import FIXTURES

SAMPLE = (FIXTURES / "gemini_review.md").read_text(encoding="utf-8")


def test_meta_parsed_and_stripped():
    parsed = parse_review(SAMPLE)
    assert parsed.meta_found
    assert parsed.verdict == "critical" and parsed.score == 3.5
    assert "reviewpilot-meta" not in parsed.body
    assert parsed.summary.startswith("- **What it does:** Adds naive retries")


def test_structured_findings_counted():
    parsed = parse_review(SAMPLE.replace('<!-- reviewpilot-meta: {"score": 3.5, "verdict": "critical"} -->', ""))
    assert not parsed.meta_found
    assert parsed.verdict == "critical"
    excerpt = findings_excerpt(SAMPLE)
    assert excerpt.startswith("- **Critical** · **Non-idempotent retries**")
    assert "**File(s):** `app/payments.py`" in excerpt


def test_score_clamped_and_rounded():
    md = '### Executive Summary\nok\n<!-- reviewpilot-meta: {"score": 14.27, "verdict": "passed"} -->'
    assert parse_review(md).score == 10.0
    md = '<!-- reviewpilot-meta: {"score": -3, "verdict": "warning"} -->'
    assert parse_review(md).score == 0.0


def test_last_meta_wins():
    md = (
        '<!-- reviewpilot-meta: {"score": 1, "verdict": "critical"} -->\n'
        '<!-- reviewpilot-meta: {"score": 9, "verdict": "passed"} -->'
    )
    parsed = parse_review(md)
    assert (parsed.score, parsed.verdict) == (9.0, "passed")


def test_invalid_meta_falls_back_to_findings():
    md = "### Architectural Findings\n- **Warning** thing\n<!-- reviewpilot-meta: {not json} -->"
    parsed = parse_review(md)
    assert not parsed.meta_found
    assert parsed.verdict == "warning" and 5.0 <= parsed.score <= 7.9


def test_missing_meta_fallbacks():
    assert parse_review("### Architectural Findings\n- **Passed** fine").verdict == "passed"
    crit = parse_review("### Architectural Findings\n- **Critical** a\n- **Critical** b\n- **Warning** c")
    assert crit.verdict == "critical" and crit.score <= 4.9
    assert parse_review("### Architectural Findings\n- **Passed** fine").score == 8.5


def test_passed_with_critical_is_overridden():
    md = (
        "### Architectural Findings\n- **Critical** leak\n"
        '<!-- reviewpilot-meta: {"score": 9.1, "verdict": "passed"} -->'
    )
    parsed = parse_review(md)
    assert parsed.verdict == "critical" and parsed.score == 4.9


def test_invalid_verdict_uses_fallback_but_keeps_score():
    md = '### Architectural Findings\n- **Warning** x\n<!-- reviewpilot-meta: {"score": 6, "verdict": "meh"} -->'
    parsed = parse_review(md)
    assert parsed.verdict == "warning" and parsed.score == 6.0


def test_summary_without_heading_uses_first_paragraph():
    assert extract_summary("First paragraph here.\n\nSecond.") == "First paragraph here."


def test_summary_truncated():
    md = "### Executive Summary\n" + "x" * 5000 + "\n### Next"
    assert len(extract_summary(md)) == 1000


def test_findings_excerpt_uses_section_and_truncates():
    md = "### Executive Summary\nIgnore me\n### Architectural Findings\n- **Warning** a\n### Recommendations\nfix it"
    assert findings_excerpt(md) == "- **Warning** a"
    long = "### Architectural Findings\n" + ("line\n" * 400)
    excerpt = findings_excerpt(long, max_chars=40)
    assert len(excerpt) <= 42 and excerpt.endswith("…")
