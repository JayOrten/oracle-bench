import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from docker.errors import DockerException, ImageNotFound
from fixtures import evaluation_result, instance_record

from oracle_bench.config import JudgeConfig, RuntimeConfig, load_config
from oracle_bench.harnesses import claude
from oracle_bench.io import digest, read_json, write_json
from oracle_bench.judge.run import judge as run_judge
from oracle_bench.paths import RunPaths
from oracle_bench.results import write_result

SAMPLE = Path(__file__).parents[1] / "configs/smoke.yaml"
VALID_JUDGMENT = """{
  "no_attempt_reason": null,
  "tests_issue": "yes",
  "attempt_detail": "missing_required_condition",
  "rationale": "The generated assertion targets the reported behavior but misses its trigger."
}"""


def judge(paths):
    """Invoke the standalone stage with the saved run's resolved configuration."""
    return run_judge(load_config(paths.config, resolved=True), paths)


def saved_run(tmp_path):
    paths = RunPaths.create(tmp_path)
    config = load_config(SAMPLE)
    config.runtime = RuntimeConfig(
        image="example/runtime",
        source_roots=["package"],
        import_modules=["package"],
        existing_test_globs=["tests"],
    )
    config.judge = JudgeConfig(
        rubric=str(paths.judge.rubric),
        instructions=str(paths.judge.instructions),
        harness="claude",
        # Set on purpose. The default is openrouter, and these tests want to
        # exercise the anthropic credential path.
        provider="anthropic",
        model="judge-model",
        limit={"kind": "wall_seconds", "value": 300},
    )
    paths.config.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False))
    paths.judge.rubric.write_text("# Frozen rubric\n\nChoose labels.\n")
    paths.judge.instructions.write_text("Inspect $root/buggy/ and $root/golden/.\n\n")
    write_json(paths.runtime, {"image": "example/runtime"})
    write_json(paths.status, {"stage": "finished", "state": "completed", "judge_status": "missing"})
    write_result(paths.instance, instance_record())
    write_json(paths.results, evaluation_result())
    generated = paths.submission / "files/oracle_tests/test_generated.py"
    generated.parent.mkdir(parents=True)
    generated.write_text("def test_generated(): pass\n")
    files = {
        "oracle_tests/test_generated.py": {
            "sha256": digest(generated.read_bytes()),
            "mode": 0o644,
        }
    }
    write_json(
        paths.submission / "manifest.json",
        {
            "files": files,
            "empty": False,
            "sha256": digest(json.dumps(files, sort_keys=True).encode()),
        },
    )
    return paths


def install_fakes(monkeypatch, final_text=VALID_JUDGMENT, status="completed"):
    client = Mock()

    @contextmanager
    def client_context():
        yield client

    sandbox = Mock()

    @contextmanager
    def sandbox_context(*args, **kwargs):
        yield sandbox

    def claude_turn(_sandbox, request):
        assert request.working_directory == "/oracle-judge"
        assert request.harness.limit.kind == "wall_seconds"
        assert request.harness.timeout_seconds == 300
        assert request.harness.multi_agent is False
        request.artifact_directory.mkdir(parents=True, exist_ok=True)
        (request.artifact_directory / "final.txt").write_text(final_text)
        return {
            "status": status,
            "duration_seconds": 2.5,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "cost_usd": 0.01,
            "errors": [] if status == "completed" else [{"message": "harness failed"}],
        }

    monkeypatch.setattr("oracle_bench.judge.run.docker_client", client_context)
    monkeypatch.setattr("oracle_bench.judge.run.open_sandbox", sandbox_context)
    monkeypatch.setattr("oracle_bench.judge.run.build_judge_workspace", Mock())
    monkeypatch.setattr("oracle_bench.harnesses.claude.run_turn", claude_turn)
    return client


