from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from oracle_bench.config import RunConfig
from oracle_bench.io import digest, write_json


@dataclass
class CommandResult:
    exit_code: int
    duration_seconds: float
    timed_out: bool = False


class Docker:
    """Small CLI backend. Only disposable containers receive repository writes."""

    def __init__(self, config: RunConfig):
        self.config = config

    def check(self):
        if not shutil.which("docker"):
            raise RuntimeError("Docker CLI is missing. Install Docker and start its daemon.")
        result = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode or result.stdout.strip() != "linux":
            raise RuntimeError(
                "A reachable Linux Docker daemon is required: " + result.stderr.strip()
            )

    def command(
        self,
        args: list[str],
        log: Path,
        timeout: float,
        *,
        env: dict | None = None,
        check: bool = True,
    ) -> CommandResult:
        log.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        with log.open("ab") as output:
            try:
                proc = subprocess.run(
                    ["docker", *args], stdout=output, stderr=output, timeout=timeout, env=env
                )
                result = CommandResult(proc.returncode, time.monotonic() - started)
            except subprocess.TimeoutExpired:
                result = CommandResult(124, time.monotonic() - started, True)
        if check and result.exit_code:
            raise RuntimeError(f"Docker command failed (exit {result.exit_code}); see {log}")
        return result

    def inspect_image(self, image: str) -> dict | None:
        result = subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, text=True, timeout=30
        )
        return json.loads(result.stdout)[0] if result.returncode == 0 else None

    def prepare_image(self, run_dir: Path) -> str:
        config = self.config
        build = run_dir / "build"
        build.mkdir()
        log = build / "output.log"
        # Pull the selected instance image; build only the small instrumentation/runtime layer.
        source = self.inspect_image(config.environment.image)
        if source is None:
            self.command(
                ["pull", "--platform", config.environment.platform, config.environment.image],
                log,
                config.limits.setup_seconds,
            )
            source = self.inspect_image(config.environment.image)
        if source is None:
            raise RuntimeError("Pulled image cannot be inspected")
        node = self.inspect_image(config.harness.node_image)
        if node is None:
            self.command(
                ["pull", "--platform", config.environment.platform, config.harness.node_image],
                log,
                config.limits.setup_seconds,
            )
            node = self.inspect_image(config.harness.node_image)
        if node is None:
            raise RuntimeError("Node runtime image cannot be inspected")
        # Registry digests work with BuildKit as well as the legacy builder.
        # Locally built images can instead be referenced by their image ID.
        source_ref = (source.get("RepoDigests") or [source["Id"]])[0]
        node_ref = (node.get("RepoDigests") or [node["Id"]])[0]
        python_dir = str(Path(config.environment.python).parent)
        package = (
            "@anthropic-ai/claude-code" if config.harness.kind == "claude" else "@openai/codex"
        )
        agent_prefix = "/opt/oracle-" + config.harness.kind
        recipe = f"""FROM {node_ref} AS agent_runtime
RUN npm install --prefix {agent_prefix} {package}@{config.harness.version}
FROM {source_ref}
USER root
COPY --from=agent_runtime /usr/local/bin/node /opt/oracle-node/node
COPY --from=agent_runtime {agent_prefix} {agent_prefix}
ENV PATH={python_dir}:/opt/oracle-node:{agent_prefix}/node_modules/.bin:$PATH
RUN {shlex.quote(config.environment.python)} -m pip install pytest=={config.environment.pytest_version} coverage=={config.environment.coverage_version}
RUN useradd --create-home --uid 10001 oracle
"""
        (build / "Dockerfile").write_text(recipe)
        (build / ".dockerignore").write_text("*\n!Dockerfile\n!.dockerignore\n")
        image = "oracle-bench/runtime:" + digest(recipe.encode())[:24]
        if self.inspect_image(image) is None:
            self.command(
                ["build", "--platform", config.environment.platform, "-t", image, str(build)],
                log,
                config.limits.setup_seconds,
            )
        resolved = self.inspect_image(image)
        if resolved is None:
            raise RuntimeError("Runtime build did not create an image")
        write_json(
            build / "images.json",
            {
                "source": {
                    "reference": config.environment.image,
                    "id": source["Id"],
                    "digests": source.get("RepoDigests", []),
                },
                "node": {"reference": config.harness.node_image, "id": node["Id"]},
                "runtime": {"reference": image, "id": resolved["Id"]},
            },
        )
        return resolved["Id"]

    @contextmanager
    def container(self, image: str, log: Path, *, network: bool = False):
        name = "oracle-bench-" + uuid.uuid4().hex[:16]
        limits = self.config.limits
        args = [
            "run",
            "--detach",
            "--init",
            "--name",
            name,
            "--platform",
            self.config.environment.platform,
            "--memory",
            limits.memory,
            "--cpus",
            str(limits.cpus),
            "--security-opt",
            "no-new-privileges",
            "--entrypoint",
            "/bin/bash",
        ]
        if not network:
            args += ["--network", "none"]
        try:
            self.command([*args, image, "-c", "sleep infinity"], log, 60)
            yield name
        finally:
            self.command(["rm", "--force", name], log, 60, check=False)

    def execute(
        self,
        container: str,
        argv: list[str],
        log: Path,
        timeout: float,
        *,
        user: str | None = None,
        environment: dict | None = None,
        check: bool = True,
    ) -> CommandResult:
        args = ["exec", "--workdir", self.config.environment.workdir]
        if user:
            args += ["--user", user]
        env = os.environ.copy()
        for key, value in (environment or {}).items():
            env[key] = value
            args += ["--env", key]  # Values never enter command arguments or saved config.
        result = self.command(
            [*args, container, "timeout", "--signal=TERM", "--kill-after=10", str(timeout), *argv],
            log,
            timeout + 30,
            env=env,
            check=False,
        )
        if result.exit_code in (124, 137):
            result.timed_out = True
        if check and result.exit_code:
            raise RuntimeError(f"Container command failed (exit {result.exit_code}); see {log}")
        return result

    def shell(self, container: str, script: str, log: Path, timeout: float, **kwargs):
        return self.execute(
            container, ["/bin/bash", "-c", "set -euo pipefail\n" + script], log, timeout, **kwargs
        )

    def put(self, container: str, source: Path, target: str, log: Path):
        self.command(["cp", str(source), f"{container}:{target}"], log, 60)

    def put_contents(self, container: str, source: Path, target: str, log: Path):
        self.command(["cp", str(source) + "/.", f"{container}:{target}"], log, 60)

    def get(self, container: str, source: str, target: Path, log: Path, *, check=True):
        target.parent.mkdir(parents=True, exist_ok=True)
        return self.command(["cp", f"{container}:{source}", str(target)], log, 60, check=check)


