"""Initial schema: users, repo_rules, pr_reviews, review_feedback, webhook_events, jobs.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("github_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("email", sa.String(255)),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime()),
    )

    op.create_table(
        "repo_rules",
        sa.Column("repo_full_name", sa.String(200), primary_key=True),
        sa.Column("custom_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("verbosity", sa.String(10), nullable=False, server_default="concise"),
        sa.Column("review_mode", sa.String(10), nullable=False, server_default="auto"),
        sa.Column("enable_security", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.CheckConstraint("verbosity IN ('concise','detailed')", name="ck_repo_rules_verbosity"),
        sa.CheckConstraint("review_mode IN ('auto','on_demand')", name="ck_repo_rules_review_mode"),
    )

    op.create_table(
        "pr_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("repo_full_name", sa.String(200), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("pr_title", sa.String(500), nullable=False, server_default=""),
        sa.Column("author", sa.String(100), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("full_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("verdict", sa.String(10), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("lines_reviewed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("trigger", sa.String(10), nullable=False, server_default="comment"),
        sa.Column("requester", sa.String(100)),
        sa.Column("github_comment_id", sa.Integer()),
        sa.Column("diff_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("model", sa.String(100), nullable=False, server_default=""),
        sa.CheckConstraint("verdict IN ('passed','warning','critical')", name="ck_pr_reviews_verdict"),
    )
    op.create_index("ix_pr_reviews_repo_full_name", "pr_reviews", ["repo_full_name"])
    op.create_index("ix_pr_reviews_created_at", "pr_reviews", ["created_at"])
    op.create_index("ix_pr_reviews_repo_pr", "pr_reviews", ["repo_full_name", "pr_number"])

    op.create_table(
        "review_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("pr_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("rating", sa.String(10), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("rating IN ('helpful','unhelpful')", name="ck_review_feedback_rating"),
        sa.UniqueConstraint("review_id", "user_id", name="uq_review_feedback_review_user"),
    )
    op.create_index("ix_review_feedback_review_id", "review_feedback", ["review_id"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("delivery_id", sa.String(64), unique=True),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50)),
        sa.Column("repo", sa.String(200)),
        sa.Column("sender", sa.String(100)),
        sa.Column("payload_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('queued','processed','ignored','failed')", name="ck_webhook_events_status"),
    )
    op.create_index("ix_webhook_events_repo", "webhook_events", ["repo"])
    op.create_index("ix_webhook_events_created_at", "webhook_events", ["created_at"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("webhook_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("pr_reviews.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('review','welcome','plan')", name="ck_jobs_kind"),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed')", name="ck_jobs_status"),
    )
    op.create_index("ix_jobs_event_id", "jobs", ["event_id"])
    op.create_index("ix_jobs_status_next_run", "jobs", ["status", "next_run_at"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("webhook_events")
    op.drop_table("review_feedback")
    op.drop_table("pr_reviews")
    op.drop_table("repo_rules")
    op.drop_table("users")
