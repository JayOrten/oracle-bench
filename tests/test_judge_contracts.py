import json

import pytest

from oracle_bench.io import read_json, write_json
from oracle_bench.judge.contracts import (
    MAX_RATIONALE_LENGTH,
    CompletedJudgment,
    failed_judgment,
    mark_judgments_stale,
    parse_judgment,
)
from oracle_bench.paths import RunPaths


def labels(**changes):
    value = {
        "issue_target_alignment": "direct",
        "trigger_alignment": "matches",
        "oracle_alignment": "behaviorally_aligned",
        "test_strategy": "exception_behavior",
        "final_verdict": "unassessable",
        "rationale": "The generated assertion reaches the relevant path.",
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(
    "field,value",
    [
        ("issue_target_alignment", value)
        for value in ["direct", "partial", "adjacent", "unrelated", "indeterminate"]
    ]
    + [
        ("trigger_alignment", value)
        for value in ["matches", "misses_required_condition", "wrong_path", "not_assessable"]
    ]
    + [
        ("oracle_alignment", value)
        for value in [
            "behaviorally_aligned",
            "behaviorally_misaligned",
            "implementation_coupled",
            "no_clear_oracle",
            "not_assessable",
        ]
    ]
    + [
        ("test_strategy", value)
        for value in [
            "return_value_or_status",
            "exception_behavior",
            "state_or_artifact",
            "external_interaction",
            "resource_or_nondeterminism",
            "implementation_inspection",
            "no_meaningful_assertion",
        ]
    ],
)
def test_parser_accepts_every_facet_label(field, value):
    result = parse_judgment(json.dumps(labels(**{field: value})), has_relevant_fail_to_pass=False)

    assert isinstance(result, CompletedJudgment)
    assert getattr(result, field) == value


@pytest.mark.parametrize(
    "changes,has_fail_to_pass",
    [
        (
            {"final_verdict": "confirmed_issue_reproduction"},
            True,
        ),
        (
            {
                "issue_target_alignment": "partial",
                "final_verdict": "issue_relevant_not_confirmed",
            },
            False,
        ),
        (
            {
                "issue_target_alignment": "direct",
                "final_verdict": "issue_relevant_but_invalid",
            },
            False,
        ),
        (
            {
                "issue_target_alignment": "unrelated",
                "final_verdict": "not_issue_relevant",
            },
            True,
        ),
        ({"final_verdict": "unassessable"}, False),
    ],
)
def test_parser_accepts_every_consistent_verdict(changes, has_fail_to_pass):
    result = parse_judgment(
        json.dumps(labels(**changes)), has_relevant_fail_to_pass=has_fail_to_pass
    )

    assert result.status == "completed"


def test_parser_accepts_one_json_markdown_fence():
    raw = "```json\n" + json.dumps(labels()) + "\n```"
    assert parse_judgment(raw, has_relevant_fail_to_pass=False).status == "completed"


@pytest.mark.parametrize(
    "raw",
    [
        "before " + json.dumps(labels()),
        "```json\n" + json.dumps(labels()) + "\n```\nafter",
        "{not json}",
        json.dumps([]),
        json.dumps({key: value for key, value in labels().items() if key != "rationale"}),
        json.dumps(labels(unexpected="field")),
        json.dumps(labels(trigger_alignment="almost")),
        json.dumps(labels(rationale="   ")),
        json.dumps(labels(rationale="x" * (MAX_RATIONALE_LENGTH + 1))),
        json.dumps(labels(rationale=3)),
    ],
)
def test_parser_returns_explicit_invalid_output(raw):
    result = parse_judgment(raw, has_relevant_fail_to_pass=False)

    assert result.status == "invalid_output"
    assert result.error


@pytest.mark.parametrize(
    "changes,has_fail_to_pass",
    [
        ({"final_verdict": "confirmed_issue_reproduction"}, False),
        (
            {
                "oracle_alignment": "behaviorally_misaligned",
                "final_verdict": "confirmed_issue_reproduction",
            },
            True,
        ),
        ({"final_verdict": "not_issue_relevant"}, False),
        (
            {
                "issue_target_alignment": "adjacent",
                "final_verdict": "issue_relevant_not_confirmed",
            },
            False,
        ),
        (
            {
                "issue_target_alignment": "unrelated",
                "final_verdict": "issue_relevant_but_invalid",
            },
            False,
        ),
    ],
)
def test_parser_rejects_contradictory_labels(changes, has_fail_to_pass):
    result = parse_judgment(
        json.dumps(labels(**changes)), has_relevant_fail_to_pass=has_fail_to_pass
    )

    assert result.status == "invalid_output"


def test_failure_results_distinguish_failure_from_timeout():
    assert failed_judgment("harness exited").status == "failed"
    assert failed_judgment("deadline exceeded", timed_out=True).status == "timed_out"


def test_marking_stale_retains_every_previous_annotation(tmp_path):
    paths = RunPaths.create(tmp_path)
    previous = parse_judgment(
        json.dumps(labels(final_verdict="issue_relevant_not_confirmed")),
        has_relevant_fail_to_pass=False,
    )
    human = paths.judge.human.judgments / "rater_1/judgment.json"
    human.parent.mkdir(parents=True)
    for path in (paths.judge.judgment, human):
        write_json(path, previous.model_dump())

    mark_judgments_stale(paths)

    for path in (paths.judge.judgment, human):
        stale = read_json(path)
        assert stale["status"] == "stale"
        assert stale["previous_judgment"] == previous.model_dump()

    # Replacing the evidence twice keeps the original annotation instead of nesting.
    first = read_json(paths.judge.judgment)
    mark_judgments_stale(paths)
    assert read_json(paths.judge.judgment) == first
