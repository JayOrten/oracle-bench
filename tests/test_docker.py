"""Opt-in checks using a prepared smoke image; never invoke an agent or model."""

import json
import os
import shutil
import uuid
from pathlib import Path

import docker
import pytest
import yaml

from oracle_bench.config import load_config
from oracle_bench.container import Profile, open_sandbox
from oracle_bench.container.images import ASSETS, build_image
from oracle_bench.evaluate import run_version
from oracle_bench.io import digest, read_json, write_json
from oracle_bench.paths import RunPaths
from oracle_bench.run import reevaluate
from oracle_bench.runners.pytest import pair_results

pytestmark = pytest.mark.docker


def test_local_sdk_build_exec_and_copy(tmp_path):
    """Opt-in image/API smoke check using only a previously prepared runtime."""
    saved = os.environ.get("ORACLE_BENCH_SMOKE_RUN")
    if not saved:
        pytest.skip("Set ORACLE_BENCH_SMOKE_RUN to use a local prepared runtime")
    saved = Path(saved).resolve()
    saved_paths = RunPaths.open(saved)
    config = load_config(saved_paths.config, resolved=True)
    parent = read_json(saved_paths.runtime)["image"]
    context = tmp_path / "context"
    context.mkdir()
    shutil.copyfile(ASSETS / "docker/smoke.Dockerfile", context / "smoke.Dockerfile")
    shutil.copytree(
        ASSETS / "container_helpers",
        context / "container_helpers",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    client = docker.from_env()
    try:
        with (tmp_path / "build.log").open("w") as log:
            image = build_image(
                client,
                context,
                "smoke.Dockerfile",
                {"BASE_IMAGE": parent, "SMOKE_ID": uuid.uuid4().hex},
                config.runtime.platform,
                log,
            )
        try:
            with open_sandbox(
                client, image.id, config, Profile.EVALUATION, tmp_path / "log"
            ) as sandbox:
                prompt = tmp_path / "prompt"
                prompt.write_text("fixture input")
                result = sandbox.run(
                    [
                        config.runtime.python,
                        "-c",
                        "import sys; print(sys.stdin.read()); print('stderr', file=sys.stderr)",
                    ],
                    stdin=prompt,
                    stdout=tmp_path / "stdout",
                    stderr=tmp_path / "stderr",
                )
                assert result.exit_code == 0
                assert (tmp_path / "stdout").read_text().strip() == "fixture input"
                assert (tmp_path / "stderr").read_text().strip() == "stderr"
                sandbox.upload(prompt, "/tmp/oracle-copy")
                sandbox.download("/tmp/oracle-copy", tmp_path / "copied")
                assert (tmp_path / "copied").read_bytes() == prompt.read_bytes()
        finally:
            client.images.remove(image.id)
    finally:
        client.close()


# Deliberately handwritten evaluator probes, not benchmark predictions.
PROBES = """import socket
import pytest
import requests

def exception_type():
    class Raw:
        def stream(self, chunk_size, decode_content=None):
            raise socket.error('controlled stream failure')
    response = requests.Response()
    response.raw = Raw()
    with pytest.raises(Exception) as caught:
        list(response.iter_content())
    return type(caught.value)

def test_pass_on_both():
    assert requests.Response().status_code is None

def test_fail_on_buggy_pass_on_golden():
    assert exception_type() is requests.exceptions.ConnectionError

def test_pass_on_buggy_fail_on_golden():
    assert exception_type() is socket.error

def test_fail_on_both():
    assert requests.Response().status_code == 123456
"""


@pytest.mark.parametrize("visibility", ["keep", "hide"])
def test_real_requests_pair_and_artifact_copy(tmp_path, visibility, monkeypatch, request):
    saved = os.environ.get("ORACLE_BENCH_SMOKE_RUN")
    if not saved:
        pytest.skip("Set ORACLE_BENCH_SMOKE_RUN to a run with a prepared Requests smoke image")
    saved = Path(saved).resolve()
    saved_paths = RunPaths.open(saved)
    config = load_config(saved_paths.config, resolved=True)
    config.task.existing_tests = visibility
    instance = read_json(saved_paths.instance)
    assert instance["instance_id"] == "psf__requests-2148"
    image = read_json(saved_paths.runtime)["image"]
    client = docker.from_env()
    request.addfinalizer(client.close)
    paths = RunPaths.create(tmp_path)
    path = paths.submission / "files" / config.task.generated_dir / "test_probes.py"
    path.parent.mkdir(parents=True)
    path.write_text(PROBES)
    files = {
        f"{config.task.generated_dir}/test_probes.py": {
            "sha256": digest(path.read_bytes()),
            "mode": 0o644,
        }
    }
    write_json(
        paths.submission / "manifest.json",
        {
            "files": files,
            "sha256": digest(json.dumps(files, sort_keys=True).encode()),
            "empty": False,
            "compliant": True,
            "forbidden_changes": [],
        },
    )
    buggy = run_version(client, config, image, instance, tmp_path, "buggy")
    golden = run_version(client, config, image, instance, tmp_path, "golden")
    result = pair_results(buggy, golden)
    assert buggy["status"] == golden["status"] == "completed", (buggy, golden)
    assert [cell["count"] for cell in result["matrix"].values()] == [1, 1, 1, 1]
    for version in ["buggy", "golden"]:
        coverage = read_json(paths.evaluation / version / "coverage.json")
        assert coverage["status"] == "available"
        assert coverage["covered_lines"] > 0
        assert coverage["executable_lines"] >= coverage["covered_lines"]
    if visibility == "keep":
        # Replay a saved artifact through the public reevaluation path, with no credentials.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("CODEX_API_KEY", raising=False)
        paths.config.write_text(yaml.safe_dump(config.to_dict()))
        write_json(paths.instance, instance)
        write_json(paths.runtime, {"image": image})
        write_json(
            paths.generation / "result.json",
            {
                "status": "not_run_handwritten_probe",
                "duration_seconds": 0,
                "usage": None,
            },
        )
        report = reevaluate(tmp_path)
        assert report.is_file()
        replay = read_json(paths.results)
        assert replay["matrix"] == result["matrix"]
        assert replay["artifact_sha256"] == read_json(paths.submission / "manifest.json")["sha256"]
