from pathlib import Path

import pytest
from fixtures import evaluation_result

from oracle_bench.io import digest, read_json, write_json
from oracle_bench.judge.agreement import (
    _agreement_for_facet,
    _comparison_group,
    analyze_agreement,
)
from oracle_bench.judge.contracts import (
    JUDGMENT_LABEL_KEYS,
    LlmJudgeIdentity,
    Rating,
    Ratings,
    RunEvaluation,
    RunProvenance,
    RunRatings,
)
from oracle_bench.paths import RunPaths
from oracle_bench.results import MATRIX_CELLS

DEFAULT_LABELS = {
    "issue_target_alignment": "direct",
    "trigger_alignment": "matches",
    "oracle_alignment": "behaviorally_aligned",
    "test_strategy": "return_value_or_status",
    "final_verdict": "confirmed_issue_reproduction",
}


def observation(left: str, right: str, instance: str) -> dict:
    return {
        "instance_id": instance,
        "run_dir": f"/runs/{instance}",
        "left_rater": "human:rater_1",
        "right_rater": "human:rater_2",
        "left": {"issue_target_alignment": left},
        "right": {"issue_target_alignment": right},
    }


def rating(status: str = "completed", **labels: str) -> Rating:
    values = DEFAULT_LABELS | labels if status == "completed" else None
    return Rating(status=status, labels=values)


def rated_instance(
    instance: str,
    *,
    llm: Rating,
    humans: dict[str, Rating],
) -> RunRatings:
    return RunRatings(
        run_dir=f"/runs/{instance}",
        instance_id=instance,
        matrix={},
        evaluation=RunEvaluation(),
        ratings=Ratings(llm=llm, humans=humans),
        provenance=RunProvenance(llm=LlmJudgeIdentity()),
    )


def judgment(target: str = "direct", verdict: str = "issue_relevant_not_confirmed") -> dict:
    return {
        "status": "completed",
        "issue_target_alignment": target,
        "trigger_alignment": "matches",
        "oracle_alignment": "behaviorally_aligned",
        "test_strategy": "return_value_or_status",
        "final_verdict": verdict,
        "rationale": "Synthetic agreement fixture.",
    }


def write_rated_run(
    run_dir: Path,
    instance: str,
    *,
    matrix_cell: str,
    llm_target: str = "direct",
    llm_verdict: str = "issue_relevant_not_confirmed",
    human_targets: dict[str, str] | None = None,
    compliant: bool = True,
) -> None:
    paths = RunPaths.create(run_dir)
    matrix = {key: {"count": int(key == matrix_cell), "test_ids": []} for key in MATRIX_CELLS}
    write_json(
        paths.results,
        evaluation_result(
            instance_id=instance,
            submission_compliant=compliant,
            matrix=matrix,
        ),
    )
    write_json(paths.judge.judgment, judgment(llm_target, llm_verdict))
    paths.judge.rubric.write_text("rubric fixture")
    paths.judge.prompt.write_text("prompt fixture")
    write_json(
        paths.judge.result,
        {
            "harness": "codex",
            "provider": "openai",
            "model": "judge-model",
            "harness_version": "1.2.3",
        },
    )
    for rater, target in (human_targets or {}).items():
        directory = paths.judge.human.judgments / rater
        write_json(directory / "judgment.json", judgment(target))
        write_json(
            directory / "provenance.json",
            {
                "container": f"oracle-judge-{rater}",
                "rater": rater,
                "network_mode": "none",
                "rubric_sha256": "e" * 64,
                "workspace_spec_sha256": "f" * 64,
            },
        )


def test_cohen_kappa_matches_hand_calculation_and_confusion_table():
    observations = [
        observation("direct", "direct", "one"),
        observation("direct", "partial", "two"),
        observation("partial", "partial", "three"),
        observation("partial", "partial", "four"),
    ]

    result = _agreement_for_facet(observations, "issue_target_alignment")

    assert result["observations"] == 4
    assert result["matches"] == 3
    assert result["raw_agreement"] == 0.75
    assert result["expected_agreement"] == 0.5
    assert result["cohen_kappa"] == 0.5
    assert result["confusion"] == {
        "direct": {"direct": 1, "partial": 1},
        "partial": {"partial": 2},
    }
    assert result["disagreements"][0]["instance_id"] == "two"


def test_kappa_is_undefined_when_chance_agreement_is_one():
    result = _agreement_for_facet(
        [observation("direct", "direct", "one")], "issue_target_alignment"
    )

    assert result["raw_agreement"] == 1
    assert result["expected_agreement"] == 1
    assert result["cohen_kappa"] is None


