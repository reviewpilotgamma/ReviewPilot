"""On-demand insights over stored ReviewPilot reviews."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import Accessible, CurrentUser, DbSession, csrf_protect, scoped_repos
from app.schemas.insights import AnalyzeIn, InsightState
from app.services.errors import GeminiError
from app.services.insights import InsightParseError, NoUsableReviews, analyze, get_state

router = APIRouter(prefix="/insights", tags=["insights"], dependencies=[Depends(csrf_protect)])


def _require_repo(accessible: Accessible, repo: str | None) -> str:
    if not repo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Repository is required")
    repos = scoped_repos(accessible, repo)
    return repos[0]


@router.get("", response_model=InsightState)
def read_insights(
    db: DbSession,
    accessible: Accessible,
    repo: str | None = Query(default=None, max_length=200),
) -> InsightState:
    return get_state(db, _require_repo(accessible, repo))


@router.post("/analyze", response_model=InsightState)
async def run_analyze(body: AnalyzeIn, db: DbSession, user: CurrentUser, accessible: Accessible) -> InsightState:
    repo = _require_repo(accessible, body.repo)
    try:
        return await analyze(db, repo, user.username, rebuild=body.rebuild)
    except NoUsableReviews as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except InsightParseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The model returned an unreadable insight") from exc
    except GeminiError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Insight generation failed") from exc
