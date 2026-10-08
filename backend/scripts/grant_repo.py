"""Grant (or revoke) a user's access to repositories the GitHub App is installed on.

Usage (from backend/):
    python -m scripts.grant_repo dev reviewpilotgamma/reviewpilot [more/repos ...]
    python -m scripts.grant_repo dev reviewpilotgamma/reviewpilot --revoke
    python -m scripts.grant_repo dev --list

The user sees a granted repository only while the App is installed on it. Admins already see every installation.
"""

from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import delete, select

from app.core.database import SessionLocal, run_migrations
from app.models import RepoGrant, User
from app.schemas.common import REPO_SEGMENT_PATTERN


def _valid(full_name: str) -> bool:
    parts = full_name.split("/")
    return len(parts) == 2 and all(re.fullmatch(REPO_SEGMENT_PATTERN, p) for p in parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("repos", nargs="*", help="owner/repo")
    parser.add_argument("--revoke", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    run_migrations()
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.username.ilike(args.username)).order_by(User.password_hash.is_(None), User.id)
        )
        if user is None:
            print(f"No user named {args.username!r}", file=sys.stderr)
            return 1
        repos = [r.lower() for r in args.repos]
        bad = [r for r in repos if not _valid(r)]
        if bad:
            print(f"Not an owner/repo name: {', '.join(bad)}", file=sys.stderr)
            return 1
        if args.revoke:
            db.execute(delete(RepoGrant).where(RepoGrant.user_id == user.id, RepoGrant.repo_full_name.in_(repos)))
        else:
            existing = set(db.scalars(select(RepoGrant.repo_full_name).where(RepoGrant.user_id == user.id)))
            db.add_all(RepoGrant(user_id=user.id, repo_full_name=r) for r in repos if r not in existing)
        db.commit()
        granted = db.scalars(
            select(RepoGrant.repo_full_name).where(RepoGrant.user_id == user.id).order_by(RepoGrant.repo_full_name)
        )
        print(f"{user.username}: {', '.join(granted) or '(no granted repositories)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
