"""Aggregate saved run artifacts into one batch summary and Markdown report.

Like `report.py` for a single run, this reads artifacts and writes artifacts. It
never executes a run, so a summary can be rebuilt from saved evidence alone.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

from oracle_bench.io import read_json, write_json
from oracle_bench.judge.contracts import JUDGMENT_LABEL_KEYS, read_judgment_state
from oracle_bench.paths import RunPaths
from oracle_bench.results import MATRIX_CELLS, read_evaluation_result


def summarize_job(job: dict) -> dict:
    summary = {
        "index": job["index"],
        "config": job["config"],
        "state": job["state"],
        "run_dir": job["run_dir"],
        "error": job["error"],
    }
    if not job["run_dir"]:
        return summary
    paths = RunPaths.open(Path(job["run_dir"]))
    if not paths.results.is_file():
        return summary
    result = read_evaluation_result(paths.results)
    summary.update(
        instance_id=result.instance_id,
        compliant=result.submission_compliant,
        detected=result.detected,
        matrix={key: cell.count for key, cell in result.matrix.items()},
        buggy_status=result.buggy_status,
        golden_status=result.golden_status,
        coverage_percent={
            version: coverage.percent if coverage.status == "available" else None
            for version, coverage in result.coverage.items()
        },
        generation_cost_usd=result.agent.cost_usd,
        generation_duration_seconds=result.agent.duration_seconds,
        judge=_summarize_judge(paths),
    )
    return summary


def _summarize_judge(paths: RunPaths) -> dict:
    """Read the normalized annotation and attempt metadata for one run."""
    judgment = read_judgment_state(paths)
    status = judgment["status"]
    summary = {"status": status}
    if status == "completed":
        summary.update({key: judgment[key] for key in JUDGMENT_LABEL_KEYS})
        summary["rationale"] = judgment["rationale"]
    elif status in {"invalid_output", "invalid_artifact", "failed", "timed_out"}:
        summary["error"] = judgment.get("error")
    elif status == "stale":
        summary["reason"] = judgment.get("reason")

    attempt_path = paths.judge.result
    if attempt_path.is_file():
        attempt = read_json(attempt_path)
        summary.update(
            harness=attempt["harness"],
            provider=attempt["provider"],
            model=attempt["model"],
            harness_version=attempt["harness_version"],
            limit=attempt["limit"],
            usage=attempt["usage"],
            cost_usd=attempt["cost_usd"],
            duration_seconds=attempt["duration_seconds"],
        )
    return summary


def write_summary(batch_dir: Path, name: str, jobs: list[dict]) -> dict:
    job_summaries = [summarize_job(job) for job in jobs]
    attempted = sum(job["state"] != "pending" for job in jobs)
    completed = sum("matrix" in job for job in job_summaries)
    completed_evaluations = sum(
        job.get("buggy_status") == job.get("golden_status") == "completed" for job in job_summaries
    )
    detected = sum(bool(job.get("detected")) for job in job_summaries)
    matrix = {
        key: sum(job.get("matrix", {}).get(key, 0) for job in job_summaries) for key in MATRIX_CELLS
    }
    generation_costs = [
        job["generation_cost_usd"]
        for job in job_summaries
        if job.get("generation_cost_usd") is not None
    ]
    judge_costs = [
        job["judge"]["cost_usd"]
        for job in job_summaries
        if job.get("judge", {}).get("cost_usd") is not None
    ]
    judge_aggregation = _aggregate_judgments(job_summaries)
    generation_cost = sum(generation_costs) if generation_costs else None
    judge_cost = sum(judge_costs) if judge_costs else None
    summary = {
        "name": name,
        "planned": len(jobs),
        "attempted": attempted,
        "completed_with_results": completed,
        "completed_evaluations": completed_evaluations,
        "detected": detected,
        # Match SWE-bench's resolved/submitted denominator while naming our distinct metric.
        "detection_rate_attempted": detected / attempted if attempted else None,
        "matrix_detection_rate": (
            detected / completed_evaluations if completed_evaluations else None
        ),
        "judge_tests_issue_yes_rate": (
            judge_aggregation["tests_issue_yes"] / judge_aggregation["valid_judgments"]
            if judge_aggregation["valid_judgments"]
            else None
        ),
        # Generation and judging are separate model calls, so keep their costs separable.
        "generation_cost_usd": generation_cost,
        "judge_cost_usd": judge_cost,
        "total_cost_usd": (
            None
            if generation_cost is None and judge_cost is None
            else (generation_cost or 0) + (judge_cost or 0)
        ),
        "matrix": matrix,
        "judge": judge_aggregation,
        "jobs": job_summaries,
    }
    write_json(batch_dir / "summary.json", summary)
    _write_report(batch_dir, summary)
    return summary


def _aggregate_judgments(jobs: list[dict]) -> dict:
    """Aggregate completed labels separately from judge execution failures."""
    eligible = [job for job in jobs if "matrix" in job]
    status_counts = Counter(job.get("judge", {}).get("status", "missing") for job in eligible)
    valid = [job for job in eligible if job.get("judge", {}).get("status") == "completed"]
    label_counts = {
        key: dict(sorted(Counter(job["judge"][key] or "null" for job in valid).items()))
        for key in JUDGMENT_LABEL_KEYS
    }

    detection_by_issue_answer = _cross_tab(
        valid,
        row=lambda job: "detected" if job.get("detected") else "not_detected",
        column=lambda job: job["judge"]["tests_issue"],
    )
    attempt_detail_by_matrix_presence = {
        matrix_key: _cross_tab(
            valid,
            row=lambda job, key=matrix_key: (
                "present" if job.get("matrix", {}).get(key, 0) > 0 else "absent"
            ),
            column=lambda job: job["judge"]["attempt_detail"] or "null",
        )
        for matrix_key in MATRIX_CELLS
    }
    return {
        "eligible_runs": len(eligible),
        "valid_judgments": len(valid),
        "tests_issue_yes": sum(job["judge"]["tests_issue"] == "yes" for job in valid),
        "status_counts": dict(sorted(status_counts.items())),
        "label_counts": label_counts,
        "matrix_detection_by_tests_issue": detection_by_issue_answer,
        "attempt_detail_by_matrix_cell_presence": attempt_detail_by_matrix_presence,
    }


def _cross_tab(
    jobs: list[dict], *, row: Callable[[dict], str], column: Callable[[dict], str]
) -> dict:
    table = defaultdict(Counter)
    for job in jobs:
        table[row(job)][column(job)] += 1
    return {row_name: dict(sorted(counts.items())) for row_name, counts in sorted(table.items())}


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _write_report(batch_dir: Path, summary: dict) -> None:
    lines = _headline_lines(summary)
    lines += _job_table_lines(summary["jobs"])
    lines += [
        "",
        "Aggregate paired-test counts: "
        + ", ".join(f"`{key}`={count}" for key, count in summary["matrix"].items())
        + ".",
        "",
        "## Judge label frequencies",
        "",
    ]
    lines += _label_frequency_lines(summary["judge"]["label_counts"])
    lines += [
        "See [summary.json](summary.json) for machine-readable per-instance details.",
        "",
    ]
    (batch_dir / "report.md").write_text("\n".join(lines))


def _headline_lines(summary: dict) -> list[str]:
    """The header: totals, detection rates, and the start of the per-instance table."""
    return [
        f"# Oracle Bench batch: {summary['name']}",
        "",
        f"Planned: **{summary['planned']}**. Attempted: **{summary['attempted']}**. "
        f"Completed with results: **{summary['completed_with_results']}**. Completed paired "
        f"evaluations: **{summary['completed_evaluations']}**.",
        "",
        f"Matrix detections: **{summary['detected']}** of "
        f"**{summary['completed_evaluations']}** completed paired evaluations "
        f"(**{_percent(summary['matrix_detection_rate'])}**). The rate over all attempted "
        f"instances is **{_percent(summary['detection_rate_attempted'])}**.",
        "",
        "An instance is detected when a compliant submission has at least one test that fails "
        "on buggy and passes on golden. Incomplete and diagnostic-only runs never count as "
        "detected.",
        "",
        f"Judge says tests attempt the issue: **{summary['judge']['tests_issue_yes']}** of "
        f"**{summary['judge']['valid_judgments']}** valid judgments "
        f"(**{_percent(summary['judge_tests_issue_yes_rate'])}**).",
        "",
        "| Instance | State | Matrix detection | Attempts issue? | Attempt detail | No-attempt reason "
        "| Cheating | Generation cost | Judge cost |",
        "|---|---|---:|---|---|---|---|---:|---:|",
    ]


def _job_table_lines(jobs: list[dict]) -> list[str]:
    """One table row per job. Links to the run's own report if there is one."""
    lines = []
    for job in jobs:
        instance = job.get("instance_id", Path(job["config"]).stem)
        if job.get("run_dir"):
            report = Path(job["run_dir"]) / "report.md"
            instance = f"[{instance}]({report.as_posix()})"
        judge = job.get("judge", {})
        generation_cost = job.get("generation_cost_usd")
        judge_cost = judge.get("cost_usd")
        lines.append(
            f"| {instance} | {job['state']} | {'yes' if job.get('detected') else 'no'} "
            f"| {judge.get('tests_issue') or judge.get('status', 'missing')} "
            f"| {judge.get('attempt_detail') or '—'} "
            f"| {judge.get('no_attempt_reason') or '—'} "
            f"| {judge.get('cheating') or '—'} "
            f"| {'—' if generation_cost is None else f'${generation_cost:.4f}'} "
            f"| {'—' if judge_cost is None else f'${judge_cost:.4f}'} |"
        )
    return lines


def _label_frequency_lines(label_counts: dict) -> list[str]:
    """One small table per judged facet. Facets with no ratings show a zero row."""
    lines = []
    for facet, counts in label_counts.items():
        lines += [f"### `{facet}`", "", "| Label | Count |", "|---|---:|"]
        lines += [f"| `{label}` | {count} |" for label, count in counts.items()]
        if not counts:
            lines.append("| — | 0 |")
        lines.append("")
    return lines
