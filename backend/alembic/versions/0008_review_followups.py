"""Follow-up reviews: the head commit each review saw, and the review it follows up.

Revision ID: 0008_review_followups
Revises: 0007_purge_bot_events
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_review_followups"
down_revision: str | None = "0007_purge_bot_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN: no table rebuild, so review_feedback rows (ON DELETE CASCADE) are never touched.
    op.add_column("pr_reviews", sa.Column("head_sha", sa.String(40)))
    if op.get_bind().dialect.name == "sqlite":
        # SQLite accepts a REFERENCES clause on ADD COLUMN, but Alembic only adds constraints by rebuilding.
        op.execute(
            "ALTER TABLE pr_reviews ADD COLUMN previous_review_id INTEGER "
            "REFERENCES pr_reviews (id) ON DELETE SET NULL"
        )
    else:
        op.add_column(
            "pr_reviews",
            sa.Column(
                "previous_review_id",
                sa.Integer(),
                sa.ForeignKey("pr_reviews.id", ondelete="SET NULL", name="fk_pr_reviews_previous_review_id"),
            ),
        )


def downgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"
    if sqlite:
        # The batch rebuild drops "pr_reviews"; with FKs on, that would cascade-delete review_feedback.
        op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("pr_reviews") as batch:
        batch.drop_column("previous_review_id")
        batch.drop_column("head_sha")
    if sqlite:
        op.execute("PRAGMA foreign_keys=ON")
