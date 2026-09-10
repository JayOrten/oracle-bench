"""Shared I/O and credential policy for the two command-line harnesses."""

import os

from oracle_bench.container import ORACLE_USER
from oracle_bench.container.lifecycle import preserve_failure
from oracle_bench.io import write_json


def launch(sandbox, config, run_dir, argv, environment, credential_name, *, final_file=False):
    directory = run_dir / "agent"
    directory.mkdir(exist_ok=True)
    log = directory / "launch.log"
    key = os.environ[config.agent.credential_env]
    environment = {**environment, credential_name: key, "HOME": "/home/oracle"}
    write_json(directory / "command.json", argv)
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
    sandbox.run(
        [argv[0], "--version"],
        user=ORACLE_USER,
        stdout=directory / "version.txt",
        log=log,
        secrets=(key,),
    )
    try:
        outcome = sandbox.run(
            argv,
            timeout=config.agent.wall_seconds,
            user=ORACLE_USER,
            environment=environment,
            stdin=run_dir / "prompt.txt",
            stdout=directory / "trace.jsonl",
            stderr=directory / "stderr.log",
            log=log,
            check=False,
            secrets=(key,),
        )
    finally:
        with preserve_failure(
            "Agent output collection also failed; streamed evidence is retained."
        ):
            collect_output(sandbox, directory, key, final_file)
    return outcome


def collect_output(sandbox, directory, key, final_file):
    # Detached descendants can escape a process group. Restarting the same
    # disposable container freezes the filesystem before collecting evidence.
    sandbox.stop_background_processes()
    if final_file:
        sandbox.download(
            "/tmp/oracle-agent/final.txt",
            directory / "final.txt",
            required=False,
            secrets=(key,),
        )
