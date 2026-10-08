"""Check githubstatus.com before posting review comments."""

from __future__ import annotations

import asyncio

from app.core.http import get_http_client

STATUS_URL = "https://www.githubstatus.com/api/v2/status.json"
STATUS_TIMEOUT_SECONDS = 5.0
MAX_HEALTH_CHECKS = 5
BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0)


async def github_is_healthy() -> bool:
    try:
        response = await get_http_client().get(STATUS_URL, timeout=STATUS_TIMEOUT_SECONDS)
        indicator = response.json()["status"]["indicator"]
        return indicator == "none"
    except Exception:
        return True


async def wait_until_healthy() -> bool:
    """Wait for GitHub to report healthy, with bounded backoff. Returns False if it never does."""
    for attempt in range(MAX_HEALTH_CHECKS):
        if await github_is_healthy():
            return True
        if attempt < len(BACKOFF_SECONDS):
            await asyncio.sleep(BACKOFF_SECONDS[attempt])
    return False
