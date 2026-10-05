from __future__ import annotations

import copy

import pytest

from app.services import dispatcher
from app.services.rules import upsert_rule
from tests.conftest import load_fixture


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("@review", ""),
        ("@review focus on auth boundaries", "focus on auth boundaries"),
        ("@Review  Check Idempotency", "Check Idempotency"),
        ("please\n@review async lifecycles\nthanks", "async lifecycles"),
        ("@review first\n@review second", "first"),
    ],
)
def test_extract_review_note(body, expected):
    assert dispatcher.extract_review_note(body) == expected


@pytest.mark.parametrize("body", ["@reviewer please look", "mail me at a@review.com", "no trigger", "@@review"])
def test_review_trigger_not_matched(body):
    assert dispatcher.extract_review_note(body) is None


def test_note_is_capped():
    assert len(dispatcher.extract_review_note("@review " + "x" * 2000)) == dispatcher.MAX_NOTE_CHARS


@pytest.mark.parametrize("body", ["@bot plan", "@BOT   Plan please", "hey\n@bot plan"])
def test_plan_trigger(body):
    assert dispatcher.has_plan_trigger(body)


def test_plan_trigger_not_matched():
    assert not dispatcher.has_plan_trigger("@bot planning")


@pytest.mark.parametrize(
    "payload",
    [
        {"sender": {"type": "Bot", "login": "x"}},
        {"sender": {"type": "User", "login": "x"}, "comment": {"user": {"type": "Bot"}}},
        {"sender": {"type": "User", "login": "reviewpilot[bot]"}},
        {"sender": {"type": "User", "login": "x"}, "comment": {"user": {"login": "ci[bot]"}}},
    ],
)
def test_bot_events_detected(payload):
    assert dispatcher.is_bot_event(payload)


def test_human_event_not_bot():
    assert not dispatcher.is_bot_event(load_fixture("issue_comment_review.json"))


def test_pr_opened_auto_mode_creates_review(db):
    result = dispatcher.plan_jobs(db, "pull_request", load_fixture("pull_request_opened.json"))
    assert [j.kind for j in result.jobs] == ["review"]
    job = result.jobs[0].payload
    assert job["trigger"] == "auto" and job["pr_number"] == 7 and job["installation_id"] == 99
    assert (job["owner"], job["repo"]) == ("Acme", "API")


def test_pr_opened_on_demand_mode_creates_welcome(db):
    upsert_rule(
        db,
        "acme/api",
        custom_instructions="",
        verbosity="concise",
        review_mode="on_demand",
        enable_security=True,
        user_id=None,
    )
    result = dispatcher.plan_jobs(db, "pull_request", load_fixture("pull_request_opened.json"))
    assert [j.kind for j in result.jobs] == ["welcome"]
    assert result.jobs[0].payload["author"] == "bob"


def test_comment_review_job(db):
    result = dispatcher.plan_jobs(db, "issue_comment", load_fixture("issue_comment_review.json"))
    assert [j.kind for j in result.jobs] == ["review"]
    payload = result.jobs[0].payload
    assert payload["requester"] == "alice"
    assert payload["requester_note"] == "focus on auth boundaries"
    assert payload["comment_id"] == 555
    assert payload["trigger"] == "comment"


def test_comment_review_runs_even_in_on_demand_mode(db):
    upsert_rule(
        db,
        "acme/api",
        custom_instructions="",
        verbosity="concise",
        review_mode="on_demand",
        enable_security=True,
        user_id=None,
    )
    result = dispatcher.plan_jobs(db, "issue_comment", load_fixture("issue_comment_review.json"))
    assert [j.kind for j in result.jobs] == ["review"]


def test_both_triggers_create_review_then_plan(db):
    payload = load_fixture("issue_comment_review.json")
    payload["comment"]["body"] = "@review security\n@bot plan"
    result = dispatcher.plan_jobs(db, "issue_comment", payload)
    assert [j.kind for j in result.jobs] == ["review", "plan"]


def test_comment_on_plain_issue_ignored(db):
    payload = copy.deepcopy(load_fixture("issue_comment_review.json"))
    del payload["issue"]["pull_request"]
    result = dispatcher.plan_jobs(db, "issue_comment", payload)
    assert result.jobs == [] and result.ignore_reason == "not a pull request"


def test_comment_without_trigger_ignored(db):
    payload = load_fixture("issue_comment_review.json")
    payload["comment"]["body"] = "nice work"
    assert dispatcher.plan_jobs(db, "issue_comment", payload).ignore_reason == "no trigger"


def test_installation_event_flags_change(db):
    result = dispatcher.plan_jobs(db, "installation", {"action": "created"})
    assert result.installation_changed and not result.jobs


def test_unhandled_event(db):
    assert dispatcher.plan_jobs(db, "push", {}).ignore_reason == "unhandled event"


def test_preview_is_compact():
    preview = dispatcher.build_preview("issue_comment", load_fixture("issue_comment_review.json"))
    assert '"pr_number": 7' in preview and "comment_excerpt" in preview
    assert len(preview) <= dispatcher.MAX_PREVIEW_CHARS
