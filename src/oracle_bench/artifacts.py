from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from oracle_bench.config import repo_path
from oracle_bench.containers import Docker
from oracle_bench.io import digest, read_json, write_json

SCRIPTS = Path(__file__).parent / "scripts"


def changed_files(before: dict, after: dict, generated_dir: str) -> tuple[list[str], list[str]]:
    allowed, forbidden = [], []
    root = PurePosixPath(generated_dir)
    for name in sorted(before.keys() | after.keys()):
        if before.get(name) == after.get(name):
            continue
        path = PurePosixPath(repo_path(name))
        entry = after.get(name)
        # New regular files only; symlinks cannot cause host-side reads or replacement of code.
        if root in path.parents and name not in before and entry and entry["kind"] == "file":
            allowed.append(name)
        else:
            forbidden.append(name)
    return allowed, forbidden


def snapshot(docker: Docker, container: str, target: Path, log: Path):
    config = docker.config
    runtime = config.require_runtime()
    docker.put(container, SCRIPTS / "workspace.py", "/tmp/oracle-workspace.py", log)
    docker.execute(
        container,
        [
            runtime.python,
            "/tmp/oracle-workspace.py",
            "snapshot",
            runtime.workdir,
            "/tmp/oracle-snapshot.json",
        ],
        log,
        120,
    )
    docker.get(container, "/tmp/oracle-snapshot.json", target, log)
    return read_json(target)


def capture(docker: Docker, container: str, run_dir: Path, before: dict, baseline: str):
    config = docker.config
    runtime = config.require_runtime()
    log = run_dir / "agent" / "capture.log"
    after = snapshot(docker, container, run_dir / "agent" / "after.json", log)
    allowed, forbidden = changed_files(before, after, config.task.generated_dir)
    generated = run_dir / "generated"
    generated.mkdir()
    docker.execute(
        container,
        [
            runtime.python,
            "/tmp/oracle-workspace.py",
            "diff",
            runtime.workdir,
            "/tmp/oracle-workspace.diff",
            baseline,
        ],
        log,
        120,
        check=False,
    )
    docker.get(
        container,
        "/tmp/oracle-workspace.diff",
        run_dir / "agent" / "workspace.diff",
        log,
        check=False,
    )
    files = {}
    for name in allowed:
        target = generated / "files" / name
        docker.get(container, runtime.workdir + "/" + name, target, log)
        # Copy only regular files with the exact bytes measured in the final snapshot.
        if target.is_symlink() or digest(target.read_bytes()) != after[name]["sha256"]:
            raise RuntimeError(f"Artifact changed during capture: {name}")
        files[name] = {"sha256": after[name]["sha256"], "mode": after[name]["mode"]}
    manifest = {
        "schema_version": 1,
        "files": files,
        "forbidden_changes": forbidden,
        "compliant": not forbidden,
        "empty": not files,
        "sha256": digest(json.dumps(files, sort_keys=True).encode()),
    }
    write_json(generated / "manifest.json", manifest)
    return manifest


def verify_bundle(run_dir: Path) -> dict:
    manifest = read_json(run_dir / "generated" / "manifest.json")
    if digest(json.dumps(manifest["files"], sort_keys=True).encode()) != manifest["sha256"]:
        raise ValueError("Generated manifest checksum mismatch")
    for name, info in manifest["files"].items():
        path = run_dir / "generated" / "files" / repo_path(name)
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != info["sha256"]:
            raise ValueError(f"Generated artifact checksum mismatch: {name}")
    return manifest
