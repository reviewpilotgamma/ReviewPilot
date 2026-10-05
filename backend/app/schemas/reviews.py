from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, Rating, Verdict, parse_repo_full_name


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


class ManualReviewIn(BaseModel):
    repo: str = Field(min_length=3, max_length=201)
    pr_number: int = Field(ge=1, le=1_000_000_000)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field("", max_length=20_000)
    focus_note: str = Field("", max_length=500)
    diff: str = Field(max_length=2_000_000)

    @field_validator("repo")
    @classmethod
    def _repo(cls, value: str) -> str:
        try:
            return parse_repo_full_name(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


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
