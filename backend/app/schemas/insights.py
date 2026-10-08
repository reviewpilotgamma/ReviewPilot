from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, Verdict, parse_repo_full_name


class InsightTheme(BaseModel):
    title: str = Field(max_length=200)
    severity: Verdict
    count: int = Field(ge=1, le=10_000)
    last_seen_review_id: int
    example_review_ids: list[int] = Field(default_factory=list, max_length=5)
    evidence: str = Field(default="", max_length=500)


class InsightSnapshot(ORMModel):
    id: int
    repo_full_name: str
    through_review_id: int
    included_count: int
    pending_analyzed_count: int
    summary_markdown: str
    themes: list[InsightTheme]
    new_this_period: list[str]
    still_showing: list[str]
    model: str
    created_at: datetime
    created_by: str


class InsightState(BaseModel):
    repo_full_name: str
    snapshot: InsightSnapshot | None
    total_reviews: int
    pending_count: int
    pending_capped: bool
    ran_model: bool = False


class AnalyzeIn(BaseModel):
    repo: str = Field(max_length=200)
    rebuild: bool = False

    @field_validator("repo")
    @classmethod
    def _repo(cls, value: str) -> str:
        return parse_repo_full_name(value)
