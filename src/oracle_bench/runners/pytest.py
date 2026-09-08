from pathlib import Path

from oracle_bench.io import read_json, write_json


def incomplete_result(directory: Path, status: str, reason: str) -> dict:
    path = directory / "tests.json"
    result = (
        read_json(path)
        if path.exists()
        else {
            "schema_version": 1,
            "tests": {},
            "collected": 0,
            "collection_errors": [],
            "exit_code": None,
        }
    )
    result.update(status=status, error=reason)
    write_json(path, result)
    if not (directory / "coverage.json").exists():
        write_json(directory / "coverage.json", {"status": "unavailable", "reason": reason})
    return result


def pair_results(buggy: dict, golden: dict) -> dict:
    labels = {
        ("pass", "pass"): "pass_on_both",
        ("fail", "pass"): "fail_on_buggy_pass_on_golden",
        ("pass", "fail"): "pass_on_buggy_fail_on_golden",
        ("fail", "fail"): "fail_on_both",
    }
    matrix = {name: [] for name in labels.values()}
    other = []
    rows = []
    for nodeid in sorted(buggy["tests"].keys() | golden["tests"].keys()):
        b = buggy["tests"].get(nodeid, {}).get("outcome", "not_collected")
        g = golden["tests"].get(nodeid, {}).get("outcome", "not_collected")
        row = {"test_id": nodeid, "buggy": b, "golden": g}
        label = labels.get((b, g))
        if buggy["status"] != "completed" or golden["status"] != "completed":
            label = None
        row["cell"] = label
        if label:
            matrix[label].append(nodeid)
        else:
            other.append(row)
        rows.append(row)
    return {
        "schema_version": 1,
        "matrix": {name: {"count": len(ids), "test_ids": ids} for name, ids in matrix.items()},
        "other_outcomes": other,
        "tests": rows,
        "buggy_status": buggy["status"],
        "golden_status": golden["status"],
        "has_fail_on_buggy_pass_on_golden": bool(matrix["fail_on_buggy_pass_on_golden"]),
    }
