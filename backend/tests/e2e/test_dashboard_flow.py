"""Reviews produced by the pipeline are what the dashboard APIs serve: history, detail, events, feedback, metrics."""

from __future__ import annotations

from app.core.database import utcnow
from tests.e2e.diffs import PLANTED_SCENARIOS


async def run_two_reviews(pipeline) -> tuple[str, str]:
    critical = pipeline.open_pr(40, PLANTED_SCENARIOS["hardcoded_secret"])
    passed = pipeline.open_pr(41, PLANTED_SCENARIOS["clean"])
    assert await pipeline.drain() == 2
    return critical, passed


async def test_history_detail_and_events_match_pipeline_output(pipeline, login):
    login()
    critical_delivery, _ = await run_two_reviews(pipeline)
    client = pipeline.client

    page = client.get("/api/v1/reviews").json()
    assert page["total"] == 2
    by_pr = {item["pr_number"]: item for item in page["items"]}
    assert by_pr[40]["verdict"] == "critical" and by_pr[41]["verdict"] == "passed"
    assert by_pr[40]["pr_title"] == PLANTED_SCENARIOS["hardcoded_secret"].title
    assert by_pr[40]["trigger"] == "auto"

    filtered = client.get("/api/v1/reviews", params={"verdict": "critical"}).json()
    assert [item["pr_number"] for item in filtered["items"]] == [40]

    detail = client.get(f"/api/v1/reviews/{by_pr[40]['id']}").json()
    assert detail["full_markdown"] == pipeline.github.comments_for(40)[0]
    assert detail["diff_truncated"] is False
    assert detail["model"] == "gemini-2.0-flash"

    events = client.get("/api/v1/webhooks/events").json()
    assert len(events) == 2
    event = next(e for e in events if e["delivery_id"] == critical_delivery)
    assert event["status"] == "processed"
    assert [(j["kind"], j["status"]) for j in event["jobs"]] == [("review", "succeeded")]


async def test_feedback_updates_counts_and_metrics(pipeline, login):
    login("alice", github_id=1001)
    await run_two_reviews(pipeline)
    client = pipeline.client
    ids = {item["pr_number"]: item["id"] for item in client.get("/api/v1/reviews").json()["items"]}

    empty = client.get("/api/v1/metrics/summary").json()
    assert empty["total_reviews"] == 2
    reviewed = client.get("/api/v1/reviews").json()["items"]
    assert empty["lines_reviewed"] == sum(i["lines_reviewed"] for i in reviewed) > 0
    assert empty["verdict_counts"] == {"passed": 1, "warning": 0, "critical": 1}
    assert empty["pass_rate"] == 50.0
    assert empty["avg_score"] == round((3.0 + 9.0) / 2, 1)

    assert client.post(f"/api/v1/reviews/{ids[40]}/feedback", json={"rating": "helpful"}).status_code == 200
    login("carol", github_id=1002)
    response = client.post(f"/api/v1/reviews/{ids[40]}/feedback", json={"rating": "unhelpful", "notes": "noisy"})
    assert response.status_code == 200
    assert client.post(f"/api/v1/reviews/{ids[41]}/feedback", json={"rating": "helpful"}).status_code == 200

    item = next(i for i in client.get("/api/v1/reviews").json()["items"] if i["id"] == ids[40])
    assert item["feedback_counts"] == {"helpful": 1, "unhelpful": 1}
    assert len(client.get(f"/api/v1/reviews/{ids[40]}/feedback").json()) == 2

    summary = client.get("/api/v1/metrics/summary").json()
    assert {r["pr_number"] for r in summary["recent"]} == {40, 41}

    trend = client.get("/api/v1/metrics/trend", params={"days": 7}).json()
    assert len(trend) == 7
    # Both reviews ran just now, so they land in one (UTC) day bucket.
    assert trend[-1]["reviews"] == 2 and sum(p["reviews"] for p in trend) == 2
    assert trend[-1]["date"] == utcnow().date().isoformat()
