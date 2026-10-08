"""Tenant isolation: which repositories a user may see, based on their GitHub App installations."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass

from app.models import User
from app.services import github_app, github_user
from app.services.errors import ReauthRequired

CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class RepoInfo:
    full_name: str
    installation_id: int
    account_login: str
    account_type: str
    account_avatar_url: str
    private: bool
    html_url: str


APP_CACHE_KEY = -1  # cache slot for the App-wide repository list (user ids are positive)

_cache: dict[int, tuple[float, dict[str, RepoInfo]]] = {}
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def clear_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _cache.clear()
        _locks.clear()
    else:
        _cache.pop(user_id, None)


async def get_app_repos(*, refresh: bool = False) -> dict[str, RepoInfo]:
    """Every repository of every installation of the GitHub App, via the App's own credentials (admins)."""
    async with _locks[APP_CACHE_KEY]:
        cached = _cache.get(APP_CACHE_KEY)
        if cached and not refresh and cached[0] > time.time():
            return cached[1]

        repos: dict[str, RepoInfo] = {}
        for inst in await github_app.list_app_installations():
            account = inst.get("account") or {}
            for repo in await github_app.list_installation_repositories(int(inst["id"])):
                full_name = str(repo["full_name"]).lower()
                repos[full_name] = _repo_info(repo, inst, account)
        _cache[APP_CACHE_KEY] = (time.time() + CACHE_TTL_SECONDS, repos)
        return repos


def _repo_info(repo: dict, inst: dict, account: dict) -> RepoInfo:
    return RepoInfo(
        full_name=str(repo["full_name"]).lower(),
        installation_id=int(inst["id"]),
        account_login=account.get("login", ""),
        account_type=account.get("type", ""),
        account_avatar_url=account.get("avatar_url", ""),
        private=bool(repo.get("private")),
        html_url=repo.get("html_url", f"https://github.com/{repo['full_name']}"),
    )


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
                repos[full_name] = _repo_info(repo, inst, account)
        _cache[user.id] = (time.time() + CACHE_TTL_SECONDS, repos)
        return repos
