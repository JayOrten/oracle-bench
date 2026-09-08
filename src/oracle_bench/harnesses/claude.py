from __future__ import annotations

import json
import os
import shlex
from dataclasses import asdict
from pathlib import Path

from oracle_bench.io import write_json


def require_credentials(config):
    if not os.environ.get(config.agent.credential_env):
        raise RuntimeError(f"Set {config.agent.credential_env} to run the Claude Code harness")


def parse_trace(path: Path) -> dict:
    result = None
    malformed = 0
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
            elif event.get("type") == "result":
                result = event
    completed = bool(result and result.get("subtype") == "success" and not result.get("is_error"))
    errors = []
    if result and not completed:
        errors = [
            {"message": str(result.get("errors") or result.get("result") or result.get("subtype"))}
        ]
    return {
        "turn_completed": completed,
        "turn_failed": bool(result and not completed),
        "usage": result.get("usage") if result else None,
        "cost_usd": result.get("total_cost_usd") if result else None,
        "model_usage": result.get("modelUsage") if result else None,
        "errors": errors,
        "unparsed_trace_lines": malformed,
        "final_text": result.get("result", "") if result else "",
    }


def generate(docker, container: str, run_dir: Path):
    config = docker.config
    require_credentials(config)
    directory = run_dir / "agent"
    directory.mkdir(exist_ok=True)
    log = directory / "launch.log"
    docker.put(container, run_dir / "prompt.txt", "/tmp/oracle-prompt.txt", log)
    argv = [
        "claude",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--safe-mode",
        "--strict-mcp-config",
        "--dangerously-skip-permissions",
        "--model",
        config.agent.model,
        "--max-budget-usd",
        str(config.agent.max_budget_usd),
        "--max-turns",
        str(config.agent.max_turns),
    ]
    if not config.agent.multi_agent:
        argv += ["--tools", "Bash,Read,Write,Edit,Glob,Grep"]
    # Permission bypass is confined to the non-root agent inside Docker.
    write_json(directory / "command.json", argv)
    script = (
        "mkdir -p /tmp/oracle-agent /home/oracle/.claude\n"
        "claude --version > /tmp/oracle-agent/version.txt\n"
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
                "ANTHROPIC_API_KEY" if config.agent.auth == "api_key" else "CLAUDE_CODE_OAUTH_TOKEN"
            ): key,
            "CLAUDE_CONFIG_DIR": "/home/oracle/.claude",
            "HOME": "/home/oracle",
            "DISABLE_AUTOUPDATER": "1",
        },
        check=False,
    )
    for name in ["trace.jsonl", "stderr.log", "version.txt"]:
        target = directory / name
        docker.get(container, "/tmp/oracle-agent/" + name, target, log, check=False)
        if target.exists():
            target.write_text(target.read_text(errors="replace").replace(key, "[REDACTED]"))
    summary = {**asdict(outcome), **parse_trace(directory / "trace.jsonl")}
    (directory / "final.txt").write_text(summary.pop("final_text"))
    summary["status"] = (
        "timeout"
        if outcome.timed_out
        else "failed"
        if outcome.exit_code or not summary["turn_completed"]
        else "completed"
    )
    write_json(directory / "result.json", summary)
    return summary
