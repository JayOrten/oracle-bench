"""Runs OpenCode: builds the command, reads back its JSON events. OpenRouter only."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from oracle_bench.container.sandbox import Sandbox
from oracle_bench.harnesses.launch import (
    AgentTurnRequest,
    run_agent_turn,
)


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


def run_turn(sandbox: Sandbox, request: AgentTurnRequest) -> dict:
    """Run OpenCode with caller-supplied prompt, workspace, and artifacts."""
    harness = request.harness
    directory = request.artifact_directory
    model = f"openrouter/{harness.model}"

    argv = [
        "opencode",
        "run",
        "--format",
        "json",
        "--auto",
        "--dir",
        request.working_directory,
        "--model",
        model,
    ]

    environment = {
        "XDG_CONFIG_HOME": "/home/oracle/.config",
        "XDG_DATA_HOME": "/home/oracle/.local/share",
        "OPENCODE_DISABLE_AUTOUPDATE": "true",
    }
    if not harness.multi_agent:
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(
            {"permission": {"task": "deny"}}, separators=(",", ":")
        )

    outcome = run_agent_turn(
        sandbox,
        request,
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
    return summary
