"""The /health endpoint reports status, DB, worker and version."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "1.0.0"
    assert body["db"] is True
