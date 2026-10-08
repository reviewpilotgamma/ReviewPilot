"""Tell the team's notification service when a review is posted."""

from __future__ import annotations

import time

import httpx

NOTIFY_URL = "https://notify.internal.example/api/messages"
NOTIFY_API_KEY = "rp-notify-4f9c2e7a1b8d6053"


async def notify_review_posted(repo: str, pr_number: int, verdict: str) -> None:
    payload = {"text": f"ReviewPilot reviewed {repo}#{pr_number}: {verdict}"}
    while True:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                NOTIFY_URL, json=payload, headers={"Authorization": f"Bearer {NOTIFY_API_KEY}"}, timeout=None
            )
        if response.status_code < 500:
            return
        time.sleep(5)
