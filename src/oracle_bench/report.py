"""Present validated, machine-readable run artifacts as a Markdown audit report."""

from pathlib import Path

from oracle_bench.judge.contracts import (
    JUDGMENT_LABELS,
    JudgeAttempt,
    read_judge_attempt,
    read_judgment_state,
)
from oracle_bench.paths import RunPaths
from oracle_bench.repo_classification.contracts import (
    CLASSIFICATION_LABELS,
    latest_classification,
    read_classification_attempt,
)
from oracle_bench.results import (
    MATRIX_CELLS,
    VERSIONS,
    EvaluationResult,
    read_evaluation_result,
)


def report(paths: RunPaths) -> Path:
    results = read_evaluation_result(paths.results)
    judgment = read_judgment_state(paths)
    judge_attempt = read_judge_attempt(paths.judge.result) if paths.judge.result.is_file() else None
    lines = _summary_lines(results, judgment)
    lines.extend(_classification_lines(paths))
    lines.extend(_ground_truth_lines(paths))
    lines.extend(_matrix_lines(results))
    lines.extend(_failure_lines(results))
    lines.extend(_coverage_lines(results))
    lines.extend(_judge_lines(paths, judgment, judge_attempt))
    lines.extend(_artifact_lines(paths))
    lines.extend(_limits_lines(results))
    lines.extend(_usage_lines(results, judge_attempt))
    paths.report.write_text("\n".join(lines))
    return paths.report


def _summary_lines(results: EvaluationResult, judgment: dict) -> list[str]:
    scope = (
        "**calculated localized target**."
        if results.task_scope == "localized"
        else "**whole repository**."
    )
    lines = [
        f"# Oracle Bench: {results.instance_id}",
        "",
        "## Run summary",
        "",
        f"Overall result: **{_overall_state(results)}**.",
        "",
        f"Generation: **{results.agent.status}**. "
        f"Buggy evaluation: **{results.buggy_status}**. "
        f"Golden evaluation: **{results.golden_status}**. "
        f"Generated-test judgment: **{judgment['status']}**.",
        "",
        "Test-generation scope: " + scope,
        "",
        f"Existing repository test modules visible to agent: "
        f"**{'yes' if results.existing_tests == 'keep' else 'no'}**.",
        "",
    ]
    if results.task_scope == "localized":
        lines += [f"Calculated target: **{results.test_target}**.", ""]
    if results.diagnostic_only:
        lines += [
            "**Diagnostic only:** the agent changed files outside its allowed test artifact.",
            "",
            *[f"- `{name}`" for name in results.forbidden_changes],
            "",
        ]
    if results.agent.errors:
        error = results.agent.errors[-1]
        message = error.get("message") or error.get("error", {}).get("message", "See agent logs")
        lines += [f"Agent message: {message}", ""]
    if results.agent.status != "completed":
        lines += [
            f"Why this run completed with errors: generation ended with "
            f"**{results.agent.status}**. Any test files captured before it stopped were "
            "still evaluated.",
            "",
        ]
    return lines


def _overall_state(results: EvaluationResult) -> str:
    complete = (
        results.agent.status == "completed"
        and results.both_completed
        and results.submission_compliant
    )
    return "completed" if complete else "completed with errors"


def _classification_lines(paths: RunPaths) -> list[str]:
    classification, attempt = latest_classification(paths)
    status = classification["status"]
    lines = ["## Task classification", "", f"Status: **{status}**.", ""]
    attempt_result = attempt / "agent/result.json" if attempt is not None else None
    if attempt_result is not None and attempt_result.is_file():
        classifier = read_classification_attempt(attempt_result)
        lines += [
            f"Harness: `{classifier.harness}`. Provider: `{classifier.provider}`. "
            f"Model: `{classifier.model}`. Limit: "
            f"`{classifier.limit['kind']}={classifier.limit['value']}`.",
            "",
        ]
    if status == "completed":
        if classification["task_nature"] == "out_of_scope":
            lines += [f"Task nature: `{classification['task_nature']}`.", ""]
        else:
            lines += [
                "| Facet | Label |",
                "|---|---|",
                *[
                    f"| {label} | `{_classification_value(classification[key])}` |"
                    for key, label in CLASSIFICATION_LABELS.items()
                ],
                "",
            ]
        lines += ["Rationale:", "", *_blockquote(classification["rationale"]), ""]
    elif status == "missing":
        lines += ["No central classification has been saved for this problem.", ""]
    else:
        lines += [f"Reason: {classification['error']}", ""]
    return lines


