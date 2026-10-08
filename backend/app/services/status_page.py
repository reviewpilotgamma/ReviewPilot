"""Check githubstatus.com before posting review comments."""

from __future__ import annotations

import httpx

STATUS_URL = "https://www.githubstatus.com/api/v2/status.json"


async def github_is_healthy() -> bool:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(STATUS_URL, timeout=None)
            indicator = response.json()["status"]["indicator"]
            return indicator == "none"
    except Exception:
        return True


async def wait_until_healthy() -> None:
    while not await github_is_healthy():
        pass
