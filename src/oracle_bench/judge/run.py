"""Standalone execution of the privileged generated-test judge."""

from __future__ import annotations

from datetime import datetime, timezone
from string import Template

from docker import DockerClient
from docker.errors import DockerException

from oracle_bench.config import RunConfig
from oracle_bench.container.images import require_saved_image
from oracle_bench.container.sandbox import Profile, Sandbox, docker_client, open_sandbox
from oracle_bench.generation import verify_bundle
from oracle_bench.harnesses import provenance, run_turn, turn_request
from oracle_bench.harnesses.launch import AgentTurnRequest, require_credential
from oracle_bench.io import archive_files, read_json, require_files, write_json
from oracle_bench.judge.contracts import (
    JudgmentResult,
    failed_judgment,
    parse_judgment,
    validate_judgment,
)
from oracle_bench.judge.workspace import JUDGE_ROOT, build_judge_workspace
from oracle_bench.paths import RunPaths
from oracle_bench.results import (
    EvaluationResult,
    InstanceRecord,
    read_evaluation_result,
    read_instance_record,
)


def judge(config: RunConfig, paths: RunPaths) -> JudgmentResult:
    """Judge one completed run without repeating generation or evaluation.

    Rendering belongs to the caller, so this stage never depends on the report.
    """
    require_credential(config.require_judge())
    require_files(
        [
            paths.runtime,
            paths.instance,
            paths.results,
            paths.judge.rubric,
            paths.judge.instructions,
        ],
        "Judge inputs",
    )
    image = read_json(paths.runtime)["image"]
    instance = read_instance_record(paths.instance)
    evaluation = read_evaluation_result(paths.results)

    manifest = verify_bundle(paths)
    if manifest["empty"]:
        raise ValueError("Cannot judge an empty generated-test submission")
    with docker_client() as client:
        require_saved_image(client, image, "judging")
        judgment = judge_stage(
            client, config, paths, image, instance, evaluation, manifest=manifest
        )

    if paths.status.is_file():
        status = read_json(paths.status)
        status["judge_status"] = judgment.status
        status["updated_at"] = datetime.now(timezone.utc).isoformat()
        write_json(paths.status, status)
    return judgment


def judge_stage(
    client: DockerClient,
    config: RunConfig,
    paths: RunPaths,
    image: str,
    instance: InstanceRecord,
    evaluation: EvaluationResult,
    *,
    manifest: dict | None = None,
) -> JudgmentResult:
    """Build the workspace, run one judge turn, and always save a judgment either way."""
    # Built before anything is moved, so a bad harness pin fails without destroying
    # the previous attempt. The failure handler needs it to record provenance.
    request = turn_request(
        config, config.require_judge(), paths.judge.prompt, JUDGE_ROOT, paths.judge.agent
    )
    try:
        # Move a previous automated attempt aside. Human ratings stay put.
        human = paths.judge.human
        preserved = {
            paths.judge.rubric.name,
            paths.judge.instructions.name,
            human.judgments.name,
            human.history.name,
            human.workspaces.name,
        }
        previous = [path for path in paths.judge.root.iterdir() if path.name not in preserved]
        archive_files(previous, paths.judge.history)

        # The instructions name the workspace; the rubric follows them verbatim.
        instructions = Template(paths.judge.instructions.read_text())
        paths.judge.prompt.write_text(
            instructions.substitute(root=JUDGE_ROOT) + paths.judge.rubric.read_text()
        )
        with open_sandbox(client, image, config, Profile.JUDGE, paths.judge.log) as sandbox:
            build_judge_workspace(
                sandbox, config, paths, image, instance, evaluation, manifest=manifest
            )
            _execute_judge_turn(sandbox, request, paths, evaluation)
    except (RuntimeError, OSError, ValueError, DockerException) as error:
        # A judge failure is an annotation failure. It must never discard the completed
        # generation and evaluation evidence it describes. A judgment this attempt
        # already saved is kept, because a late failure such as container cleanup does
        # not invalidate an answer the model already gave.
        attempt_path = paths.judge.result
        if attempt_path.is_file():
            attempt = read_json(attempt_path)
        else:
            attempt = {
                "status": "failed",
                "duration_seconds": 0,
                "usage": None,
                "cost_usd": None,
                "errors": [],
                **provenance(request),
            }
        attempt["errors"] = [*attempt["errors"], {"message": str(error)}]
        write_json(attempt_path, attempt)
        if not paths.judge.judgment_raw.exists():
            # Keep whatever the model managed to write before the failure.
            final = paths.judge.final
            paths.judge.judgment_raw.write_text(
                final.read_text(errors="replace") if final.is_file() else ""
            )
        if not paths.judge.judgment.is_file():
            write_json(paths.judge.judgment, failed_judgment(str(error)).model_dump())
    return validate_judgment(read_json(paths.judge.judgment))


def _execute_judge_turn(
    sandbox: Sandbox, request: AgentTurnRequest, paths: RunPaths, evaluation: EvaluationResult
) -> None:
    """Turn the harness result into a saved judgment.

    Harness failures are left to propagate, so judge_stage records them in one place.
    """
    result = run_turn(sandbox, request)
    final = paths.judge.final
    raw = final.read_text(errors="replace") if final.is_file() else ""
    paths.judge.judgment_raw.write_text(raw)
    if result["status"] == "completed":
        judgment = parse_judgment(
            raw, has_relevant_fail_to_pass=evaluation.has_fail_on_buggy_pass_on_golden
        )
    else:
        # Prefer the harness's own last error over a generic status line.
        errors = result["errors"]
        if errors:
            last = errors[-1]
            message = last.get("message") if isinstance(last, dict) else None
            reason = str(message or last)
        else:
            reason = f"Judge harness ended with status {result['status']}"
        judgment = failed_judgment(reason, timed_out=result["status"] == "timeout")
    write_json(paths.judge.judgment, judgment.model_dump())
