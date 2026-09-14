import subprocess
import sys

from oracle_bench.container_helpers.prepare import remove_existing_tests


def test_helper_annotations_are_not_evaluated_by_old_repository_python():
    assert remove_existing_tests.__annotations__["patterns"] == "list[str]"


def test_remove_existing_tests_expands_files_directories_and_nested_globs(tmp_path):
    production = tmp_path / "package" / "module.py"
    nested_test = tmp_path / "package" / "feature" / "tests" / "test_feature.py"
    top_level_test = tmp_path / "test_project.py"
    unrelated = tmp_path / "examples" / "test_example.py"
    runtime_helper = nested_test.parent / "runner.py"
    package_marker = nested_test.parent / "__init__.py"
    for path in [
        production,
        nested_test,
        top_level_test,
        unrelated,
        runtime_helper,
        package_marker,
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content")

    remove_existing_tests(tmp_path, ["package/**/tests", "test_project.py"])

    assert production.exists()
    assert unrelated.exists()
    assert nested_test.parent.exists()
    assert runtime_helper.exists()
    assert package_marker.exists()
    assert not nested_test.exists()
    assert not top_level_test.exists()


def test_removing_tests_preserves_runtime_imports_from_test_package(tmp_path):
    package = tmp_path / "example"
    tests = package / "tests"
    tests.mkdir(parents=True)
    (package / "__init__.py").write_text("from .tests.runner import run\n")
    (tests / "__init__.py").write_text("")
    (tests / "runner.py").write_text("def run(): return 'available'\n")
    (tests / "test_behavior.py").write_text("def test_behavior(): assert False\n")
    (tests / "tests.py").write_text("def test_legacy_name(): assert False\n")

    remove_existing_tests(tmp_path, ["example/tests"])

    result = subprocess.run(
        [sys.executable, "-c", "import example; print(example.run())"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == "available"
    assert not (tests / "test_behavior.py").exists()
    assert not (tests / "tests.py").exists()
