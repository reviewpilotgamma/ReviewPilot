"""Review, welcome and plan flows from signed webhook to posted comment and stored review."""

from __future__ import annotations

import pytest

from app.core.config import reload_settings
from app.services.prompts import SECURITY_DISABLED_DIRECTIVE, VERBOSITY_DIRECTIVES
from app.services.replies import render_reply
from app.services.reviewer import BANNER, COMMENT_TRUNCATION_NOTE, FOOTER, PLAN_BANNER
from tests.e2e.diffs import (
    EDGE_SCENARIOS,
    PLANTED_SCENARIOS,
    UNICODE_MARKER,
    review_markdown,
    scenario_for_tier,
)

VERDICT_LABEL_TEXT = {"passed": "Passed", "warning": "Warning", "critical": "Critical Risk"}


def set_rules(client, **rules) -> None:
    body = {"custom_instructions": "", "verbosity": "concise", "review_mode": "auto", "enable_security": True, **rules}
    response = client.put("/api/v1/rules/acme/api", json=body)
    assert response.status_code == 200, response.text


async def test_auto_mode_pr_opened_posts_review(pipeline):
    scenario = PLANTED_SCENARIOS["sql_injection"]
    delivery = pipeline.open_pr(7, scenario)

    assert await pipeline.drain() == 1

    comments = pipeline.github.comments_for(7)
    assert len(comments) == 1 and comments[0].startswith(BANNER)
    [review] = pipeline.reviews()
    assert (review.repo_full_name, review.pr_number, review.trigger) == ("acme/api", 7, "auto")
    assert review.requester is None
    assert review.full_markdown == comments[0]
    assert review.github_comment_id == pipeline.github.comments[0].id
    [job] = pipeline.jobs(delivery)
    assert (job.kind, job.status, job.review_id) == ("review", "succeeded", review.id)
    assert pipeline.event(delivery).status == "processed"
    pipeline.record(scenario, delivery)


async def test_on_demand_mode_welcome_then_review_with_note(pipeline, login):
    login()
    set_rules(pipeline.client, review_mode="on_demand")
    scenario = PLANTED_SCENARIOS["no_timeout_retry"]

    opened = pipeline.open_pr(8, scenario)
    await pipeline.drain()
    assert [j.kind for j in pipeline.jobs(opened)] == ["welcome"]
    assert pipeline.github.comments_for(8) == [render_reply("welcome", author="bob", app_name="ReviewPilot")]
    assert pipeline.reviews() == []

    commented = pipeline.comment(8, "Thanks!\n@review focus on retries\n")
    await pipeline.drain()

    assert pipeline.github.reactions == [("acme", "api", pipeline.last_comment_id, "eyes")]
    [review] = pipeline.reviews()
    assert (review.trigger, review.requester) == ("comment", "alice")
    comment = pipeline.github.comments_for(8)[-1]
    assert "_Requested by @alice: “focus on retries”_" in comment
    assert "Requester Note (from the developer who asked for the review): focus on retries" in (
        pipeline.llm.system_prompt(pipeline.llm.requests[-1])
    )
    pipeline.record(scenario, commented)


async def test_plan_trigger_posts_plan(pipeline):
    pipeline.llm.respond_with("- [ ] Add a migration\n- [ ] Add rollback notes")
    pipeline.github.add_pr(9, PLANTED_SCENARIOS["breaking_api"])
    delivery = pipeline.comment(9, "@bot plan")

    await pipeline.drain()

    assert [j.kind for j in pipeline.jobs(delivery)] == ["plan"]
    [body] = pipeline.github.comments_for(9)
    assert body.startswith(PLAN_BANNER) and "- [ ] Add a migration" in body
    assert pipeline.reviews() == []


async def test_plan_falls_back_to_canned_on_permanent_error(pipeline):
    pipeline.llm.fail_next(400)
    pipeline.github.add_pr(9, PLANTED_SCENARIOS["breaking_api"])
    delivery = pipeline.comment(9, "@bot plan")

    await pipeline.drain()

    assert pipeline.github.comments_for(9) == [render_reply("plan")]
    assert pipeline.jobs(delivery)[0].status == "succeeded"


async def test_review_and_plan_in_one_comment_creates_two_jobs(pipeline):
    pipeline.github.add_pr(10, PLANTED_SCENARIOS["clean"])
    delivery = pipeline.comment(10, "@review\n@bot plan")

    assert await pipeline.drain() == 2

    assert sorted(j.kind for j in pipeline.jobs(delivery)) == ["plan", "review"]
    assert all(j.status == "succeeded" for j in pipeline.jobs(delivery))
    bodies = pipeline.github.comments_for(10)
    assert sum(b.startswith(BANNER) for b in bodies) == 1
    assert sum(b.startswith(PLAN_BANNER) for b in bodies) == 1
    assert pipeline.event(delivery).status == "processed"


