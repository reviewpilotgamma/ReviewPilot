"""Review history queries and feedback persistence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import PRReview, ReviewFeedback
from app.schemas.reviews import FeedbackOut, ReviewDetail, ReviewListItem


@dataclass(frozen=True)
class ReviewFilters:
    repo: str | None = None
    author: str | None = None
    verdict: str | None = None
    q: str | None = None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def feedback_counts_for(db: Session, review_ids: Sequence[int]) -> dict[int, dict[str, int]]:
    counts: dict[int, dict[str, int]] = {rid: {"helpful": 0, "unhelpful": 0} for rid in review_ids}
    if not review_ids:
        return counts
    rows = db.execute(
        select(ReviewFeedback.review_id, ReviewFeedback.rating, func.count(ReviewFeedback.id))
        .where(ReviewFeedback.review_id.in_(review_ids))
        .group_by(ReviewFeedback.review_id, ReviewFeedback.rating)
    )
    for review_id, rating, n in rows:
        counts[review_id][rating] = n
    return counts


def to_list_item(review: PRReview, counts: dict[str, int] | None = None) -> ReviewListItem:
    item = ReviewListItem.model_validate(review)
    if counts is not None:
        item.feedback_counts = counts
    return item


def list_reviews(
    db: Session,
    repos: Sequence[str],
    filters: ReviewFilters,
    *,
    page: int,
    page_size: int,
    sort_desc: bool = True,
) -> tuple[list[ReviewListItem], int]:
    if not repos:
        return [], 0
    conditions = [PRReview.repo_full_name.in_(repos)]
    if filters.repo:
        conditions.append(PRReview.repo_full_name == filters.repo.lower())
    if filters.author:
        conditions.append(func.lower(PRReview.author) == filters.author.strip().lower())
    if filters.verdict:
        conditions.append(PRReview.verdict == filters.verdict)
    if filters.q:
        conditions.append(PRReview.pr_title.ilike(f"%{_escape_like(filters.q.strip())}%", escape="\\"))

    total = db.scalar(select(func.count(PRReview.id)).where(*conditions)) or 0
    order = PRReview.created_at.desc() if sort_desc else PRReview.created_at.asc()
    rows = db.scalars(
        select(PRReview)
        .where(*conditions)
        .order_by(order, PRReview.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    counts = feedback_counts_for(db, [r.id for r in rows])
    return [to_list_item(r, counts[r.id]) for r in rows], total


def review_detail(db: Session, review: PRReview, user_id: int) -> ReviewDetail:
    counts = feedback_counts_for(db, [review.id])[review.id]
    mine = db.scalar(
        select(ReviewFeedback).where(ReviewFeedback.review_id == review.id, ReviewFeedback.user_id == user_id)
    )
    detail = ReviewDetail.model_validate(review)
    detail.feedback_counts = counts
    detail.my_feedback = FeedbackOut.model_validate(mine) if mine else None
    return detail


def upsert_feedback(db: Session, review_id: int, user_id: int, rating: str, notes: str) -> ReviewFeedback:
    feedback = db.scalar(
        select(ReviewFeedback).where(ReviewFeedback.review_id == review_id, ReviewFeedback.user_id == user_id)
    )
    if feedback is None:
        feedback = ReviewFeedback(review_id=review_id, user_id=user_id)
    feedback.rating = rating
    feedback.notes = notes.strip()
    feedback.created_at = utcnow()
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def list_feedback(db: Session, review_id: int) -> list[ReviewFeedback]:
    return list(
        db.scalars(
            select(ReviewFeedback)
            .where(ReviewFeedback.review_id == review_id)
            .order_by(ReviewFeedback.created_at.desc())
        )
    )
