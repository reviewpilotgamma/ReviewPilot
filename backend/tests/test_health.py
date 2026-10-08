from __future__ import annotations


def test_health_reports_uptime(client):
    data = client.get("/health").json()
    assert isinstance(data["uptime_seconds"], int)
    assert data["uptime_seconds"] >= 0
