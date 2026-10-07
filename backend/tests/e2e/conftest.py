"""Fixtures for the end-to-end pipeline suite. Every test under ``tests/e2e`` is marked ``e2e``."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx

from app.core.config import reload_settings
from tests.conftest import FIXTURES
from tests.e2e.harness import INSTALLATION_TOKEN, FakeGitHub, MockGemini, Pipeline, ReportCollector, StageTimer

E2E_DIR = Path(__file__).parent
REPORT_DIR = Path(os.environ.get("REVIEWPILOT_E2E_REPORT_DIR", E2E_DIR.parents[1] / "e2e-reports"))
LIVE_FLAG = "REVIEWPILOT_E2E_LIVE"
LIVE_KEY = "REVIEWPILOT_E2E_GEMINI_API_KEY"
LIVE_MODEL = "REVIEWPILOT_E2E_GEMINI_MODEL"
LIVE_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
LIVE_SKIP_REASON = f"set {LIVE_FLAG}=1 and {LIVE_KEY} to run"

# One collector for the whole session; written once at the end.
REPORT = ReportCollector()
REPORT.secrets.update({"gemini-key-1234", INSTALLATION_TOKEN})


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if E2E_DIR in item.path.parents:
            item.add_marker(pytest.mark.e2e)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if REPORT:
        written = REPORT.write(REPORT_DIR)
        if written:
            reporter = session.config.pluginmanager.get_plugin("terminalreporter")
            if reporter is not None:
                reporter.write_line(f"E2E report: {written[1]}")


@pytest.fixture
def e2e_report() -> ReportCollector:
    return REPORT


@pytest.fixture
def fake_github(mock_http: respx.MockRouter) -> FakeGitHub:
    return FakeGitHub(mock_http)


@pytest.fixture
def mock_gemini(mock_http: respx.MockRouter) -> MockGemini:
    return MockGemini(mock_http, default_markdown=(FIXTURES / "gemini_review.md").read_text(encoding="utf-8"))


@pytest.fixture
def stage_timer(monkeypatch: pytest.MonkeyPatch) -> StageTimer:
    timer = StageTimer()
    timer.install(monkeypatch)
    return timer


@pytest.fixture
def pipeline(client, fake_github, mock_gemini, stage_timer, e2e_report) -> Pipeline:
    """Mocked GitHub + mocked Gemini, timed and reported."""
    return Pipeline(client, fake_github, mock_gemini, stage_timer, e2e_report)


@pytest.fixture
def live_gemini(monkeypatch: pytest.MonkeyPatch, mock_http: respx.MockRouter, e2e_report) -> Iterator[str]:
    """Point the app at the real Gemini API (GitHub stays mocked). Skips unless explicitly enabled."""
    key = os.environ.get(LIVE_KEY, "")
    if os.environ.get(LIVE_FLAG) != "1" or not key:
        pytest.skip(LIVE_SKIP_REASON)
    e2e_report.secrets.add(key)
    monkeypatch.setenv("GEMINI_API_KEY", key)
    monkeypatch.setenv("GEMINI_API_URL", LIVE_GEMINI_URL)
    if os.environ.get(LIVE_MODEL):
        monkeypatch.setenv("GEMINI_MODEL", os.environ[LIVE_MODEL])
    settings = reload_settings()
    mock_http.route(host="generativelanguage.googleapis.com").pass_through()
    yield settings.GEMINI_MODEL


@pytest.fixture
def live_pipeline(client, fake_github, stage_timer, e2e_report, live_gemini) -> Pipeline:
    """Mocked GitHub + real Gemini."""
    return Pipeline(client, fake_github, None, stage_timer, e2e_report)
