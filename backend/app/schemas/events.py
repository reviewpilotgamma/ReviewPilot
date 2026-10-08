from __future__ import annotations

from datetime import datetime

from pydantic import computed_field

from app.schemas.common import EventStatus, ORMModel
from app.services.errors import error_code_for


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error_code(self) -> str | None:
        """Stable code for errors the UI explains (e.g. ``diff_too_large``)."""
        return error_code_for(self.last_error)


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
