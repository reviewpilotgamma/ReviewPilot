from __future__ import annotations

import itertools

import pytest

from app.services import prompts
from app.services.github_app import PullRequest
from app.services.prompts import RuleSettings, build_pr_context, build_review_system_prompt


@pytest.mark.parametrize(("verbosity", "security"), list(itertools.product(["concise", "detailed"], [True, False])))
def test_rule_directives_injected(verbosity, security):
    rules = RuleSettings(custom_instructions="Strict idempotency keys", verbosity=verbosity, enable_security=security)
    prompt = build_review_system_prompt(rules, "focus on auth")
    assert "Strict idempotency keys" in prompt
    assert prompts.VERBOSITY_DIRECTIVES[verbosity] in prompt
    expected = prompts.SECURITY_ENABLED_DIRECTIVE if security else prompts.SECURITY_DISABLED_DIRECTIVE
    assert expected in prompt
    assert "Requester Note (from the developer who asked for the review): focus on auth" in prompt


def test_placeholders_for_empty_values():
    prompt = build_review_system_prompt(RuleSettings(), None)
    assert prompts.NO_INSTRUCTIONS in prompt
    assert "asked for the review): (none)" in prompt


def test_meta_instruction_present_with_literal_braces():
    prompt = build_review_system_prompt(RuleSettings(), None)
    assert '<!-- reviewpilot-meta: {"score": <number>' in prompt


def test_user_braces_do_not_break_formatting():
    prompt = build_review_system_prompt(RuleSettings(custom_instructions="use {curly} braces"), "{x}")
    assert "use {curly} braces" in prompt


def test_pr_context_contains_metadata_and_truncates_description():
    pr = PullRequest(7, "Title", "d" * 5000, "bob", "main", "feat", "open", False, 10, 2, 3)
    context = build_pr_context(pr, "acme", "api", "diff-body")
    assert "Pull Request: #7 — Title" in context
    assert "Base: main ← Head: feat" in context
    assert "+10 / -2 across 3 files" in context
    assert "[... description truncated ...]" in context
    assert "```diff\ndiff-body\n```" in context


def test_presets_well_formed():
    ids = {p["id"] for p in prompts.RULE_PRESETS}
    assert ids == {"microservices", "security", "performance"}
    assert all(p["instructions"] for p in prompts.RULE_PRESETS)


@pytest.mark.parametrize("prompt", [build_review_system_prompt(RuleSettings(), None), prompts.MERGE_SYSTEM_PROMPT])
def test_output_format_rules(prompt):
    assert prompts.OUTPUT_FORMAT in prompt
    for rule in ("**File(s):**", "**Problem:**", "**Impact:**", "**What it does:**", "Do not use emoji."):
        assert rule in prompt
    assert "Do not cite line numbers." in prompt
