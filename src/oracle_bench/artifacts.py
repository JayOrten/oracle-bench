from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from oracle_bench.config import repo_path
from oracle_bench.container import Sandbox
from oracle_bench.io import digest, read_json, write_json

CONTAINER_HELPERS = Path(__file__).parent / "container_helpers"


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


def snapshot(sandbox: Sandbox, target: Path, log: Path):
    runtime = sandbox.runtime
    sandbox.run(
        [
            runtime.python,
            sandbox.helpers + "/workspace.py",
            "snapshot",
            runtime.workdir,
            "/tmp/oracle-snapshot.json",
        ],
        log=log,
        timeout=120,
    )
    sandbox.download("/tmp/oracle-snapshot.json", target)
    return read_json(target)


def capture(sandbox: Sandbox, config, run_dir: Path, before: dict, baseline: str):
    runtime = config.require_runtime()
    log = run_dir / "agent" / "capture.log"
    after = snapshot(sandbox, run_dir / "agent" / "after.json", log)
    allowed, forbidden = changed_files(before, after, config.task.generated_dir)
    generated = run_dir / "generated"
    generated.mkdir()
    sandbox.run(
        [
            runtime.python,
            sandbox.helpers + "/workspace.py",
            "diff",
            runtime.workdir,
            "/tmp/oracle-workspace.diff",
            baseline,
        ],
        log=log,
        timeout=120,
        check=False,
    )
    sandbox.download(
        "/tmp/oracle-workspace.diff",
        run_dir / "agent" / "workspace.diff",
        required=False,
    )
    files = {}
    for name in allowed:
        target = generated / "files" / name
        sandbox.download(runtime.workdir + "/" + name, target)
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
    """Validate the external bundle before transferring it to either code version."""
    manifest = read_json(run_dir / "generated" / "manifest.json")
    if digest(json.dumps(manifest["files"], sort_keys=True).encode()) != manifest["sha256"]:
        raise ValueError("Generated manifest checksum mismatch")
    root = run_dir / "generated" / "files"
    entries = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_symlink() or not path.is_dir()
    }
    if entries != set(manifest["files"]):
        raise ValueError("Generated bundle contains missing or unmanifested files")
    for name, info in manifest["files"].items():
        path = root / repo_path(name)
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != info["sha256"]:
            raise ValueError(f"Generated artifact checksum mismatch: {name}")
    return manifest
