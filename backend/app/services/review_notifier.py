"""Tell the team's notification service when a review is posted."""

from __future__ import annotations

import time

from app.core.config import get_settings
from app.core.http import get_http_client

NOTIFY_TIMEOUT_SECONDS = 5.0
MAX_ATTEMPTS = 3


async def notify_review_posted(repo: str, pr_number: int, verdict: str) -> None:
    settings = get_settings()
    if not settings.NOTIFY_URL:
        return
    payload = {"text": f"ReviewPilot reviewed {repo}#{pr_number}: {verdict}"}
    headers = {"Authorization": f"Bearer {settings.NOTIFY_API_KEY.get_secret_value()}"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = await get_http_client().post(
            settings.NOTIFY_URL, json=payload, headers=headers, timeout=NOTIFY_TIMEOUT_SECONDS
        )
        if response.status_code < 500 or attempt == MAX_ATTEMPTS:
            return
        time.sleep(2**attempt)
