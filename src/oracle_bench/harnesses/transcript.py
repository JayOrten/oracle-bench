"""Readable, offline rendering of the events emitted by either agent CLI."""

import json
from pathlib import Path


def _text(value):
    return value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)


def render_session(run_dir: Path) -> Path:
    directory = run_dir / "agent"
    directory.mkdir(exist_ok=True)
    lines = [
        "AGENT SESSION",
        "Rendered from saved CLI events; raw events remain in trace.jsonl.",
        "Only output exposed by the CLI is available. Tool output may be truncated by the CLI.",
        "",
    ]
    prompt = run_dir / "prompt.txt"
    if prompt.exists():
        lines += ["=== PROMPT ===", prompt.read_text(), ""]
    trace = directory / "trace.jsonl"
    if trace.exists():
        for number, raw in enumerate(trace.read_text(errors="replace").splitlines(), 1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                lines += [f"=== UNPARSED EVENT {number} ===", raw, ""]
                continue
            if not isinstance(event, dict):
                lines += [f"=== EVENT {number} ===", _text(event), ""]
                continue
            kind = event.get("type", "unknown")
            stamp = event.get("timestamp", "")
            lines += [f"=== EVENT {number}: {kind} {stamp} ===".rstrip()]
            # Claude exposes message content as individual text/tool blocks.
            message = event.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), list):
                for block in message["content"]:
                    if not isinstance(block, dict):
                        lines.append(_text(block))
                        continue
                    block_type = block.get("type")
                    if block_type == "text":
                        lines.append(block.get("text", ""))
                    elif block_type == "thinking":
                        lines += [
                            "[Thinking output]",
                            block.get("thinking") or "[Not exposed by CLI]",
                        ]
                    elif block_type == "tool_use":
                        lines += [
                            f"Tool: {block.get('name')} [{block.get('id')}]",
                            _text(block.get("input")),
                        ]
                    elif block_type == "tool_result":
                        lines += [
                            f"Tool result: {block.get('tool_use_id')} (error={block.get('is_error', False)})",
                            _text(block.get("content")),
                        ]
                    else:
                        lines.append(_text(block))
                if event.get("parent_tool_use_id"):
                    lines.append(f"Parent tool: {event['parent_tool_use_id']}")
            elif (
                isinstance(event.get("item"), dict)
                and event["item"].get("type") == "command_execution"
            ):
                item = event["item"]
                lines += [
                    f"Command [{item.get('id')}]: {item.get('command', '')}",
                    f"Status: {item.get('status')} | Exit code: {item.get('exit_code')}",
                    item.get("aggregated_output", ""),
                ]
            elif isinstance(event.get("item"), dict) and "text" in event["item"]:
                item = event["item"]
                lines += [f"{item.get('type')} [{item.get('id')}]", _text(item["text"])]
            else:
                # Codex items include commands, output, edits, and collaboration
                # events. Preserve all fields, including unfamiliar event types.
                lines.append(_text(event))
            lines.append("")
    else:
        lines += ["[No trace captured]", ""]
    stderr = directory / "stderr.log"
    if stderr.exists() and stderr.stat().st_size:
        lines += [
            "=== STDERR (ordering relative to events unavailable) ===",
            stderr.read_text(errors="replace"),
            "",
        ]
    result = directory / "result.json"
    if result.exists():
        lines += ["=== HARNESS RESULT ===", result.read_text(), ""]
    path = directory / "session.log"
    path.write_text("\n".join(lines))
    return path
