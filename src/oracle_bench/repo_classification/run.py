"""Standalone execution of one SWE-bench task-classification turn."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from docker import DockerClient
from docker.errors import DockerException

from oracle_bench.config import ClassificationConfig
from oracle_bench.container.images import prepare_image
from oracle_bench.container.sandbox import Profile, Sandbox, docker_client, open_sandbox
from oracle_bench.harnesses import provenance, run_turn, turn_request
from oracle_bench.harnesses.launch import AgentTurnRequest, require_credential
from oracle_bench.instance import resolve_source
from oracle_bench.io import digest, utc_stamp, write_json
from oracle_bench.repo_classification.contracts import (
    ClassificationResult,
    ExposedArtifact,
    SavedClassification,
    WorkspaceSpec,
    failed_classification,
    parse_classification,
    read_saved_classification,
)
from oracle_bench.results import InstanceRecord, write_result

CLASSIFICATION_ROOT = "/oracle-classification"


def classify(config: ClassificationConfig) -> Path:
    """Resolve, prepare, and classify one problem in a new immutable attempt."""
    require_credential(config.classifier)
    instance, config.runtime = resolve_source(config.source)
    attempt_id = utc_stamp() + "-" + uuid.uuid4().hex[:8]
    attempt = Path(config.output) / instance.instance_id / attempt_id
    for directory in (attempt / "inputs", attempt / "image-build", attempt / "agent"):
        directory.mkdir(parents=True, exist_ok=True)
    stage = "resolve"
    try:
        _status(attempt, stage)
        rubric = attempt / "inputs/rubric.md"
        rubric.write_bytes(Path(config.rubric).read_bytes())
        config.rubric = str(rubric.resolve())
        (attempt / "inputs/config.resolved.yaml").write_text(
            yaml.safe_dump(config.to_dict(), sort_keys=False)
        )
        write_result(attempt / "inputs/instance.json", instance)

        with docker_client() as client:
            stage = "build"
            _status(attempt, stage)
            image = prepare_image(client, config, attempt / "image-build")
            write_json(attempt / "image-build/runtime.json", {"image": image})

            stage = "classify"
            _status(attempt, stage)
            result = _classification_stage(client, config, attempt, image, instance)

        state = "completed" if result.status == "completed" else "completed_with_errors"
        _status(attempt, "finished", state, classification_status=result.status)
    except KeyboardInterrupt:
        _status(attempt, stage, "interrupted")
        raise
    except Exception as error:
        _status(attempt, stage, "failed", error=str(error))
        raise
    return attempt


def _classification_stage(
    client: DockerClient,
    config: ClassificationConfig,
    attempt: Path,
    image: str,
    instance: InstanceRecord,
) -> ClassificationResult:
    request = turn_request(
        config,
        config.classifier,
        attempt / "inputs/rubric.md",
        config.require_runtime().workdir,
        attempt / "agent",
    )
    classification = attempt / "classification.json"
    result_path = attempt / "agent/result.json"
    raw = attempt / "classification.raw.txt"
    final = attempt / "agent/final.txt"
    try:
        with open_sandbox(
            client, image, config, Profile.CLASSIFICATION, attempt / "workspace.log"
        ) as sandbox:
            build_classification_workspace(sandbox, config, attempt, image, instance)
            result = _execute_turn(sandbox, request, attempt)
            # Save before container cleanup so a late cleanup failure cannot replace a
            # valid model response with an annotation failure.
            _save_classification(attempt, instance, result)
    except (RuntimeError, OSError, ValueError, DockerException) as error:
        if classification.is_file():
            return read_saved_classification(classification).result
        if not result_path.is_file():
            write_json(
                result_path,
                {
                    "status": "failed",
                    "duration_seconds": 0,
                    "usage": None,
                    "cost_usd": None,
                    "errors": [{"message": str(error)}],
                    **provenance(request),
                },
            )
        if not raw.is_file():
            raw.write_text(final.read_text(errors="replace") if final.is_file() else "")
        result = failed_classification(str(error))
        _save_classification(attempt, instance, result)
    return result


def _execute_turn(
    sandbox: Sandbox, request: AgentTurnRequest, attempt: Path
) -> ClassificationResult:
    harness_result = run_turn(sandbox, request)
    final = attempt / "agent/final.txt"
    raw = final.read_text(errors="replace") if final.is_file() else ""
    (attempt / "classification.raw.txt").write_text(raw)
    if harness_result["status"] == "completed":
        return parse_classification(raw)
    errors = harness_result["errors"]
    reason = (
        str(errors[-1].get("message", errors[-1]))
        if errors
        else (f"Classifier harness ended with status {harness_result['status']}")
    )
    return failed_classification(reason, timed_out=harness_result["status"] == "timeout")


def _save_classification(
    attempt: Path,
    instance: InstanceRecord,
    result: ClassificationResult,
) -> None:
    saved = SavedClassification(
        instance_id=instance.instance_id,
        base_commit=instance.base_commit,
        source_record_sha256=instance.source.record_sha256,
        rubric_sha256=digest((attempt / "inputs/rubric.md").read_bytes()),
        result=result,
    )
    write_json(attempt / "classification.json", saved.model_dump(mode="json"))


def build_classification_workspace(
    sandbox: Sandbox,
    config: ClassificationConfig,
    attempt: Path,
    image: str,
    instance: InstanceRecord,
) -> WorkspaceSpec:
    """Reset the checkout and expose exactly the private evidence named here."""
    runtime = config.require_runtime()
    sandbox.run(
        ["git", "-C", runtime.workdir, "reset", "--hard", instance.base_commit],
        timeout=config.limits.setup_seconds,
    )
    sandbox.run(["mkdir", "-p", CLASSIFICATION_ROOT])

    evidence = [
        (attempt / "inputs/instance.json", CLASSIFICATION_ROOT + "/instance.json"),
        (attempt / "inputs/rubric.md", CLASSIFICATION_ROOT + "/rubric.md"),
    ]
    artifacts = []
    for source, destination in evidence:
        sandbox.upload(source, destination)
        artifacts.append(
            ExposedArtifact(
                source=source.relative_to(attempt).as_posix(),
                destination=destination,
                sha256=digest(source.read_bytes()),
            )
        )
    sandbox.run(["chmod", "-R", "a+rX", CLASSIFICATION_ROOT])

    spec = WorkspaceSpec(image=image, base_commit=instance.base_commit, artifacts=artifacts)
    write_json(attempt / "workspace-spec.json", spec.model_dump())
    return spec


def _status(attempt: Path, stage: str, state: str = "running", **details) -> None:
    write_json(
        attempt / "status.json",
        {
            "stage": stage,
            "state": state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **details,
        },
    )
    print(f"[{stage}] {state}: {attempt}", flush=True)
