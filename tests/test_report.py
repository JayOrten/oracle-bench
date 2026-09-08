import json

import pytest

from oracle_bench.report import LABELS, report


@pytest.mark.parametrize("cost", [None, 0.0378])
def test_report_renders_optional_harness_cost(tmp_path, cost):
    results = {
        "instance_id": "test-instance",
        "existing_tests": "keep",
        "agent": {"status": "completed", "cost_usd": cost},
        "buggy_status": "completed",
        "golden_status": "completed",
        "diagnostic_only": False,
        "matrix": {key: {"count": 0} for key in LABELS},
        "other_outcomes": [],
        "coverage": {},
    }
    (tmp_path / "results.json").write_text(json.dumps(results))
    text = report(tmp_path).read_text()
    assert ("$0.0378" in text) == (cost is not None)
    assert ("Monetary cost is unavailable" in text) == (cost is None)
