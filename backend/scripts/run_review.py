"""Run the review pipeline on a local diff and store the result.

Usage (from ``backend/``)::

    python -m scripts.run_review --repo local/manual --pr 1 --title "Add retries" --diff change.diff
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.database import SessionLocal
from app.schemas.common import parse_repo_full_name
from app.services.errors import EmptyDiffError, NotConfiguredError, ServiceError
from app.services.reviewer import run_manual_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ReviewPilot pipeline on a local diff.")
    parser.add_argument("--repo", required=True, help="Repository as owner/name")
    parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    parser.add_argument("--title", required=True, help="Pull request title")
    parser.add_argument("--description", default="", help="Pull request description")
    parser.add_argument("--note", default="", help="Optional focus note")
    parser.add_argument("--author", default="dev", help="Author stored on the review")
    parser.add_argument("--diff", required=True, type=Path, help="Path to a unified diff")
    args = parser.parse_args(argv)

    try:
        repo = parse_repo_full_name(args.repo)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.pr < 1:
        print("Pull request number must be at least 1", file=sys.stderr)
        return 1
    if not args.diff.is_file():
        print(f"Diff file not found: {args.diff}", file=sys.stderr)
        return 1

    try:
        review = asyncio.run(
            run_manual_review(
                repo_full_name=repo,
                pr_number=args.pr,
                title=args.title,
                description=args.description,
                author=args.author,
                focus_note=args.note,
                diff=args.diff.read_text(encoding="utf-8"),
            )
        )
    except EmptyDiffError:
        print("Diff is empty", file=sys.stderr)
        return 1
    except NotConfiguredError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ServiceError as exc:
        print(exc.user_reason, file=sys.stderr)
        return 1

    with SessionLocal() as db:
        db.add(review)
        db.commit()
        db.refresh(review)
        review_id, verdict, score = review.id, review.verdict, review.score
    print(f"review {review_id}  verdict={verdict}  score={score:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
