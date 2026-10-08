"""GitHub App integration: RS256 App JWT, cached installation tokens and repo REST operations."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.core.config import get_settings
from app.core.http import get_http_client
from app.services.errors import (
    GitHubNotConfigured,
    GitHubPermanentError,
    GitHubRateLimited,
    GitHubTransientError,
)

logger = logging.getLogger(__name__)

API_VERSION = "2022-11-28"
TOKEN_SAFETY_MARGIN_SECONDS = 60
MAX_REPO_PAGES = 20


def base_headers() -> dict[str, str]:
    return {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION}


# --------------------------------------------------------------------------- error mapping
def raise_for_github(response: httpx.Response) -> None:
    """Translate a GitHub HTTP response into the service error hierarchy."""
    status = response.status_code
    if status < 400:
        return
    try:
        message = response.json().get("message", response.text)
    except ValueError:
        message = response.text
    message = f"GitHub {status}: {str(message)[:300]}"

    remaining = response.headers.get("x-ratelimit-remaining")
    retry_after = response.headers.get("retry-after")
    if status == 429 or (status == 403 and (remaining == "0" or retry_after)):
        wait = float(retry_after) if retry_after and retry_after.isdigit() else 60.0
        reset = response.headers.get("x-ratelimit-reset")
        if not retry_after and reset and reset.isdigit():
            wait = max(1.0, float(reset) - time.time())
        raise GitHubRateLimited(message, retry_after=wait, status_code=status)
    if status >= 500:
        raise GitHubTransientError(message, status_code=status)
    raise GitHubPermanentError(message, status_code=status)


async def github_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Perform a request, mapping transport failures to retryable errors."""
    try:
        return await get_http_client().request(method, url, **kwargs)
    except httpx.TimeoutException as exc:
        raise GitHubTransientError(f"GitHub request timed out: {method} {url}") from exc
    except httpx.TransportError as exc:
        raise GitHubTransientError(f"GitHub transport error: {exc.__class__.__name__}") from exc


# --------------------------------------------------------------------------- App JWT
_key_cache: dict[tuple[str, float], str] = {}


def _load_private_key() -> str:
    settings = get_settings()
    path = settings.private_key_path
    if not settings.GITHUB_APP_ID:
        raise GitHubNotConfigured("GITHUB_APP_ID is not set")
    try:
        mtime = path.stat().st_mtime
    except OSError as exc:
        raise GitHubNotConfigured(f"GitHub App private key not found at {path}") from exc
    cache_key = (str(path), mtime)
    if cache_key not in _key_cache:
        _key_cache.clear()
        _key_cache[cache_key] = path.read_text(encoding="utf-8")
    return _key_cache[cache_key]


def create_app_jwt() -> str:
    """RS256 JWT identifying the App itself (valid 10 minutes, back-dated 60 s for clock drift)."""
    settings = get_settings()
    private_key = _load_private_key()
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": str(settings.GITHUB_APP_ID)}
    try:
        return jwt.encode(payload, private_key, algorithm="RS256")
    except (ValueError, TypeError) as exc:
        raise GitHubNotConfigured("GitHub App private key is invalid") from exc


# --------------------------------------------------------------------------- installation tokens
_token_cache: dict[int, tuple[str, float]] = {}
_token_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def clear_caches() -> None:
    """Drop cached tokens and keys (called when credentials change)."""
    _token_cache.clear()
    _token_locks.clear()
    _key_cache.clear()


def invalidate_installation_token(installation_id: int) -> None:
    _token_cache.pop(installation_id, None)


async def get_installation_token(installation_id: int) -> str:
    async with _token_locks[installation_id]:
        cached = _token_cache.get(installation_id)
        if cached and cached[1] - time.time() > TOKEN_SAFETY_MARGIN_SECONDS:
            return cached[0]
        settings = get_settings()
        response = await github_request(
            "POST",
            f"{settings.GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
            headers={**base_headers(), "Authorization": f"Bearer {create_app_jwt()}"},
        )
        raise_for_github(response)
        token = response.json()["token"]
        _token_cache[installation_id] = (token, time.time() + settings.INSTALLATION_TOKEN_TTL_SECONDS)
        return token


