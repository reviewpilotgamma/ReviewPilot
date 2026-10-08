"""Insight service edge cases: lenient JSON parsing, theme sanitizing and analyze() failure paths."""

from __future__ import annotations

import json

import pytest

from app.models import ReviewFeedback
from app.services import insights
from app.services.errors import GeminiPermanentError
from app.services.insights import InsightParseError, NoUsableReviews, parse_insight_payload, sanitize_llm_output
from tests.test_insights import GEMINI_URL, add_review, mock_gemini


def _model_says(mock_http, text: str):
    return mock_http.post(GEMINI_URL).respond(
        200, json={"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}
    )


def test_parse_finds_json_inside_prose():
    assert parse_insight_payload('Here you go: {"summary_markdown": "hi"} Thanks!') == {"summary_markdown": "hi"}


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("no json at all", "no JSON object"),
        ("prefix {not: valid} suffix", "invalid JSON"),
        ("[1, 2, 3]", "JSON root must be an object"),
    ],
)
def test_parse_rejects_unusable_output(text, error):
    with pytest.raises(InsightParseError, match=error):
        parse_insight_payload(text)


def test_sanitize_skips_malformed_themes_and_blank_names():
    theme = {"title": "Keys", "severity": "warning", "count": 2, "example_review_ids": ["3", "x", None, 99]}
    summary, themes, new_names, still = sanitize_llm_output(
        {
            "summary_markdown": "  ok  ",
            "themes": [
                "not a theme",
                theme,
                {**theme, "title": "No valid examples", "example_review_ids": [99]},
                {**theme, "title": "Bad severity", "severity": "catastrophic"},
            ],
            "new_this_period": ["Keys", "  ", ""],
            "still_showing": [None, "Logging"],
        },
        valid_ids={3},
    )
    assert summary == "ok"
    assert [(t.title, t.example_review_ids, t.last_seen_review_id) for t in themes] == [("Keys", [3], 3)]
    assert new_names == ["Keys"]
    assert still == ["None", "Logging"]


async def test_analyze_needs_usable_reviews(db):
    with pytest.raises(NoUsableReviews, match="No reviews to analyze"):
        await insights.analyze(db, "acme/api", "alice")

    review = add_review(db)
    db.add(ReviewFeedback(review_id=review.id, user_id=None, rating="unhelpful", notes=""))
    db.commit()
    with pytest.raises(NoUsableReviews, match="No usable reviews"):
        await insights.analyze(db, "acme/api", "alice")


async def test_analyze_wraps_malformed_theme_lists(db, mock_http):
    add_review(db)
    _model_says(mock_http, json.dumps({"summary_markdown": "s", "themes": 5}))
    with pytest.raises(InsightParseError):
        await insights.analyze(db, "acme/api", "alice")


async def test_analyze_rejects_empty_insights(db, mock_http):
    add_review(db)
    _model_says(mock_http, json.dumps({"summary_markdown": "", "themes": []}))
    with pytest.raises(GeminiPermanentError, match="no insight content"):
        await insights.analyze(db, "acme/api", "alice")


async def test_rebuild_keeps_the_larger_included_count(db, mock_http):
    first = add_review(db, number=1)
    second = add_review(db, number=2)
    mock_gemini(mock_http, [first.id, second.id])

    state = await insights.analyze(db, "acme/api", "alice")
    assert state.ran_model is True
    assert state.snapshot.included_count == 2

    # Nothing new: no model call, same snapshot.
    again = await insights.analyze(db, "acme/api", "alice")
    assert again.ran_model is False
    assert again.snapshot.id == state.snapshot.id

    rebuilt = await insights.analyze(db, "acme/api", "bob", rebuild=True)
    assert rebuilt.ran_model is True
    assert rebuilt.snapshot.id != state.snapshot.id
    assert rebuilt.snapshot.through_review_id == second.id
    assert rebuilt.snapshot.included_count == 2
    assert rebuilt.snapshot.created_by == "bob"
