import json

import pytest

from oracle_bench.harnesses.claude import parse_trace


@pytest.mark.parametrize(
    "subtype,is_error,completed",
    [
        ("success", False, True),
        ("success", True, False),
        ("error_max_budget_usd", True, False),
        ("error_max_turns", True, False),
    ],
)
def test_claude_result_preserves_failure_and_cost(tmp_path, subtype, is_error, completed):
    path = tmp_path / "trace.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "result",
                "subtype": subtype,
                "is_error": is_error,
                "usage": {"input_tokens": 20},
                "total_cost_usd": 0.02,
            }
        )
        + "\n"
    )
    result = parse_trace(path)
    assert result["turn_completed"] == completed
    assert bool(result["errors"]) != completed
    assert result["cost_usd"] == 0.02
    assert result["usage"] == {"input_tokens": 20}


def test_incomplete_claude_trace_is_not_success(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text('broken\n{"type":"assistant"}\n')
    result = parse_trace(path)
    assert not result["turn_completed"]
    assert result["cost_usd"] is None
    assert result["unparsed_trace_lines"] == 1