def test_comparison_group_scores_every_facet_independently():
    human = rating(
        trigger_alignment="misses_required_condition",
        final_verdict="issue_relevant_not_confirmed",
    )
    instance = rated_instance("one", llm=rating(), humans={"rater_1": human})

    group = _comparison_group([instance], [("human:rater_1", "llm")])

    assert set(group["facets"]) == set(JUDGMENT_LABEL_KEYS)
    assert group["facets"]["issue_target_alignment"]["matches"] == 1
    assert group["facets"]["oracle_alignment"]["matches"] == 1
    assert group["facets"]["test_strategy"]["matches"] == 1
    assert group["facets"]["trigger_alignment"]["matches"] == 0
    assert group["facets"]["final_verdict"]["matches"] == 0
    assert group["facets"]["trigger_alignment"]["disagreements"] == [
        {
            "instance_id": "one",
            "run_dir": "/runs/one",
            "left_rater": "human:rater_1",
            "right_rater": "llm",
            "left_label": "misses_required_condition",
            "right_label": "matches",
        }
    ]


def test_comparison_group_excludes_incomplete_ratings_and_counts_missing_pairs():
    instances = [
        rated_instance("complete", llm=rating(), humans={"rater_1": rating()}),
        rated_instance("missing", llm=rating(), humans={"rater_1": rating("missing")}),
        rated_instance("invalid", llm=rating("invalid_artifact"), humans={"rater_1": rating()}),
        rated_instance("stale", llm=rating(), humans={"rater_1": rating("stale")}),
    ]

    group = _comparison_group(instances, [("human:rater_1", "llm")])

    assert group["possible_pairs"] == 4
    assert group["available_pairs"] == 1
    assert group["missing_pairs"] == 3
    assert group["facets"]["final_verdict"]["observations"] == 1
    assert list(group["by_pair"]) == ["human:rater_1|llm"]


def test_headline_kappa_is_weighted_by_each_pairs_shared_observations():
    llm_targets = ["direct", "partial", "partial", "partial"]
    alice_targets = ["direct", "direct", "partial", "partial"]
    bob_targets = ["partial", "direct", None, None]
    instances = []
    for index, (llm_target, alice_target, bob_target) in enumerate(
        zip(llm_targets, alice_targets, bob_targets, strict=True), start=1
    ):
        humans = {
            "alice": rating(issue_target_alignment=alice_target),
            "bob": (
                rating(issue_target_alignment=bob_target)
                if bob_target is not None
                else rating("missing")
            ),
        }
        instances.append(
            rated_instance(
                str(index),
                llm=rating(issue_target_alignment=llm_target),
                humans=humans,
            )
        )

    group = _comparison_group(
        instances,
        [("human:alice", "llm"), ("human:bob", "llm")],
    )
    facet = group["facets"]["issue_target_alignment"]

    assert group["possible_pairs"] == 8
    assert group["available_pairs"] == 6
    assert facet["raw_agreement"] == 0.5
    assert facet["pairwise_cohen_kappa"] == {
        "human:alice|llm": 0.5,
        "human:bob|llm": -1.0,
    }
    assert facet["mean_pairwise_cohen_kappa"] == 0.0


def test_undefined_pair_kappa_is_not_included_in_headline_mean():
    instances = [
        rated_instance(
            "one",
            llm=rating(issue_target_alignment="direct"),
            humans={
                "constant": rating(issue_target_alignment="direct"),
                "variable": rating(issue_target_alignment="direct"),
            },
        ),
        rated_instance(
            "two",
            llm=rating(issue_target_alignment="partial"),
            humans={
                "constant": rating("missing"),
                "variable": rating(issue_target_alignment="partial"),
            },
        ),
    ]

    group = _comparison_group(
        instances,
        [("human:constant", "llm"), ("human:variable", "llm")],
    )
    facet = group["facets"]["issue_target_alignment"]

    assert facet["pairwise_cohen_kappa"] == {
        "human:constant|llm": None,
        "human:variable|llm": 1.0,
    }
    assert facet["mean_pairwise_cohen_kappa"] == 1.0


def test_empty_comparison_group_has_no_agreement_denominators():
    group = _comparison_group([], [])

    assert group["possible_pairs"] == 0
    assert group["available_pairs"] == 0
    assert group["missing_pairs"] == 0
    assert group["by_pair"] == {}
    for facet in group["facets"].values():
        assert facet["observations"] == 0
        assert facet["raw_agreement"] is None
        assert facet["mean_pairwise_cohen_kappa"] is None
        assert facet["pairwise_cohen_kappa"] == {}


