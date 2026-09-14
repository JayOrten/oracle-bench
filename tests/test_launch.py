"""Harness adapters share transport policy while retaining their own arguments."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from oracle_bench.config import RuntimeConfig, load_config
from oracle_bench.container import CommandResult
from oracle_bench.harnesses import claude, codex, opencode
from oracle_bench.harnesses.launch import launch
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
            if harness is codex:
                assert "features.multi_agent=false" in argv
                if provider == "openrouter":
                    assert 'model_provider="openrouter"' in argv
                trace = {"type": "turn.completed"}
            elif harness is claude:
                assert argv[argv.index("--max-turns") + 1] == "10"
                assert argv[argv.index("--max-budget-usd") + 1] == "0.25"
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
    result = harness.generate(sandbox, config, tmp_path)
    assert result["status"] == "completed"
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
        launch(sandbox, config, tmp_path, ["codex", "exec"], {}, "CODEX_API_KEY")
    assert "collection also failed" in error.value.__notes__[0]
