from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from docker.errors import ImageNotFound

from oracle_bench.artifacts import capture, snapshot
from oracle_bench.config import RunConfig, load_config, validate_resolved_config
from oracle_bench.container import Profile, docker_client, open_sandbox
from oracle_bench.container.images import prepare_image
from oracle_bench.datasets import resolve_source
from oracle_bench.evaluate import check_reference, evaluate
from oracle_bench.ground_truth import write_ground_truth
from oracle_bench.harnesses import generate, require_credentials
from oracle_bench.io import read_json, write_json
from oracle_bench.paths import RunPaths
from oracle_bench.prompts import render_prompt
from oracle_bench.report import report
from oracle_bench.workspace import RepositoryWorkspace


def status(run_dir: Path, stage: str, state="running", **details):
    write_json(
        run_dir / "status.json",
        {
            "stage": stage,
            "state": state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **details,
        },
    )
    print(f"[{stage}] {state}: {run_dir}", flush=True)


def completion_state(result: dict) -> str:
    if (
        result["agent"]["status"] == "completed"
        and result["buggy_status"] == result["golden_status"] == "completed"
        and result["submission_compliant"]
    ):
        return "completed"
    return "completed_with_errors"


def run(config: RunConfig) -> Path:
    require_credentials(config)
    prompt_template = Path(config.task.prompt).read_text()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = Path(config.output) / run_id
    run_dir.mkdir(parents=True)
    paths = RunPaths.create(run_dir)

    stage = "resolve"
    try:
        # Verify dataset source adapter exists
        status(run_dir, stage)
        instance, config.runtime = resolve_source(config.source)
        validate_resolved_config(config)
        # Freeze both the expanded configuration and exact delivered prompt in the run.
        config.task.prompt = str(paths.prompt)
        paths.config.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False))
        test_target = instance["test_target"] if config.task.scope == "localized" else None
        paths.prompt.write_text(render_prompt(prompt_template, config, test_target))
        write_json(paths.instance, instance)
        write_ground_truth(paths, instance)
        with docker_client() as client:
            # Preapre task image
            stage = "build"
            status(run_dir, stage)
            image = prepare_image(client, config, run_dir)
            write_json(paths.runtime, {"image": image})

            # Check that a fail->pass pair exists
            # NOTE: in the future this will probably need to be changed to accomodate other
            # datasets
            stage = "reference"
            status(run_dir, stage)
            check_reference(client, config, image, instance, run_dir)

            # Generate tests in the sandbox with the correct harness
            stage = "generate"
            status(run_dir, stage)
            log = paths.generation / "setup.log"
            with open_sandbox(client, image, config, Profile.GENERATION, log) as sandbox:
                workspace = RepositoryWorkspace(sandbox, config)
                workspace.prepare(instance["base_commit"], paths.generation)
                before = snapshot(sandbox, paths.generation / "before.json", log)
                baseline = workspace.baseline(paths.generation / "baseline.txt")
                generate(sandbox, config, run_dir)

                # Capture changes made
                stage = "capture"
                status(run_dir, stage)
                capture(sandbox, config, run_dir, before, baseline)

            # Run evaluation on the generated tests
            stage = "evaluate"
            status(run_dir, stage)
            result = evaluate(client, config, image, instance, run_dir)
        report(run_dir)
        status(run_dir, "finished", completion_state(result))
    except KeyboardInterrupt:
        status(run_dir, stage, "interrupted")
        raise
    except Exception as exc:
        status(run_dir, stage, "failed", error=str(exc))
        raise
    return run_dir


def reevaluate(run_dir: Path) -> Path:
    paths = RunPaths.open(run_dir)
    config = load_config(paths.config, resolved=True)
    image = read_json(paths.runtime)["image"]
    status(run_dir, "evaluate")
    try:
        with docker_client() as client:
            try:
                client.images.get(image)
            except ImageNotFound:
                raise RuntimeError(
                    "Saved runtime image is missing. Restore it before reevaluation."
                ) from None
            result = evaluate(client, config, image, read_json(paths.instance), run_dir)
        path = report(run_dir)
        status(run_dir, "finished", completion_state(result))
        return path
    except KeyboardInterrupt:
        status(run_dir, "evaluate", "interrupted")
        raise
    except Exception as exc:
        status(run_dir, "evaluate", "failed", error=str(exc))
        raise
