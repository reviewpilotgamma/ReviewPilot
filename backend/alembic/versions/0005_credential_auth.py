"""Credential sign-in: user roles and password hashes; GitHub identity becomes an optional link.

Revision ID: 0005_credential_auth
Revises: 0004_review_insights
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_credential_auth"
down_revision: str | None = "0004_review_insights"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Names the unnamed UNIQUE(github_id) from 0001 on SQLite so the batch rebuild can drop it.
NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _rebuild_users(sqlite: bool):
    return op.batch_alter_table("users", naming_convention=NAMING if sqlite else None)


def upgrade() -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite"
    if sqlite:
        # The rebuild drops and recreates "users"; with FKs on, that would fire ON DELETE SET NULL on referencing rows.
        op.execute("PRAGMA foreign_keys=OFF")
    with _rebuild_users(sqlite) as batch:
        batch.add_column(sa.Column("role", sa.String(10), nullable=False, server_default="dev"))
        batch.add_column(sa.Column("password_hash", sa.String(255)))
        batch.add_column(sa.Column("github_login", sa.String(100)))
        batch.drop_constraint("uq_users_github_id" if sqlite else "users_github_id_key", type_="unique")
        batch.alter_column("github_id", existing_type=sa.Integer(), nullable=True)
        batch.create_index("ix_users_github_id", ["github_id"])
    # Rows created by the old GitHub OAuth login: their username was the GitHub login.
    op.execute("UPDATE users SET github_login = username WHERE github_id IS NOT NULL AND github_id <> 0")
    if sqlite:
        op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite"
    if sqlite:
        op.execute("PRAGMA foreign_keys=OFF")
    # Restore NOT NULL + UNIQUE: unlinked users and all but the first user per GitHub account get a placeholder id.
    op.execute(
        "UPDATE users SET github_id = -id WHERE github_id IS NULL "
        "OR id NOT IN (SELECT MIN(id) FROM users WHERE github_id IS NOT NULL GROUP BY github_id)"
    )
    with _rebuild_users(sqlite) as batch:
        batch.drop_index("ix_users_github_id")
        batch.alter_column("github_id", existing_type=sa.Integer(), nullable=False)
        batch.create_unique_constraint("uq_users_github_id", ["github_id"])
        batch.drop_column("github_login")
        batch.drop_column("password_hash")
        batch.drop_column("role")
    if sqlite:
        op.execute("PRAGMA foreign_keys=ON")
