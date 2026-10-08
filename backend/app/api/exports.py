"""Download stored reviews for quality reporting."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.api.deps import Accessible, DbSession, csrf_protect, scoped_repos
from app.services.review_export import ExportFormat, export_reviews

router = APIRouter(prefix="/exports", tags=["exports"], dependencies=[Depends(csrf_protect)])


@router.get("/reviews", response_class=PlainTextResponse)
def download_reviews(db: DbSession, accessible: Accessible, fmt: ExportFormat = "csv", repo: str | None = None) -> str:
    return export_reviews(db, scoped_repos(accessible, repo), fmt)
