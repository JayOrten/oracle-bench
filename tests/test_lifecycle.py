from pathlib import Path

import pytest

from oracle_bench.config import load_config
from oracle_bench.containers import CommandResult, Docker, prepare_workspace
from oracle_bench.evaluate import archive_previous_evaluation
from oracle_bench.harnesses.codex import generate, parse_trace
from oracle_bench.run import completion_state

SAMPLE = Path(__file__).parents[1] / "configs" / "smoke.yaml"


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_generation_routes_credentials_without_saving_them(tmp_path, monkeypatch, provider):
    import json

    docker = RecordingDocker()
    docker.config.harness.provider = provider
    docker.config.harness.api_key_env = "TEST_PROVIDER_KEY"
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-test-value")

    def get(container, source, target, log, **kwargs):
        if source.endswith("trace.jsonl"):
            target.write_text('{"type":"turn.completed"}\n')
        else:
            target.write_text("secret-test-value")

    monkeypatch.setattr(docker, "get", get)
    result = generate(docker, "container", tmp_path)
    assert result["status"] == "completed"
    argv = json.loads((tmp_path / "agent/command.json").read_text())
    invocation = next(kwargs for args, kwargs in docker.calls if args[0] == "exec")
    env = invocation["env"]
    if provider == "openrouter":
        assert env["OPENROUTER_API_KEY"] == "secret-test-value"
        assert 'model_provider="openrouter"' in argv
        assert 'model_providers.openrouter.wire_api="responses"' in argv
        assert "CODEX_API_KEY" not in env
    else:
        assert env["CODEX_API_KEY"] == "secret-test-value"
        assert "--config" not in argv
    for artifact in (tmp_path / "agent").iterdir():
        assert "secret-test-value" not in artifact.read_text()


class RecordingDocker(Docker):
    def __init__(self):
        super().__init__(load_config(SAMPLE))
        self.calls = []

    def command(self, args, log, timeout, **kwargs):
        self.calls.append((args, kwargs))
        return CommandResult(0, 0)


def test_container_is_removed_if_work_raises(tmp_path):
    docker = RecordingDocker()
    with pytest.raises(RuntimeError, match="work failed"):
        with docker.container("test-image", tmp_path / "log"):
            raise RuntimeError("work failed")
    assert docker.calls[-1][0][:2] == ["rm", "--force"]
    assert "--network" in docker.calls[0][0]
    assert "none" in docker.calls[0][0]


def test_api_key_is_forwarded_by_name_only(tmp_path):
    docker = RecordingDocker()
    docker.execute(
        "container",
        ["codex", "exec"],
        tmp_path / "log",
        10,
        environment={"CODEX_API_KEY": "secret-test-value"},
    )
    args, kwargs = docker.calls[0]
    assert "secret-test-value" not in " ".join(args)
    assert kwargs["env"]["CODEX_API_KEY"] == "secret-test-value"
    assert "CODEX_API_KEY" in args


@pytest.mark.parametrize(
    "visibility,reference,removed",
    [
        ("keep", False, False),
        ("hide", False, True),
        ("hide", True, False),
    ],
)
def test_prepare_applies_visibility_without_removing_reference_tests(
    tmp_path, visibility, reference, removed
):
    docker = RecordingDocker()
    docker.config.task.existing_tests = visibility
    prepare_workspace(
        docker, "container", {"base_commit": "a" * 40}, tmp_path / "log", keep_tests=reference
    )
    commands = [" ".join(args) for args, _ in docker.calls]
    assert any("shutil.rmtree" in command for command in commands) == removed


def test_directory_copy_uses_contents_semantics(tmp_path):
    docker = RecordingDocker()
    docker.put_contents("container", tmp_path / "files", "/testbed", tmp_path / "log")
    assert docker.calls[0][0] == ["cp", str(tmp_path / "files") + "/.", "container:/testbed"]


def test_reevaluation_archives_results_but_preserves_generated_tests(tmp_path):
    (tmp_path / "buggy").mkdir()
    (tmp_path / "buggy" / "tests.json").write_text("old")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "manifest.json").write_text("keep")
    archive_previous_evaluation(tmp_path)
    assert not (tmp_path / "buggy").exists()
    assert next((tmp_path / "evaluations").glob("*/buggy/tests.json")).read_text() == "old"
    assert (tmp_path / "generated" / "manifest.json").read_text() == "keep"


def test_trace_usage_is_reported_without_inventing_cost(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text('not-json\n{"type":"turn.completed","usage":{"input_tokens":12}}\n')
    result = parse_trace(path)
    assert result["usage"] == {"input_tokens": 12}
    assert result["cost_usd"] is None
    assert result["unparsed_trace_lines"] == 1


def test_recovered_stream_error_does_not_mean_the_turn_failed(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(
        '{"type":"error","message":"reconnecting"}\n'
        '{"type":"turn.completed","usage":{"output_tokens":2}}\n'
    )
    result = parse_trace(path)
    assert result["turn_completed"] and not result["turn_failed"]
    assert result["errors"]


def test_failed_agent_is_not_reported_as_a_successful_pipeline():
    result = {
        "agent": {"status": "failed"},
        "buggy_status": "no_tests",
        "golden_status": "no_tests",
        "submission_compliant": True,
    }
    assert completion_state(result) == "completed_with_errors"
    result.update(
        agent={"status": "completed"}, buggy_status="completed", golden_status="completed"
    )
    assert completion_state(result) == "completed"
