from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, utcnow


class PRReview(Base):
    __tablename__ = "pr_reviews"
    __table_args__ = (
        CheckConstraint("verdict IN ('passed','warning','critical')", name="ck_pr_reviews_verdict"),
        Index("ix_pr_reviews_repo_pr", "repo_full_name", "pr_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_full_name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    author: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    full_markdown: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verdict: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    lines_reviewed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True, nullable=False)
    trigger: Mapped[str] = mapped_column(String(10), default="comment", nullable=False)
    requester: Mapped[str | None] = mapped_column(String(100))
    github_comment_id: Mapped[int | None] = mapped_column(Integer)
    diff_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    # JSON: which golden prompt, instructions and documents this review used (null for older reviews).
    review_context: Mapped[str | None] = mapped_column(Text)
    # Head commit this review saw, and the review it follows up (null for first reviews and older rows).
    head_sha: Mapped[str | None] = mapped_column(String(40))
    previous_review_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pr_reviews.id", ondelete="SET NULL"))

    feedback = relationship(
        "ReviewFeedback", back_populates="review", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def pr_url(self) -> str:
        return f"https://github.com/{self.repo_full_name}/pull/{self.pr_number}"
