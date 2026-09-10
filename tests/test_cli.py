from pathlib import Path

import pytest

from oracle_bench import cli

SAMPLE = Path(__file__).parents[1] / "configs" / "smoke.yaml"


@pytest.mark.parametrize("shell_value", [None, "from-shell"])
def test_run_loads_local_keys_without_overriding_shell(tmp_path, monkeypatch, shell_value):
    import os

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    if shell_value is not None:
        monkeypatch.setenv("OPENAI_API_KEY", shell_value)
    (tmp_path / ".env").write_text('OPENAI_API_KEY="literal-${HOME}"\n')

    def run(config):
        assert os.environ["OPENAI_API_KEY"] == (shell_value or "literal-${HOME}")
        assert "literal-${HOME}" not in str(config.to_dict())
        return tmp_path

    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(cli, "read_json", lambda path: {"state": "completed"})
    assert cli.main(["run", str(SAMPLE)]) == 0


@pytest.mark.parametrize("command", ["evaluate", "report"])
def test_offline_commands_do_not_load_credentials(tmp_path, monkeypatch, command):
    def unexpected_load(*args, **kwargs):
        pytest.fail("Offline commands must not load credentials")

    monkeypatch.setattr(cli, "load_dotenv", unexpected_load)
    monkeypatch.setattr(cli, "reevaluate", lambda path: tmp_path)
    monkeypatch.setattr(cli, "report", lambda path: tmp_path)
    monkeypatch.setattr(cli, "read_json", lambda path: {"state": "completed"})
    assert cli.main([command, str(tmp_path)]) == 0


def test_batch_loads_credentials_and_returns_batch_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=test-value\n")
    batch_dir = tmp_path / "batches" / "batch-id"
    write_status = batch_dir / "status.json"
    write_status.parent.mkdir(parents=True)
    write_status.write_text('{"state": "completed"}')
    monkeypatch.setattr(cli, "run_batch", lambda path, resume: batch_dir)

    assert cli.main(["batch", "batch.yaml"]) == 0
