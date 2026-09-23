import json
import re

import pytest
from fixtures import judge_attempt

from oracle_bench.io import write_json
from oracle_bench.paths import RunPaths
from oracle_bench.report import report
from oracle_bench.results import MATRIX_CELLS


@pytest.mark.parametrize(
    ("scope", "target", "expected_scope"),
    [
        ("repository", None, "Test-generation scope: **whole repository**."),
        (
            "localized",
            "package/module.py (function_name)",
            "Test-generation scope: **calculated localized target**.",
        ),
    ],
)
@pytest.mark.parametrize("cost", [None, 0.0378])
def test_report_renders_run_metadata(tmp_path, cost, scope, target, expected_scope):
    results = report_results(
        task_scope=scope,
        test_target=target,
        existing_tests="keep",
        agent={"status": "completed", "cost_usd": cost},
        failure_kinds={
            "buggy": {"assertion": 2, "exception": 1, "unknown": 0},
            "golden": {"assertion": 0, "exception": 1, "unknown": 0},
        },
    )
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(json.dumps(results))
    (paths.ground_truth / "issue.md").write_text("issue")
    (paths.ground_truth / "fix.patch").write_text("patch")
    text = report(paths).read_text()
    assert ("$0.0378" in text) == (cost is not None)
    assert ("Monetary cost is unavailable" in text) == (cost is None)
    assert "Existing repository test modules visible to agent: **yes**" in text
    assert expected_scope in text
    assert ("Calculated target: **package/module.py (function_name)**." in text) == (
        scope == "localized"
    )
    assert "[Original issue](ground-truth/issue.md)" in text
    assert "[Buggy-to-golden fix diff](ground-truth/fix.patch)" in text
    assert "| buggy | 2 | 1 | 0 |" in text
    assert "Status: **disabled**" in text


def report_results(**changes):
    """A complete evaluation result; tests override only what they exercise."""
    results = {
        "instance_id": "test-instance",
        "artifact_sha256": "a" * 64,
        "submission_compliant": True,
        "forbidden_changes": [],
        "task_scope": "repository",
        "test_target": None,
        "existing_tests": "hide_all",
        "agent": {
            "status": "completed",
            "cost_usd": 0.125,
            "duration_seconds": 4,
            "usage": {"input_tokens": 12},
        },
        "buggy_status": "completed",
        "golden_status": "completed",
        "matrix": {key: {"count": 0, "test_ids": []} for key in MATRIX_CELLS},
        "other_outcomes": [],
        "tests": [],
        "failure_kinds": {
            "buggy": {"assertion": 0, "exception": 0, "unknown": 0},
            "golden": {"assertion": 0, "exception": 0, "unknown": 0},
        },
        "coverage": {},
    }
    results.update(changes)
    return results


def completed_judgment():
    return {
        "status": "completed",
        "no_attempt_reason": None,
        "tests_issue": "yes",
        "attempt_detail": "correct_assertion",
        "cheating": "no",
        "rationale": "The generated assertion reaches the issue and distinguishes both revisions.",
    }


def test_report_renders_completed_judge_with_provenance_cost_and_supporting_files(tmp_path):
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(json.dumps(report_results()))
    paths.judge.judgment.write_text(json.dumps(completed_judgment()))
    write_targets = [
        paths.judge.judgment_raw,
        paths.judge.prompt,
        paths.judge.rubric,
        paths.judge.workspace_spec,
        paths.judge.agent / "trace.jsonl",
        paths.judge.agent / "stderr.log",
    ]
    for path in write_targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence")
    write_json(
        paths.judge.result,
        judge_attempt(
            harness="claude",
            provider="anthropic",
            model="judge-model",
            harness_version="2.1.263",
            duration_seconds=3,
            usage={"input_tokens": 20},
            cost_usd=0.025,
        ),
    )

    text = report(paths).read_text()

    assert "Status: **completed**" in text
    assert "| Do the generated tests attempt to test the issue? | `yes` |" in text
    assert "| Attempt detail | `correct_assertion` |" in text
    assert "| No-attempt reason | `null` |" in text
    assert "> The generated assertion reaches the issue" in text
    assert "Model: `judge-model`" in text
    assert "Generation wall time: 4.0s" in text and "$0.1250" in text
    assert "Judge wall time: 3.0s" in text and "$0.0250" in text
    assert "[Judge workspace contents](judge/workspace-spec.json)" in text
    for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
        assert (tmp_path / target).is_file(), target


@pytest.mark.parametrize(
    "judgment,expected",
    [
        (
            {"status": "invalid_output", "error": "bad JSON"},
            "Reason: bad JSON",
        ),
        (
            {"status": "failed", "error": "provider failed"},
            "Reason: provider failed",
        ),
        (
            {"status": "timed_out", "error": "deadline"},
            "Reason: deadline",
        ),
        (
            {"status": "skipped", "reason": "generation failed"},
            "Reason: generation failed",
        ),
        (
            {
                "status": "stale",
                "reason": "Evaluation changed.",
                "previous_judgment": completed_judgment(),
            },
            "Previous issue-tested answer: `yes`.",
        ),
    ],
)
def test_report_renders_noncompleted_judge_states(tmp_path, judgment, expected):
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(json.dumps(report_results()))
    paths.judge.judgment.write_text(json.dumps(judgment))

    text = report(paths).read_text()

    assert f"Status: **{judgment['status']}**" in text
    assert expected in text
    assert "| Issue-target alignment |" not in text


