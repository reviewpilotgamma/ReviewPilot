"""Migration 0008 adds follow-up columns without touching existing reviews or their feedback."""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.test_migration_credential_auth import _config


def test_followup_columns_round_trip(tmp_path):
    path = tmp_path / "m.db"
    cfg = _config(f"sqlite:///{path.as_posix()}")
    command.upgrade(cfg, "0007_purge_bot_events")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO pr_reviews (id, repo_full_name, pr_number, pr_title, author, summary, full_markdown, verdict, "
            "score, lines_reviewed, created_at, trigger, diff_truncated, model) "
            "VALUES (1, 'a/b', 7, 't', 'bob', '', '', 'warning', 6.5, 10, '2026-10-08', 'auto', 0, '')"
        )
        conn.execute(
            "INSERT INTO review_feedback (review_id, rating, notes, created_at) VALUES (1, 'helpful', '', '2026-10-08')"
        )

    command.upgrade(cfg, "head")
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO pr_reviews (id, repo_full_name, pr_number, pr_title, author, summary, full_markdown, verdict, "
            "score, lines_reviewed, created_at, trigger, diff_truncated, model, head_sha, previous_review_id) "
            "VALUES (2, 'a/b', 7, 't', 'bob', '', '', 'passed', 9, 4, '2026-10-08', 'push', 0, '', 'abc', 1)"
        )
        assert conn.execute("SELECT head_sha, previous_review_id FROM pr_reviews WHERE id = 2").fetchone() == ("abc", 1)

    command.downgrade(cfg, "0007_purge_bot_events")
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pr_reviews").fetchone() == (2,)
        assert conn.execute("SELECT COUNT(*) FROM review_feedback").fetchone() == (1,)


def test_upgrade_tolerates_columns_from_an_interrupted_run(tmp_path):
    path = tmp_path / "m.db"
    cfg = _config(f"sqlite:///{path.as_posix()}")
    command.upgrade(cfg, "0007_purge_bot_events")
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE pr_reviews ADD COLUMN head_sha VARCHAR(40)")
        conn.execute("ALTER TABLE pr_reviews ADD COLUMN previous_review_id INTEGER")

    command.upgrade(cfg, "head")
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0008_review_followups",)
