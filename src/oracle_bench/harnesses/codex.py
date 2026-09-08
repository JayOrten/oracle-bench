from __future__ import annotations

import json
import os
import shlex
from dataclasses import asdict
from pathlib import Path

from oracle_bench.containers import Docker
from oracle_bench.io import write_json


def require_credentials(config):
    if not os.environ.get(config.agent.credential_env):
        raise RuntimeError(f"Set {config.agent.credential_env} to run the Codex harness")


def parse_trace(path: Path) -> dict:
    usage = None
    errors = []
    malformed = 0
    completed = False
    failed = False
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(event, dict):
                malformed += 1
                continue
            if event.get("type") == "turn.completed":
                usage = event.get("usage")
                completed = True
                failed = False
            if event.get("type") == "turn.failed":
                failed = True
            if event.get("type") in {"error", "turn.failed"}:
                errors.append(event)
    return {
        "usage": usage,
        "cost_usd": None,
        "errors": errors,
        "unparsed_trace_lines": malformed,
        "turn_completed": completed,
        "turn_failed": failed,
    }


def generate(docker: Docker, container: str, run_dir: Path):
    config = docker.config
    runtime = config.require_runtime()
    require_credentials(config)
    directory = run_dir / "agent"
    directory.mkdir(exist_ok=True)
    log = directory / "launch.log"
    docker.put(container, run_dir / "prompt.txt", "/tmp/oracle-prompt.txt", log)
    argv = [
        "codex",
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        config.agent.model,
        "--cd",
        runtime.workdir,
        "--output-last-message",
        "/tmp/oracle-agent/final.txt",
        "-",
    ]
    if not config.agent.multi_agent:
        argv[2:2] = ["--config", "features.multi_agent=false"]
    if config.agent.provider == "openrouter":
        # CLI overrides still apply with --ignore-user-config. Credentials stay
        # in the process environment, never in the saved command or config.
        for setting in [
            'model_provider="openrouter"',
            'model_providers.openrouter.name="OpenRouter"',
            'model_providers.openrouter.base_url="https://openrouter.ai/api/v1"',
            'model_providers.openrouter.env_key="OPENROUTER_API_KEY"',
            'model_providers.openrouter.wire_api="responses"',
            "model_providers.openrouter.request_max_retries=0",
            "model_providers.openrouter.stream_max_retries=0",
        ]:
            argv[2:2] = ["--config", setting]
    # Docker provides isolation. Never invoke these flags in a host-side agent process.
    write_json(directory / "command.json", argv)
    script = (
        "mkdir -p /tmp/oracle-agent /home/oracle/.codex\n"
        "codex --version > /tmp/oracle-agent/version.txt\n"
        f"{shlex.join(argv)} < /tmp/oracle-prompt.txt "
        "> /tmp/oracle-agent/trace.jsonl 2> /tmp/oracle-agent/stderr.log"
    )
    key = os.environ[config.agent.credential_env]
    outcome = docker.shell(
        container,
        script,
        log,
        config.agent.wall_seconds,
        user="10001:10001",
        environment={
            (
                "OPENROUTER_API_KEY" if config.agent.provider == "openrouter" else "CODEX_API_KEY"
            ): key,
            "CODEX_HOME": "/home/oracle/.codex",
            "HOME": "/home/oracle",
        },
        check=False,
    )
    for name in ["trace.jsonl", "stderr.log", "final.txt", "version.txt"]:
        target = directory / name
        docker.get(container, "/tmp/oracle-agent/" + name, target, log, check=False)
        if target.exists():
            target.write_text(target.read_text(errors="replace").replace(key, "[REDACTED]"))
    summary = {**asdict(outcome), **parse_trace(directory / "trace.jsonl")}
    summary["status"] = (
        "timeout"
        if outcome.timed_out
        else "failed"
        if outcome.exit_code or summary["turn_failed"] or not summary["turn_completed"]
        else "completed"
    )
    write_json(directory / "result.json", summary)
    return summary
