from oracle_bench.evaluate import archive_previous_evaluation
from oracle_bench.harnesses.codex import parse_trace
from oracle_bench.paths import RunPaths
from oracle_bench.run import completion_state


def test_reevaluation_archives_results_but_preserves_generated_tests(tmp_path):
    paths = RunPaths.create(tmp_path)
    (paths.evaluation / "buggy").mkdir()
    (paths.evaluation / "buggy" / "tests.json").write_text("old")
    (paths.submission / "manifest.json").write_text("keep")
    archive_previous_evaluation(tmp_path)
    assert not (paths.evaluation / "buggy").exists()
    assert next(paths.evaluation_history.glob("*/buggy/tests.json")).read_text() == "old"
    assert (paths.submission / "manifest.json").read_text() == "keep"


def test_trace_usage_is_reported_without_inventing_cost(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text('not-json\n{"type":"turn.completed","usage":{"input_tokens":12}}\n')
    result = parse_trace(path)
    assert result["usage"] == {"input_tokens": 12}
    assert result["cost_usd"] is None
    assert result["unparsed_trace_lines"] == 1


def test_recovered_stream_error_does_not_mean_the_turn_failed(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(
        '{"type":"error","message":"reconnecting"}\n'
        '{"type":"turn.completed","usage":{"output_tokens":2}}\n'
    )
    result = parse_trace(path)
    assert result["turn_completed"] and not result["turn_failed"]
    assert result["errors"]


def test_failed_agent_is_not_reported_as_a_successful_pipeline():
    result = {
        "agent": {"status": "failed"},
        "buggy_status": "no_tests",
        "golden_status": "no_tests",
        "submission_compliant": True,
    }
    assert completion_state(result) == "completed_with_errors"
    result.update(
        agent={"status": "completed"}, buggy_status="completed", golden_status="completed"
    )
    assert completion_state(result) == "completed"
