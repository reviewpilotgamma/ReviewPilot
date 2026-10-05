from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class RepoRule(Base):
    __tablename__ = "repo_rules"
    __table_args__ = (
        CheckConstraint("verbosity IN ('concise','detailed')", name="ck_repo_rules_verbosity"),
        CheckConstraint("review_mode IN ('auto','on_demand')", name="ck_repo_rules_review_mode"),
    )

    repo_full_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    custom_instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verbosity: Mapped[str] = mapped_column(String(10), default="concise", nullable=False)
    review_mode: Mapped[str] = mapped_column(String(10), default="auto", nullable=False)
    enable_security: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