def prepare_workspace(
    docker: Docker, container: str, instance: dict, log: Path, *, keep_tests: bool = False
):
    config = docker.config
    q = shlex.quote
    # The container is new and private to this attempt; resetting it never touches the host repo.
    docker.shell(
        container,
        f"git reset --hard {q(instance['base_commit'])}\ngit clean -fdx\n"
        f"{config.environment.rebuild}\n"
        "git config user.email oracle-bench@localhost\n"
        "git config user.name OracleBench\n"
        f"git config --global --add safe.directory {q(config.environment.workdir)}\n",
        log,
        config.limits.setup_seconds,
    )
    if not keep_tests and config.task.existing_tests == "hide":
        script = """import pathlib, shutil, sys
for name in sys.argv[1:]:
    p = pathlib.Path(name)
    if p.is_symlink() or p.is_file(): p.unlink()
    elif p.is_dir(): shutil.rmtree(p)
"""
        docker.execute(
            container,
            [config.environment.python, "-c", script, *config.environment.existing_test_paths],
            log,
            60,
        )
    docker.shell(
        container,
        f"test ! -e {q(config.task.generated_dir)}\n"
        f"mkdir -p {q(config.task.generated_dir)}\n"
        "git add -A\ngit commit --allow-empty -m 'Oracle Bench workspace'\n"
        f"chown -R 10001:10001 {q(config.environment.workdir)}\n",
        log,
        config.limits.setup_seconds,
    )


def apply_patch(docker: Docker, container: str, patch: str, path: Path, log: Path):
    path.write_text(patch)
    docker.put(container, path, "/tmp/oracle.patch", log)
    docker.shell(
        container,
        "git apply --check /tmp/oracle.patch\ngit apply /tmp/oracle.patch\nrm /tmp/oracle.patch",
        log,
        docker.config.limits.setup_seconds,
    )
