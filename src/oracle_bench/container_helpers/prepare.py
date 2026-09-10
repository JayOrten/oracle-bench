"""Finalize a disposable repository workspace after rebuilding (Python 3.9+)."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def git(*args):
    subprocess.run(["git", *args], check=True)


def prepare(settings):
    root = Path(settings["workdir"])
    os.chdir(root)
    if settings["hide"]:
        paths = {path for pattern in settings["existing_test_globs"] for path in root.glob(pattern)}
        for path in sorted(paths, key=lambda item: len(item.parts), reverse=True):
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
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
