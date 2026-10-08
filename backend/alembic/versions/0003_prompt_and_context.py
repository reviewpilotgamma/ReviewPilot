"""Add the editable golden prompt and per-review context.

Revision ID: 0003_prompt_and_context
Revises: 0002_repo_documents
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_prompt_and_context"
down_revision: str | None = "0002_repo_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_prompt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(100), nullable=False, server_default=""),
    )
    with op.batch_alter_table("pr_reviews") as batch:
        batch.add_column(sa.Column("review_context", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pr_reviews") as batch:
        batch.drop_column("review_context")
    op.drop_table("review_prompt")
