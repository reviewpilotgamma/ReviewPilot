"""Webhook trust boundary end to end: signatures, bot loops, duplicate deliveries, secret hygiene."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import Job, PRReview, WebhookEvent
from tests.conftest import post_webhook, sign
from tests.e2e.diffs import PLANTED_SCENARIOS
from tests.e2e.harness import INSTALLATION_TOKEN, comment_payload, pr_opened_payload

WEBHOOK_URL = "/api/v1/webhooks/github"
GEMINI_TEST_KEY = "gemini-key-1234"


def counts() -> tuple[int, int, int]:
    with SessionLocal() as db:
        return tuple(db.scalar(select(func.count()).select_from(m)) for m in (WebhookEvent, Job, PRReview))


def headers(signature: str | None) -> dict[str, str]:
    base = {"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "sec-1", "Content-Type": "application/json"}
    return {**base, "X-Hub-Signature-256": signature} if signature is not None else base


@pytest.mark.parametrize("case", ["missing", "wrong_secret", "tampered_body", "malformed_header"])
async def test_invalid_signature_is_rejected_and_nothing_runs(pipeline, case):
    pipeline.github.add_pr(50, PLANTED_SCENARIOS["clean"])
    body = json.dumps(pr_opened_payload(50, PLANTED_SCENARIOS["clean"])).encode()
    sent, signature = body, sign(body)
    if case == "missing":
        signature = None
    elif case == "wrong_secret":
        signature = sign(body, secret="not-the-secret")
    elif case == "tampered_body":
        sent = body.replace(b'"opened"', b'"closed"')
    else:
        signature = signature.removeprefix("sha256=")

    response = pipeline.client.post(WEBHOOK_URL, content=sent, headers=headers(signature))

    assert response.status_code == 401
    assert counts() == (0, 0, 0)
    assert await pipeline.drain() == 0
    assert pipeline.github.comments == [] and pipeline.llm.generate_calls == 0


async def test_malformed_json_with_valid_signature_is_400(pipeline):
    body = b"{not json"
    response = pipeline.client.post(WEBHOOK_URL, content=body, headers=headers(sign(body)))
    assert response.status_code == 400
    assert counts() == (0, 0, 0)


@pytest.mark.parametrize(
    ("commenter", "commenter_type"), [("reviewpilot-test[bot]", "User"), ("ci-helper", "Bot")]
)
async def test_bot_comment_never_triggers_a_review(pipeline, commenter, commenter_type):
    pipeline.github.add_pr(51, PLANTED_SCENARIOS["clean"])
    delivery = pipeline.comment(51, "@review please", commenter=commenter, commenter_type=commenter_type)

    assert await pipeline.drain() == 0

    event = pipeline.event(delivery)
    assert (event.status, event.error_message) == ("ignored", "bot sender")
    assert pipeline.jobs(delivery) == []
    assert pipeline.github.comments == [] and pipeline.llm.generate_calls == 0


async def test_duplicate_delivery_is_processed_once(pipeline):
    scenario = PLANTED_SCENARIOS["clean"]
    pipeline.open_pr(52, scenario, delivery="dup-1")

    replay = post_webhook(pipeline.client, "pull_request", pr_opened_payload(52, scenario), "dup-1")

    assert replay.status_code == 200 and replay.json() == {"status": "duplicate", "jobs": 0}
    assert await pipeline.drain() == 1
    assert len(pipeline.reviews()) == 1
    assert len(pipeline.github.comments_for(52)) == 1
    assert counts()[:2] == (1, 1)


async def test_non_pr_issue_comment_is_ignored(pipeline):
    payload = comment_payload(53, "@review", comment_id=1)
    payload["issue"].pop("pull_request")
    response = post_webhook(pipeline.client, "issue_comment", payload, "issue-1")
    assert response.status_code == 200 and response.json()["jobs"] == 0
    assert pipeline.event("issue-1").error_message == "not a pull request"


async def test_secrets_never_reach_comments_reviews_or_errors(pipeline, e2e_report):
    pipeline.open_pr(54, PLANTED_SCENARIOS["hardcoded_secret"])
    pipeline.open_pr(55, PLANTED_SCENARIOS["clean"])
    pipeline.llm.fail_next(400)  # first job fails permanently → error comment + last_error; second succeeds

    await pipeline.drain()

    texts = [c.body for c in pipeline.github.comments]
    texts += [r.full_markdown for r in pipeline.reviews()]
    texts += [j.last_error or "" for j in pipeline.jobs()]
    texts += [e.payload_preview for e in (pipeline.event("e2e-1"), pipeline.event("e2e-2"))]
    texts.append(e2e_report.to_markdown())
    assert len(pipeline.github.comments) == 2
    for text in texts:
        assert GEMINI_TEST_KEY not in text
        assert INSTALLATION_TOKEN not in text
