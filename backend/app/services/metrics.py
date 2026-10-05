"""Aggregate review metrics, scoped to a set of accessible repositories."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import PRReview, ReviewFeedback
from app.schemas.metrics import MetricsSummary, TrendPoint
from app.services.reviews import feedback_counts_for, to_list_item

RECENT_LIMIT = 10


def _pct(numerator: int | None, denominator: int | None) -> float | None:
    if not denominator:
        return None
    return round(100.0 * (numerator or 0) / denominator, 1)


def summary(db: Session, repos: Sequence[str], days: int) -> MetricsSummary:
    empty_counts = {"passed": 0, "warning": 0, "critical": 0}
    if not repos:
        return MetricsSummary(
            total_reviews=0,
            avg_score=None,
            pass_rate=None,
            helpful_rate=None,
            verdict_counts=empty_counts,
            recent=[],
        )
    since = utcnow() - timedelta(days=days)
    scope = (PRReview.repo_full_name.in_(repos), PRReview.created_at >= since)

    total, avg_score, passed = db.execute(
        select(
            func.count(PRReview.id),
            func.avg(PRReview.score),
            func.sum(case((PRReview.verdict == "passed", 1), else_=0)),
        ).where(*scope)
    ).one()

    verdict_counts = dict(empty_counts)
    for verdict, count in db.execute(
        select(PRReview.verdict, func.count(PRReview.id)).where(*scope).group_by(PRReview.verdict)
    ):
        verdict_counts[verdict] = count

    feedback_total, helpful = db.execute(
        select(
            func.count(ReviewFeedback.id),
            func.sum(case((ReviewFeedback.rating == "helpful", 1), else_=0)),
        )
        .join(PRReview, PRReview.id == ReviewFeedback.review_id)
        .where(*scope)
    ).one()

    recent_rows = db.scalars(
        select(PRReview).where(*scope).order_by(PRReview.created_at.desc()).limit(RECENT_LIMIT)
    ).all()
    counts = feedback_counts_for(db, [r.id for r in recent_rows])

    return MetricsSummary(
        total_reviews=total or 0,
        avg_score=round(avg_score, 1) if avg_score is not None else None,
        pass_rate=_pct(passed, total),
        helpful_rate=_pct(helpful, feedback_total),
        verdict_counts=verdict_counts,
        recent=[to_list_item(r, counts.get(r.id)) for r in recent_rows],
    )


def trend(db: Session, repos: Sequence[str], days: int) -> list[TrendPoint]:
    today = utcnow().date()
    start = today - timedelta(days=days - 1)
    buckets: dict[date, tuple[int, float | None]] = {}
    if repos:
        day = func.date(PRReview.created_at)
        rows = db.execute(
            select(day, func.count(PRReview.id), func.avg(PRReview.score))
            .where(PRReview.repo_full_name.in_(repos), func.date(PRReview.created_at) >= start.isoformat())
            .group_by(day)
        ).all()
        buckets = {date.fromisoformat(d): (n, round(avg, 1) if avg is not None else None) for d, n, avg in rows}
    return [
        TrendPoint(
            date=start + timedelta(days=i),
            reviews=buckets.get(start + timedelta(days=i), (0, None))[0],
            avg_score=buckets.get(start + timedelta(days=i), (0, None))[1],
        )
        for i in range(days)
    ]
