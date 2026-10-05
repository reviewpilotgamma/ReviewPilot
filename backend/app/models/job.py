from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, utcnow


class Job(Base):
    """Durable unit of asynchronous work created from a webhook event."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('review','welcome','plan')", name="ck_jobs_kind"),
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="ck_jobs_status"),
        Index("ix_jobs_status_next_run", "status", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("webhook_events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    review_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pr_reviews.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    event = relationship("WebhookEvent", back_populates="jobs")

    @property
    def data(self) -> dict[str, Any]:
        return json.loads(self.payload)
