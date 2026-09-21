"""Runs Claude Code: builds the command, then reads back its JSON event stream."""

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


def run_turn(sandbox: Sandbox, request: AgentTurnRequest) -> dict:
    """Run Claude Code under exactly the stopping limit its configuration selects."""
    harness = request.harness
    directory = request.artifact_directory

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
        harness.model,
    ]
    # A wall limit is already the container deadline; the CLI enforces the rest.
    if harness.limit.kind == "budget_usd":
        argv += ["--max-budget-usd", str(harness.limit.value)]
    elif harness.limit.kind == "turns":
        argv += ["--max-turns", str(harness.limit.value)]
    if not harness.multi_agent:
        argv += ["--tools", "Bash,Read,Write,Edit,Glob,Grep"]

    environment = {"CLAUDE_CONFIG_DIR": "/home/oracle/.claude", "DISABLE_AUTOUPDATER": "1"}
    credential_name = harness.credential_env
    if harness.provider == "openrouter":
        environment.update(
            ANTHROPIC_BASE_URL="https://openrouter.ai/api",
            ANTHROPIC_API_KEY="",
        )
        credential_name = "ANTHROPIC_AUTH_TOKEN"

    outcome = run_agent_turn(
        sandbox,
        request,
        argv,
        environment,
        credential_name,
    )

    summary = {**asdict(outcome), **parse_trace(directory / "trace.jsonl")}
    (directory / "final.txt").write_text(summary.pop("final_text"))
    summary["status"] = (
        "timeout"
        if outcome.timed_out
        else "failed"
        if outcome.exit_code or not summary["turn_completed"]
        else "completed"
    )
    return summary
