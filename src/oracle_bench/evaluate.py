from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from docker.errors import DockerException

from oracle_bench.artifacts import verify_bundle
from oracle_bench.container import Profile, open_sandbox
from oracle_bench.io import read_json, write_json
from oracle_bench.paths import RunPaths
from oracle_bench.runners.execution import run_tests
from oracle_bench.runners.pytest import incomplete_result, pair_results
from oracle_bench.workspace import RepositoryWorkspace


def run_version(
    client, config, image: str, instance: dict, run_dir: Path, version: str, *, reference=False
) -> dict:
    runtime = config.require_runtime()
    paths = RunPaths.open(run_dir)
    directory = (paths.reference if reference else paths.evaluation) / version
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "output.log"
    try:
        profile = Profile.REFERENCE if reference else Profile.EVALUATION
        with open_sandbox(client, image, config, profile, log) as sandbox:
            workspace = RepositoryWorkspace(sandbox, config)
            workspace.prepare(instance["base_commit"], directory, reference=reference)
            if version == "golden":
                workspace.apply_patch(instance["golden_patch"], directory / "repair.patch")
                workspace.rebuild()
            if reference:
                workspace.apply_patch(
                    instance["reference_test_patch"], directory / "reference.patch"
                )
                targets = instance["reference_test_ids"]
                if not targets:
                    raise ValueError("No reference test IDs available for the pair smoke check")
            else:
                manifest = verify_bundle(run_dir)
                if manifest["empty"]:
                    return incomplete_result(directory, "no_tests", "Agent produced no test files")
                sandbox.upload(paths.submission / "files", runtime.workdir, contents=True)
                targets = [config.task.generated_dir]
            return run_tests(sandbox, config, targets, directory)
    except (RuntimeError, OSError, ValueError, DockerException) as exc:
        return incomplete_result(directory, "infrastructure_error", str(exc))


def check_reference(client, config, image: str, instance: dict, run_dir: Path):
    buggy = run_version(client, config, image, instance, run_dir, "buggy", reference=True)
    golden = run_version(client, config, image, instance, run_dir, "golden", reference=True)
    paired = pair_results(buggy, golden)
    write_json(RunPaths.open(run_dir).reference / "results.json", paired)
    if not paired["has_fail_on_buggy_pass_on_golden"]:
        raise RuntimeError(
            "Reference pair check did not reproduce a fail/pass test; "
            "inspect reference-check/ before spending on generation"
        )


def archive_previous_evaluation(run_dir: Path):
    paths = RunPaths.open(run_dir)
    names = [
        name for name in ["buggy", "golden", "results.json"] if (paths.evaluation / name).exists()
    ]
    if names:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive = paths.evaluation_history / stamp
        archive.mkdir(parents=True)
        for name in names:
            shutil.move(paths.evaluation / name, archive / name)


def evaluate(client, config, image: str, instance: dict, run_dir: Path):
    paths = RunPaths.open(run_dir)
    manifest = verify_bundle(run_dir)
    archive_previous_evaluation(run_dir)
    buggy = run_version(client, config, image, instance, run_dir, "buggy")
    golden = run_version(client, config, image, instance, run_dir, "golden")
    result = pair_results(buggy, golden)
    result.update(
        instance_id=instance["instance_id"],
        artifact_sha256=manifest["sha256"],
        submission_compliant=manifest["compliant"],
        forbidden_changes=manifest["forbidden_changes"],
        task_scope=config.task.scope,
        test_target=instance.get("test_target") if config.task.scope == "localized" else None,
        existing_tests=config.task.existing_tests,
        agent=read_json(paths.generation / "result.json"),
        coverage={
            version: read_json(paths.evaluation / version / "coverage.json")
            for version in ["buggy", "golden"]
        },
    )
    result["diagnostic_only"] = not manifest["compliant"]
    write_json(paths.results, result)
    return result
