"""PR review history and reviewer feedback."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text

from app.api.deps import Accessible, CurrentUser, DbSession, csrf_protect, scoped_repos
from app.models import PRReview
from app.schemas.common import Page, Verdict
from app.schemas.reviews import FeedbackIn, FeedbackOut, ReviewDetail, ReviewListItem
from app.services import reviews as reviews_service

router = APIRouter(prefix="/reviews", tags=["reviews"], dependencies=[Depends(csrf_protect)])


def _get_accessible_review(db: DbSession, review_id: int, accessible: Accessible) -> PRReview:
    review = db.get(PRReview, review_id)
    if review is None or review.repo_full_name not in accessible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    return review


AccessibleReview = Annotated[PRReview, Depends(_get_accessible_review)]


@router.get("", response_model=Page[ReviewListItem])
def list_reviews(
    db: DbSession,
    accessible: Accessible,
    repo: Annotated[str | None, Query(max_length=200)] = None,
    author: Annotated[str | None, Query(max_length=100)] = None,
    verdict: Verdict | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal["-created_at", "created_at"] = "-created_at",
) -> Page[ReviewListItem]:
    repos = scoped_repos(accessible, repo)
    filters = reviews_service.ReviewFilters(
        author=author or None, verdict=verdict.value if verdict else None, q=q or None
    )
    items, total = reviews_service.list_reviews(
        db, repos, filters, page=page, page_size=page_size, sort_desc=sort.startswith("-")
    )
    return Page[ReviewListItem](items=items, total=total, page=page, page_size=page_size)


SEARCH_SORT_COLUMNS = {"created_at", "score", "pr_number"}
_search_cache: dict[tuple[str, str], list[dict]] = {}


@router.get("/search")
def search_reviews(db: DbSession, term: str, order_by: str = "created_at") -> list[dict]:
    """Free-text search over PR titles and summaries."""
    if order_by not in SEARCH_SORT_COLUMNS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported sort column")
    key = (term, order_by)
    if key not in _search_cache:
        sql = (
            "SELECT id, repo_full_name, pr_number, pr_title, verdict, score FROM pr_reviews "
            f"WHERE pr_title LIKE :pattern OR summary LIKE :pattern ORDER BY {order_by} DESC"
        )
        rows = db.execute(text(sql), {"pattern": f"%{term}%"})
        _search_cache[key] = [dict(row._mapping) for row in rows]
    return _search_cache[key]


@router.get("/{review_id}", response_model=ReviewDetail)
def get_review(db: DbSession, user: CurrentUser, review: AccessibleReview) -> ReviewDetail:
    return reviews_service.review_detail(db, review, user.id)


@router.get("/{review_id}/feedback", response_model=list[FeedbackOut])
def list_feedback(db: DbSession, review: AccessibleReview) -> list:
    return reviews_service.list_feedback(db, review.id)


@router.post("/{review_id}/feedback", response_model=FeedbackOut)
def submit_feedback(body: FeedbackIn, db: DbSession, user: CurrentUser, review: AccessibleReview) -> FeedbackOut:
    feedback = reviews_service.upsert_feedback(db, review.id, user.id, body.rating.value, body.notes)
    return FeedbackOut.model_validate(feedback)