async def _installation_request(
    installation_id: int, method: str, path: str, *, accept: str | None = None, **kwargs: Any
) -> httpx.Response:
    """Request with an installation token; on 401 refresh the token once and retry."""
    settings = get_settings()
    url = f"{settings.GITHUB_API_URL}{path}"
    for attempt in range(2):
        token = await get_installation_token(installation_id)
        headers = {**base_headers(), "Authorization": f"token {token}"}
        if accept:
            headers["Accept"] = accept
        response = await github_request(method, url, headers=headers, **kwargs)
        if response.status_code == 401 and attempt == 0:
            logger.info("Installation token rejected; refreshing (installation=%s)", installation_id)
            invalidate_installation_token(installation_id)
            continue
        raise_for_github(response)
        return response
    raise GitHubPermanentError("GitHub rejected a freshly minted installation token", status_code=401)


# --------------------------------------------------------------------------- repository operations
@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    body: str
    author: str
    base_ref: str
    head_ref: str
    state: str
    draft: bool
    additions: int
    deletions: int
    changed_files: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PullRequest:
        return cls(
            number=int(data["number"]),
            title=data.get("title") or "",
            body=data.get("body") or "",
            author=(data.get("user") or {}).get("login", ""),
            base_ref=(data.get("base") or {}).get("ref", ""),
            head_ref=(data.get("head") or {}).get("ref", ""),
            state=data.get("state", "open"),
            draft=bool(data.get("draft")),
            additions=int(data.get("additions") or 0),
            deletions=int(data.get("deletions") or 0),
            changed_files=int(data.get("changed_files") or 0),
        )


async def get_pull(installation_id: int, owner: str, repo: str, number: int) -> PullRequest:
    response = await _installation_request(installation_id, "GET", f"/repos/{owner}/{repo}/pulls/{number}")
    return PullRequest.from_api(response.json())


async def get_pull_diff(installation_id: int, owner: str, repo: str, number: int) -> str:
    response = await _installation_request(
        installation_id,
        "GET",
        f"/repos/{owner}/{repo}/pulls/{number}",
        accept="application/vnd.github.v3.diff",
    )
    return response.text


async def post_issue_comment(installation_id: int, owner: str, repo: str, number: int, body: str) -> int:
    response = await _installation_request(
        installation_id, "POST", f"/repos/{owner}/{repo}/issues/{number}/comments", json={"body": body}
    )
    return int(response.json()["id"])


async def add_reaction(installation_id: int, owner: str, repo: str, comment_id: int, content: str) -> None:
    """Best effort: failures are logged and swallowed."""
    try:
        await _installation_request(
            installation_id,
            "POST",
            f"/repos/{owner}/{repo}/issues/comments/{comment_id}/reactions",
            json={"content": content},
        )
    except Exception as exc:  # noqa: BLE001 - reactions are cosmetic
        logger.info("Could not add reaction to comment %s: %s", comment_id, exc)


# --------------------------------------------------------------------------- App-level endpoints
async def _app_request(path: str) -> httpx.Response:
    settings = get_settings()
    response = await github_request(
        "GET",
        f"{settings.GITHUB_API_URL}{path}",
        headers={**base_headers(), "Authorization": f"Bearer {create_app_jwt()}"},
    )
    raise_for_github(response)
    return response


async def get_app() -> dict[str, Any]:
    return (await _app_request("/app")).json()


async def list_app_installations() -> list[dict[str, Any]]:
    return (await _app_request("/app/installations?per_page=100")).json()


async def list_installation_repositories(installation_id: int) -> list[dict[str, Any]]:
    """Every repository an installation grants (installation token, paginated)."""
    repos: list[dict[str, Any]] = []
    for page in range(1, MAX_REPO_PAGES + 1):
        response = await _installation_request(
            installation_id, "GET", f"/installation/repositories?per_page=100&page={page}"
        )
        batch = response.json().get("repositories", [])
        repos.extend(batch)
        if len(batch) < 100:
            break
    return repos
