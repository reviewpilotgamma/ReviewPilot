from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, utcnow


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        CheckConstraint("status IN ('queued','processed','ignored','failed')", name="ck_webhook_events_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    delivery_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    event: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str | None] = mapped_column(String(50))
    repo: Mapped[str | None] = mapped_column(String(200), index=True)
    sender: Mapped[str | None] = mapped_column(String(100))
    payload_preview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True, nullable=False)

    jobs = relationship("Job", back_populates="event", order_by="Job.id")
