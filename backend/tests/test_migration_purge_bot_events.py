"""Migration 0007 deletes stored bot-sender events and keeps everything else."""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.test_migration_credential_auth import _config


def test_upgrade_deletes_only_bot_sender_events(tmp_path):
    path = tmp_path / "m.db"
    cfg = _config(f"sqlite:///{path.as_posix()}")
    command.upgrade(cfg, "0006_repo_grants")
    with sqlite3.connect(path) as conn:
        conn.executemany(
            "INSERT INTO webhook_events (delivery_id, event, status, error_message, created_at) "
            "VALUES (?, 'issue_comment', ?, ?, '2026-10-08')",
            [
                ("bot", "ignored", "bot sender"),
                ("human", "ignored", "no trigger"),
                ("pr", "processed", None),
            ],
        )

    command.upgrade(cfg, "head")
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT delivery_id FROM webhook_events ORDER BY id").fetchall()
    assert rows == [("human",), ("pr",)]

    command.downgrade(cfg, "0006_repo_grants")
