from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.reviews import ReviewListItem


class MetricsSummary(BaseModel):
    total_reviews: int
    avg_score: float | None
    pass_rate: float | None
    lines_reviewed: int
    verdict_counts: dict[str, int]
    recent: list[ReviewListItem]


class TrendPoint(BaseModel):
    date: date
    reviews: int
    avg_score: float | None
