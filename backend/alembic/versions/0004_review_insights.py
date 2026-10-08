"""Store on-demand review-comment insight snapshots per repository.

Revision ID: 0004_review_insights
Revises: 0003_prompt_and_context
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_review_insights"
down_revision: str | None = "0003_prompt_and_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_insight_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("repo_full_name", sa.String(200), nullable=False, index=True),
        sa.Column("through_review_id", sa.Integer(), nullable=False),
        sa.Column("included_count", sa.Integer(), nullable=False),
        sa.Column("pending_analyzed_count", sa.Integer(), nullable=False),
        sa.Column("summary_markdown", sa.Text(), nullable=False),
        sa.Column("themes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("new_this_period_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("still_showing_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("model", sa.String(100), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("review_insight_snapshots")
