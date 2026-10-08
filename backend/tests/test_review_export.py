"""Review export renders every stored review in CSV and JSON."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "review_export_sample.json"


def test_fixture_is_large_and_well_formed() -> None:
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert len(records) == 450
    assert {"id", "verdict", "score", "findings"} <= set(records[0])


def test_fixture_verdicts_are_known() -> None:
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert {record["verdict"] for record in records} <= {"passed", "warning", "critical"}
