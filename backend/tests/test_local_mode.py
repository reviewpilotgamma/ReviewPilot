"""Local sign-in, with GitHub left unconfigured."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.config import reload_settings
from app.models import PRReview


def _local(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "")
    monkeypatch.setenv("GITHUB_APP_ID", "")
    reload_settings()


def test_dev_login_sets_session_outside_production(client, db, monkeypatch):
    _local(monkeypatch)
    client.headers["X-Requested-With"] = "ReviewPilot"
    response = client.post("/api/v1/auth/dev-login")
    assert response.status_code == 200
    assert response.json()["username"] == "dev"
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "dev"
    assert db.scalar(select(func.count()).select_from(PRReview)) == 0


def test_dev_login_hidden_in_production(client, monkeypatch):
    monkeypatch.setenv("ENV", "production")
    reload_settings()
    client.headers["X-Requested-With"] = "ReviewPilot"
    assert client.post("/api/v1/auth/dev-login").status_code == 404


def test_local_installations_do_not_call_github(client, monkeypatch, mock_http):
    _local(monkeypatch)
    client.headers["X-Requested-With"] = "ReviewPilot"
    assert client.post("/api/v1/auth/dev-login").status_code == 200
    data = client.get("/api/v1/github/installations").json()
    assert data[0]["account_login"] == "local"
    assert data[0]["repos"][0]["full_name"] == "local/manual"
    assert mock_http.calls.call_count == 0
    app = client.get("/api/v1/github/app").json()
    assert app["local_mode"] is True


def test_manual_review_endpoint_is_gone(client, login):
    login()
    response = client.post(
        "/api/v1/reviews/manual",
        json={"repo": "acme/widgets", "pr_number": 1, "title": "Add retries", "diff": "+line\n"},
    )
    assert response.status_code in (404, 405)
