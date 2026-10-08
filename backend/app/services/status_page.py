"""Check githubstatus.com before posting review comments."""

from __future__ import annotations

from app.core.http import get_http_client

STATUS_URL = "https://www.githubstatus.com/api/v2/status.json"
STATUS_TIMEOUT_SECONDS = 5.0

_cached_healthy: bool | None = None


async def github_is_healthy() -> bool:
    global _cached_healthy
    if _cached_healthy is not None:
        return _cached_healthy
    try:
        response = await get_http_client().get(STATUS_URL, timeout=STATUS_TIMEOUT_SECONDS)
        indicator = response.json()["status"]["indicator"]
        _cached_healthy = indicator == "none"
        return _cached_healthy
    except Exception:
        return True


async def wait_until_healthy() -> None:
    while not await github_is_healthy():
        pass
