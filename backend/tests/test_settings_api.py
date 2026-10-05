from __future__ import annotations

from app.core.config import env_file_path, get_settings
from app.services import config_store
from tests.conftest import GEMINI_API, GITHUB_API


def test_settings_are_masked(client, login):
    login()
    data = client.get("/api/v1/settings").json()
    assert data["gemini_api_key"] == "••••••••1234"
    assert data["github_webhook_secret"].startswith("••••")
    assert "client-secret" not in str(data)
    assert data["webhook_url"] == "http://api.test/api/v1/webhooks/github"
    assert data["is_admin"] is False and data["github_private_key_present"] is True


def test_non_admin_cannot_update(client, login):
    login()
    assert client.put("/api/v1/settings", json={"gemini_model": "x"}).status_code == 403
    assert client.put("/api/v1/settings/replies", json={}).status_code in (403, 422)


def test_admin_update_writes_env_preserving_comments(client, login, monkeypatch):
    login("admin-user")
    monkeypatch.delenv("GEMINI_API_KEY")
    response = client.put(
        "/api/v1/settings",
        json={
            "gemini_model": "gemini-2.5-pro",
            "gemini_api_key": "new key value 9876",
            "github_webhook_secret": "••••x",
        },
    )
    assert response.status_code == 200
    content = env_file_path().read_text(encoding="utf-8")
    assert content.startswith("# test env")
    assert "GEMINI_MODEL=gemini-2.5-pro" in content
    assert 'GEMINI_API_KEY="new key value 9876"' in content
    assert "GITHUB_WEBHOOK_SECRET" not in content  # masked value ignored
    assert get_settings().GEMINI_MODEL == "gemini-2.5-pro"
    assert get_settings().GEMINI_API_KEY.get_secret_value() == "new key value 9876"
    assert response.json()["gemini_api_key"] == "••••••••9876"


def test_invalid_key_path_rejected(client, login):
    login("admin-user")
    response = client.put("/api/v1/settings", json={"github_private_key_path": "/nope/missing.pem"})
    assert response.status_code == 422


def test_invalid_model_name_rejected(client, login):
    login("admin-user")
    assert client.put("/api/v1/settings", json={"gemini_model": "bad model; rm"}).status_code == 422


def test_write_env_rejects_newlines():
    import pytest

    with pytest.raises(config_store.ConfigValidationError):
        config_store.write_env({"GEMINI_MODEL": "a\nSESSION_SECRET=x"})


def test_validate_gemini(client, login, mock_http):
    login("admin-user")
    mock_http.get(f"{GEMINI_API}/models/gemini-2.0-flash").respond(200, json={"name": "models/gemini-2.0-flash"})
    assert client.post("/api/v1/settings/validate/gemini", json={}).json()["ok"] is True
    mock_http.get(f"{GEMINI_API}/models/nope").respond(404)
    result = client.post("/api/v1/settings/validate/gemini", json={"model": "nope"}).json()
    assert result["ok"] is False and "not found" in result["message"]


def test_validate_github(client, login, mock_http):
    login("admin-user")
    mock_http.get(f"{GITHUB_API}/app").respond(200, json={"name": "ReviewPilot"})
    mock_http.get(f"{GITHUB_API}/app/installations?per_page=100").respond(200, json=[{"id": 1}, {"id": 2}])
    data = client.post("/api/v1/settings/validate/github").json()
    assert data == {
        "ok": True,
        "message": "GitHub App credentials are valid",
        "model": None,
        "app_name": "ReviewPilot",
        "installations": 2,
    }


def test_replies_round_trip(client, login):
    login("admin-user")
    replies = client.get("/api/v1/settings/replies").json()
    replies["welcome"] = "Hi @{author}!"
    assert client.put("/api/v1/settings/replies", json=replies).status_code == 200
    assert client.get("/api/v1/settings/replies").json()["welcome"] == "Hi @{author}!"
    replies["error"] = ""
    assert client.put("/api/v1/settings/replies", json=replies).status_code == 422


def test_render_reply_tolerates_unknown_placeholders(client, login):
    from app.services.replies import render_reply, save_replies

    save_replies({"welcome": "Hi {author} {unknown} {}", "plan": "p", "error": "e {reason}", "empty_diff": "x"})
    assert render_reply("welcome", author="bob") == "Hi bob {unknown} {}"
