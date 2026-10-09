from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.database import utcnow
from app.models import PRReview


def add_review(
    db, repo="acme/api", number=1, verdict="passed", score=8.5, author="bob", title="Feature", age_days=0
) -> PRReview:
    review = PRReview(
        repo_full_name=repo,
        pr_number=number,
        pr_title=title,
        author=author,
        summary="s",
        full_markdown="## md",
        verdict=verdict,
        score=score,
        lines_reviewed=10,
        trigger="comment",
        created_at=utcnow() - timedelta(days=age_days),
        model="gemini-2.0-flash",
    )
    db.add(review)
    db.commit()
    return review


@pytest.fixture
def seeded(db):
    return [
        add_review(db, number=1, verdict="passed", title="Add cache", age_days=2),
        add_review(db, number=2, verdict="warning", score=6.0, author="carol", title="Refactor auth", age_days=1),
        add_review(db, number=3, verdict="critical", score=3.0, title="100%_done"),
        add_review(db, repo="other/repo", number=4),
    ]


def test_list_is_tenant_scoped_and_sorted(client, login, seeded):
    login()
    data = client.get("/api/v1/reviews").json()
    assert data["total"] == 3
    assert [r["pr_number"] for r in data["items"]] == [3, 2, 1]
    assert data["items"][0]["pr_url"] == "https://github.com/acme/api/pull/3"


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"verdict": "warning"}, [2]),
        ({"author": "CAROL"}, [2]),
        ({"q": "auth"}, [2]),
        ({"q": "100%_"}, [3]),
        ({"q": "%"}, [3]),
        ({"repo": "acme/api", "sort": "created_at"}, [1, 2, 3]),
    ],
)
def test_filters(client, login, seeded, params, expected):
    login()
    assert [r["pr_number"] for r in client.get("/api/v1/reviews", params=params).json()["items"]] == expected


def test_pagination(client, login, seeded):
    login()
    data = client.get("/api/v1/reviews", params={"page": 2, "page_size": 2}).json()
    assert data["total"] == 3 and [r["pr_number"] for r in data["items"]] == [1]


def test_list_and_detail_expose_tokens_used(client, login, db, seeded):
    seeded[1].tokens_used = 12_480
    db.commit()
    login()
    tokens = {r["pr_number"]: r["tokens_used"] for r in client.get("/api/v1/reviews").json()["items"]}
    assert tokens == {1: None, 2: 12_480, 3: None}
    assert client.get(f"/api/v1/reviews/{seeded[1].id}").json()["tokens_used"] == 12_480


def test_filter_by_inaccessible_repo_404(client, login, seeded):
    login()
    assert client.get("/api/v1/reviews", params={"repo": "other/repo"}).status_code == 404


def test_detail_and_cross_tenant_404(client, login, seeded):
    login()
    detail = client.get(f"/api/v1/reviews/{seeded[0].id}").json()
    assert detail["full_markdown"] == "## md" and detail["my_feedback"] is None
    assert client.get(f"/api/v1/reviews/{seeded[3].id}").status_code == 404
    assert client.get("/api/v1/reviews/9999").status_code == 404


def test_feedback_upsert_one_per_user(client, login, seeded):
    login()
    rid = seeded[0].id
    first = client.post(f"/api/v1/reviews/{rid}/feedback", json={"rating": "helpful", "notes": " great "})
    assert first.status_code == 200 and first.json()["notes"] == "great"
    second = client.post(f"/api/v1/reviews/{rid}/feedback", json={"rating": "unhelpful"})
    assert second.json()["id"] == first.json()["id"]

    detail = client.get(f"/api/v1/reviews/{rid}").json()
    assert detail["my_feedback"]["rating"] == "unhelpful"
    assert detail["feedback_counts"] == {"helpful": 0, "unhelpful": 1}
    assert len(client.get(f"/api/v1/reviews/{rid}/feedback").json()) == 1


def test_feedback_validation_and_tenant(client, login, seeded):
    login()
    assert client.post(f"/api/v1/reviews/{seeded[0].id}/feedback", json={"rating": "meh"}).status_code == 422
    assert client.post(f"/api/v1/reviews/{seeded[3].id}/feedback", json={"rating": "helpful"}).status_code == 404


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (None, None),
        ("{not json", None),
        ('{"prompt": "bogus"}', None),
        (
            '{"prompt": "custom", "prompt_updated_at": "2026-10-07T10:00:00+00:00", "instructions_chars": 42,'
            ' "verbosity": "detailed", "security": false, "documents": ["arch.md"], "documents_mode": "cached",'
            ' "requester_note": true}',
            {"prompt": "custom", "documents": ["arch.md"], "documents_mode": "cached", "instructions_chars": 42},
        ),
    ],
)
def test_review_detail_exposes_review_context(client, login, db, stored, expected):
    login()
    review = add_review(db)
    review.review_context = stored
    db.commit()

    context = client.get(f"/api/v1/reviews/{review.id}").json()["review_context"]

    if expected is None:
        assert context is None
    else:
        assert {key: context[key] for key in expected} == expected
