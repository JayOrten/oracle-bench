"""Shared execution and artifact policy for one coding-agent turn."""

import os
from dataclasses import dataclass
from pathlib import Path

from oracle_bench.config import HARNESS_LIMITS, HarnessConfig
from oracle_bench.container.lifecycle import preserve_failure
from oracle_bench.container.sandbox import ORACLE_USER, CommandResult, Sandbox
from oracle_bench.io import write_json


def require_credential(harness: HarnessConfig) -> None:
    """Fail before a container starts if the selected credential is missing."""
    if not os.environ.get(harness.credential_env):
        raise RuntimeError(f"Set {harness.credential_env} to run the {harness.harness} harness")


def require_enforceable_limit(harness: HarnessConfig) -> None:
    """Config rejects this pairing first. Refuse it here too rather than ignore it."""
    if harness.limit.kind not in HARNESS_LIMITS[harness.harness]:
        raise ValueError(
            f"The {harness.harness} harness cannot enforce a {harness.limit.kind} limit"
        )


@dataclass(frozen=True)
class AgentTurnRequest:
    """Where one bounded agent turn runs and where its evidence is written.

    Harness adapters remain responsible for commands, limits, and trace
    parsing, all of which they read from the harness configuration. Callers
    describe only the task: which prompt to deliver and where artifacts belong.
    """

    harness: HarnessConfig
    harness_version: str
    prompt: Path
    working_directory: str
    artifact_directory: Path


def run_agent_turn(
    sandbox: Sandbox,
    request: AgentTurnRequest,
    argv: list[str],
    environment: dict[str, str],
    credential_name: str,
    *,
    last_message_path: str | None = None,
) -> CommandResult:
    """Launch one harness command while enforcing credential and I/O policy."""
    require_enforceable_limit(request.harness)
    require_credential(request.harness)
    directory = request.artifact_directory
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "launch.log"
    key = os.environ[request.harness.credential_env]
    environment = {**environment, credential_name: key, "HOME": "/home/oracle"}
    write_json(directory / "command.json", argv)

    # The CLIs expect their config directories to already exist.
    sandbox.run(
        [
            "mkdir",
            "-p",
            "/tmp/oracle-agent",
            "/home/oracle/.codex",
            "/home/oracle/.claude",
            "/home/oracle/.config/opencode",
            "/home/oracle/.local/share/opencode",
        ],
        user=ORACLE_USER,
        log=log,
    )
    # Save what version of the CLI actually ran.
    sandbox.run(
        [argv[0], "--version"],
        user=ORACLE_USER,
        stdout=directory / "version.txt",
        log=log,
        secrets=(key,),
        workdir=request.working_directory,
    )

    try:
        outcome = sandbox.run(
            argv,
            timeout=request.harness.timeout_seconds,
            user=ORACLE_USER,
            environment=environment,
            stdin=request.prompt,
            stdout=directory / "trace.jsonl",
            stderr=directory / "stderr.log",
            log=log,
            check=False,
            secrets=(key,),
            workdir=request.working_directory,
        )
    finally:
        with preserve_failure(
            "Agent output collection also failed; streamed evidence is retained."
        ):
            collect_output(sandbox, directory, key, last_message_path)
    return outcome


def collect_output(
    sandbox: Sandbox, directory: Path, key: str, last_message_path: str | None
) -> None:
    # Detached descendants can escape a process group. Restarting the same
    # disposable container freezes the filesystem before collecting evidence.
    sandbox.stop_background_processes()
    if last_message_path:
        sandbox.download(
            last_message_path,
            directory / "final.txt",
            required=False,
            secrets=(key,),
        )
