"""Golden prompt API: everyone can read it, only admins can change or reset it."""

from __future__ import annotations

from app.services.prompts import DEFAULT_REVIEW_TEMPLATE, NO_INSTRUCTIONS, VERBOSITY_DIRECTIVES

URL = "/api/v1/prompt"
VALID = "Review carefully.\n{{custom_instructions}}\n{{verbosity_directive}}\n<!-- reviewpilot-meta: {} -->"


def test_get_returns_default_with_segments_and_directives(client, login):
    login()
    data = client.get(URL).json()

    assert data["is_default"] is True and data["updated_by"] is None
    assert data["template"] == DEFAULT_REVIEW_TEMPLATE
    assert [s["name"] for s in data["segments"] if s["type"] == "slot"] == [
        "custom_instructions",
        "verbosity_directive",
        "security_directive",
        "requester_note",
    ]
    assert {s["name"]: s["required"] for s in data["slots"]}["custom_instructions"] is True
    assert data["directives"]["verbosity"]["detailed"] == VERBOSITY_DIRECTIVES["detailed"]
    assert data["placeholders"]["no_instructions"] == NO_INSTRUCTIONS
    assert data["warnings"] == []


def test_admin_saves_and_resets(client, login):
    login("admin-user", github_id=2001)

    saved = client.put(URL, json={"template": VALID})
    assert saved.status_code == 200
    body = saved.json()
    assert (body["is_default"], body["updated_by"], body["template"]) == (False, "admin-user", VALID)
    assert len(body["warnings"]) == 2  # security + requester note unused
    assert client.get(URL).json()["template"] == VALID

    assert client.delete(URL).status_code == 204
    assert client.get(URL).json()["is_default"] is True


def test_invalid_template_is_rejected_with_reasons(client, login):
    login("admin-user", github_id=2001)

    response = client.put(URL, json={"template": "Just review it. {{tone}}"})

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert len(errors) == 3
    assert any("{{custom_instructions}}" in e for e in errors)
    assert any("{{tone}}" in e for e in errors)
    assert client.get(URL).json()["is_default"] is True


def test_non_admin_cannot_edit_or_reset(client, login):
    login("alice")
    assert client.put(URL, json={"template": VALID}).status_code == 403
    assert client.delete(URL).status_code == 403
    assert client.get(URL).status_code == 200


def test_requires_sign_in(client):
    assert client.get(URL).status_code == 401
