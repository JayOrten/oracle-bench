import json
from pathlib import Path

import pytest
import yaml

from oracle_bench.config import load_config
from oracle_bench.datasets.swebench import image_for, resolve, runtime_for


def test_image_is_derived_from_instance_id():
    assert image_for("psf__requests-2148") == (
        "swebench/sweb.eval.x86_64.psf_1776_requests-2148:latest"
    )


def test_local_record_resolves_instance_and_runtime(tmp_path):
    record = {
        "instance_id": "psf__requests-2148",
        "repo": "psf/requests",
        "base_commit": "a" * 40,
        "patch": "diff --git a/requests/a.py b/requests/a.py\n",
        "test_patch": "diff --git a/test_requests.py b/test_requests.py\n",
        "FAIL_TO_PASS": ["test_requests.py::test_example"],
    }
    (tmp_path / "record.json").write_text(json.dumps(record))
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "source": {"instance": record["instance_id"], "record": "record.json"},
                "agent": {"model": "test-model"},
                "task": {"prompt": str(Path(__file__).parents[1] / "prompts/unit-tests.md")},
            }
        )
    )

    config = load_config(config_path)
    instance, runtime = resolve(config.source)

    assert instance["instance_id"] == record["instance_id"]
    assert instance["source"]["dataset"] == "lite"
    assert runtime.image == image_for(record["instance_id"])
    assert runtime.source_roots == ["requests"]
    assert runtime.import_modules == ["requests"]
    assert runtime.existing_test_globs == ["test_requests.py", "tests"]
    assert runtime.rebuild == ":"


def test_unknown_repository_has_no_guessed_runtime():
    with pytest.raises(ValueError, match="No tested SWE-bench runtime profile"):
        runtime_for({"instance_id": "example__project-1", "repo": "example/project"})
