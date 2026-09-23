"""Harness adapters share transport policy while retaining their own arguments."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from oracle_bench.config import JudgeConfig, RuntimeConfig, WallTimeLimit, load_config
from oracle_bench.container.sandbox import CommandResult
from oracle_bench.harnesses import claude, codex, generate, opencode, run_turn
from oracle_bench.harnesses.launch import AgentTurnRequest, run_agent_turn
from oracle_bench.paths import RunPaths


@pytest.mark.parametrize(
    "harness,provider,auth,credential,target",
    [
        (codex, "openai", "api_key", "OPENAI_API_KEY", "CODEX_API_KEY"),
        (codex, "openrouter", "api_key", "OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
        (claude, "anthropic", "api_key", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
        (claude, "anthropic", "oauth", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"),
        (claude, "openrouter", "api_key", "OPENROUTER_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
        (opencode, "openrouter", "api_key", "OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
    ],
)
def test_launch_routes_only_selected_credential(
    tmp_path,
    monkeypatch,
    harness,
    provider,
    auth,
    credential,
    target,
):
    paths = RunPaths.create(tmp_path)
    config = load_config(Path(__file__).parents[1] / "configs/smoke.yaml")
    config.agent.harness = harness.__name__.rsplit(".", 1)[-1]
    config.agent.provider = provider
    config.agent.auth = auth
    config.agent.multi_agent = False
    config.agent.limit = WallTimeLimit(kind="wall_seconds", value=300)
    config.runtime = RuntimeConfig(
        image="example/image",
        source_roots=["requests"],
        import_modules=["requests"],
        existing_test_globs=["tests"],
    )
    monkeypatch.setenv(credential, "credential-fixture")
    monkeypatch.setenv("UNRELATED_CREDENTIAL", "wrong-account")
    sandbox = Mock()

    def run(argv, **kwargs):
        if "environment" in kwargs:
            environment = kwargs["environment"]
            assert environment[target] == "credential-fixture"
            assert "UNRELATED_CREDENTIAL" not in environment
            assert "credential-fixture" not in str(argv)
            assert kwargs["user"] == "10001:10001"
            assert kwargs["secrets"] == ("credential-fixture",)
            assert kwargs["workdir"] == config.runtime.workdir
            if harness is codex:
                assert "features.multi_agent=false" in argv
                if provider == "openrouter":
                    assert 'model_provider="openrouter"' in argv
                    assert "model_providers.openrouter.request_max_retries=4" in argv
                    assert "model_providers.openrouter.stream_max_retries=5" in argv
                trace = {"type": "turn.completed"}
            elif harness is claude:
                assert "Bash,Read,Write,Edit,Glob,Grep" in argv
                trace = {"type": "result", "subtype": "success", "total_cost_usd": 0.01}
                if provider == "openrouter":
                    assert environment["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"
                    assert environment["ANTHROPIC_API_KEY"] == ""
            else:
                assert argv[:2] == ["opencode", "run"]
                assert argv[argv.index("--model") + 1] == f"openrouter/{config.agent.model}"
                assert json.loads(environment["OPENCODE_CONFIG_CONTENT"])["permission"] == {
                    "task": "deny"
                }
                trace = {
                    "type": "step_finish",
                    "part": {"reason": "stop", "cost": 0, "tokens": {"input": 1, "output": 1}},
                }
            kwargs["stdout"].write_text(json.dumps(trace))
        return CommandResult(0, 1)

    sandbox.run.side_effect = run
    result = generate(sandbox, config, paths)
    assert result["status"] == "completed"
    if harness is claude:
        assert result["cost_usd"] == (None if provider == "openrouter" else 0.01)
    assert (paths.generation / "session.log").is_file()
    sandbox.stop_background_processes.assert_called_once()
    for artifact in paths.generation.iterdir():
        assert "credential-fixture" not in artifact.read_text()


def test_interruption_remains_visible_when_collection_fails(tmp_path, monkeypatch):
    RunPaths.create(tmp_path)
    config = load_config(Path(__file__).parents[1] / "configs/smoke.yaml")
    monkeypatch.setenv(config.agent.credential_env, "credential-fixture")
    sandbox = Mock()
    sandbox.run.side_effect = [CommandResult(0, 0), CommandResult(0, 0), KeyboardInterrupt()]
    sandbox.stop_background_processes.side_effect = RuntimeError("cleanup failed")
    with pytest.raises(KeyboardInterrupt) as error:
        request = AgentTurnRequest(
            harness=config.agent,
            harness_version="1.2.3",
            prompt=RunPaths.open(tmp_path).prompt,
            working_directory="/testbed",
            artifact_directory=RunPaths.open(tmp_path).generation,
        )
        run_agent_turn(sandbox, request, ["codex", "exec"], {}, "CODEX_API_KEY")
    assert "collection also failed" in error.value.__notes__[0]


def test_agent_turn_uses_caller_supplied_paths_and_working_directory(tmp_path, monkeypatch):
    config = load_config(Path(__file__).parents[1] / "configs/smoke.yaml")
    prompt = tmp_path / "judge-prompt.md"
    prompt.write_text("Inspect the saved evidence.")
    artifacts = tmp_path / "judge" / "agent"
    monkeypatch.setenv(config.agent.credential_env, "credential-fixture")
    sandbox = Mock()
    sandbox.run.return_value = CommandResult(0, 1)
    config.agent.limit = WallTimeLimit(kind="wall_seconds", value=45)
    request = AgentTurnRequest(
        harness=config.agent,
        harness_version="1.2.3",
        prompt=prompt,
        working_directory="/oracle-judge",
        artifact_directory=artifacts,
    )

    run_agent_turn(
        sandbox,
        request,
        ["codex", "exec"],
        {},
        "CODEX_API_KEY",
        last_message_path="/tmp/oracle-agent/final.txt",
    )

    turn = sandbox.run.call_args_list[2]
    assert turn.kwargs["stdin"] == prompt
    assert turn.kwargs["stdout"] == artifacts / "trace.jsonl"
    assert turn.kwargs["stderr"] == artifacts / "stderr.log"
    assert turn.kwargs["workdir"] == "/oracle-judge"
    assert turn.kwargs["timeout"] == 45
    assert json.loads((artifacts / "command.json").read_text()) == ["codex", "exec"]
    sandbox.download.assert_called_once_with(
        "/tmp/oracle-agent/final.txt",
        artifacts / "final.txt",
        required=False,
        secrets=("credential-fixture",),
    )


def test_claude_judge_uses_wall_time_and_disables_subagents(tmp_path, monkeypatch):
    judge = JudgeConfig(
        rubric="rubric.md",
        instructions="instructions.md",
        harness="claude",
        model="judge-model",
        limit={"kind": "wall_seconds", "value": 45},
    )
    monkeypatch.setenv(judge.credential_env, "credential-fixture")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("judge")
    request = AgentTurnRequest(
        harness=judge,
        harness_version="1.2.3",
        prompt=prompt,
        working_directory="/oracle-judge",
        artifact_directory=tmp_path / "agent",
    )
    sandbox = Mock()

    def run(argv, **kwargs):
        if "environment" in kwargs:
            assert "Bash,Read,Write,Edit,Glob,Grep" in argv
            kwargs["stdout"].write_text(
                json.dumps({"type": "result", "subtype": "success", "result": "{}"})
            )
        return CommandResult(0, 1)

    sandbox.run.side_effect = run

    result = run_turn(sandbox, request)

    assert result["status"] == "completed"


def test_codex_judge_turn_collects_its_own_last_message_file(tmp_path, monkeypatch):
    """The caller never names a harness-specific container path."""
    judge = JudgeConfig(
        rubric="rubric.md",
        instructions="instructions.md",
        harness="codex",
        model="judge-model",
        limit={"kind": "wall_seconds", "value": 45},
    )
    monkeypatch.setenv(judge.credential_env, "credential-fixture")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("judge")
    request = AgentTurnRequest(
        harness=judge,
        harness_version="1.2.3",
        prompt=prompt,
        working_directory="/oracle-judge",
        artifact_directory=tmp_path / "agent",
    )
    sandbox = Mock()

    def run(argv, **kwargs):
        if "environment" in kwargs:
            assert "features.multi_agent=false" in argv
            kwargs["stdout"].write_text(json.dumps({"type": "turn.completed", "usage": {}}))
        return CommandResult(0, 1)

    sandbox.run.side_effect = run

    result = run_turn(sandbox, request)

    assert result["status"] == "completed"
    sandbox.download.assert_called_once_with(
        codex.LAST_MESSAGE_PATH,
        request.artifact_directory / "final.txt",
        required=False,
        secrets=("credential-fixture",),
    )
