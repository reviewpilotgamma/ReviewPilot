"""Local sign-in and manual reviews, with GitHub left unconfigured."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.config import reload_settings
from app.models import PRReview
from scripts.run_review import main
from tests.conftest import FIXTURES, GEMINI_API

DIFF = (FIXTURES / "sample.diff").read_text(encoding="utf-8")
LLM_OUTPUT = (FIXTURES / "gemini_review.md").read_text(encoding="utf-8")
GEMINI_URL = f"{GEMINI_API}/models/gemini-2.0-flash:generateContent"
MANUAL = {
    "repo": "local/manual",
    "pr_number": 1,
    "title": "Add payment retries",
    "description": "Retries the charge call",
    "focus_note": "idempotency",
    "diff": DIFF,
}


def _local(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "")
    monkeypatch.setenv("GITHUB_APP_ID", "")
    reload_settings()


def _gemini(text: str = LLM_OUTPUT) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


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


def test_manual_review_is_listed(client, monkeypatch, mock_http):
    _local(monkeypatch)
    client.headers["X-Requested-With"] = "ReviewPilot"
    client.post("/api/v1/auth/dev-login")
    mock_http.post(GEMINI_URL).respond(200, json=_gemini())
    created = client.post("/api/v1/reviews/manual", json=MANUAL)
    assert created.status_code == 200
    body = created.json()
    assert body["verdict"] == "critical"
    assert body["trigger"] == "manual"
    assert body["repo_full_name"] == "local/manual"
    assert "idempotency" in body["full_markdown"]

    again = client.post("/api/v1/reviews/manual", json={**MANUAL, "pr_number": 1})
    assert again.status_code == 200
    listed = client.get("/api/v1/reviews").json()
    assert listed["total"] == 2


def test_empty_diff_saves_nothing(client, db, monkeypatch, mock_http):
    _local(monkeypatch)
    client.headers["X-Requested-With"] = "ReviewPilot"
    client.post("/api/v1/auth/dev-login")
    response = client.post("/api/v1/reviews/manual", json={**MANUAL, "diff": "   \n"})
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(PRReview)) == 0
    assert mock_http.calls.call_count == 0


def test_missing_gemini_key_saves_nothing(client, db, monkeypatch):
    _local(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    reload_settings()
    client.headers["X-Requested-With"] = "ReviewPilot"
    client.post("/api/v1/auth/dev-login")
    response = client.post("/api/v1/reviews/manual", json=MANUAL)
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]
    assert db.scalar(select(func.count()).select_from(PRReview)) == 0


def test_manual_review_rejects_unknown_repo_when_github_is_configured(client, login, mock_http):
    login()
    response = client.post("/api/v1/reviews/manual", json={**MANUAL, "repo": "other/repo"})
    assert response.status_code == 404
    assert mock_http.calls.call_count == 0


def test_script_prints_saved_review(monkeypatch, mock_http, tmp_path, capsys):
    _local(monkeypatch)
    diff = tmp_path / "change.diff"
    diff.write_text(DIFF, encoding="utf-8")
    mock_http.post(GEMINI_URL).respond(200, json=_gemini())
    code = main(["--repo", "local/manual", "--pr", "4", "--title", "Add retries", "--diff", str(diff)])
    assert code == 0
    assert "verdict=critical" in capsys.readouterr().out


def test_script_rejects_empty_diff(monkeypatch, tmp_path, capsys):
    _local(monkeypatch)
    diff = tmp_path / "empty.diff"
    diff.write_text("\n", encoding="utf-8")
    code = main(["--repo", "local/manual", "--pr", "4", "--title", "Empty", "--diff", str(diff)])
    assert code == 1
    assert "empty" in capsys.readouterr().err.lower()