def _classification_value(value: object) -> str:
    return ", ".join(value) if isinstance(value, list) else str(value)


def _matrix_lines(results: EvaluationResult) -> list[str]:
    return [
        "## Generated-test results",
        "",
        "These outcomes describe the tests written by the generation agent, run "
        "unchanged against the buggy and golden repository versions.",
        "",
        "### Paired outcomes",
        "",
        "| Outcome | Tests |",
        "|---|---:|",
        *[f"| {cell.label} | {results.matrix[cell].count} |" for cell in MATRIX_CELLS],
        "",
        f"Other/unmatched outcomes: {len(results.other_outcomes)}.",
        "",
        "Pass on both means the test did not distinguish these versions. "
        "It does not by itself establish an incorrect oracle.",
        "",
    ]


def _failure_lines(results: EvaluationResult) -> list[str]:
    return [
        "### Failure causes",
        "",
        "Call-phase failures are classified by the exception that escaped the test. "
        "This is diagnostic and does not change matrix scoring.",
        "",
        "| Version | Assertion failures | Other exceptions | Unknown |",
        "|---|---:|---:|---:|",
        *[
            f"| {version} | {results.failure_kinds[version]['assertion']} | "
            f"{results.failure_kinds[version]['exception']} | "
            f"{results.failure_kinds[version]['unknown']} |"
            for version in VERSIONS
        ],
        "",
    ]


def _ground_truth_lines(paths: RunPaths) -> list[str]:
    links = _existing_links(
        paths,
        [
            ("Original issue", paths.ground_truth / "issue.md"),
            ("Buggy-to-golden fix diff", paths.ground_truth / "fix.patch"),
        ],
    )
    return [
        "## Ground truth",
        "",
        "Private dataset evidence, retained for manual analysis and never exposed "
        "to the generation agent:",
        "",
        *(links or ["Ground-truth files are unavailable for this run."]),
        "",
    ]


def _coverage_lines(results: EvaluationResult) -> list[str]:
    lines = [
        "### Line coverage",
        "",
        "| Version | Covered / executable lines | Coverage |",
        "|---|---:|---:|",
    ]
    for version, coverage in results.coverage.items():
        if coverage.status == "available":
            lines.append(
                f"| {version} | {coverage.covered_lines} / {coverage.executable_lines} "
                f"| {coverage.percent:.2f}% |"
            )
        else:
            lines.append(f"| {version} | unavailable | — |")
    return [*lines, ""]


def _judge_lines(paths: RunPaths, judgment: dict, attempt: JudgeAttempt | None) -> list[str]:
    status = judgment["status"]
    lines = ["## Generated-test judgment", "", f"Status: **{status}**.", ""]
    if attempt:
        lines += [
            f"Harness: `{attempt.harness}`. "
            f"Provider: `{attempt.provider}`. "
            f"Model: `{attempt.model}`. "
            f"CLI version: `{attempt.harness_version}`. "
            f"Limit: `{attempt.limit['kind']}={attempt.limit['value']}`.",
            "",
        ]
    if status == "completed":
        lines += [
            "| Facet | Label |",
            "|---|---|",
            *[
                f"| {label} | `{judgment[key] if judgment[key] is not None else 'null'}` |"
                for key, label in JUDGMENT_LABELS.items()
            ],
            "",
            "Rationale:",
            "",
            *_blockquote(judgment["rationale"]),
            "",
        ]
    elif status == "stale":
        lines += [judgment["reason"], ""]
        previous = judgment.get("previous_judgment", {})
        if previous.get("status") == "completed":
            lines += [f"Previous issue-tested answer: `{previous['tests_issue']}`.", ""]
    elif status == "skipped":
        lines += [f"Reason: {judgment['reason']}", ""]
    elif status in {"invalid_output", "invalid_artifact", "failed", "timed_out"}:
        lines += [f"Reason: {judgment['error']}", ""]
    elif status == "missing":
        lines += ["The run was configured for judging, but no judgment is saved.", ""]
    else:
        lines += ["This run was not configured for generated-test judging.", ""]

    return lines


