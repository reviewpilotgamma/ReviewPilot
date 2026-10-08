"""Golden prompt: token rendering, default regression, validation, stored override."""

from __future__ import annotations

import itertools

import pytest

from app.services import golden_prompt as gp
from app.services.prompts import (
    DEFAULT_REVIEW_TEMPLATE,
    REVIEW_SYSTEM_TEMPLATE,
    RuleSettings,
    build_review_system_prompt,
    render_template,
    review_slot_values,
)

VALID = "Review it.\nRules:\n{{custom_instructions}}\n<!-- reviewpilot-meta: {\"score\": 1} -->"


@pytest.mark.parametrize(("verbosity", "security"), list(itertools.product(["concise", "detailed"], [True, False])))
def test_default_template_renders_exactly_like_before(verbosity, security):
    rules = RuleSettings(custom_instructions="Use {braces} and {{double}}", verbosity=verbosity, enable_security=security)
    values = review_slot_values(rules, "focus {x}")
    assert build_review_system_prompt(rules, "focus {x}") == REVIEW_SYSTEM_TEMPLATE.format(**values)


def test_literal_braces_and_repeated_tokens():
    template = 'JSON {"a": 1} {single} {{custom_instructions}} / {{ custom_instructions }}'
    out = render_template(template, {"custom_instructions": "R"})
    assert out == 'JSON {"a": 1} {single} R / R'


def test_values_are_not_rescanned():
    assert render_template("{{custom_instructions}}", {"custom_instructions": "{{requester_note}}"}) == (
        "{{requester_note}}"
    )


def test_segments_split_text_and_known_slots():
    segs = gp.segments("A {{custom_instructions}} B {{unknown}} C")
    assert segs == [
        {"type": "text", "text": "A "},
        {"type": "slot", "name": "custom_instructions"},
        {"type": "text", "text": " B {{unknown}} C"},
    ]
    names = [s["name"] for s in gp.segments(DEFAULT_REVIEW_TEMPLATE) if s["type"] == "slot"]
    assert names == ["custom_instructions", "verbosity_directive", "security_directive", "requester_note"]


def test_default_template_is_valid():
    assert gp.validate_template(DEFAULT_REVIEW_TEMPLATE) == ([], [])


@pytest.mark.parametrize(
    ("template", "fragment"),
    [
        ("   ", "cannot be empty"),
        ("No slot here. reviewpilot-meta", "Missing {{custom_instructions}}"),
        ("{{custom_instructions}} only", "reviewpilot-meta"),
        ("{{custom_instructions}} {{tone}} reviewpilot-meta", "Unknown placeholder(s): {{tone}}"),
        ("{{custom_instructions}} reviewpilot-meta " + "x" * 20_000, "longer than 20,000"),
    ],
)
def test_invalid_templates(template, fragment):
    errors, _ = gp.validate_template(template)
    assert any(fragment in e for e in errors), errors


def test_missing_optional_slots_only_warn():
    errors, warnings = gp.validate_template(VALID)
    assert errors == []
    assert len(warnings) == 3 and any("{{security_directive}}" in w for w in warnings)


def test_save_load_reset_round_trip(db):
    assert gp.load_effective(db).is_default

    saved = gp.save_template(db, VALID, "admin-user")
    assert (saved.is_default, saved.template, saved.updated_by) == (False, VALID, "admin-user")
    assert saved.updated_at is not None and saved.updated_at.tzinfo is not None

    again = gp.save_template(db, VALID + "\nMore.", "other")
    assert again.updated_by == "other" and again.template.endswith("More.")

    reset = gp.reset_template(db)
    assert reset.is_default and reset.template == DEFAULT_REVIEW_TEMPLATE


def test_save_rejects_invalid(db):
    with pytest.raises(gp.PromptValidationError) as exc:
        gp.save_template(db, "nothing useful", "admin-user")
    assert len(exc.value.errors) == 2
    assert gp.load_effective(db).is_default


def test_build_uses_custom_template():
    rules = RuleSettings(custom_instructions="Never block the loop.")
    out = build_review_system_prompt(rules, None, VALID)
    assert out.startswith("Review it.\nRules:\nNever block the loop.")
