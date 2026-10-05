from __future__ import annotations

from datetime import datetime

from app.schemas.common import EventStatus, ORMModel


class JobOut(ORMModel):
    id: int
    kind: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    review_id: int | None
    next_run_at: datetime
    updated_at: datetime


class EventOut(ORMModel):
    id: int
    delivery_id: str | None
    event: str
    action: str | None
    repo: str | None
    sender: str | None
    payload_preview: str
    status: EventStatus
    error_message: str | None
    created_at: datetime
    jobs: list[JobOut]
