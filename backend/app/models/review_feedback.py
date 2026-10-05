from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, utcnow


class ReviewFeedback(Base):
    __tablename__ = "review_feedback"
    __table_args__ = (
        CheckConstraint("rating IN ('helpful','unhelpful')", name="ck_review_feedback_rating"),
        UniqueConstraint("review_id", "user_id", name="uq_review_feedback_review_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pr_reviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    rating: Mapped[str] = mapped_column(String(10), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    review = relationship("PRReview", back_populates="feedback")
