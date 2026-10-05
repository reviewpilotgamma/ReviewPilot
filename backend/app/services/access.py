"""Tenant isolation: which repositories a user may see, based on their GitHub App installations."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PRReview, RepoRule, User
from app.services import github_user
from app.services.errors import ReauthRequired

CACHE_TTL_SECONDS = 300
LOCAL_GITHUB_ID = 0
LOCAL_INSTALLATION_ID = 0
DEFAULT_LOCAL_REPO = "local/manual"


@dataclass(frozen=True)
class RepoInfo:
    full_name: str
    installation_id: int
    account_login: str
    account_type: str
    account_avatar_url: str
    private: bool
    html_url: str


_cache: dict[int, tuple[float, dict[str, RepoInfo]]] = {}
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def clear_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _cache.clear()
        _locks.clear()
    else:
        _cache.pop(user_id, None)


def local_workspace(db: Session) -> dict[str, RepoInfo]:
    """Repos visible when GitHub is not connected: the default repo plus anything already stored."""
    names = {DEFAULT_LOCAL_REPO}
    names.update(db.scalars(select(RepoRule.repo_full_name)))
    names.update(db.scalars(select(PRReview.repo_full_name).distinct()))
    return {
        name: RepoInfo(
            full_name=name,
            installation_id=LOCAL_INSTALLATION_ID,
            account_login="local",
            account_type="User",
            account_avatar_url="",
            private=False,
            html_url="",
        )
        for name in names
    }


async def get_accessible_repos(user: User, token: str | None, *, refresh: bool = False) -> dict[str, RepoInfo]:
    """Map of lowercase ``owner/repo`` -> info for every repo the user can reach via an installation."""
    if token is None:
        raise ReauthRequired("Stored GitHub token cannot be decrypted")
    async with _locks[user.id]:
        cached = _cache.get(user.id)
        if cached and not refresh and cached[0] > time.time():
            return cached[1]

        repos: dict[str, RepoInfo] = {}
        for inst in await github_user.list_user_installations(token):
            account = inst.get("account") or {}
            for repo in await github_user.list_installation_repos(token, int(inst["id"])):
                full_name = str(repo["full_name"]).lower()
                repos[full_name] = RepoInfo(
                    full_name=full_name,
                    installation_id=int(inst["id"]),
                    account_login=account.get("login", ""),
                    account_type=account.get("type", ""),
                    account_avatar_url=account.get("avatar_url", ""),
                    private=bool(repo.get("private")),
                    html_url=repo.get("html_url", f"https://github.com/{repo['full_name']}"),
                )
        _cache[user.id] = (time.time() + CACHE_TTL_SECONDS, repos)
        return repos
