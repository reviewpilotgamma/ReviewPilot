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
    for rule in ("### Scope Check", "**Unexpected changes:**", "**Described but not found:**"):
        assert rule in prompt
    assert "**No description to compare against.**" in prompt
    assert "never add a finding, change the verdict, or lower the score" in prompt


def test_merge_prompt_owns_described_but_not_found():
    assert "Write one Scope Check for the whole PR" in prompts.MERGE_SYSTEM_PROMPT
    assert 'decide "Described but not\n  found"' in prompts.MERGE_SYSTEM_PROMPT


def test_pr_context_lists_changed_files_only_when_given():
    pr = PullRequest(7, "Title", "Fix typo", "bob", "main", "feat", "open", False, 1, 1, 2)
    assert "Changed files:" not in build_pr_context(pr, "acme", "api", "d")
    context = build_pr_context(pr, "acme", "api", "d", manifest=[("README.md", 1, 1), ("app/config.py", 3, 0)])
    assert "Changed files:\n- README.md (+1/-1)\n- app/config.py (+3/-0)\n\nDiff:" in context


def test_empty_description_is_marked():
    pr = PullRequest(7, "Title", "  ", "bob", "main", "feat", "open", False, 1, 1, 1)
    assert "Description:\n(no description)" in build_pr_context(pr, "acme", "api", "d")


PREVIOUS_MD = (
    "## ReviewPilot Architectural Audit\n\n**Verdict:** x\n\n### Executive Summary\n- old summary\n\n"
    "### Architectural Findings\n- **Critical** · **Hardcoded secret**\n  - **File(s):** `app/config.py`\n\n"
    "### Specific Recommendations\n1. **Move the secret** in `app/config.py`\n\n### What Looks Solid\n- tests\n"
)


def test_previous_review_block_keeps_findings_and_changed_files():
    block = prompts.build_previous_review_block(
        PREVIOUS_MD, head_sha="abcdef123456", verdict="critical", score=3.5, changed_files=[("app/config.py", 2, 1)]
    )
    assert block.startswith("Previous ReviewPilot review of commit abcdef1 (verdict critical, score 3.5/10)")
    assert "UNTRUSTED" in block
    assert "**Hardcoded secret**" in block and "**Move the secret**" in block
    assert "old summary" not in block and "What Looks Solid" not in block
    assert block.endswith("Files changed since the previous review:\n- app/config.py (+2/-1)")


def test_previous_review_block_unknown_history_and_truncation():
    long_md = "### Architectural Findings\n" + "x" * (prompts.MAX_PREVIOUS_REVIEW_CHARS + 100)
    block = prompts.build_previous_review_block(long_md, head_sha=None, verdict="warning", score=6.0, changed_files=None)
    assert "review of an earlier commit" in block
    assert "[... previous review truncated ...]" in block
    assert block.endswith("Files changed since the previous review: unknown.")


def test_pr_context_puts_previous_review_before_diff():
    pr = PullRequest(7, "Title", "Fix", "bob", "main", "feat", "open", False, 1, 1, 1)
    context = build_pr_context(pr, "acme", "api", "d", manifest=[("a.py", 1, 0)], previous="PREVIOUS BLOCK")
    assert context.index("PREVIOUS BLOCK") < context.index("Changed files:") < context.index("Diff:")


def test_merge_content_carries_previous_review():
    pr = PullRequest(7, "Title", "Fix", "bob", "main", "feat", "open", False, 1, 1, 1)
    content = prompts.build_merge_content(pr, "acme", "api", [(1, ["a.py"], "warning", 6.0, "body")], 1, previous="PREV")
    assert content.index("PREV") < content.index("Reviewed in 1 parts")
    assert "PREV" not in prompts.build_merge_content(pr, "acme", "api", [(1, ["a.py"], "warning", 6.0, "body")], 1)


def test_followup_directive_rules():
    directive = prompts.FOLLOWUP_DIRECTIVE
    for rule in ("### Follow-up Status", "**Fixed:**", "**Still open:**", "**New:**", "Never list fixed findings"):
        assert rule in directive
    assert "before Scope Check" in directive
    assert "exactly once" in directive and "Never leave one out." in directive



@pytest.mark.parametrize(
    "bullet",
    [
        "- **Warning** · **Broad exception swallowing**\n  - **File(s):** `a.py`",
        "- **Warning**: Broad exception swallowing\n  - *Affected file(s)*: `a.py`",
        "- **Warning** | Broad exception swallowing | `a.py` | details",
        "- **Warning** Broad exception swallowing — `a.py`: details",
    ],
)
def test_previous_findings_titles_across_formats(bullet):
    md = f"### Architectural Findings\n- **Passed** · **Fine**\n{bullet}\n### Specific Recommendations\n1. x"
    assert prompts.previous_findings(md) == [("warning", "Broad exception swallowing")]


def test_previous_review_block_lists_checklist():
    block = prompts.build_previous_review_block(
        PREVIOUS_MD, head_sha=None, verdict="critical", score=3.5, changed_files=None
    )
    assert (
        "Previous Critical and Warning findings to account for (each exactly once, under Fixed or Still open):\n"
        "1. Hardcoded secret (was critical)\n\nFiles changed since"
    ) in block
