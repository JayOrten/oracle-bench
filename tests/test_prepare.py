from oracle_bench.container_helpers.prepare import remove_existing_tests


def test_remove_existing_tests_expands_files_directories_and_nested_globs(tmp_path):
    production = tmp_path / "package" / "module.py"
    nested_test = tmp_path / "package" / "feature" / "tests" / "test_feature.py"
    top_level_test = tmp_path / "test_project.py"
    unrelated = tmp_path / "examples" / "test_example.py"
    for path in [production, nested_test, top_level_test, unrelated]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content")

    remove_existing_tests(tmp_path, ["package/**/tests", "test_project.py"])

    assert production.exists()
    assert unrelated.exists()
    assert not nested_test.parent.exists()
    assert not top_level_test.exists()
