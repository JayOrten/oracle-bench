from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from oracle_bench.artifacts import SCRIPTS, verify_bundle
from oracle_bench.containers import Docker, apply_patch, prepare_workspace
from oracle_bench.io import read_json, write_json
from oracle_bench.runners.pytest import incomplete_result, pair_results


def run_version(
    docker: Docker, image: str, instance: dict, run_dir: Path, version: str, *, reference=False
) -> dict:
    config = docker.config
    directory = (run_dir / "reference" if reference else run_dir) / version
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "output.log"
    try:
        with docker.container(image, log) as container:
            prepare_workspace(docker, container, instance, log, keep_tests=reference)
            if version == "golden":
                apply_patch(
                    docker, container, instance["golden_patch"], directory / "repair.patch", log
                )
                docker.shell(
                    container, config.environment.rebuild, log, config.limits.setup_seconds
                )
            if reference:
                apply_patch(
                    docker,
                    container,
                    instance["reference_test_patch"],
                    directory / "reference.patch",
                    log,
                )
                targets = config.environment.reference_targets or instance["reference_test_ids"]
                if not targets:
                    raise ValueError("No reference test IDs available for the pair smoke check")
            else:
                manifest = verify_bundle(run_dir)
                if manifest["empty"]:
                    return incomplete_result(directory, "no_tests", "Agent produced no test files")
                docker.put_contents(
                    container, run_dir / "generated" / "files", config.environment.workdir, log
                )
                targets = [config.task.generated_dir]
            settings = {
                "workdir": config.environment.workdir,
                "output": "/tmp/oracle-results",
                "targets": targets,
                "source_roots": config.environment.source_roots,
                "import_modules": config.environment.import_modules,
            }
            write_json(directory / "runner.json", settings)
            docker.put(container, SCRIPTS / "pytest_runner.py", "/tmp/oracle-runner.py", log)
            docker.put(container, directory / "runner.json", "/tmp/oracle-runner.json", log)
            execution = docker.execute(
                container,
                [config.environment.python, "/tmp/oracle-runner.py", "/tmp/oracle-runner.json"],
                log,
                config.limits.evaluation_seconds,
                check=False,
            )
            docker.get(container, "/tmp/oracle-results/.", directory, log, check=False)
            write_json(directory / "execution.json", vars(execution))
            if execution.timed_out:
                return incomplete_result(directory, "timeout", "Evaluation exceeded its time limit")
            if not (directory / "tests.json").exists():
                return incomplete_result(
                    directory, "runner_error", "Runner did not produce results"
                )
            result = read_json(directory / "tests.json")
            if execution.exit_code and result["status"] == "completed":
                return incomplete_result(directory, "runner_error", "Runner exited unsuccessfully")
            return result
    except (RuntimeError, OSError, ValueError) as exc:
        return incomplete_result(directory, "infrastructure_error", str(exc))


def check_reference(docker: Docker, image: str, instance: dict, run_dir: Path):
    buggy = run_version(docker, image, instance, run_dir, "buggy", reference=True)
    golden = run_version(docker, image, instance, run_dir, "golden", reference=True)
    paired = pair_results(buggy, golden)
    write_json(run_dir / "reference" / "results.json", paired)
    if not paired["has_fail_on_buggy_pass_on_golden"]:
        raise RuntimeError(
            "Reference pair check did not reproduce a fail/pass test; "
            "inspect reference/ before spending on generation"
        )


def archive_previous_evaluation(run_dir: Path):
    names = [
        name
        for name in ["buggy", "golden", "results.json", "report.md"]
        if (run_dir / name).exists()
    ]
    if names:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive = run_dir / "evaluations" / stamp
        archive.mkdir(parents=True)
        for name in names:
            shutil.move(run_dir / name, archive / name)


def evaluate(docker: Docker, image: str, instance: dict, run_dir: Path):
    manifest = verify_bundle(run_dir)
    archive_previous_evaluation(run_dir)
    buggy = run_version(docker, image, instance, run_dir, "buggy")
    golden = run_version(docker, image, instance, run_dir, "golden")
    result = pair_results(buggy, golden)
    result.update(
        instance_id=instance["instance_id"],
        artifact_sha256=manifest["sha256"],
        submission_compliant=manifest["compliant"],
        forbidden_changes=manifest["forbidden_changes"],
        existing_tests=docker.config.task.existing_tests,
        agent=read_json(run_dir / "agent" / "result.json"),
        coverage={v: read_json(run_dir / v / "coverage.json") for v in ["buggy", "golden"]},
    )
    result["diagnostic_only"] = not manifest["compliant"]
    write_json(run_dir / "results.json", result)
    return result
