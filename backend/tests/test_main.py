"""App factory: health check, API error mapping, request ids and the worker lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.core.config import reload_settings
from app.services.errors import GitHubError, NotConfiguredError, ReauthRequired


def test_health_reports_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True, "worker": "stopped"}


def test_health_reports_a_broken_database_as_degraded(client, monkeypatch):
    def broken():
        raise RuntimeError("db down")

    monkeypatch.setattr(main, "SessionLocal", broken)
    assert client.get("/health").json() == {"status": "degraded", "db": False, "worker": "stopped"}


def test_request_id_is_echoed_or_generated(client):
    assert client.get("/health", headers={"X-Request-ID": "abc123"}).headers["X-Request-ID"] == "abc123"
    assert len(client.get("/health").headers["X-Request-ID"]) == 12


@pytest.mark.parametrize(
    ("error", "status", "body"),
    [
        (ReauthRequired("expired"), 401, {"detail": "reauth_required"}),
        (NotConfiguredError("GitHub App is not configured"), 503, {"detail": "GitHub App is not configured"}),
        (GitHubError("boom", status_code=500), 502, {"detail": "GitHub API request failed"}),
    ],
)
def test_service_errors_map_to_http_responses(app, error, status, body):
    @app.get("/raise")
    def _raise():
        raise error

    with TestClient(app, base_url="http://api.test") as client:
        response = client.get("/raise")
    assert response.status_code == status
    assert response.json() == body


def test_unhandled_errors_hide_details_and_return_the_request_id(app):
    @app.get("/crash")
    def _crash():
        raise RuntimeError("secret internals")

    with TestClient(app, base_url="http://api.test", raise_server_exceptions=False) as client:
        response = client.get("/crash", headers={"X-Request-ID": "rid-1"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "request_id": "rid-1"}
    assert response.headers["X-Request-ID"] == "rid-1"
    assert "secret" not in response.text

    with TestClient(app, base_url="http://api.test", raise_server_exceptions=False) as client:
        generated = client.get("/crash")
    assert len(generated.json()["request_id"]) == 12
    assert generated.headers["X-Request-ID"] == generated.json()["request_id"]


def test_lifespan_starts_and_stops_the_worker_when_enabled(monkeypatch):
    monkeypatch.setenv("WORKER_ENABLED", "true")
    reload_settings()
    start, stop = AsyncMock(), AsyncMock()
    monkeypatch.setattr(main.worker, "start", start)
    monkeypatch.setattr(main.worker, "stop", stop)

    with TestClient(main.create_app(), base_url="http://api.test") as client:
        assert client.get("/health").status_code == 200
        start.assert_awaited_once()
        stop.assert_not_awaited()
    stop.assert_awaited_once()
