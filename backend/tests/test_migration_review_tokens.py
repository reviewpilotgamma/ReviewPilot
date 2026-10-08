"""Migration 0009 adds the token-usage column without touching existing reviews or their feedback."""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.test_migration_credential_auth import _config

COLUMNS = (
    "id, repo_full_name, pr_number, pr_title, author, summary, full_markdown, verdict, "
    "score, lines_reviewed, created_at, trigger, diff_truncated, model"
)


def test_tokens_column_round_trip(tmp_path):
    path = tmp_path / "m.db"
    cfg = _config(f"sqlite:///{path.as_posix()}")
    command.upgrade(cfg, "0008_review_followups")
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"INSERT INTO pr_reviews ({COLUMNS}) "
            "VALUES (1, 'a/b', 7, 't', 'bob', '', '', 'warning', 6.5, 10, '2026-10-08', 'auto', 0, '')"
        )
        conn.execute(
            "INSERT INTO review_feedback (review_id, rating, notes, created_at) VALUES (1, 'helpful', '', '2026-10-08')"
        )

    command.upgrade(cfg, "head")
    with sqlite3.connect(path) as conn:
        # Older reviews have no token count.
        assert conn.execute("SELECT tokens_used FROM pr_reviews WHERE id = 1").fetchone() == (None,)
        conn.execute(
            f"INSERT INTO pr_reviews ({COLUMNS}, tokens_used) "
            "VALUES (2, 'a/b', 7, 't', 'bob', '', '', 'passed', 9, 4, '2026-10-08', 'push', 0, '', 12480)"
        )
        assert conn.execute("SELECT tokens_used FROM pr_reviews WHERE id = 2").fetchone() == (12480,)

    command.downgrade(cfg, "0008_review_followups")
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(pr_reviews)")}
        assert "tokens_used" not in columns
        assert conn.execute("SELECT COUNT(*) FROM pr_reviews").fetchone() == (2,)
        assert conn.execute("SELECT COUNT(*) FROM review_feedback").fetchone() == (1,)


def test_upgrade_tolerates_a_column_from_an_interrupted_run(tmp_path):
    path = tmp_path / "m.db"
    cfg = _config(f"sqlite:///{path.as_posix()}")
    command.upgrade(cfg, "0008_review_followups")
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE pr_reviews ADD COLUMN tokens_used INTEGER")

    command.upgrade(cfg, "0009_review_tokens")
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0009_review_tokens",)
