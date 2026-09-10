from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from oracle_bench.harnesses.launch import launch
from oracle_bench.io import write_json


def require_credentials(config):
    if not os.environ.get(config.agent.credential_env):
        raise RuntimeError("Set OPENROUTER_API_KEY to run the OpenCode harness")


def parse_trace(path: Path) -> dict:
    """Normalize OpenCode's JSON event stream into the shared harness result."""
    usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
    cost = 0.0
    final_text = ""
    errors = []
    malformed = 0
    completed = False
    finish_seen = False
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
            part = event.get("part") or {}
            if event.get("type") == "text":
                final_text = str(part.get("text", ""))
            elif event.get("type") == "step_finish":
                finish_seen = True
                tokens = part.get("tokens") or {}
                usage["input_tokens"] += tokens.get("input", 0)
                usage["output_tokens"] += tokens.get("output", 0)
                usage["reasoning_tokens"] += tokens.get("reasoning", 0)
                cost += part.get("cost", 0) or 0
                completed = part.get("reason") == "stop"
            elif event.get("type") == "error":
                errors.append(event)
    return {
        "usage": usage if any(usage.values()) else None,
        "cost_usd": cost if finish_seen else None,
        "errors": errors,
        "unparsed_trace_lines": malformed,
        "turn_completed": completed,
        "turn_failed": bool(errors),
        "final_text": final_text,
    }


def generate(sandbox, config, run_dir: Path):
    runtime = config.require_runtime()
    require_credentials(config)
    directory = run_dir / "agent"
    directory.mkdir(exist_ok=True)
    model = f"openrouter/{config.agent.model}"
    argv = [
        "opencode",
        "run",
        "--format",
        "json",
        "--auto",
        "--dir",
        runtime.workdir,
        "--model",
        model,
    ]
    environment = {
        "XDG_CONFIG_HOME": "/home/oracle/.config",
        "XDG_DATA_HOME": "/home/oracle/.local/share",
        "OPENCODE_DISABLE_AUTOUPDATE": "true",
    }
    if not config.agent.multi_agent:
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(
            {"permission": {"task": "deny"}}, separators=(",", ":")
        )
    outcome = launch(
        sandbox,
        config,
        run_dir,
        argv,
        environment,
        "OPENROUTER_API_KEY",
    )
    parsed = parse_trace(directory / "trace.jsonl")
    (directory / "final.txt").write_text(parsed.pop("final_text"))
    summary = {**asdict(outcome), **parsed}
    summary["status"] = (
        "timeout"
        if outcome.timed_out
        else "failed"
        if outcome.exit_code or summary["turn_failed"] or not summary["turn_completed"]
        else "completed"
    )
    write_json(directory / "result.json", summary)
    return summary
