import json

import pytest

from oracle_bench.harnesses.claude import parse_trace


@pytest.mark.parametrize(
    "subtype,is_error,completed",
    [
        ("success", False, True),
        ("success", True, False),
        ("error", True, False),
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


def test_claude_error_lists_render_as_plain_messages(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "result",
                "subtype": "error",
                "is_error": True,
                "errors": ["Provider request failed"],
            }
        )
        + "\n"
    )

    assert parse_trace(path)["errors"] == [{"message": "Provider request failed"}]
