from pathlib import Path

import yaml

from oracle_bench.batch import load_batch_config, run_batch
from oracle_bench.io import read_json, write_json
from oracle_bench.paths import RunPaths


def write_run_config(path: Path, instance: str) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "source": {"instance": instance},
                "agent": {"model": "test-model"},
                "task": {"prompt": "prompt.md"},
                "output": "runs",
            }
        )
    )


def write_batch_config(path: Path, jobs: list[str]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "name": "test-batch",
                "jobs": [{"config": job} for job in jobs],
                "output": "batches",
            }
        )
    )


def fake_result(run_dir: Path, instance: str, detected: bool = False) -> None:
    paths = RunPaths.create(run_dir)
    matrix = {
        "pass_on_both": {"count": 2, "test_ids": []},
        "fail_on_buggy_pass_on_golden": {
            "count": int(detected),
            "test_ids": ["test_detects_bug"] if detected else [],
        },
        "pass_on_buggy_fail_on_golden": {"count": 0, "test_ids": []},
        "fail_on_both": {"count": 0, "test_ids": []},
    }
    write_json(
        paths.results,
        {
            "instance_id": instance,
            "submission_compliant": True,
            "matrix": matrix,
            "buggy_status": "completed",
            "golden_status": "completed",
            "coverage": {
                "buggy": {"status": "available", "percent": 12.5},
                "golden": {"status": "unavailable"},
            },
            "agent": {"status": "completed", "cost_usd": 0.1, "duration_seconds": 3},
        },
    )
    write_json(run_dir / "status.json", {"state": "completed"})


def test_batch_paths_are_relative_and_all_jobs_validate(tmp_path):
    (tmp_path / "prompt.md").write_text("Generate tests")
    write_run_config(tmp_path / "one.yaml", "owner__one-1")
    write_run_config(tmp_path / "two.yaml", "owner__two-2")
    manifest = tmp_path / "batch.yaml"
    write_batch_config(manifest, ["one.yaml", "two.yaml"])

    config, paths = load_batch_config(manifest)

    assert config.output == str(tmp_path / "batches")
    assert paths == [tmp_path / "one.yaml", tmp_path / "two.yaml"]


def test_batch_continues_after_failure_and_aggregates_results(tmp_path):
    (tmp_path / "prompt.md").write_text("Generate tests")
    write_run_config(tmp_path / "one.yaml", "owner__one-1")
    write_run_config(tmp_path / "two.yaml", "owner__two-2")
    manifest = tmp_path / "batch.yaml"
    write_batch_config(manifest, ["one.yaml", "two.yaml"])
    calls = []

    def run_one(config):
        calls.append(config.source.instance)
        if config.source.instance == "owner__one-1":
            raise RuntimeError("setup failed")
        run_dir = tmp_path / "runs" / config.source.instance
        fake_result(run_dir, config.source.instance, detected=True)
        return run_dir

    batch_dir = run_batch(manifest, run_one=run_one)
    summary = read_json(batch_dir / "summary.json")

    assert calls == ["owner__one-1", "owner__two-2"]
    assert summary["attempted"] == 2
    assert summary["completed_with_results"] == 1
    assert summary["detected"] == 1
    assert summary["detection_rate_attempted"] == 0.5
    assert read_json(batch_dir / "status.json")["state"] == "completed_with_errors"


def test_resume_skips_completed_jobs_and_retries_failed_job(tmp_path):
    (tmp_path / "prompt.md").write_text("Generate tests")
    write_run_config(tmp_path / "one.yaml", "owner__one-1")
    write_run_config(tmp_path / "two.yaml", "owner__two-2")
    manifest = tmp_path / "batch.yaml"
    write_batch_config(manifest, ["one.yaml", "two.yaml"])

    def first_run(config):
        if config.source.instance == "owner__two-2":
            raise RuntimeError("temporary failure")
        run_dir = tmp_path / "runs" / config.source.instance
        fake_result(run_dir, config.source.instance)
        return run_dir

    batch_dir = run_batch(manifest, run_one=first_run)
    resumed = []

    def resumed_run(config):
        resumed.append(config.source.instance)
        run_dir = tmp_path / "runs" / config.source.instance
        fake_result(run_dir, config.source.instance, detected=True)
        return run_dir

    assert run_batch(batch_dir, resume=True, run_one=resumed_run) == batch_dir
    assert resumed == ["owner__two-2"]
    assert read_json(batch_dir / "status.json")["state"] == "completed"
