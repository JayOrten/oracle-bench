from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from oracle_bench.harnesses.launch import launch
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


def generate(sandbox, config, run_dir: Path):
    runtime = config.require_runtime()
    require_credentials(config)
    directory = run_dir / "agent"
    directory.mkdir(exist_ok=True)
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
            'model_providers.openrouter.wire_api="responses"',
            "model_providers.openrouter.request_max_retries=0",
            "model_providers.openrouter.stream_max_retries=0",
        ]:
            argv[2:2] = ["--config", setting]
        for setting in [
            'model_providers.openrouter.auth.command="sh"',
            'model_providers.openrouter.auth.args=["-c", "echo $OPENROUTER_API_KEY"]',
        ]:
            argv[2:2] = ["--config", setting]
    credential_name = (
        "OPENROUTER_API_KEY" if config.agent.provider == "openrouter" else "CODEX_API_KEY"
    )
    outcome = launch(
        sandbox,
        config,
        run_dir,
        argv,
        {"CODEX_HOME": "/home/oracle/.codex"},
        credential_name,
        final_file=True,
    )
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
