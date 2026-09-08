from pathlib import Path

import pytest
import yaml

from oracle_bench.config import load_config

SAMPLE = Path(__file__).parents[1] / "configs" / "smoke.yaml"


def config_file(tmp_path, section, key, value):
    raw = yaml.safe_load(SAMPLE.read_text())
    raw[section][key] = value
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


@pytest.mark.parametrize("visibility", ["keep", "hide"])
def test_test_visibility_is_explicit_and_paths_are_config_relative(tmp_path, visibility):
    config = load_config(config_file(tmp_path, "task", "existing_tests", visibility))
    assert config.task.existing_tests == visibility
    assert config.task.prompt == str((tmp_path / "../prompts/unit-tests.md").resolve())
    assert config.output == str((tmp_path / "../runs").resolve())


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("task", "existing_tests", "sometimes"),
        ("task", "generated_dir", "../outside"),
        ("task", "generated_dir", "/outside"),
        ("task", "generated_dir", ".git/hooks"),
        ("task", "generated_dir", "requests/tests"),
        ("environment", "existing_test_paths", ["."]),
        ("dataset", "revision", "main"),
        ("harness", "wall_seconds", 0),
        ("harness", "wall_seconds", True),
        ("harness", "api_key_env", "not a variable name"),
        ("harness", "typo", 123),
        ("harness", "provider", "unknown"),
    ],
)
def test_invalid_config_fails_before_starting_containers(tmp_path, section, key, value):
    with pytest.raises(ValueError):
        load_config(config_file(tmp_path, section, key, value))


def test_resolved_configuration_contains_no_credential_value(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-value")
    config = load_config(SAMPLE)
    assert "secret-test-value" not in yaml.safe_dump(config.to_dict())
