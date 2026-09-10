# NOTE: obviously generated, probably modify this in the future
from pathlib import Path

from oracle_bench.harnesses.transcript import render_session
from oracle_bench.io import read_json

LABELS = {
    "pass_on_both": "Pass on both",
    "fail_on_buggy_pass_on_golden": "Fail on buggy, pass on golden",
    "pass_on_buggy_fail_on_golden": "Pass on buggy, fail on golden",
    "fail_on_both": "Fail on both",
}


def report(run_dir: Path) -> Path:
    results = read_json(run_dir / "results.json")
    render_session(run_dir)
    lines = [
        f"# Oracle Bench: {results['instance_id']}",
        "",
        f"Existing repository tests visible to agent: "
        f"**{'yes' if results['existing_tests'] == 'keep' else 'no'}**. "
        f"Agent: **{results['agent']['status']}**.",
        "",
        f"Buggy execution: **{results['buggy_status']}**. "
        f"Golden execution: **{results['golden_status']}**.",
        "",
    ]
    if results.get("test_target"):
        lines += [f"Localized test target: **{results['test_target']}**.", ""]
    if results["diagnostic_only"]:
        lines += [
            "**Diagnostic only:** the agent changed files outside its allowed test artifact.",
            "",
            *[f"- `{name}`" for name in results["forbidden_changes"]],
            "",
        ]
    if results["agent"].get("errors"):
        error = results["agent"]["errors"][-1]
        message = error.get("message") or error.get("error", {}).get("message", "See agent logs")
        lines += [f"Agent message: {message}", ""]
    lines += [
        "| Outcome | Tests |",
        "|---|---:|",
        *[f"| {label} | {results['matrix'][key]['count']} |" for key, label in LABELS.items()],
        "",
        f"Other/unmatched outcomes: {len(results['other_outcomes'])}.",
        "",
        "Pass on both means the test did not distinguish these versions. "
        "It does not by itself establish an incorrect oracle.",
        "",
        "## Generated-test line coverage",
        "",
        "| Version | Covered / executable lines | Coverage |",
        "|---|---:|---:|",
    ]
    for version, cov in results["coverage"].items():
        if cov["status"] == "available":
            lines.append(
                f"| {version} | {cov['covered_lines']} / {cov['executable_lines']} "
                f"| {cov['percent']:.2f}% |"
            )
        else:
            lines.append(f"| {version} | unavailable | — |")
    lines += [
        "",
        "## Artifacts",
        "",
        "- [Paired outcomes and test IDs](results.json)",
        "- [Frozen test manifest](generated/manifest.json)",
        "- [Image provenance](build/images.json)",
        "- [Readable agent session](agent/session.log)",
        "- [Raw agent events](agent/trace.jsonl)",
        "- [Workspace diff](agent/workspace.diff)",
        "- [Buggy results](buggy/tests.json) · [log](buggy/output.log)",
        "- [Golden results](golden/tests.json) · [log](golden/output.log)",
        "",
        "## Limits of this exploratory run",
        "",
        "Git history and upstream retrieval have not been audited. "
        "The paired counts include only completed test executions on both versions. "
        "Skips, expected failures, setup/collection errors, and incomplete runs are separate. "
        "Coverage excludes existing tests as execution targets. "
        + (
            "Because existing tests were visible, generated tests may reuse their fixtures."
            if results["existing_tests"] == "keep"
            else "Existing test paths were removed from both final evaluation workspaces."
        ),
        "",
        f"Agent wall time: {results['agent'].get('duration_seconds', 0):.1f}s. "
        f"Reported token usage: `{results['agent'].get('usage')}`. "
        + (
            f"Harness-reported model cost: ${results['agent']['cost_usd']:.4f}."
            if results["agent"].get("cost_usd") is not None
            else "Monetary cost is unavailable unless supplied by the harness."
        ),
        "",
    ]
    path = run_dir / "report.md"
    path.write_text("\n".join(lines))
    return path