def test_report_distinguishes_configured_missing_judgment(tmp_path):
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(json.dumps(report_results()))
    paths.judge.rubric.write_text("rubric")

    text = report(paths).read_text()

    assert "Status: **missing**" in text
    assert "no judgment is saved" in text


def test_report_renders_a_run_without_judge_configuration(tmp_path):
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(json.dumps(report_results()))

    text = report(paths).read_text()

    assert "Status: **disabled**" in text
    assert "not configured for generated-test judging" in text


def test_report_derives_diagnostic_status_from_submission_compliance(tmp_path):
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(
        json.dumps(
            report_results(
                submission_compliant=False,
                forbidden_changes=["src/application.py"],
            )
        )
    )

    text = report(paths).read_text()

    assert "**Diagnostic only:**" in text
    assert "`src/application.py`" in text


def test_report_explains_generation_timeout_and_labels_generated_test_results(tmp_path):
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(
        json.dumps(report_results(agent={"status": "timeout", "duration_seconds": 60}))
    )

    text = report(paths).read_text()

    assert "Overall result: **completed with errors**" in text
    assert "generation ended with **timeout**" in text
    assert "Any test files captured before it stopped were still evaluated" in text
    assert "## Generated-test results" in text
    assert "These outcomes describe the tests written by the generation agent" in text
    assert "## Supporting files" in text
    assert "Audit artifacts" not in text


def test_report_does_not_regenerate_the_generation_transcript(tmp_path):
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(json.dumps(report_results()))
    session = paths.generation / "session.log"
    session.write_text("frozen generation transcript\n")
    (paths.generation / "trace.jsonl").write_text('{"type": "newer-event"}\n')

    report(paths)

    assert session.read_text() == "frozen generation transcript\n"


def test_report_renders_central_task_classification_and_provenance(tmp_path, monkeypatch):
    paths = RunPaths.create(tmp_path / "run")
    paths.results.write_text(json.dumps(report_results()))
    attempt = tmp_path / "classifications/test-instance/attempt"
    evidence = [
        attempt / "classification.json",
        attempt / "classification.raw.txt",
        attempt / "inputs/rubric.md",
        attempt / "agent/trace.jsonl",
    ]
    for path in evidence:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence")
    write_json(
        attempt / "agent/result.json",
        {
            "status": "completed",
            "duration_seconds": 2,
            "usage": {"input_tokens": 10},
            "cost_usd": 0.01,
            "errors": [],
            "harness": "codex",
            "provider": "openrouter",
            "model": "classifier-model",
            "harness_version": "0.153.4",
            "limit": {"kind": "wall_seconds", "value": 90},
        },
    )
    classification = {
        "status": "completed",
        "task_nature": "behavioral_bug",
        "defect_mechanisms": ["control_logic", "data_state"],
        "primary_assertion_target": "return_value_or_status",
        "required_test_setup": "sequence",
        "code_only_oracle_availability": "repository_pattern",
        "required_test_scope": "component",
        "benchmark_quality": "usable",
        "rationale": "A nearby implementation establishes the expected behavior.",
    }
    monkeypatch.setattr(
        "oracle_bench.report.latest_classification", lambda run_paths: (classification, attempt)
    )

    text = report(paths).read_text()

    assert "## Task classification" in text
    assert "| Defect mechanisms | `control_logic, data_state` |" in text
    assert "| Code-only oracle availability | `repository_pattern` |" in text
    assert "> A nearby implementation establishes the expected behavior." in text
    assert "Model: `classifier-model`" in text
    assert "`wall_seconds=90`" in text
    assert f"[Classification result]({attempt / 'classification.json'})" in text
    assert f"[Classifier rubric]({attempt / 'inputs/rubric.md'})" in text
    assert f"[Classifier trace]({attempt / 'agent/trace.jsonl'})" in text


@pytest.mark.parametrize(
    ("classification", "expected"),
    [
        (
            {
                "status": "completed",
                "task_nature": "out_of_scope",
                "rationale": "This task adds a new feature.",
            },
            "Task nature: `out_of_scope`.",
        ),
        (
            {"status": "invalid_artifact", "error": "latest attempt is incomplete"},
            "Reason: latest attempt is incomplete",
        ),
    ],
)
def test_report_renders_out_of_scope_and_unsuccessful_classifications(
    tmp_path, monkeypatch, classification, expected
):
    paths = RunPaths.create(tmp_path)
    paths.results.write_text(json.dumps(report_results()))
    monkeypatch.setattr(
        "oracle_bench.report.latest_classification", lambda run_paths: (classification, None)
    )

    text = report(paths).read_text()

    assert expected in text
