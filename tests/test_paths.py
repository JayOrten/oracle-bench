from oracle_bench.paths import RunPaths


def test_run_paths_group_artifacts_by_lifecycle_stage(tmp_path):
    paths = RunPaths.create(tmp_path)

    assert paths.config == tmp_path / "inputs/config.resolved.yaml"
    assert paths.runtime == tmp_path / "image-build/runtime.json"
    assert paths.reference == tmp_path / "reference-check"
    assert paths.generation == tmp_path / "generation"
    assert paths.submission == tmp_path / "submission"
    assert paths.results == tmp_path / "evaluation/results.json"
    assert paths.evaluation_history == tmp_path / "evaluation-history"
    assert paths.ground_truth == tmp_path / "ground-truth"
