"""Review token usage: the Gemini tokens each review used.

Revision ID: 0009_review_tokens
Revises: 0008_review_followups
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_review_tokens"
down_revision: str | None = "0008_review_followups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Skip the column if it exists: an interrupted earlier run of this revision may have added it without stamping.
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("pr_reviews")}
    # Plain ADD COLUMN: no table rebuild, so review_feedback rows (ON DELETE CASCADE) are never touched.
    if "tokens_used" not in existing:
        op.add_column("pr_reviews", sa.Column("tokens_used", sa.Integer()))


def downgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"
    if sqlite:
        # The batch rebuild drops "pr_reviews"; with FKs on, that would cascade-delete review_feedback.
        op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("pr_reviews") as batch:
        batch.drop_column("tokens_used")
    if sqlite:
        op.execute("PRAGMA foreign_keys=ON")
