# NOTE: obviously generated, probably modify this in the future
from pathlib import Path

from oracle_bench.harnesses.transcript import render_session
from oracle_bench.io import read_json
from oracle_bench.paths import RunPaths

LABELS = {
    "pass_on_both": "Pass on both",
    "fail_on_buggy_pass_on_golden": "Fail on buggy, pass on golden",
    "pass_on_buggy_fail_on_golden": "Pass on buggy, fail on golden",
    "fail_on_both": "Fail on both",
}


def report(run_dir: Path) -> Path:
    paths = RunPaths.open(run_dir)
    results = read_json(paths.results)
    render_session(run_dir)
    lines = [
        f"# Oracle Bench: {results['instance_id']}",
        "",
        "Test-generation scope: "
        + (
            "**calculated localized target**."
            if results["task_scope"] == "localized"
            else "**whole repository**."
        ),
        "",
        f"Existing repository test modules visible to agent: "
        f"**{'yes' if results['existing_tests'] == 'keep' else 'no'}**. "
        f"Agent: **{results['agent']['status']}**.",
        "",
        f"Buggy execution: **{results['buggy_status']}**. "
        f"Golden execution: **{results['golden_status']}**.",
        "",
    ]
    if results["task_scope"] == "localized":
        lines += [f"Calculated target: **{results['test_target']}**.", ""]
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
        "## Ground truth",
        "",
        "Private dataset evidence, retained for manual analysis and never exposed "
        "to the generation agent:",
        "",
        "- [Original issue](ground-truth/issue.md)",
        "- [Buggy-to-golden fix diff](ground-truth/fix.patch)",
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
        "- [Paired outcomes and test IDs](evaluation/results.json)",
        "- [Frozen test manifest](submission/manifest.json)",
        "- [Image provenance](image-build/images.json)",
        "- [Readable agent session](generation/session.log)",
        "- [Raw agent events](generation/trace.jsonl)",
        "- [Workspace diff](generation/workspace.diff)",
        "- [Buggy results](evaluation/buggy/tests.json) · [log](evaluation/buggy/output.log)",
        "- [Golden results](evaluation/golden/tests.json) · [log](evaluation/golden/output.log)",
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
            else "Existing test modules were removed from both final evaluation workspaces."
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
    path = paths.report
    path.write_text("\n".join(lines))
    return path
