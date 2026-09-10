import json

from oracle_bench.harnesses.opencode import parse_trace


def test_parse_trace_accumulates_usage_cost_and_final_text(tmp_path):
    trace = tmp_path / "trace.jsonl"
    events = [
        {"type": "text", "part": {"text": "working"}},
        {
            "type": "step_finish",
            "part": {
                "reason": "tool-calls",
                "cost": 0.01,
                "tokens": {"input": 10, "output": 2, "reasoning": 1},
            },
        },
        {"type": "text", "part": {"text": "done"}},
        {
            "type": "step_finish",
            "part": {
                "reason": "stop",
                "cost": 0.02,
                "tokens": {"input": 20, "output": 3, "reasoning": 2},
            },
        },
    ]
    trace.write_text("\n".join(map(json.dumps, events)))

    result = parse_trace(trace)

    assert result["turn_completed"]
    assert result["cost_usd"] == 0.03
    assert result["usage"] == {
        "input_tokens": 30,
        "output_tokens": 5,
        "reasoning_tokens": 3,
    }
    assert result["final_text"] == "done"


def test_parse_trace_treats_missing_final_event_as_incomplete(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps({"type": "text", "part": {"text": "partial"}}))

    result = parse_trace(trace)

    assert not result["turn_completed"]
    assert result["cost_usd"] is None
