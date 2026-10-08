from __future__ import annotations

import json

from sqlalchemy import select

from app.models import Job, WebhookEvent
from tests.conftest import load_fixture, post_webhook, sign


def _events(db):
    return db.scalars(select(WebhookEvent).order_by(WebhookEvent.id)).all()


def test_invalid_signature_rejected_without_db_write(client, db):
    response = client.post(
        "/api/v1/webhooks/github",
        content=b"{}",
        headers={"X-Hub-Signature-256": "sha256=bad", "X-GitHub-Event": "ping"},
    )
    assert response.status_code == 401
    assert _events(db) == []


def test_missing_signature_rejected(client):
    assert client.post("/api/v1/webhooks/github", content=b"{}").status_code == 401


def test_invalid_json_rejected(client):
    body = b"not json"
    response = client.post("/api/v1/webhooks/github", content=body, headers={"X-Hub-Signature-256": sign(body)})
    assert response.status_code == 400


def test_ping_processed(client, db):
    response = post_webhook(client, "ping", {"zen": "hi"})
    assert response.status_code == 200
    assert _events(db)[0].status == "processed"


def test_pr_opened_enqueues_review_atomically(client, db):
    response = post_webhook(client, "pull_request", load_fixture("pull_request_opened.json"))
    assert response.json() == {"status": "ok", "jobs": 1}
    event = _events(db)[0]
    assert event.status == "queued" and event.repo == "acme/api" and event.sender == "bob"
    job = db.scalars(select(Job)).one()
    assert job.kind == "review" and job.status == "queued" and job.event_id == event.id
    assert json.loads(job.payload)["pr_number"] == 7


def test_duplicate_delivery_not_reprocessed(client, db):
    payload = load_fixture("pull_request_opened.json")
    post_webhook(client, "pull_request", payload, delivery="same")
    response = post_webhook(client, "pull_request", payload, delivery="same")
    assert response.json()["status"] == "duplicate"
    assert len(_events(db)) == 1
    assert len(db.scalars(select(Job)).all()) == 1


def test_bot_sender_ignored(client, db):
    payload = load_fixture("issue_comment_review.json")
    payload["sender"] = {"login": "reviewpilot[bot]", "type": "Bot"}
    post_webhook(client, "issue_comment", payload)
    event = _events(db)[0]
    assert event.status == "ignored" and event.error_message == "bot sender"
    assert db.scalars(select(Job)).all() == []


def test_non_trigger_comment_ignored_with_reason(client, db):
    payload = load_fixture("issue_comment_review.json")
    payload["comment"]["body"] = "lgtm"
    post_webhook(client, "issue_comment", payload)
    assert _events(db)[0].error_message == "no trigger"


def test_legacy_webhook_alias(client):
    body = json.dumps({"zen": "x"}).encode()
    response = client.post(
        "/webhook", content=body, headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "ping"}
    )
    assert response.status_code == 200


def test_events_endpoint_is_tenant_scoped(client, db, login):
    post_webhook(client, "pull_request", load_fixture("pull_request_opened.json"), delivery="a")
    other = load_fixture("pull_request_opened.json")
    other["repository"]["full_name"] = "other/repo"
    post_webhook(client, "pull_request", other, delivery="b")

    login(repos=("acme/api",))
    response = client.get("/api/v1/webhooks/events")
    assert response.status_code == 200
    items = response.json()
    assert [e["repo"] for e in items] == ["acme/api"]
    assert items[0]["jobs"][0]["kind"] == "review"

    assert client.get("/api/v1/webhooks/events", params={"repo": "other/repo"}).status_code == 404


def test_events_require_auth(client):
    assert client.get("/api/v1/webhooks/events").status_code == 401


def test_events_hide_bot_sender_by_default(client, db, login):
    post_webhook(client, "pull_request", load_fixture("pull_request_opened.json"), delivery="pr")
    bot = load_fixture("issue_comment_review.json")
    bot["sender"] = {"login": "reviewpilot[bot]", "type": "Bot"}
    post_webhook(client, "issue_comment", bot, delivery="bot")
    human = load_fixture("issue_comment_review.json")
    human["comment"]["body"] = "lgtm"
    post_webhook(client, "issue_comment", human, delivery="human")

    login(repos=("acme/api",))
    default = client.get("/api/v1/webhooks/events").json()
    assert [e["delivery_id"] for e in default] == ["human", "pr"]
    assert default[0]["error_message"] == "no trigger"
    assert default[1]["error_message"] is None

    everything = client.get("/api/v1/webhooks/events", params={"include_bot": "true"}).json()
    assert [e["delivery_id"] for e in everything] == ["human", "bot", "pr"]

    ignored = client.get("/api/v1/webhooks/events", params={"status": "ignored"}).json()
    assert [e["delivery_id"] for e in ignored] == ["human"]


def test_non_object_json_rejected(client, db):
    response = post_webhook(client, "ping", [1, 2, 3])  # type: ignore[arg-type]
    assert response.status_code == 400
    assert db.query(WebhookEvent).count() == 0


def test_installation_events_refresh_repository_access(client, monkeypatch):
    from app.api import webhooks

    cleared = []
    monkeypatch.setattr(webhooks.access, "clear_cache", lambda: cleared.append(True))
    response = post_webhook(client, "installation", {"action": "created", "installation": {"id": 99}})
    assert response.json() == {"status": "ok", "jobs": 0}
    assert cleared == [True]


def test_events_filter_by_repo_and_page_with_before_id(client, db, login):
    for delivery in ("one", "two", "three"):
        post_webhook(client, "pull_request", load_fixture("pull_request_opened.json"), delivery=delivery)

    login(repos=("acme/api", "acme/web"))
    scoped = client.get("/api/v1/webhooks/events", params={"repo": "ACME/API"}).json()
    assert [e["delivery_id"] for e in scoped] == ["three", "two", "one"]

    older = client.get("/api/v1/webhooks/events", params={"before_id": scoped[0]["id"], "limit": 1}).json()
    assert [e["delivery_id"] for e in older] == ["two"]


def test_admins_also_see_events_without_a_repository(client, db, login):
    post_webhook(client, "ping", {"zen": "hi"}, delivery="ping")
    post_webhook(client, "pull_request", load_fixture("pull_request_opened.json"), delivery="pr")

    login("alice", repos=("acme/api",))
    assert [e["delivery_id"] for e in client.get("/api/v1/webhooks/events").json()] == ["pr"]

    login("admin-user", repos=("acme/api",), github_id=2002)
    assert [e["delivery_id"] for e in client.get("/api/v1/webhooks/events").json()] == ["pr", "ping"]
    # An explicit repo filter still excludes repository-less events.
    assert [e["delivery_id"] for e in client.get("/api/v1/webhooks/events", params={"repo": "acme/api"}).json()] == [
        "pr"
    ]
