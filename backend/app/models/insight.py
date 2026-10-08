from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class ReviewInsightSnapshot(Base):
    """Latest LLM synthesis of ReviewPilot comments for one repository (many rows; GET uses newest)."""

    __tablename__ = "review_insight_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_full_name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    through_review_id: Mapped[int] = mapped_column(Integer, nullable=False)
    included_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_analyzed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_markdown: Mapped[str] = mapped_column(Text, default="", nullable=False)
    themes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    new_this_period_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    still_showing_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
