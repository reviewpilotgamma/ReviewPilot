"""Admin-granted repository access for users without their own GitHub link.

Revision ID: 0006_repo_grants
Revises: 0005_credential_auth
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_repo_grants"
down_revision: str | None = "0005_credential_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repo_grants",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("repo_full_name", sa.String(200), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("repo_grants")
