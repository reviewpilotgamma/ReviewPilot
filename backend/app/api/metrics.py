"""Analytics endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import Accessible, DbSession, scoped_repos
from app.schemas.metrics import MetricsSummary, TrendPoint
from app.services import metrics as metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"])

Days = Annotated[int, Query(ge=1, le=365)]
RepoFilter = Annotated[str | None, Query(max_length=200)]


@router.get("/summary", response_model=MetricsSummary)
def summary(db: DbSession, accessible: Accessible, repo: RepoFilter = None, days: Days = 30) -> MetricsSummary:
    return metrics_service.summary(db, scoped_repos(accessible, repo), days)


@router.get("/trend", response_model=list[TrendPoint])
def trend(db: DbSession, accessible: Accessible, repo: RepoFilter = None, days: Days = 30) -> list[TrendPoint]:
    return metrics_service.trend(db, scoped_repos(accessible, repo), days)
