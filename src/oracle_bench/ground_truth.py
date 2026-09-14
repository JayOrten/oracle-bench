"""Materialize private dataset evidence for human analysis after a run."""

from __future__ import annotations

from oracle_bench.paths import RunPaths


def write_ground_truth(paths: RunPaths, instance: dict) -> None:
    """Write readable issue and repair artifacts without exposing them to the agent."""
    issue = instance["original_record"].get("problem_statement", "").rstrip()
    issue_document = f"# {instance['instance_id']}\n\n{issue}\n"
    (paths.ground_truth / "issue.md").write_text(issue_document)

    patch = instance["golden_patch"]
    (paths.ground_truth / "fix.patch").write_text(patch.rstrip() + "\n")
