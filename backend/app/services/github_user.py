"""User-to-server GitHub calls: OAuth code exchange, profile and installation discovery."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import get_settings
from app.services.errors import GitHubPermanentError, NotConfiguredError, ReauthRequired
from app.services.github_app import base_headers, github_request, raise_for_github

_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')
MAX_PAGES = 20


def _user_headers(token: str) -> dict[str, str]:
    return {**base_headers(), "Authorization": f"Bearer {token}"}


async def exchange_code(code: str, redirect_uri: str) -> str:
    """Exchange an OAuth authorization code for a user access token."""
    settings = get_settings()
    if not settings.oauth_configured:
        raise NotConfiguredError("GitHub OAuth client is not configured")
    response = await github_request(
        "POST",
        f"{settings.GITHUB_OAUTH_URL}/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET.get_secret_value(),
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    raise_for_github(response)
    data = response.json()
    if "error" in data or "access_token" not in data:
        raise GitHubPermanentError(f"OAuth exchange failed: {data.get('error', 'no token')}")
    return data["access_token"]


async def _get(token: str, url: str) -> Any:
    response = await github_request("GET", url, headers=_user_headers(token))
    if response.status_code == 401:
        raise ReauthRequired("GitHub user token rejected")
    raise_for_github(response)
    return response


async def get_user(token: str) -> dict[str, Any]:
    return (await _get(token, f"{get_settings().GITHUB_API_URL}/user")).json()


async def get_primary_email(token: str) -> str | None:
    """Best effort: the endpoint is unavailable without the email permission."""
    try:
        emails = (await _get(token, f"{get_settings().GITHUB_API_URL}/user/emails")).json()
    except (GitHubPermanentError, ReauthRequired):
        return None
    for entry in emails:
        if entry.get("primary") and entry.get("verified"):
            return entry.get("email")
    return None


async def _paginate(token: str, url: str, key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    next_url: str | None = url
    for _ in range(MAX_PAGES):
        if not next_url:
            break
        response = await _get(token, next_url)
        items.extend(response.json().get(key, []))
        match = _LINK_NEXT_RE.search(response.headers.get("link", ""))
        next_url = match.group(1) if match else None
    return items


async def list_user_installations(token: str) -> list[dict[str, Any]]:
    api = get_settings().GITHUB_API_URL
    return await _paginate(token, f"{api}/user/installations?per_page=100", "installations")


async def list_installation_repos(token: str, installation_id: int) -> list[dict[str, Any]]:
    api = get_settings().GITHUB_API_URL
    return await _paginate(
        token, f"{api}/user/installations/{installation_id}/repositories?per_page=100", "repositories"
    )
