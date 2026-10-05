"""PR review history and reviewer feedback."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import Accessible, CurrentUser, DbSession, csrf_protect, scoped_repos
from app.core.config import get_settings
from app.models import PRReview
from app.schemas.common import Page, Verdict
from app.schemas.reviews import FeedbackIn, FeedbackOut, ManualReviewIn, ReviewDetail, ReviewListItem
from app.services import reviewer
from app.services import reviews as reviews_service
from app.services.errors import EmptyDiffError, NotConfiguredError, ServiceError

router = APIRouter(prefix="/reviews", tags=["reviews"], dependencies=[Depends(csrf_protect)])


def _get_accessible_review(db: DbSession, review_id: int, accessible: Accessible) -> PRReview:
    review = db.get(PRReview, review_id)
    if review is None or review.repo_full_name not in accessible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    return review


AccessibleReview = Annotated[PRReview, Depends(_get_accessible_review)]


@router.post("/manual", response_model=ReviewDetail)
async def create_manual_review(
    body: ManualReviewIn, db: DbSession, user: CurrentUser, accessible: Accessible
) -> ReviewDetail:
    """Run the AI pipeline on a pasted diff and store the review. Does not post to GitHub."""
    if not get_settings().local_mode and body.repo not in accessible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    try:
        review = await reviewer.run_manual_review(
            repo_full_name=body.repo,
            pr_number=body.pr_number,
            title=body.title,
            description=body.description,
            author=user.username,
            focus_note=body.focus_note,
            diff=body.diff,
        )
    except EmptyDiffError as exc:
        raise HTTPException(422, "Paste a diff before running a review") from exc
    except NotConfiguredError:
        raise
    except ServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.user_reason) from exc
    db.add(review)
    db.commit()
    db.refresh(review)
    return reviews_service.review_detail(db, review, user.id)


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
