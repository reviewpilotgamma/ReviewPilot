from __future__ import annotations

import json

from app.models import PRReview, ReviewFeedback
from app.services.insights import (
    MAX_NEW,
    build_user_payload_for_tests,
    parse_insight_payload,
    sanitize_llm_output,
)
from tests.conftest import GEMINI_API

GEMINI_URL = f"{GEMINI_API}/models/gemini-2.0-flash:generateContent"
FINDINGS = "### Architectural Findings\n- **Warning** Missing idempotency — `pay.py`: retries are not keyed."


def add_review(db, *, repo="acme/api", number=1, title="Feature", markdown=FINDINGS) -> PRReview:
    review = PRReview(
        repo_full_name=repo,
        pr_number=number,
        pr_title=title,
        author="bob",
        summary="Retries need keys",
        full_markdown=markdown,
        verdict="warning",
        score=6.0,
        lines_reviewed=10,
        trigger="comment",
        model="gemini-2.0-flash",
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def gemini_body(review_ids: list[int]) -> dict:
    theme = {
        "title": "Missing idempotency",
        "severity": "warning",
        "count": len(review_ids),
        "last_seen_review_id": review_ids[-1],
        "example_review_ids": review_ids[:3],
        "evidence": "Retries without keys on the payment path.",
    }
    text = json.dumps(
        {
            "summary_markdown": "## Recurring issues\nIdempotency is the main theme.",
            "themes": [theme],
            "new_this_period": ["Missing idempotency"],
            "still_showing": [],
        }
    )
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


def mock_gemini(mock_http, review_ids: list[int]):
    return mock_http.post(GEMINI_URL).respond(200, json=gemini_body(review_ids))


def test_parse_fenced_and_raw_json():
    raw = '{"summary_markdown": "hi", "themes": []}'
    assert parse_insight_payload(raw)["summary_markdown"] == "hi"
    assert parse_insight_payload(f"```json\n{raw}\n```")["themes"] == []


def test_sanitize_drops_unknown_review_ids():
    summary, themes, _, _ = sanitize_llm_output(
        {
            "summary_markdown": "ok",
            "themes": [
                {
                    "title": "x",
                    "severity": "critical",
                    "count": 2,
                    "last_seen_review_id": 99,
                    "example_review_ids": [1, 99],
                    "evidence": "e",
                },
                {
                    "title": "invented",
                    "severity": "warning",
                    "count": 1,
                    "last_seen_review_id": 99,
                    "example_review_ids": [99],
                    "evidence": "e",
                },
            ],
        },
        valid_ids={1},
    )
    assert summary == "ok"
    assert len(themes) == 1
    assert themes[0].example_review_ids == [1]
    assert themes[0].last_seen_review_id == 1


def test_get_requires_repo_and_scopes(client, login, db):
    add_review(db)
    login()
    assert client.get("/api/v1/insights").status_code == 422
    assert client.get("/api/v1/insights", params={"repo": "other/repo"}).status_code == 404
    data = client.get("/api/v1/insights", params={"repo": "acme/api"}).json()
    assert data["total_reviews"] == 1 and data["pending_count"] == 1 and data["snapshot"] is None


def test_analyze_incremental_then_noop(client, login, db, mock_http):
    first = add_review(db, number=1)
    login()
    route = mock_gemini(mock_http, [first.id])

    created = client.post("/api/v1/insights/analyze", json={"repo": "acme/api"})
    assert created.status_code == 200
    body = created.json()
    assert body["ran_model"] is True
    assert body["snapshot"]["themes"][0]["title"] == "Missing idempotency"
    assert body["pending_count"] == 0
    assert route.call_count == 1

    second = add_review(db, number=2, title="More retries")
    cards, payload = build_user_payload_for_tests(db, "acme/api")
    assert [c["id"] for c in cards] == [second.id]
    previous = json.loads(payload)["previous"]
    assert previous["themes"][0]["title"] == "Missing idempotency"
    assert json.loads(payload)["new_reviews"][0]["pr_title"] == "More retries"

    mock_gemini(mock_http, [first.id, second.id])
    again = client.post("/api/v1/insights/analyze", json={"repo": "acme/api"}).json()
    assert again["ran_model"] is True
    assert again["snapshot"]["included_count"] == 2
    assert again["snapshot"]["pending_analyzed_count"] == 1

    noop = client.post("/api/v1/insights/analyze", json={"repo": "acme/api"}).json()
    assert noop["ran_model"] is False
    assert noop["snapshot"]["id"] == again["snapshot"]["id"]


def test_rebuild_ignores_snapshot_in_payload(client, login, db, mock_http):
    add_review(db, number=1)
    add_review(db, number=2)
    login()
    mock_gemini(mock_http, [1])
    client.post("/api/v1/insights/analyze", json={"repo": "acme/api"})
    _cards, payload = build_user_payload_for_tests(db, "acme/api", rebuild=True)
    data = json.loads(payload)
    assert data["rebuild"] is True
    assert data["previous"] is None
    assert {c["pr_number"] for c in data["new_reviews"]} == {1, 2}


def test_unhelpful_reviews_are_not_cards(db):
    review = add_review(db)
    db.add(ReviewFeedback(review_id=review.id, user_id=None, rating="unhelpful", notes=""))
    db.commit()
    cards, _payload = build_user_payload_for_tests(db, "acme/api")
    assert cards == []


def test_no_reviews_is_422(client, login):
    login()
    assert client.post("/api/v1/insights/analyze", json={"repo": "acme/api"}).status_code == 422


def test_unreadable_model_output_is_502(client, login, db, mock_http):
    add_review(db)
    login()
    mock_http.post(GEMINI_URL).respond(
        200, json={"candidates": [{"content": {"parts": [{"text": "not json"}]}, "finishReason": "STOP"}]}
    )
    assert client.post("/api/v1/insights/analyze", json={"repo": "acme/api"}).status_code == 502
    assert client.get("/api/v1/insights", params={"repo": "acme/api"}).json()["snapshot"] is None


def test_requires_sign_in(client):
    assert client.get("/api/v1/insights", params={"repo": "acme/api"}).status_code == 401


def test_pending_cap_flag(client, login, db):
    login()
    for n in range(MAX_NEW + 2):
        add_review(db, number=n + 1, title=f"PR {n}")
    data = client.get("/api/v1/insights", params={"repo": "acme/api"}).json()
    assert data["pending_count"] == MAX_NEW + 2
    assert data["pending_capped"] is True


def test_invalid_repo_payload(client, login):
    login()
    assert client.post("/api/v1/insights/analyze", json={"repo": "not-a-repo"}).status_code == 422
