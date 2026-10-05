"""Import repo_rules, pr_reviews and review_feedback from the PoC ``reviewpilot.db``.

Usage (from backend/):
    python -m scripts.import_legacy_db --src ../old/reviewpilot.db [--dry-run]

Repository names are lower-cased; new columns get defaults. Existing rows are left untouched
(rules are skipped if present; reviews are always appended), so run it once.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.core.database import SessionLocal, run_migrations
from app.models import PRReview, RepoRule, ReviewFeedback

VERDICTS = {"passed", "warning", "critical"}


def _parse_ts(value: object) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return conn.execute(f"SELECT * FROM {table}").fetchall() if exists else []  # noqa: S608 - fixed names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.src.is_file():
        print(f"Source database not found: {args.src}", file=sys.stderr)
        return 1

    run_migrations()
    src = sqlite3.connect(args.src)
    src.row_factory = sqlite3.Row
    counts = {"rules": 0, "reviews": 0, "feedback": 0}

    with SessionLocal() as db:
        for row in _rows(src, "repo_rules"):
            name = str(row["repo_full_name"]).lower()
            if db.get(RepoRule, name):
                continue
            db.add(
                RepoRule(
                    repo_full_name=name,
                    custom_instructions=row["custom_instructions"] or "",
                    verbosity=row["verbosity"] if row["verbosity"] in ("concise", "detailed") else "concise",
                    review_mode=row["review_mode"] if row["review_mode"] in ("auto", "on_demand") else "auto",
                    enable_security=bool(row["enable_security"]),
                    updated_at=_parse_ts(row["updated_at"]),
                )
            )
            counts["rules"] += 1

        id_map: dict[int, int] = {}
        for row in _rows(src, "pr_reviews"):
            review = PRReview(
                repo_full_name=str(row["repo_full_name"]).lower(),
                pr_number=int(row["pr_number"]),
                pr_title=row["pr_title"] or "",
                author=row["author"] or "",
                summary=row["summary"] or "",
                full_markdown=row["full_markdown"] or "",
                verdict=row["verdict"] if row["verdict"] in VERDICTS else "warning",
                score=max(0.0, min(10.0, float(row["score"] or 0))),
                lines_reviewed=int(row["lines_reviewed"] or 0),
                created_at=_parse_ts(row["created_at"]),
                trigger="comment",
                model="legacy",
            )
            db.add(review)
            db.flush()
            id_map[int(row["id"])] = review.id
            counts["reviews"] += 1

        for row in _rows(src, "review_feedback"):
            new_id = id_map.get(int(row["review_id"]))
            if new_id is None or row["rating"] not in ("helpful", "unhelpful"):
                continue
            db.add(
                ReviewFeedback(
                    review_id=new_id,
                    user_id=None,
                    rating=row["rating"],
                    notes=row["notes"] or "",
                    created_at=_parse_ts(row["created_at"]),
                )
            )
            counts["feedback"] += 1

        if args.dry_run:
            db.rollback()
            print(f"[dry-run] would import {counts}")
        else:
            db.commit()
            print(f"Imported {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
