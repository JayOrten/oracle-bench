"""Finalize a disposable repository workspace after rebuilding (Python 3.8+)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def git(*args):
    subprocess.run(["git", *args], check=True)


def remove_existing_tests(root: Path, patterns: list[str]) -> None:
    """Remove every adapter-declared test path, including nested test trees."""
    paths = {path for pattern in patterns for path in root.glob(pattern)}
    # Remove children before parents when adapter patterns happen to overlap.
    for path in sorted(paths, key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def prepare(settings):
    root = Path(settings["workdir"])
    os.chdir(root)
    if settings["hide"]:
        remove_existing_tests(root, settings["existing_test_globs"])
    # Refuse to repurpose an existing directory: only new files are submissions.
    (root / settings["generated_dir"]).mkdir(parents=True, exist_ok=False)
    git("config", "user.email", "oracle-bench@localhost")
    git("config", "user.name", "OracleBench")
    git("config", "--global", "--add", "safe.directory", str(root))
    git("add", "-A")
    git("commit", "--allow-empty", "-m", "Oracle Bench workspace")
    subprocess.run(["chown", "-R", "10001:10001", str(root)], check=True)


if __name__ == "__main__":
    prepare(json.loads(Path(sys.argv[1]).read_text()))
