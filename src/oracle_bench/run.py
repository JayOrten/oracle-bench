from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from oracle_bench.artifacts import capture, snapshot
from oracle_bench.config import RunConfig, load_config
from oracle_bench.containers import Docker, prepare_workspace
from oracle_bench.datasets.swebench import resolve
from oracle_bench.evaluate import check_reference, evaluate
from oracle_bench.harnesses import generate, require_credentials
from oracle_bench.io import read_json, write_json
from oracle_bench.report import report


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
    docker = Docker(config)
    docker.check()
    require_credentials(config)
    prompt = Path(config.task.prompt).read_text()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = Path(config.output) / run_id
    run_dir.mkdir(parents=True)
    # Save the prompt in the run so reevaluation does not depend on the original file.
    config.task.prompt = str(run_dir / "prompt.txt")
    (run_dir / "config.resolved.yaml").write_text(yaml.safe_dump(config.to_dict(), sort_keys=False))
    context = (
        f"\n\nPlace new tests and fixtures under `{config.task.generated_dir}/`. "
        "Do not edit existing files outside that directory.\n"
        f"The project Python is `{config.environment.python}`. "
        f"Run tests with `python -m pytest -o addopts= {config.task.generated_dir}`.\n"
    )
    (run_dir / "prompt.txt").write_text(prompt.rstrip() + context)
    stage = "resolve"
    try:
        status(run_dir, stage)
        instance = resolve(config.dataset)
        write_json(run_dir / "instance.json", instance)
        stage = "build"
        status(run_dir, stage)
        image = docker.prepare_image(run_dir)
        write_json(run_dir / "runtime.json", {"image": image})
        stage = "reference"
        status(run_dir, stage)
        check_reference(docker, image, instance, run_dir)
        stage = "generate"
        status(run_dir, stage)
        log = run_dir / "agent" / "setup.log"
        with docker.container(image, log, network=True) as container:
            prepare_workspace(docker, container, instance, log)
            before = snapshot(docker, container, run_dir / "agent" / "before.json", log)
            docker.shell(container, "git rev-parse HEAD > /tmp/oracle-baseline.txt", log, 30)
            docker.get(
                container, "/tmp/oracle-baseline.txt", run_dir / "agent" / "baseline.txt", log
            )
            baseline = (run_dir / "agent" / "baseline.txt").read_text().strip()
            generate(docker, container, run_dir)
            stage = "capture"
            status(run_dir, stage)
            capture(docker, container, run_dir, before, baseline)
        stage = "evaluate"
        status(run_dir, stage)
        result = evaluate(docker, image, instance, run_dir)
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
    config = load_config(run_dir / "config.resolved.yaml")
    docker = Docker(config)
    docker.check()
    image = read_json(run_dir / "runtime.json")["image"]
    if docker.inspect_image(image) is None:
        raise RuntimeError("Saved runtime image is missing. Restore it before reevaluation.")
    status(run_dir, "evaluate")
    try:
        result = evaluate(docker, image, read_json(run_dir / "instance.json"), run_dir)
        path = report(run_dir)
        status(run_dir, "finished", completion_state(result))
        return path
    except KeyboardInterrupt:
        status(run_dir, "evaluate", "interrupted")
        raise
    except Exception as exc:
        status(run_dir, "evaluate", "failed", error=str(exc))
        raise