def test_offline_report_preserves_missing_ratings_and_builds_stratified_sample(tmp_path):
    batch_dir = tmp_path / "batch"
    runs = []
    fixtures = [
        ("fp", "fail_on_buggy_pass_on_golden", "issue_relevant_not_confirmed", True),
        ("ff", "fail_on_both", "issue_relevant_not_confirmed", True),
        ("pp", "pass_on_both", "issue_relevant_not_confirmed", True),
        ("invalid", "pass_on_both", "issue_relevant_but_invalid", False),
        ("unrelated", "pass_on_both", "not_issue_relevant", True),
    ]
    for index, (instance, cell, verdict, compliant) in enumerate(fixtures):
        run_dir = tmp_path / "runs" / instance
        human_targets = {"rater_1": "direct", "rater_2": "direct"}
        if instance == "unrelated":
            human_targets = {"rater_1": "direct"}
        write_rated_run(
            run_dir,
            instance,
            matrix_cell=cell,
            llm_target="unrelated" if instance == "unrelated" else "direct",
            llm_verdict=verdict,
            human_targets=human_targets,
            compliant=compliant,
        )
        runs.append(
            {
                "index": index + 1,
                "config": f"{instance}.yaml",
                "state": "completed",
                "run_dir": str(run_dir),
                "error": None,
            }
        )
    write_json(
        batch_dir / "batch.resolved.json",
        {"name": "calibration", "execution": {}, "jobs": runs},
    )

    report = analyze_agreement(batch_dir, sample_per_stratum=1)
    summary = read_json(report.parent / "summary.json")
    calibration = read_json(report.parent / "calibration-sample.json")

    assert summary["comparisons"]["human_human"]["possible_pairs"] == 5
    assert summary["comparisons"]["human_human"]["available_pairs"] == 4
    assert summary["comparisons"]["human_human"]["missing_pairs"] == 1
    assert summary["comparisons"]["human_llm"]["possible_pairs"] == 10
    assert summary["comparisons"]["human_llm"]["available_pairs"] == 9
    assert summary["comparisons"]["human_llm"]["missing_pairs"] == 1
    assert set(calibration["strata"]) == {
        "fail_on_buggy_pass_on_golden",
        "fail_on_both",
        "pass_on_both",
        "invalid",
        "unrelated",
    }
    assert all(values["selected"] for values in calibration["strata"].values())
    assert calibration["ready_for_calibration"] is False
    assert summary["ratings_by_run"][0]["provenance"]["rubric_sha256"] == digest(b"rubric fixture")
    assert summary["ratings_by_run"][0]["provenance"]["llm"]["model"] == "judge-model"
    assert summary["provenance_versions"]["human_workspace_spec_sha256"] == {"f" * 64: 9}
    assert summary["ratings_by_run"][-1]["ratings"]["humans"]["rater_2"] == {"status": "missing"}
    assert "calibration" not in summary
    assert "Human–human agreement" in report.read_text()
    assert "Human–LLM agreement" in report.read_text()


def test_analysis_builds_all_human_pairs_and_each_human_llm_pair(tmp_path):
    batch_dir = tmp_path / "batch"
    runs = []
    for index in range(2):
        run_dir = tmp_path / "runs" / str(index)
        write_rated_run(
            run_dir,
            str(index),
            matrix_cell="pass_on_both",
            human_targets={"alice": "direct", "bob": "partial", "carol": "direct"},
        )
        runs.append({"run_dir": str(run_dir)})
    write_json(batch_dir / "batch.resolved.json", {"jobs": runs})

    report = analyze_agreement(batch_dir)
    comparisons = read_json(report.parent / "summary.json")["comparisons"]

    human_human = comparisons["human_human"]
    assert human_human["possible_pairs"] == 6
    assert human_human["available_pairs"] == 6
    assert set(human_human["by_pair"]) == {
        "human:alice|human:bob",
        "human:alice|human:carol",
        "human:bob|human:carol",
    }
    human_llm = comparisons["human_llm"]
    assert human_llm["possible_pairs"] == 6
    assert human_llm["available_pairs"] == 6
    assert set(human_llm["by_pair"]) == {
        "human:alice|llm",
        "human:bob|llm",
        "human:carol|llm",
    }


def test_agreement_rejects_invalid_sample_size(tmp_path):
    with pytest.raises(ValueError, match="at least 1"):
        analyze_agreement(tmp_path, sample_per_stratum=0)
