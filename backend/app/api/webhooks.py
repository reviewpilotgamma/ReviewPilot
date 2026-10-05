"""GitHub webhook ingress (HMAC verified) and the activity log."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.api.deps import Accessible, CurrentUser, DbSession, is_admin
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import verify_github_signature
from app.models import WebhookEvent
from app.schemas.common import EventStatus
from app.schemas.events import EventOut
from app.services import access, dispatcher

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _ingest(event: str, delivery_id: str | None, payload: dict) -> dispatcher.IngestResult:
    with SessionLocal() as db:
        return dispatcher.ingest(db, event=event, delivery_id=delivery_id, payload=payload)


@router.post("/github")
async def receive(request: Request) -> dict:
    """Verify the signature over the raw body *before* parsing, record the event, enqueue jobs."""
    raw = await request.body()
    secret = get_settings().GITHUB_WEBHOOK_SECRET.get_secret_value()
    if not verify_github_signature(raw, request.headers.get("X-Hub-Signature-256"), secret):
        client = request.client.host if request.client else "unknown"
        logger.warning("Rejected webhook with invalid signature from %s", client)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON payload")

    event = request.headers.get("X-GitHub-Event", "unknown")[:50]
    delivery_id = (request.headers.get("X-GitHub-Delivery") or "")[:64] or None
    result = await run_in_threadpool(_ingest, event, delivery_id, payload)
    if result.installation_changed:
        access.clear_cache()
    logger.info(
        "Webhook %s/%s delivery=%s -> %s (%s jobs)",
        event,
        payload.get("action"),
        delivery_id,
        result.status,
        result.jobs,
    )
    return {"status": "duplicate" if result.status == "duplicate" else "ok", "jobs": result.jobs}


@router.get("/events", response_model=list[EventOut])
def list_events(
    db: DbSession,
    user: CurrentUser,
    accessible: Accessible,
    status_filter: Annotated[EventStatus | None, Query(alias="status")] = None,
    repo: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[WebhookEvent]:
    repos = list(accessible)
    if repo:
        if repo.lower() not in accessible:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
        repos = [repo.lower()]

    repo_condition = WebhookEvent.repo.in_(repos)
    if is_admin(user) and not repo:
        repo_condition = repo_condition | WebhookEvent.repo.is_(None)

    query = (
        select(WebhookEvent)
        .options(selectinload(WebhookEvent.jobs))
        .where(repo_condition)
        .order_by(WebhookEvent.id.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(WebhookEvent.status == status_filter.value)
    if before_id:
        query = query.where(WebhookEvent.id < before_id)
    return list(db.scalars(query))
