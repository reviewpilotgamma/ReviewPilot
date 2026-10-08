from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
    # Gemini tokens the review used; None for older reviews.
    tokens_used: int | None = None
    summary: str
    created_at: datetime
    trigger: str
    pr_url: str
    diff_truncated: bool = False
    head_sha: str | None = None
    previous_review_id: int | None = None
    feedback_counts: dict[str, int] = Field(default_factory=lambda: {"helpful": 0, "unhelpful": 0})


class ReviewContext(BaseModel):
    """What a review was reviewed with: golden prompt version, instructions and documents (filenames only)."""

    prompt: Literal["default", "custom"]
    prompt_updated_at: datetime | None = None
    instructions_chars: int = 0
    verbosity: str = "concise"
    security: bool = True
    documents: list[str] = Field(default_factory=list)
    documents_mode: Literal["cached", "inline", "none"] = "none"
    requester_note: bool = False


class ReviewDetail(ReviewListItem):
    full_markdown: str
    requester: str | None
    model: str
    review_context: ReviewContext | None = None
    my_feedback: FeedbackOut | None = None

    @field_validator("review_context", mode="before")
    @classmethod
    def _parse_context(cls, value: object) -> object:
        """Stored as JSON text; anything unreadable (or older reviews) becomes ``None``."""
        if value is None or isinstance(value, (dict, ReviewContext)):
            return value
        try:
            data = json.loads(value)  # type: ignore[arg-type]
            return ReviewContext.model_validate(data)
        except (TypeError, ValueError):
            return None
