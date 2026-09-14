import json

import pytest

from oracle_bench.paths import RunPaths
from oracle_bench.report import LABELS, report


@pytest.mark.parametrize(
    ("scope", "target", "expected_scope"),
    [
        ("repository", None, "Test-generation scope: **whole repository**."),
        (
            "localized",
            "package/module.py (function_name)",
            "Test-generation scope: **calculated localized target**.",
        ),
    ],
)
@pytest.mark.parametrize("cost", [None, 0.0378])
def test_report_renders_run_metadata(tmp_path, cost, scope, target, expected_scope):
    results = {
        "instance_id": "test-instance",
        "task_scope": scope,
        "test_target": target,
        "existing_tests": "keep",
        "agent": {"status": "completed", "cost_usd": cost},
        "buggy_status": "completed",
        "golden_status": "completed",
        "diagnostic_only": False,
        "matrix": {key: {"count": 0} for key in LABELS},
        "other_outcomes": [],
        "coverage": {},
    }
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(json.dumps(results))
    text = report(tmp_path).read_text()
    assert ("$0.0378" in text) == (cost is not None)
    assert ("Monetary cost is unavailable" in text) == (cost is None)
    assert "Existing repository test modules visible to agent: **yes**" in text
    assert expected_scope in text
    assert ("Calculated target: **package/module.py (function_name)**." in text) == (
        scope == "localized"
    )
    assert "[Original issue](ground-truth/issue.md)" in text
    assert "[Buggy-to-golden fix diff](ground-truth/fix.patch)" in text
