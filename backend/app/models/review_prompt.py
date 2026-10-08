from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class ReviewPrompt(Base):
    """Org-wide override of the golden review prompt (single row, ``id = 1``). No row means the built-in default."""

    __tablename__ = "review_prompt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
