import json
from pathlib import Path

import pytest

from oracle_bench.config import RuntimeConfig, load_config
from oracle_bench.containers import CommandResult
from oracle_bench.harnesses.claude import generate, parse_trace


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


@pytest.mark.parametrize("auth_mode", ["oauth", "api_key"])
def test_claude_launch_limits_and_secret_handling(tmp_path, monkeypatch, auth_mode):
    config = load_config(Path(__file__).parents[1] / "configs/smoke-claude.yaml")
    config.agent.auth = auth_mode
    config.runtime = RuntimeConfig(
        image="example/image:latest",
        source_roots=["requests"],
        import_modules=["requests"],
        existing_test_globs=["test_requests.py", "tests"],
    )
    selected = "CLAUDE_CODE_OAUTH_TOKEN" if auth_mode == "oauth" else "ANTHROPIC_API_KEY"
    other = "ANTHROPIC_API_KEY" if auth_mode == "oauth" else "CLAUDE_CODE_OAUTH_TOKEN"
    monkeypatch.setenv(selected, "secret-test-value")
    monkeypatch.setenv(other, "wrong-account")

    class FakeDocker:
        def put(self, *args):
            pass

        def shell(self, container, script, log, timeout, **kwargs):
            assert kwargs["environment"][selected] == "secret-test-value"
            assert other not in kwargs["environment"]
            assert "secret-test-value" not in script
            assert "--max-budget-usd 0.25" in script
            assert "--max-turns 10" in script
            assert "--tools Bash,Read,Write,Edit,Glob,Grep" in script
            assert kwargs["user"] == "10001:10001"
            return CommandResult(0, 1)

        def get(self, container, source, target, log, **kwargs):
            if source.endswith("trace.jsonl"):
                target.write_text(
                    json.dumps(
                        {
                            "type": "result",
                            "subtype": "success",
                            "is_error": False,
                            "result": "secret-test-value",
                            "total_cost_usd": 0.01,
                        }
                    )
                )
            else:
                target.write_text("secret-test-value")

    docker = FakeDocker()
    docker.config = config
    result = generate(docker, "test-container", tmp_path)
    assert result["status"] == "completed"
    assert result["cost_usd"] == 0.01
    for path in (tmp_path / "agent").iterdir():
        assert "secret-test-value" not in path.read_text()