async def test_rules_reflected_in_prompt(pipeline, login):
    login()
    set_rules(
        pipeline.client,
        custom_instructions="- Payments must always go through the billing SDK.",
        verbosity="detailed",
        enable_security=False,
    )
    pipeline.open_pr(11, PLANTED_SCENARIOS["no_timeout_retry"])

    await pipeline.drain()

    system = pipeline.llm.system_prompt(pipeline.llm.requests[-1])
    assert "- Payments must always go through the billing SDK." in system
    assert VERBOSITY_DIRECTIVES["detailed"] in system
    assert SECURITY_DISABLED_DIRECTIVE in system


@pytest.mark.parametrize("name", list(PLANTED_SCENARIOS))
async def test_planted_scenarios_store_expected_verdict(pipeline, name):
    scenario = PLANTED_SCENARIOS[name]
    delivery = pipeline.open_pr(20, scenario)

    await pipeline.drain()

    [review] = pipeline.reviews()
    assert review.verdict == scenario.expected_verdict
    assert "**Verdict:** " in review.full_markdown
    assert VERDICT_LABEL_TEXT[scenario.expected_verdict] in review.full_markdown
    # The exact diff reached the model inside the PR context.
    assert scenario.diff.strip() in pipeline.llm.user_content(pipeline.llm.requests[-1])
    pipeline.record(scenario, delivery)


@pytest.mark.parametrize("name", ["empty", "whitespace"])
async def test_empty_diff_replies_without_review(pipeline, name):
    pipeline.open_pr(12, EDGE_SCENARIOS[name])

    await pipeline.drain()

    assert pipeline.github.comments_for(12) == [render_reply("empty_diff")]
    assert pipeline.reviews() == []
    assert pipeline.llm.generate_calls == 0


async def test_closed_pr_is_skipped(pipeline):
    delivery = pipeline.open_pr(13, PLANTED_SCENARIOS["clean"], state="closed")

    await pipeline.drain()

    assert pipeline.github.comments == []
    assert pipeline.reviews() == []
    assert pipeline.llm.generate_calls == 0
    assert pipeline.jobs(delivery)[0].status == "succeeded"


async def test_truncation_with_max_diff_chars(pipeline, monkeypatch):
    monkeypatch.setenv("MAX_DIFF_CHARS", "2000")
    reload_settings()
    scenario = scenario_for_tier("medium")
    delivery = pipeline.open_pr(14, scenario)

    await pipeline.drain()

    [review] = pipeline.reviews()
    assert review.diff_truncated
    assert "exceeded 2,000 characters" in pipeline.github.comments_for(14)[0]
    user_content = pipeline.llm.user_content(pipeline.llm.requests[-1])
    assert "DIFF TRUNCATED" in user_content
    assert len(user_content) < 2000 + 2_000  # diff cap + PR header/description
    pipeline.record(scenario, delivery, max_diff_chars=2000)


async def test_unlimited_diff_is_sent_whole(pipeline):
    scenario = scenario_for_tier("large")
    pipeline.open_pr(15, scenario)

    await pipeline.drain()

    [review] = pipeline.reviews()
    assert not review.diff_truncated
    user_content = pipeline.llm.user_content(pipeline.llm.requests[-1])
    assert scenario.diff.rstrip().splitlines()[-1] in user_content
    assert "DIFF TRUNCATED" not in user_content


async def test_long_llm_output_is_truncated_to_comment_limit(pipeline):
    long_text = "x " * 40_000
    pipeline.llm.respond_with(
        review_markdown("Huge review.", [("Warning", "Verbose", "a.py", long_text)], verdict="warning")
    )
    pipeline.open_pr(16, PLANTED_SCENARIOS["no_timeout_retry"])

    await pipeline.drain()

    [body] = pipeline.github.comments_for(16)
    assert len(body) <= reload_settings().MAX_COMMENT_CHARS
    assert COMMENT_TRUNCATION_NOTE.strip() in body
    assert body.endswith(FOOTER)


async def test_parser_fallback_without_meta_line(pipeline):
    pipeline.llm.respond_with(
        review_markdown("No meta.", [("Warning", "Missing index", "db.py", "Add an index.")], verdict="warning",
                        with_meta=False)
    )
    pipeline.open_pr(17, PLANTED_SCENARIOS["clean"])

    await pipeline.drain()

    [review] = pipeline.reviews()
    assert review.verdict == "warning"
    assert 5.0 <= review.score <= 7.9


@pytest.mark.parametrize("name", ["binary", "rename_only", "unicode"])
async def test_edge_diffs_complete(pipeline, name):
    scenario = EDGE_SCENARIOS[name]
    delivery = pipeline.open_pr(18, scenario)

    await pipeline.drain()

    [review] = pipeline.reviews()
    assert review.verdict == "passed"
    assert pipeline.jobs(delivery)[0].status == "succeeded"
    if name == "unicode":
        assert UNICODE_MARKER in review.full_markdown
        assert UNICODE_MARKER in pipeline.github.comments_for(18)[0]
        assert "こんにちは" in pipeline.llm.user_content(pipeline.llm.requests[-1])
    pipeline.record(scenario, delivery)
