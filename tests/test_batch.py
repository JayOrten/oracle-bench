from pathlib import Path

import pytest
import yaml
from fixtures import evaluation_result, judge_attempt

from oracle_bench.batch import load_batch_config, run_batch
from oracle_bench.batch.summary import _aggregate_judgments
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


def fake_result(
    run_dir: Path,
    instance: str,
    detected: bool = False,
    *,
    matrix_overrides: dict[str, int] | None = None,
) -> None:
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
    for key, count in (matrix_overrides or {}).items():
        matrix[key] = {"count": count, "test_ids": [f"test_{key}"] if count else []}
    write_json(
        paths.results,
        evaluation_result(
            instance_id=instance,
            matrix=matrix,
            coverage={
                "buggy": {"status": "available", "percent": 12.5},
                "golden": {"status": "unavailable"},
            },
        ),
    )
    write_json(run_dir / "status.json", {"state": "completed"})


def fake_judgment(
    run_dir: Path,
    *,
    status: str = "completed",
    target: str = "direct",
    trigger: str = "matches",
    oracle: str = "behaviorally_aligned",
    strategy: str = "return_value_or_status",
    verdict: str = "confirmed_issue_reproduction",
    cost: float | None = 0.02,
) -> None:
    paths = RunPaths.open(run_dir)
    paths.judge.root.mkdir(parents=True, exist_ok=True)
    paths.judge.rubric.write_text("rubric")
    if status == "completed":
        judgment = {
            "status": status,
            "issue_target_alignment": target,
            "trigger_alignment": trigger,
            "oracle_alignment": oracle,
            "test_strategy": strategy,
            "final_verdict": verdict,
            "rationale": "Synthetic batch fixture.",
        }
    elif status == "stale":
        judgment = {
            "status": "stale",
            "reason": "Evaluation changed.",
            "previous_judgment": {
                "status": "failed",
                "error": "old failure",
            },
        }
    else:
        judgment = {"status": status, "error": f"{status} fixture"}
    write_json(paths.judge.judgment, judgment)
    write_json(paths.judge.result, judge_attempt(status=status, cost_usd=cost))


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


def test_batch_aggregates_judge_labels_disagreements_and_costs(tmp_path):
    (tmp_path / "prompt.md").write_text("Generate tests")
    instances = ["unrelated-detected", "relevant-fail-both", "invalid", "stale", "disabled"]
    for instance in instances:
        write_run_config(tmp_path / f"{instance}.yaml", instance)
    manifest = tmp_path / "batch.yaml"
    write_batch_config(manifest, [f"{instance}.yaml" for instance in instances])

    def run_one(config):
        instance = config.source.instance
        run_dir = tmp_path / "runs" / instance
        if instance == "unrelated-detected":
            fake_result(run_dir, instance, detected=True)
            fake_judgment(
                run_dir,
                target="unrelated",
                trigger="wrong_path",
                oracle="behaviorally_misaligned",
                strategy="implementation_inspection",
                verdict="not_issue_relevant",
            )
        elif instance == "relevant-fail-both":
            fake_result(run_dir, instance, matrix_overrides={"fail_on_both": 1})
            fake_judgment(
                run_dir,
                target="partial",
                trigger="misses_required_condition",
                oracle="no_clear_oracle",
                strategy="no_meaningful_assertion",
                verdict="issue_relevant_not_confirmed",
            )
        elif instance == "invalid":
            fake_result(run_dir, instance)
            fake_judgment(run_dir, status="invalid_output", cost=0.01)
        elif instance == "stale":
            fake_result(run_dir, instance)
            fake_judgment(run_dir, status="stale", cost=None)
        else:
            fake_result(run_dir, instance)
        return run_dir

    batch_dir = run_batch(manifest, run_one=run_one)
    summary = read_json(batch_dir / "summary.json")
    judge = summary["judge"]

    assert summary["completed_evaluations"] == 5
    assert summary["matrix_detection_rate"] == 0.2
    assert summary["judge_confirmed_issue_reproduction_rate"] == 0
    assert summary["generation_cost_usd"] == 0.5
    assert summary["judge_cost_usd"] == 0.05
    assert summary["total_cost_usd"] == pytest.approx(0.55)
    assert judge["valid_judgments"] == 2
    assert judge["status_counts"] == {
        "completed": 2,
        "disabled": 1,
        "invalid_output": 1,
        "stale": 1,
    }
    assert judge["matrix_detection_by_final_verdict"]["detected"] == {"not_issue_relevant": 1}
    assert judge["oracle_alignment_by_matrix_cell_presence"]["fail_on_both"]["present"] == {
        "no_clear_oracle": 1
    }
    assert summary["jobs"][0]["judge"]["model"] == "judge-model"
    assert summary["jobs"][0]["judge"]["usage"]["input_tokens"] == 100

    report = (batch_dir / "report.md").read_text()
    assert "Judge-confirmed issue reproductions" in report
    assert "not_issue_relevant" in report


def test_failed_judgment_does_not_make_completed_batch_job_resumable(tmp_path):
    (tmp_path / "prompt.md").write_text("Generate tests")
    write_run_config(tmp_path / "one.yaml", "owner__one-1")
    manifest = tmp_path / "batch.yaml"
    write_batch_config(manifest, ["one.yaml"])

    def first_run(config):
        run_dir = tmp_path / "runs" / config.source.instance
        fake_result(run_dir, config.source.instance)
        fake_judgment(run_dir, status="failed")
        return run_dir

    batch_dir = run_batch(manifest, run_one=first_run)
    rerun = []
    run_batch(batch_dir, resume=True, run_one=lambda config: rerun.append(config))

    assert rerun == []
    assert read_json(batch_dir / "summary.json")["judge"]["status_counts"] == {"failed": 1}


def test_every_judge_label_is_counted_independently():
    labels = {
        "issue_target_alignment": [
            "direct",
            "partial",
            "adjacent",
            "unrelated",
            "indeterminate",
        ],
        "trigger_alignment": [
            "matches",
            "misses_required_condition",
            "wrong_path",
            "not_assessable",
        ],
        "oracle_alignment": [
            "behaviorally_aligned",
            "behaviorally_misaligned",
            "implementation_coupled",
            "no_clear_oracle",
            "not_assessable",
        ],
        "test_strategy": [
            "return_value_or_status",
            "exception_behavior",
            "state_or_artifact",
            "external_interaction",
            "resource_or_nondeterminism",
            "implementation_inspection",
            "no_meaningful_assertion",
        ],
        "final_verdict": [
            "confirmed_issue_reproduction",
            "issue_relevant_not_confirmed",
            "issue_relevant_but_invalid",
            "not_issue_relevant",
            "unassessable",
        ],
    }
    jobs = []
    for index in range(max(map(len, labels.values()))):
        judge = {
            "status": "completed",
            **{facet: values[index % len(values)] for facet, values in labels.items()},
        }
        jobs.append({"detected": index % 2 == 0, "matrix": {}, "judge": judge})

    aggregation = _aggregate_judgments(jobs)

    for facet, values in labels.items():
        assert set(aggregation["label_counts"][facet]) == set(values)
