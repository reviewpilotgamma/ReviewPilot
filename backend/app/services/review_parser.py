"""Extract score, verdict and summary from LLM review markdown."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

META_RE = re.compile(r"<!--\s*reviewpilot-meta:\s*(\{.*?\})\s*-->", re.DOTALL | re.IGNORECASE)
SEV_RE = re.compile(r"\*\*(Critical|Warning|Passed)\*\*", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$", re.MULTILINE)

VERDICTS = ("passed", "warning", "critical")
SCORE_RANGES = {"critical": (0.0, 4.9), "warning": (5.0, 7.9), "passed": (8.0, 10.0)}
FALLBACK_SCORES = {"critical": 4.0, "warning": 6.5, "passed": 8.5}
MAX_SUMMARY_CHARS = 1_000
MAX_FINDINGS_CHARS = 1_200


@dataclass(frozen=True)
class ParsedReview:
    body: str
    summary: str
    score: float
    verdict: str
    meta_found: bool


def _section(markdown: str, title: str) -> str | None:
    """Return the text under a heading whose text contains ``title`` (case-insensitive)."""
    headings = list(HEADING_RE.finditer(markdown))
    for idx, match in enumerate(headings):
        if title.lower() in match.group(1).lower():
            end = headings[idx + 1].start() if idx + 1 < len(headings) else len(markdown)
            return markdown[match.end() : end].strip()
    return None


def _severity_counts(markdown: str) -> dict[str, int]:
    findings = _section(markdown, "Architectural Findings")
    text = findings if findings is not None else markdown
    counts = {"critical": 0, "warning": 0, "passed": 0}
    for match in SEV_RE.finditer(text):
        counts[match.group(1).lower()] += 1
    return counts


def _parse_meta(markdown: str) -> tuple[float | None, str | None]:
    matches = META_RE.findall(markdown)
    if not matches:
        return None, None
    try:
        data = json.loads(matches[-1])
    except json.JSONDecodeError:
        return None, None
    score: float | None
    try:
        score = round(min(10.0, max(0.0, float(data.get("score")))), 1)
    except (TypeError, ValueError):
        score = None
    verdict = str(data.get("verdict", "")).lower().strip()
    return score, verdict if verdict in VERDICTS else None


def _fallback_verdict(counts: dict[str, int]) -> str:
    if counts["critical"]:
        return "critical"
    if counts["warning"]:
        return "warning"
    return "passed"


def _fallback_score(verdict: str, counts: dict[str, int]) -> float:
    low, high = SCORE_RANGES[verdict]
    issues = counts["critical"] + counts["warning"]
    score = FALLBACK_SCORES[verdict] - 0.5 * max(0, issues - 1)
    return round(min(high, max(low, score)), 1)


def findings_excerpt(markdown: str, max_chars: int = MAX_FINDINGS_CHARS) -> str:
    """Architectural Findings section, or the full body, truncated for insight cards."""
    text = (_section(markdown, "Architectural Findings") or markdown).strip()
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 1]
    cut = clipped.rsplit("\n", 1)[0]
    return f"{cut or clipped}\n…"


def extract_summary(markdown: str) -> str:
    summary = _section(markdown, "Executive Summary")
    if not summary:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", markdown) if p.strip()]
        summary = next((p for p in paragraphs if not p.startswith("#")), "")
    return summary[:MAX_SUMMARY_CHARS].strip()


def strip_meta(markdown: str) -> str:
    return META_RE.sub("", markdown).rstrip()


def parse_review(markdown: str) -> ParsedReview:
    counts = _severity_counts(markdown)
    score, verdict = _parse_meta(markdown)
    meta_found = score is not None and verdict is not None

    if verdict is None:
        verdict = _fallback_verdict(counts)
    if score is None:
        score = _fallback_score(verdict, counts)

    if verdict == "passed" and counts["critical"]:
        logger.info("Overriding 'passed' verdict: review contains Critical findings")
        verdict = "critical"
        score = min(score, 4.9)

    return ParsedReview(
        body=strip_meta(markdown),
        summary=extract_summary(markdown),
        score=score,
        verdict=verdict,
        meta_found=meta_found,
    )
