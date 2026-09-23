"""Generate tests in a buggy checkout and freeze what the agent produced.

One disposable container covers the whole stage: prepare the repository, record
its state, run the agent, then capture only new files under the generated
directory. Everything outside that directory is reported as a forbidden change
rather than silently dropped.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from docker import DockerClient

from oracle_bench.config import RunConfig, repo_path
from oracle_bench.container.sandbox import Profile, Sandbox, open_sandbox
from oracle_bench.harnesses import generate
from oracle_bench.io import digest, read_json, write_json
from oracle_bench.paths import RunPaths
from oracle_bench.repository import Repository
from oracle_bench.results import InstanceRecord


def generate_submission(
    client: DockerClient,
    config: RunConfig,
    image: str,
    instance: InstanceRecord,
    paths: RunPaths,
) -> dict:
    """Run one agent turn in a fresh buggy checkout and return its frozen bundle."""
    log = paths.generation / "setup.log"
    with open_sandbox(client, image, config, Profile.GENERATION, log) as sandbox:
        workspace = Repository(sandbox, config)
        # The agent needs Git for normal inspection and diffing, but must not be able
        # to recover hidden tests or issue details from the source repository's past.
        workspace.prepare(instance.base_commit, paths.generation, sanitize_history=True)
        before = snapshot(sandbox, paths.generation / "before.json", log)
        baseline = workspace.baseline(paths.generation / "baseline.txt")
        generate(sandbox, config, paths)
        return capture(sandbox, config, paths, before, baseline)


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


def snapshot(sandbox: Sandbox, target: Path, log: Path) -> dict:
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


def capture(
    sandbox: Sandbox, config: RunConfig, paths: RunPaths, before: dict, baseline: str
) -> dict:
    runtime = config.require_runtime()
    log = paths.generation / "capture.log"
    after = snapshot(sandbox, paths.generation / "after.json", log)
    allowed, forbidden = changed_files(before, after, config.task.generated_dir)
    generated = paths.submission
    # Keep the frozen bundle structurally complete even when the agent creates no
    # tests. Downstream verification and diagnostics can then inspect an empty
    # directory instead of failing because the bundle root never existed.
    (generated / "files").mkdir(parents=True, exist_ok=True)
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
        paths.generation / "workspace.diff",
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
        "files": files,
        "forbidden_changes": forbidden,
        "compliant": not forbidden,
        "empty": not files,
        "sha256": digest(json.dumps(files, sort_keys=True).encode()),
    }
    write_json(generated / "manifest.json", manifest)
    return manifest


def verify_bundle(paths: RunPaths) -> dict:
    """Validate the external bundle before transferring it to either code version."""
    generated = paths.submission
    manifest = read_json(generated / "manifest.json")
    if digest(json.dumps(manifest["files"], sort_keys=True).encode()) != manifest["sha256"]:
        raise ValueError("Generated manifest checksum mismatch")
    root = generated / "files"
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
