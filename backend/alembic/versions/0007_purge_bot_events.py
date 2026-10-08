"""Delete stored bot-sender events: ReviewPilot's own PR comments echoed back by GitHub.

Revision ID: 0007_purge_bot_events
Revises: 0006_repo_grants
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_purge_bot_events"
down_revision: str | None = "0006_repo_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Bot events never create jobs, so no child rows reference them.
    op.execute("DELETE FROM webhook_events WHERE status = 'ignored' AND error_message = 'bot sender'")


def downgrade() -> None:
    # The deleted rows were noise and cannot be restored.
    pass
