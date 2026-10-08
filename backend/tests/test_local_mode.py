"""The removed local mode: no dev-login, no ``local/manual`` workspace, no manual review endpoint."""

from __future__ import annotations

from app.core.config import reload_settings


def test_without_github_user_is_gated_not_given_a_local_workspace(client, monkeypatch, mock_http):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "")
    monkeypatch.setenv("GITHUB_APP_ID", "")
    reload_settings()
    client.headers["X-Requested-With"] = "ReviewPilot"
    assert client.post("/api/v1/auth/dev-login").status_code == 404
    assert client.post("/api/v1/auth/login", json={"username": "dev", "password": "dev-pass-123"}).status_code == 200
    assert client.get("/api/v1/github/installations").json() == []
    assert mock_http.calls.call_count == 0
    assert "local_mode" not in client.get("/api/v1/github/app").json()


def test_manual_review_endpoint_is_gone(client, login):
    login()
    response = client.post(
        "/api/v1/reviews/manual",
        json={"repo": "acme/widgets", "pr_number": 1, "title": "Add retries", "diff": "+line\n"},
    )
    assert response.status_code in (404, 405)
