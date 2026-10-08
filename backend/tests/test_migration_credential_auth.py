"""Migration 0005 rebuilds ``users`` on SQLite; referencing rows must keep their foreign keys."""

from __future__ import annotations

import sqlite3

from alembic import command
from alembic.config import Config

from app.core.database import BACKEND_DIR


def _config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


def test_upgrade_keeps_users_and_references(tmp_path):
    path = tmp_path / "m.db"
    cfg = _config(f"sqlite:///{path.as_posix()}")
    command.upgrade(cfg, "0004_review_insights")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO users (id, github_id, username, access_token, created_at) "
            "VALUES (7, 1001, 'alice', 'x', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO repo_rules (repo_full_name, custom_instructions, verbosity, review_mode, enable_security, "
            "updated_at, updated_by_user_id) VALUES ('a/b', '', 'concise', 'auto', 1, '2026-01-01', 7)"
        )

    command.upgrade(cfg, "head")
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id, github_id, role, github_login FROM users").fetchall() == [
            (7, 1001, "dev", "alice")
        ]
        assert conn.execute("SELECT updated_by_user_id FROM repo_rules").fetchall() == [(7,)]
        # github_id is optional and no longer unique.
        conn.execute("INSERT INTO users (username, access_token, created_at) VALUES ('dev', '', '2026-01-01')")
        conn.execute("INSERT INTO users (github_id, username, access_token, created_at) VALUES (1001, 'b', '', 'x')")

    command.downgrade(cfg, "0004_review_insights")
