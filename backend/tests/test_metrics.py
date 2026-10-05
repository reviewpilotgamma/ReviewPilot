from __future__ import annotations

from app.models import ReviewFeedback
from app.services import metrics
from tests.conftest import make_user
from tests.test_reviews_api import add_review


def test_summary_aggregates(db):
    user = make_user(db)
    a = add_review(db, verdict="passed", score=9.0)
    add_review(db, verdict="warning", score=6.0)
    add_review(db, verdict="critical", score=3.0)
    add_review(db, verdict="passed", score=8.0)
    add_review(db, repo="other/repo", score=1.0)
    add_review(db, verdict="passed", score=10.0, age_days=60)
    db.add_all([ReviewFeedback(review_id=a.id, user_id=user.id, rating="helpful")])
    db.commit()

    result = metrics.summary(db, ["acme/api"], days=30)
    assert result.total_reviews == 4
    assert result.avg_score == 6.5
    assert result.pass_rate == 50.0
    assert result.helpful_rate == 100.0
    assert result.verdict_counts == {"passed": 2, "warning": 1, "critical": 1}
    assert len(result.recent) == 4


def test_summary_empty(db):
    result = metrics.summary(db, ["acme/api"], days=30)
    assert result.total_reviews == 0
    assert result.avg_score is None and result.pass_rate is None and result.helpful_rate is None
    assert metrics.summary(db, [], days=30).recent == []


def test_trend_fills_missing_days(db):
    add_review(db, score=8.0)
    add_review(db, score=6.0)
    add_review(db, score=4.0, age_days=2)
    points = metrics.trend(db, ["acme/api"], days=7)
    assert len(points) == 7
    assert (points[-1].reviews, points[-1].avg_score) == (2, 7.0)
    assert points[-3].reviews == 1
    assert points[0].reviews == 0 and points[0].avg_score is None


def test_metrics_api(client, login, db):
    login()
    add_review(db, score=7.0, verdict="warning")
    data = client.get("/api/v1/metrics/summary", params={"days": 7}).json()
    assert data["total_reviews"] == 1 and data["pass_rate"] == 0.0
    assert client.get("/api/v1/metrics/summary", params={"days": 0}).status_code == 422
    assert client.get("/api/v1/metrics/summary", params={"repo": "other/repo"}).status_code == 404
    assert len(client.get("/api/v1/metrics/trend", params={"days": 5}).json()) == 5
