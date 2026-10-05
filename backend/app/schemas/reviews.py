from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, Rating, Verdict


class FeedbackIn(BaseModel):
    rating: Rating
    notes: str = Field("", max_length=2_000)


class FeedbackOut(ORMModel):
    id: int
    review_id: int
    user_id: int | None
    rating: Rating
    notes: str
    created_at: datetime


class ReviewListItem(ORMModel):
    id: int
    repo_full_name: str
    pr_number: int
    pr_title: str
    author: str
    verdict: Verdict
    score: float
    lines_reviewed: int
    summary: str
    created_at: datetime
    trigger: str
    pr_url: str
    feedback_counts: dict[str, int] = Field(default_factory=lambda: {"helpful": 0, "unhelpful": 0})


class ReviewDetail(ReviewListItem):
    full_markdown: str
    requester: str | None
    diff_truncated: bool
    model: str
    my_feedback: FeedbackOut | None = None