def _artifact_lines(paths: RunPaths) -> list[str]:
    execution = _existing_links(
        paths,
        [
            ("Paired outcomes and test IDs", paths.results),
            ("Frozen test manifest", paths.submission / "manifest.json"),
            ("Image provenance", paths.build / "images.json"),
            ("Readable agent session", paths.generation / "session.log"),
            ("Raw agent events", paths.generation / "trace.jsonl"),
            ("Workspace diff", paths.generation / "workspace.diff"),
            ("Buggy results", paths.evaluation / "buggy/tests.json"),
            ("Buggy log", paths.evaluation / "buggy/output.log"),
            ("Golden results", paths.evaluation / "golden/tests.json"),
            ("Golden log", paths.evaluation / "golden/output.log"),
        ],
    )
    judgment = _existing_links(
        paths,
        [
            ("Normalized judgment", paths.judge.judgment),
            ("Raw judge response", paths.judge.judgment_raw),
            ("Exact judge prompt", paths.judge.prompt),
            ("Frozen judge rubric", paths.judge.rubric),
            ("Judge workspace contents", paths.judge.workspace_spec),
            ("Judge trace", paths.judge.agent / "trace.jsonl"),
            ("Judge stderr", paths.judge.agent / "stderr.log"),
        ],
    )
    _, attempt = latest_classification(paths)
    classification = []
    if attempt is not None:
        classification = [
            f"- [{label}]({path.as_posix()})"
            for label, path in [
                ("Classification result", attempt / "classification.json"),
                ("Raw classifier response", attempt / "classification.raw.txt"),
                ("Classifier rubric", attempt / "inputs/rubric.md"),
                ("Classifier trace", attempt / "agent/trace.jsonl"),
            ]
            if path.is_file()
        ]
    lines = [
        "## Supporting files",
        "",
        "These are the underlying machine-readable results, logs, prompts, and traces.",
        "",
        "### Generated tests and execution",
        "",
        *(execution or ["No execution files are available."]),
        "",
    ]
    if classification:
        lines += ["### Task classification", "", *classification, ""]
    if judgment:
        lines += ["### Generated-test judgment", "", *judgment, ""]
    return lines


def _limits_lines(results: EvaluationResult) -> list[str]:
    visibility = (
        "Because existing tests were visible, generated tests may reuse their fixtures."
        if results.existing_tests == "keep"
        else "Existing test modules were removed from both final evaluation workspaces."
    )
    return [
        "## Limits of this exploratory run",
        "",
        "Git history and upstream retrieval have not been audited. "
        "The paired counts include only completed test executions on both versions. "
        "Skips, expected failures, setup/collection errors, and incomplete runs are separate. "
        "Coverage excludes existing tests as execution targets. " + visibility,
        "",
    ]


def _usage_lines(results: EvaluationResult, judge_attempt: JudgeAttempt | None) -> list[str]:
    generation = results.agent
    lines = [
        "## Model usage and cost",
        "",
        f"Generation wall time: {generation.duration_seconds or 0:.1f}s. "
        f"Reported token usage: `{generation.usage}`. " + _cost_text(generation.cost_usd),
        "",
    ]
    if judge_attempt:
        lines += [
            f"Judge wall time: {judge_attempt.duration_seconds or 0:.1f}s. "
            f"Reported token usage: `{judge_attempt.usage}`. " + _cost_text(judge_attempt.cost_usd),
            "",
        ]
    else:
        lines += ["Judge usage: unavailable.", ""]
    return lines


def _cost_text(cost: float | None) -> str:
    return (
        f"Harness-reported model cost: ${cost:.4f}."
        if cost is not None
        else "Monetary cost is unavailable unless supplied by the harness."
    )


def _existing_links(paths: RunPaths, entries: list[tuple[str, Path]]) -> list[str]:
    return [
        f"- [{label}]({path.relative_to(paths.root).as_posix()})"
        for label, path in entries
        if path.is_file()
    ]


def _blockquote(text: str) -> list[str]:
    return ["> " + line for line in text.splitlines()]