def test_standalone_judge_saves_prompt_raw_output_provenance_and_labels(tmp_path, monkeypatch):
    paths = saved_run(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    install_fakes(monkeypatch)

    output = judge(paths)

    assert output.status == "completed"
    assert paths.judge.judgment_raw.read_text() == VALID_JUDGMENT
    judgment = read_json(paths.judge.judgment)
    assert judgment["status"] == "completed"
    assert judgment["tests_issue"] == "yes"
    result = read_json(paths.judge.result)
    assert result["model"] == "judge-model"
    assert result["harness"] == "claude"
    prompt = paths.judge.prompt.read_text()
    assert "/oracle-judge/buggy/" in prompt
    assert prompt.endswith(paths.judge.rubric.read_text())
    assert read_json(paths.status)["judge_status"] == "completed"


def test_invalid_model_output_is_saved_without_a_retry(tmp_path, monkeypatch):
    paths = saved_run(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    install_fakes(monkeypatch, final_text="explanation before JSON")
    turn = Mock(wraps=claude.run_turn)
    monkeypatch.setattr("oracle_bench.harnesses.claude.run_turn", turn)

    judge(paths)

    assert read_json(paths.judge.judgment)["status"] == "invalid_output"
    assert paths.judge.judgment_raw.read_text() == "explanation before JSON"
    assert turn.call_count == 1


@pytest.mark.parametrize(
    "harness_status,judgment_status",
    [("failed", "failed"), ("timeout", "timed_out")],
)
def test_harness_failure_produces_explicit_judgment_status(
    tmp_path, monkeypatch, harness_status, judgment_status
):
    paths = saved_run(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    install_fakes(monkeypatch, status=harness_status)

    judge(paths)

    judgment = read_json(paths.judge.judgment)
    assert judgment["status"] == judgment_status
    assert judgment["error"] == "harness failed"


def test_rerun_archives_complete_previous_attempt(tmp_path, monkeypatch):
    paths = saved_run(tmp_path)
    paths.judge.judgment.write_text('{"old": true}\n')
    paths.judge.agent.mkdir()
    (paths.judge.agent / "trace.jsonl").write_text("old trace\n")
    human = paths.judge.human.judgments / "rater_1/judgment.json"
    human.parent.mkdir(parents=True)
    human.write_text('{"human": true}\n')
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    install_fakes(monkeypatch)

    judge(paths)

    archives = list(paths.judge.history.iterdir())
    assert len(archives) == 1
    assert read_json(archives[0] / "judgment.json") == {"old": True}
    assert (archives[0] / "agent/trace.jsonl").read_text() == "old trace\n"
    assert read_json(human) == {"human": True}
    assert not (archives[0] / "human").exists()
    assert paths.judge.rubric.read_text() == "# Frozen rubric\n\nChoose labels.\n"


def test_missing_credential_fails_before_docker(tmp_path, monkeypatch):
    paths = saved_run(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    docker = Mock()
    monkeypatch.setattr("oracle_bench.judge.run.docker_client", docker)

    with pytest.raises(RuntimeError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        judge(paths)

    docker.assert_not_called()


def test_missing_evaluation_results_fail_before_docker(tmp_path, monkeypatch):
    paths = saved_run(tmp_path)
    paths.results.unlink()
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    docker = Mock()
    monkeypatch.setattr("oracle_bench.judge.run.docker_client", docker)

    with pytest.raises(FileNotFoundError, match="results.json"):
        judge(paths)

    docker.assert_not_called()


def test_unexpected_harness_error_is_saved_as_failure(tmp_path, monkeypatch):
    paths = saved_run(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    install_fakes(monkeypatch)
    turn = Mock(side_effect=RuntimeError("transport broke"))
    monkeypatch.setattr("oracle_bench.harnesses.claude.run_turn", turn)

    judge(paths)

    assert read_json(paths.judge.judgment) == {
        "status": "failed",
        "error": "transport broke",
    }
    # The stage records the attempt itself when the harness never got far enough to.
    attempt = read_json(paths.judge.result)
    assert attempt["status"] == "failed"
    assert attempt["model"] == "judge-model"
    assert attempt["errors"][-1]["message"] == "transport broke"
    assert turn.call_count == 1


@pytest.mark.parametrize(
    "error", [RuntimeError("workspace failed"), DockerException("daemon refused the container")]
)
def test_workspace_failure_is_recorded_by_standalone_judge(tmp_path, monkeypatch, error):
    paths = saved_run(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    install_fakes(monkeypatch)
    monkeypatch.setattr("oracle_bench.judge.run.build_judge_workspace", Mock(side_effect=error))

    judge(paths)

    assert read_json(paths.judge.judgment)["status"] == "failed"
    assert read_json(paths.judge.judgment)["error"] == str(error)
    assert read_json(paths.status)["judge_status"] == "failed"


def test_late_failure_keeps_the_judgment_the_attempt_already_produced(tmp_path, monkeypatch):
    paths = saved_run(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    install_fakes(monkeypatch)

    @contextmanager
    def failing_cleanup(*args, **kwargs):
        yield Mock()
        raise RuntimeError("Could not remove benchmark container")

    monkeypatch.setattr("oracle_bench.judge.run.open_sandbox", failing_cleanup)

    judge(paths)

    judgment = read_json(paths.judge.judgment)
    assert judgment["status"] == "completed"
    assert judgment["tests_issue"] == "yes"
    attempt = read_json(paths.judge.result)
    assert attempt["errors"][-1]["message"] == "Could not remove benchmark container"


def test_missing_runtime_image_does_not_archive_previous_attempt(tmp_path, monkeypatch):
    paths = saved_run(tmp_path)
    paths.judge.judgment.write_text('{"old": true}\n')
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    client = Mock()
    client.images.get.side_effect = ImageNotFound("missing")

    @contextmanager
    def client_context():
        yield client

    monkeypatch.setattr("oracle_bench.judge.run.docker_client", client_context)

    with pytest.raises(RuntimeError, match="runtime image is missing"):
        judge(paths)

    assert read_json(paths.judge.judgment) == {"old": True}


def test_empty_submission_is_rejected_before_docker(tmp_path, monkeypatch):
    paths = saved_run(tmp_path)
    manifest = read_json(paths.submission / "manifest.json")
    manifest["empty"] = True
    write_json(paths.submission / "manifest.json", manifest)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "credential-fixture")
    docker = Mock()
    monkeypatch.setattr("oracle_bench.judge.run.docker_client", docker)

    with pytest.raises(ValueError, match="empty"):
        judge(paths)

    docker.assert_not_called()
