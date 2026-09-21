import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fixtures import detecting_result, instance_record

from oracle_bench.config import JudgeConfig, RuntimeConfig, load_config
from oracle_bench.container.sandbox import CommandResult
from oracle_bench.io import digest, read_json, write_json
from oracle_bench.judge.workspace import JUDGE_ROOT, build_judge_workspace
from oracle_bench.paths import RunPaths
from oracle_bench.results import read_evaluation_result

SAMPLE = Path(__file__).parents[1] / "configs/smoke.yaml"


def prepared_run(tmp_path):
    paths = RunPaths.create(tmp_path)
    config = load_config(SAMPLE)
    config.runtime = RuntimeConfig(
        image="example/runtime",
        source_roots=["package"],
        import_modules=["package"],
        existing_test_globs=["tests"],
    )
    config.judge = JudgeConfig(
        rubric="rubric.md",
        instructions="instructions.md",
        harness="claude",
        model="judge-model",
        limit={"kind": "wall_seconds", "value": 300},
    )
    paths.judge.rubric.write_text("# Rubric\n")
    (paths.ground_truth / "issue.md").write_text("# issue\n\nIncorrect result.\n")
    fix = "diff --git a/package/core.py b/package/core.py\n--- a/package/core.py\n+++ b/package/core.py\n@@ -1 +1 @@\n-old\n+new\n"
    reference_patch = "diff --git a/tests/test_core.py b/tests/test_core.py\n"
    (paths.ground_truth / "fix.patch").write_text(fix)
    (paths.generation / "workspace.diff").write_text("generated diff\n")
    generated = paths.submission / "files/oracle_tests/test_generated.py"
    generated.parent.mkdir(parents=True)
    generated.write_text("def test_generated():\n    assert True\n")
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
            "forbidden_changes": [],
            "compliant": True,
            "empty": False,
            "sha256": digest(json.dumps(files, sort_keys=True).encode()),
        },
    )
    write_json(
        paths.results,
        detecting_result(
            tests=[
                {
                    "test_id": "oracle_tests/test_generated.py::test_generated",
                    "buggy": "fail",
                    "golden": "pass",
                    "cell": "fail_on_buggy_pass_on_golden",
                }
            ]
        ),
    )
    for version in ("buggy", "golden"):
        directory = paths.evaluation / version
        directory.mkdir(parents=True)
        write_json(directory / "tests.json", {"status": "completed", "tests": []})
        (directory / "output.log").write_text(version + " output\n")
    write_json(
        paths.build / "images.json",
        {
            "runtime": {
                "id": "sha256:" + "1" * 64,
                "digests": ["example/runtime@sha256:" + "2" * 64],
            }
        },
    )
    instance = instance_record(
        golden_patch=fix,
        reference_test_patch=reference_patch,
        original_record={
            "FAIL_TO_PASS": '["tests/test_core.py::test_fixed"]',
            "PASS_TO_PASS": [],
        },
    )
    return config, paths, instance, files, read_evaluation_result(paths.results)


def fake_sandbox(files, *, worktrees=True):
    sandbox = Mock(helpers="/opt/oracle-bench/container-helpers")
    sandbox.uploaded = {}
    expected = {name: info["sha256"] for name, info in files.items()}

    def run(command, **kwargs):
        if "worktree" in command and not worktrees:
            return CommandResult(1, 0)
        return CommandResult(0, 0)

    def download(source, destination, **kwargs):
        assert source == "/tmp/oracle-judge-file-hashes.json"
        write_json(
            destination,
            {
                JUDGE_ROOT + "/buggy": expected,
                JUDGE_ROOT + "/golden": expected,
            },
        )

    def upload(source, destination, **kwargs):
        if source.is_file():
            sandbox.uploaded[destination] = source.read_bytes()

    sandbox.run.side_effect = run
    sandbox.download.side_effect = download
    sandbox.upload.side_effect = upload
    return sandbox


def test_workspace_exposes_complete_hashed_bundle_and_identical_tests(tmp_path):
    config, paths, instance, files, evaluation = prepared_run(tmp_path)
    sandbox = fake_sandbox(files)

    spec = build_judge_workspace(sandbox, config, paths, "example/runtime", instance, evaluation)

    assert spec.workspace_method == "git_worktree"
    assert spec.prepared_image.image_id == "sha256:" + "1" * 64
    destinations = {artifact.destination for artifact in spec.artifacts}
    assert JUDGE_ROOT + "/instance/issue.md" in destinations
    assert JUDGE_ROOT + "/instructions.md" in destinations
    assert JUDGE_ROOT + "/evidence/paired-results.json" in destinations
    assert JUDGE_ROOT + "/buggy/oracle_tests/test_generated.py" in destinations
    assert JUDGE_ROOT + "/golden/oracle_tests/test_generated.py" in destinations
    assert read_json(paths.judge.workspace_spec) == spec.model_dump(mode="json")
    assert read_json(paths.judge.image) == spec.prepared_image.model_dump(mode="json")
    assert read_json(paths.judge.bundle_manifest)["artifacts"] == [
        artifact.model_dump(mode="json") for artifact in spec.artifacts
    ]
    instructions = sandbox.uploaded[JUDGE_ROOT + "/instructions.md"].decode()
    assert "## Reading order" in instructions
    assert "## Human judgment" in instructions
    assert "Fill `output/judgment.json`" in instructions
    assert "package/core.py" in instructions
    assert "tests/test_core.py::test_fixed" in instructions
    assert "fail_on_buggy_pass_on_golden" in instructions
    assert "`evidence/buggy-tests.json` and `evidence/golden-tests.json`" in instructions
    assert "| `oracle_tests/test_generated.py::test_generated` | `fail` | `pass` |" in instructions


def test_workspace_falls_back_to_explicit_repository_copies(tmp_path):
    config, paths, instance, files, evaluation = prepared_run(tmp_path)
    sandbox = fake_sandbox(files, worktrees=False)

    spec = build_judge_workspace(sandbox, config, paths, "example/runtime", instance, evaluation)

    assert spec.workspace_method == "directory_copy"
    assert all("copy-views" in command for command in spec.reconstruction_commands)


def test_workspace_reconstruction_manifest_is_deterministic(tmp_path):
    config, paths, instance, files, evaluation = prepared_run(tmp_path)

    first = build_judge_workspace(
        fake_sandbox(files), config, paths, "example/runtime", instance, evaluation
    )
    second = build_judge_workspace(
        fake_sandbox(files), config, paths, "example/runtime", instance, evaluation
    )

    assert first == second


def test_workspace_rejects_tampered_submission_before_container_work(tmp_path):
    config, paths, instance, _, evaluation = prepared_run(tmp_path)
    (paths.submission / "files/oracle_tests/test_generated.py").write_text("tampered")
    sandbox = Mock()

    with pytest.raises(ValueError, match="checksum"):
        build_judge_workspace(sandbox, config, paths, "example/runtime", instance, evaluation)

    sandbox.run.assert_not_called()


def test_workspace_reports_missing_evaluation_evidence(tmp_path):
    config, paths, instance, files, evaluation = prepared_run(tmp_path)
    (paths.evaluation / "golden/tests.json").unlink()

    with pytest.raises(FileNotFoundError, match="golden/tests.json"):
        build_judge_workspace(
            fake_sandbox(files), config, paths, "example/runtime", instance, evaluation
        )
