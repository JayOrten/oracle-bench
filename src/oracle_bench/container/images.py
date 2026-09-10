"""Build checked-in image recipes and retain their exact inputs with the run."""

import json
import shutil
from pathlib import Path

from docker.errors import ImageNotFound

from oracle_bench.container.deadline import setup_deadline
from oracle_bench.io import digest, write_json

ASSETS = Path(__file__).parents[1]


def image_record(image, reference):
    return {"reference": reference, "id": image.id, "digests": image.attrs.get("RepoDigests") or []}


def resolve_image(client, reference, platform, log):
    """Reuse a local parent image, pulling only when it is absent."""
    try:
        image = client.images.get(reference)
    except ImageNotFound:
        events = client.api.pull(reference, platform=platform, stream=True, decode=True)
        record_events(events, log, operation="pull")
        image = client.images.get(reference)
    return image


def build_inputs(context: Path, recipe: str, arguments: dict, platform: str) -> dict:
    """Describe every input that affects the cached image's identity."""
    # Include all context bytes and platform: changing a helper must invalidate
    # our tag even when the Dockerfile itself has not changed.
    inputs = {"platform": platform, "arguments": arguments, "recipe": recipe}
    inputs["files"] = {
        path.relative_to(context).as_posix(): digest(path.read_bytes())
        for path in sorted(context.rglob("*"))
        if path.is_file()
    }
    return inputs


def record_events(events, log, *, operation: str):
    """Persist SDK evidence before interpreting success or failure."""
    for event in events:
        log.write(json.dumps(event) + "\n")
        log.flush()
        if "error" in event:
            raise RuntimeError(f"Image {operation} failed; see {log.name}")


def build_image(client, context, recipe, arguments, platform, log):
    """Save build inputs, reuse a matching image, or build the checked-in recipe."""
    inputs = build_inputs(context, recipe, arguments, platform)
    identity = digest(json.dumps(inputs, sort_keys=True).encode())[:24]
    tag = "oracle-bench/" + recipe.split(".")[0] + ":" + identity
    write_json(context.parent / recipe.replace(".Dockerfile", ".inputs.json"), inputs)
    try:
        return client.images.get(tag)
    except ImageNotFound:
        pass
    # The low-level SDK build method streams evidence even when a build fails.
    events = client.api.build(
        path=str(context),
        dockerfile=recipe,
        tag=tag,
        buildargs=arguments,
        platform=platform,
        rm=True,
        forcerm=True,
        decode=True,
    )
    record_events(events, log, operation="build")
    return client.images.get(tag)


def prepare_contexts(build: Path, harness: str) -> tuple[Path, Path]:
    """Copy only public build assets, never the host run directory."""
    agent_context = build / "agent"
    runtime_context = build / "runtime"
    agent_context.mkdir(parents=True)
    runtime_context.mkdir()
    shutil.copyfile(
        ASSETS / "docker" / "agents" / f"{harness}.Dockerfile",
        agent_context / "agent.Dockerfile",
    )
    shutil.copyfile(ASSETS / "docker/runtime.Dockerfile", runtime_context / "runtime.Dockerfile")
    helpers = runtime_context / "container_helpers"
    helpers.mkdir()
    for helper in sorted((ASSETS / "container_helpers").glob("*.py")):
        shutil.copyfile(helper, helpers / helper.name)
    return agent_context, runtime_context


def runtime_arguments(config, source, agent) -> dict[str, str]:
    runtime = config.require_runtime()
    return {
        "AGENT_IMAGE": agent.id,
        "PROJECT_IMAGE": source.id,
        "PROJECT_PYTHON": runtime.python,
        "PROJECT_PYTHON_DIR": str(Path(runtime.python).parent),
        "PYTEST_VERSION": config.toolchain.pytest_version,
        "COVERAGE_VERSION": config.toolchain.coverage_version,
    }


def prepare_image(client, config, run_dir: Path) -> str:
    """Resolve parents, build the harness, then extend the repository image."""
    runtime = config.require_runtime()
    build = run_dir / "build"
    agent_context, runtime_context = prepare_contexts(build, config.agent.harness)
    provenance = {}

    def record(name, image, reference):
        provenance[name] = image_record(image, reference)
        write_json(build / "images.json", provenance)

    # Save unresolved inputs too, so a failed first pull still has provenance.
    write_json(
        build / "requested.json",
        {
            "source": runtime.image,
            "node": config.toolchain.node_image,
            "platform": runtime.platform,
            "harness": config.agent.harness,
            "version": config.agent.version,
        },
    )
    with (build / "output.log").open("a") as log:
        with setup_deadline(config.limits.setup_seconds):
            source = resolve_image(client, runtime.image, runtime.platform, log)
            record("source", source, runtime.image)
        with setup_deadline(config.limits.setup_seconds):
            node = resolve_image(client, config.toolchain.node_image, runtime.platform, log)
            record("node", node, config.toolchain.node_image)
        with setup_deadline(config.limits.setup_seconds):
            agent = build_image(
                client,
                agent_context,
                "agent.Dockerfile",
                {"NODE_IMAGE": node.id, "AGENT_VERSION": config.agent.version},
                runtime.platform,
                log,
            )
            record("agent", agent, agent.id)
        with setup_deadline(config.limits.setup_seconds):
            prepared = build_image(
                client,
                runtime_context,
                "runtime.Dockerfile",
                runtime_arguments(config, source, agent),
                runtime.platform,
                log,
            )
            record("runtime", prepared, prepared.id)
    return prepared.id
