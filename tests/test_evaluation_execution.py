"""Evaluation execution preserves binary evidence and marks incomplete output."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from oracle_bench.config import RuntimeConfig, load_config
from oracle_bench.container.sandbox import CommandResult
from oracle_bench.evaluation import run_tests
from oracle_bench.io import read_json, write_json
from oracle_bench.results import VersionResult


@pytest.fixture
def config():
    value = load_config(Path(__file__).parents[1] / "configs/smoke.yaml")
    value.runtime = RuntimeConfig(
        image="example/image",
        source_roots=["app"],
        import_modules=["app"],
        existing_test_globs=["tests"],
    )
    return value


def test_missing_coverage_does_not_erase_completed_tests(config, tmp_path):
    sandbox = Mock(helpers="/helpers")
    sandbox.run.return_value = CommandResult(0, 1)
    evidence = {"status": "completed", "tests": {"test_example": {"outcome": "fail"}}}
    sandbox.download.side_effect = lambda *args, **kwargs: write_json(
        tmp_path / "tests.json", evidence
    )
    result = run_tests(sandbox, config, ["oracle_tests"], tmp_path)
    assert result == VersionResult.model_validate(evidence)
    assert read_json(tmp_path / "coverage.json")["status"] == "unavailable"


@pytest.mark.parametrize("timed_out,status", [(True, "timeout"), (False, "runner_error")])
def test_missing_results_never_count_as_success(config, tmp_path, timed_out, status):
    sandbox = Mock(helpers="/helpers")
    sandbox.run.return_value = CommandResult(124 if timed_out else 0, 1, timed_out)
    result = run_tests(sandbox, config, ["oracle_tests"], tmp_path)
    assert result.status == status
    sandbox.download.assert_called_once()


def test_unreadable_runner_output_becomes_an_explicit_incomplete_result(config, tmp_path):
    sandbox = Mock(helpers="/helpers")
    sandbox.run.return_value = CommandResult(0, 1)
    sandbox.download.side_effect = lambda *args, **kwargs: (tmp_path / "tests.json").write_text(
        '{"status": "completed", "tests": {"test_example": "not an object"}}'
    )

    result = run_tests(sandbox, config, ["oracle_tests"], tmp_path)

    assert result.status == "runner_error"
    assert "Unreadable runner output" in result.error


def test_runner_interruption_survives_failed_partial_collection(config, tmp_path):
    sandbox = Mock(helpers="/helpers")
    sandbox.run.side_effect = KeyboardInterrupt()
    sandbox.download.side_effect = RuntimeError("copy failed")
    with pytest.raises(KeyboardInterrupt):
        run_tests(sandbox, config, ["oracle_tests"], tmp_path)


def test_collection_failure_after_successful_execution_propagates(config, tmp_path):
    sandbox = Mock(helpers="/helpers")
    sandbox.run.return_value = CommandResult(0, 1)
    sandbox.download.side_effect = RuntimeError("copy failed")
    with pytest.raises(RuntimeError, match="copy failed"):
        run_tests(sandbox, config, ["oracle_tests"], tmp_path)
