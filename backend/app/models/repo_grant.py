from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class RepoGrant(Base):
    """An admin-granted repository a user may see without reaching it through their own GitHub link."""

    __tablename__ = "repo_grants"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    repo_full_name: Mapped[str] = mapped_column(String(200), primary_key=True)  # lowercase owner/repo
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
