import json
import subprocess
import sys
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from fixtures import HELPERS

from oracle_bench.generation import changed_files, generate_submission, verify_bundle
from oracle_bench.io import digest, read_json, write_json
from oracle_bench.paths import RunPaths


def entry(data, kind="file"):
    return {"sha256": digest(data), "kind": kind, "size": len(data), "mode": 0o644}


def test_only_new_regular_files_under_generated_directory_are_allowed():
    before = {"app.py": entry(b"old"), "tests/test_old.py": entry(b"existing")}
    after = {
        "app.py": entry(b"changed"),
        "oracle_tests/test_new.py": entry(b"test"),
        "oracle_tests/fixture.json": entry(b"{}"),
        "oracle_tests/escape": entry(b"/etc/passwd", "symlink"),
    }
    allowed, forbidden = changed_files(before, after, "oracle_tests")
    assert allowed == ["oracle_tests/fixture.json", "oracle_tests/test_new.py"]
    assert forbidden == ["app.py", "oracle_tests/escape", "tests/test_old.py"]


def test_bundle_tampering_is_rejected(tmp_path):
    paths = RunPaths.create(tmp_path)
    path = paths.submission / "files" / "oracle_tests" / "test_new.py"
    path.parent.mkdir(parents=True)
    path.write_text("def test_a(): pass\n")
    files = {"oracle_tests/test_new.py": {"sha256": digest(path.read_bytes()), "mode": 0o644}}
    write_json(
        paths.submission / "manifest.json",
        {"files": files, "sha256": digest(json.dumps(files, sort_keys=True).encode())},
    )
    assert verify_bundle(RunPaths.open(tmp_path))["files"] == files
    path.write_text("modified")
    with pytest.raises(ValueError, match="checksum"):
        verify_bundle(RunPaths.open(tmp_path))


def test_unmanifested_files_are_not_transferred_to_evaluation(tmp_path):
    paths = RunPaths.create(tmp_path)
    root = paths.submission / "files"
    root.mkdir(parents=True)
    (root / "extra.py").write_text("unexpected code")
    write_json(
        paths.submission / "manifest.json",
        {
            "files": {},
            "sha256": digest(b"{}"),
        },
    )
    with pytest.raises(ValueError, match="unmanifested"):
        verify_bundle(RunPaths.open(tmp_path))


def test_empty_bundle_has_a_real_files_directory(tmp_path):
    paths = RunPaths.create(tmp_path)
    (paths.submission / "files").mkdir(parents=True)
    write_json(
        paths.submission / "manifest.json",
        {"files": {}, "empty": True, "sha256": digest(b"{}")},
    )

    assert verify_bundle(paths)["empty"] is True


def test_transient_generation_uses_clean_container_and_archives_attempt(tmp_path, monkeypatch):
    paths = RunPaths.create(tmp_path)
    sandboxes = [Mock(name="first_sandbox"), Mock(name="second_sandbox")]

    @contextmanager
    def sandbox_context(*args, **kwargs):
        yield sandboxes.pop(0)

    workspaces = []

    def repository(sandbox, config):
        workspace = Mock()
        workspace.baseline.return_value = "baseline"
        workspaces.append((sandbox, workspace))
        return workspace

    attempts = 0

    def generate(_sandbox, _config, run_paths):
        nonlocal attempts
        attempts += 1
        (run_paths.generation / "trace.jsonl").write_text(f"attempt {attempts}\n")
        return {
            "status": "failed" if attempts == 1 else "completed",
            "errors": [{"message": "stream disconnected"}] if attempts == 1 else [],
        }

    capture = Mock(return_value={"empty": False})
    delay = Mock()
    monkeypatch.setattr("oracle_bench.generation.open_sandbox", sandbox_context)
    monkeypatch.setattr("oracle_bench.generation.Repository", repository)
    monkeypatch.setattr("oracle_bench.generation.snapshot", Mock(return_value={}))
    monkeypatch.setattr("oracle_bench.generation.generate", generate)
    monkeypatch.setattr("oracle_bench.generation.capture", capture)
    monkeypatch.setattr("oracle_bench.generation.sleep", delay)

    result = generate_submission(Mock(), Mock(), "runtime-image", Mock(base_commit="a" * 40), paths)

    assert result == {"empty": False}
    assert attempts == 2
    assert len(workspaces) == 2
    assert capture.call_count == 1
    delay.assert_called_once_with(30)
    archived = list(paths.generation_history.iterdir())
    assert len(archived) == 1
    assert (archived[0] / "trace.jsonl").read_text() == "attempt 1\n"
    assert (paths.generation / "trace.jsonl").read_text() == "attempt 2\n"


def test_snapshot_captures_untracked_files_and_symlinks_without_following_them(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "new.py").write_text("new")
    (root / "outside").symlink_to(tmp_path, target_is_directory=True)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "ignored.pyc").write_bytes(b"cache")
    output = tmp_path / "snapshot.json"
    subprocess.run(
        [
            sys.executable,
            str(HELPERS / "workspace.py"),
            "snapshot",
            str(root),
            str(output),
        ],
        check=True,
    )
    result = read_json(output)
    assert set(result) == {"new.py", "outside"}
    assert result["outside"]["kind"] == "symlink"


def test_capture_diff_includes_agent_commits_and_untracked_files(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path).decode().strip()

    git("init", "-q")
    git("config", "user.name", "test")
    git("config", "user.email", "test@localhost")
    (tmp_path / "app.py").write_text("old\n")
    git("add", ".")
    git("commit", "-qm", "base")
    baseline = git("rev-parse", "HEAD")
    (tmp_path / "app.py").write_text("new\n")
    git("commit", "-qam", "agent edit")
    (tmp_path / "test_new.py").write_text("def test_new(): pass\n")
    output = tmp_path.parent / (tmp_path.name + ".diff")
    subprocess.run(
        [
            sys.executable,
            str(HELPERS / "workspace.py"),
            "diff",
            str(tmp_path),
            str(output),
            baseline,
        ],
        check=True,
    )
    diff = output.read_text()
    assert "-old" in diff and "+new" in diff and "+def test_new(): pass" in diff
