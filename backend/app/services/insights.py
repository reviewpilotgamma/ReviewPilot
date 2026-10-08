"""On-demand LLM synthesis of stored ReviewPilot comments, with a rolling snapshot."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PRReview, ReviewInsightSnapshot
from app.schemas.insights import InsightSnapshot, InsightState, InsightTheme
from app.services import gemini
from app.services.errors import GeminiPermanentError
from app.services.review_parser import findings_excerpt
from app.services.reviews import feedback_counts_for

logger = logging.getLogger(__name__)

MAX_NEW = 50
JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

INSIGHT_SYSTEM_PROMPT = """You synthesize recurring architectural themes from ReviewPilot pull-request reviews.

Rules:
- Use only the reviews and previous themes provided. Never invent pull requests or review ids.
- Merge previous themes with new reviews: increment counts that still appear, add new themes,
  drop themes with no evidence.
- Prefer architecture, boundaries, failure modes, and security. Ignore formatting nits.
- Do not use emoji.
- Reply with JSON only, no markdown fences unless the JSON itself is inside one fence. Shape:
{
  "summary_markdown": "short markdown (headings allowed) covering the period",
  "themes": [
    {
      "title": "short name",
      "severity": "critical" | "warning" | "passed",
      "count": 1,
      "last_seen_review_id": 0,
      "example_review_ids": [0],
      "evidence": "one or two sentences citing the reviews"
    }
  ],
  "new_this_period": ["theme titles added this run"],
  "still_showing": ["theme titles that persisted"]
}
"""


class InsightParseError(Exception):
    """The model returned JSON we could not turn into themes."""


class NoUsableReviews(Exception):
    """The repo has no reviews, or none that can be used as cards."""


def _latest_snapshot(db: Session, repo: str) -> ReviewInsightSnapshot | None:
    return db.scalars(
        select(ReviewInsightSnapshot)
        .where(ReviewInsightSnapshot.repo_full_name == repo)
        .order_by(ReviewInsightSnapshot.created_at.desc(), ReviewInsightSnapshot.id.desc())
        .limit(1)
    ).first()


def _review_ids(db: Session, repo: str) -> set[int]:
    return set(db.scalars(select(PRReview.id).where(PRReview.repo_full_name == repo)).all())


def _total_reviews(db: Session, repo: str) -> int:
    return db.scalar(select(func.count(PRReview.id)).where(PRReview.repo_full_name == repo)) or 0


def _pending_query(repo: str, watermark: int | None):
    conditions = [PRReview.repo_full_name == repo]
    if watermark is not None:
        conditions.append(PRReview.id > watermark)
    return select(PRReview).where(*conditions)


def pending_reviews(db: Session, repo: str, watermark: int | None, *, limit: int | None = None) -> list[PRReview]:
    stmt = _pending_query(repo, watermark).order_by(PRReview.id.asc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def pending_count(db: Session, repo: str, watermark: int | None) -> int:
    stmt = select(func.count(PRReview.id)).where(PRReview.repo_full_name == repo)
    if watermark is not None:
        stmt = stmt.where(PRReview.id > watermark)
    return db.scalar(stmt) or 0


def _rebuild_batch(db: Session, repo: str) -> list[PRReview]:
    newest = list(
        db.scalars(
            select(PRReview).where(PRReview.repo_full_name == repo).order_by(PRReview.id.desc()).limit(MAX_NEW)
        ).all()
    )
    newest.reverse()
    return newest


def _usable_card(counts: dict[str, int]) -> bool:
    return counts.get("unhelpful", 0) <= counts.get("helpful", 0)


def _cards_for(reviews: list[PRReview], counts: dict[int, dict[str, int]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for review in reviews:
        fb = counts.get(review.id, {"helpful": 0, "unhelpful": 0})
        if not _usable_card(fb):
            continue
        cards.append(
            {
                "id": review.id,
                "pr_number": review.pr_number,
                "pr_title": review.pr_title,
                "author": review.author,
                "verdict": review.verdict,
                "score": review.score,
                "created_at": review.created_at.isoformat(),
                "summary": review.summary,
                "findings": findings_excerpt(review.full_markdown),
                "feedback": fb,
            }
        )
    return cards


def _snapshot_out(row: ReviewInsightSnapshot) -> InsightSnapshot:
    themes_raw = json.loads(row.themes_json or "[]")
    return InsightSnapshot(
        id=row.id,
        repo_full_name=row.repo_full_name,
        through_review_id=row.through_review_id,
        included_count=row.included_count,
        pending_analyzed_count=row.pending_analyzed_count,
        summary_markdown=row.summary_markdown,
        themes=[InsightTheme.model_validate(t) for t in themes_raw],
        new_this_period=json.loads(row.new_this_period_json or "[]"),
        still_showing=json.loads(row.still_showing_json or "[]"),
        model=row.model,
        created_at=row.created_at,
        created_by=row.created_by,
    )


def get_state(db: Session, repo: str) -> InsightState:
    snap = _latest_snapshot(db, repo)
    watermark = snap.through_review_id if snap else None
    pending = pending_count(db, repo, watermark)
    return InsightState(
        repo_full_name=repo,
        snapshot=_snapshot_out(snap) if snap else None,
        total_reviews=_total_reviews(db, repo),
        pending_count=pending,
        pending_capped=pending > MAX_NEW,
        ran_model=False,
    )


def parse_insight_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1)
        cleaned = re.sub(r"\s*```$", "", cleaned, count=1)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = JSON_OBJECT_RE.search(cleaned)
        if not match:
            raise InsightParseError("no JSON object") from None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise InsightParseError("invalid JSON") from exc
    if not isinstance(data, dict):
        raise InsightParseError("JSON root must be an object")
    return data


def sanitize_llm_output(
    data: dict[str, Any], valid_ids: set[int]
) -> tuple[str, list[InsightTheme], list[str], list[str]]:
    summary = str(data.get("summary_markdown") or "").strip()
    themes: list[InsightTheme] = []
    for raw in data.get("themes") or []:
        if not isinstance(raw, dict):
            continue
        examples = [int(i) for i in (raw.get("example_review_ids") or []) if _is_int(i) and int(i) in valid_ids][:5]
        last = raw.get("last_seen_review_id")
        last_id = int(last) if _is_int(last) and int(last) in valid_ids else (examples[-1] if examples else 0)
        if not examples:
            continue
        try:
            themes.append(
                InsightTheme(
                    title=str(raw.get("title") or "Untitled")[:200],
                    severity=raw.get("severity") or "warning",
                    count=raw.get("count") or 1,
                    last_seen_review_id=last_id,
                    example_review_ids=examples,
                    evidence=str(raw.get("evidence") or "")[:500],
                )
            )
        except ValidationError:
            continue
    new_names = [str(x)[:200] for x in (data.get("new_this_period") or []) if str(x).strip()]
    still = [str(x)[:200] for x in (data.get("still_showing") or []) if str(x).strip()]
    return summary, themes, new_names, still


def _is_int(value: object) -> bool:
    try:
        int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def _user_payload(previous: InsightSnapshot | None, cards: list[dict[str, Any]], *, rebuild: bool) -> str:
    prev = None
    if previous and not rebuild:
        prev = {
            "summary_markdown": previous.summary_markdown,
            "themes": [t.model_dump() for t in previous.themes],
        }
    return json.dumps({"previous": prev, "rebuild": rebuild, "new_reviews": cards}, indent=2)


def _persist(
    db: Session,
    *,
    repo: str,
    batch: list[PRReview],
    previous: InsightSnapshot | None,
    summary: str,
    themes: list[InsightTheme],
    new_names: list[str],
    still: list[str],
    model: str,
    username: str,
) -> ReviewInsightSnapshot:
    through = max(r.id for r in batch)
    prior = previous.included_count if previous else 0
    row = ReviewInsightSnapshot(
        repo_full_name=repo,
        through_review_id=through,
        included_count=prior + len(batch) if previous else len(batch),
        pending_analyzed_count=len(batch),
        summary_markdown=summary,
        themes_json=json.dumps([t.model_dump() for t in themes]),
        new_this_period_json=json.dumps(new_names),
        still_showing_json=json.dumps(still),
        model=model,
        created_by=username,
    )
    if previous and through <= previous.through_review_id:
        row.included_count = max(previous.included_count, len(batch))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _state_from(db: Session, repo: str, row: ReviewInsightSnapshot, *, ran_model: bool) -> InsightState:
    pending = pending_count(db, repo, row.through_review_id)
    return InsightState(
        repo_full_name=repo,
        snapshot=_snapshot_out(row),
        total_reviews=_total_reviews(db, repo),
        pending_count=pending,
        pending_capped=pending > MAX_NEW,
        ran_model=ran_model,
    )


async def analyze(db: Session, repo: str, username: str, *, rebuild: bool = False) -> InsightState:
    total = _total_reviews(db, repo)
    if total == 0:
        raise NoUsableReviews("No reviews to analyze")

    existing_row = _latest_snapshot(db, repo)
    previous = _snapshot_out(existing_row) if existing_row else None

    if rebuild:
        batch = _rebuild_batch(db, repo)
        previous_for_model = None
        prior_snapshot = None
    else:
        watermark = previous.through_review_id if previous else None
        if previous and pending_count(db, repo, watermark) == 0:
            return get_state(db, repo)
        batch = pending_reviews(db, repo, watermark, limit=MAX_NEW)
        previous_for_model = previous
        prior_snapshot = previous

    if not batch:
        raise NoUsableReviews("No reviews to analyze")

    counts = feedback_counts_for(db, [r.id for r in batch])
    cards = _cards_for(batch, counts)
    if not cards:
        raise NoUsableReviews("No usable reviews to analyze")

    payload = _user_payload(previous_for_model, cards, rebuild=rebuild)
    result = await gemini.generate(INSIGHT_SYSTEM_PROMPT, payload)
    try:
        data = parse_insight_payload(result.text)
        summary, themes, new_names, still = sanitize_llm_output(data, _review_ids(db, repo))
    except InsightParseError:
        raise
    except (TypeError, ValueError) as exc:
        raise InsightParseError(str(exc)) from exc
    if not summary and not themes:
        raise GeminiPermanentError("Model returned no insight content")

    row = _persist(
        db,
        repo=repo,
        batch=batch,
        previous=prior_snapshot,
        summary=summary or "No summary returned.",
        themes=themes,
        new_names=new_names,
        still=still,
        model=result.model,
        username=username,
    )
    return _state_from(db, repo, row, ran_model=True)


def build_user_payload_for_tests(
    db: Session, repo: str, *, rebuild: bool = False
) -> tuple[list[dict[str, Any]], str]:
    """Return compact cards and the Gemini user payload (tests inspect this, not live Gemini)."""
    existing_row = _latest_snapshot(db, repo)
    previous = _snapshot_out(existing_row) if existing_row else None
    if rebuild:
        batch = _rebuild_batch(db, repo)
        previous_for_model = None
    else:
        watermark = previous.through_review_id if previous else None
        batch = pending_reviews(db, repo, watermark, limit=MAX_NEW)
        previous_for_model = previous
    counts = feedback_counts_for(db, [r.id for r in batch])
    cards = _cards_for(batch, counts)
    return cards, _user_payload(previous_for_model, cards, rebuild=rebuild)
