"""The perf report writer: valid JSON, one Markdown row per scenario, secret redaction, unwritable dir."""

from __future__ import annotations

import json

import pytest

from tests.e2e.harness import STAGES, ReportCollector, ScenarioResult


def result(name: str, **extra) -> ScenarioResult:
    stages = {stage: 0.001 for stage in STAGES}
    return ScenarioResult(name, "mocked", 2048, 10, "warning", 6.5, 0.05, stages, extra)


def test_writes_json_and_markdown(tmp_path):
    report = ReportCollector()
    report.add(result("tier_small"))
    report.add(result("sql_injection", keyword_hit_rate=0.5, ok=True))
    report.add_throughput(jobs=20, jobs_per_s=16.0)

    json_path, md_path = report.write(tmp_path / "out")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert [s["scenario"] for s in data["scenarios"]] == ["tier_small", "sql_injection"]
    assert data["throughput"] == [{"jobs": 20, "jobs_per_s": 16.0}]
    md = md_path.read_text(encoding="utf-8")
    assert md.count("| tier_small |") == 1 and md.count("| sql_injection |") == 2  # scenarios + live quality
    assert "## Live review quality" in md and "50%" in md
    assert "## Throughput" in md


def test_secrets_are_redacted(tmp_path):
    report = ReportCollector()
    report.secrets.add("AIza-super-secret")
    report.add(result("live_case", error="GeminiPermanentError: bad key AIza-super-secret"))

    json_path, md_path = report.write(tmp_path)

    for path in (json_path, md_path):
        text = path.read_text(encoding="utf-8")
        assert "AIza-super-secret" not in text and "***" in text


def test_unwritable_directory_only_warns(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    report = ReportCollector()
    report.add(result("tier_small"))

    with pytest.warns(UserWarning, match="Could not write E2E report"):
        assert report.write(blocker) is None
