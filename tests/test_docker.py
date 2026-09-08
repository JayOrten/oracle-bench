"""Opt-in checks using a prepared smoke image; never invoke an agent or model."""

import json
import os
from pathlib import Path

import pytest
import yaml

from oracle_bench.config import load_config
from oracle_bench.containers import Docker
from oracle_bench.evaluate import run_version
from oracle_bench.io import digest, read_json, write_json
from oracle_bench.run import reevaluate
from oracle_bench.runners.pytest import pair_results

pytestmark = pytest.mark.docker

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
def test_real_requests_pair_and_artifact_copy(tmp_path, visibility, monkeypatch):
    saved = os.environ.get("ORACLE_BENCH_SMOKE_RUN")
    if not saved:
        pytest.skip("Set ORACLE_BENCH_SMOKE_RUN to a run with a prepared Requests smoke image")
    saved = Path(saved).resolve()
    config = load_config(saved / "config.resolved.yaml")
    config.task.existing_tests = visibility
    instance = read_json(saved / "instance.json")
    assert instance["instance_id"] == "psf__requests-2148"
    image = read_json(saved / "runtime.json")["image"]
    docker = Docker(config)
    docker.check()
    path = tmp_path / "generated" / "files" / config.task.generated_dir / "test_probes.py"
    path.parent.mkdir(parents=True)
    path.write_text(PROBES)
    files = {
        f"{config.task.generated_dir}/test_probes.py": {
            "sha256": digest(path.read_bytes()),
            "mode": 0o644,
        }
    }
    write_json(
        tmp_path / "generated" / "manifest.json",
        {
            "files": files,
            "sha256": digest(json.dumps(files, sort_keys=True).encode()),
            "empty": False,
            "compliant": True,
            "forbidden_changes": [],
        },
    )
    buggy = run_version(docker, image, instance, tmp_path, "buggy")
    golden = run_version(docker, image, instance, tmp_path, "golden")
    result = pair_results(buggy, golden)
    assert buggy["status"] == golden["status"] == "completed", (buggy, golden)
    assert [cell["count"] for cell in result["matrix"].values()] == [1, 1, 1, 1]
    for version in ["buggy", "golden"]:
        coverage = read_json(tmp_path / version / "coverage.json")
        assert coverage["status"] == "available"
        assert coverage["covered_lines"] > 0
        assert coverage["executable_lines"] >= coverage["covered_lines"]
    if visibility == "keep":
        # Replay a saved artifact through the public reevaluation path, with no credentials.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("CODEX_API_KEY", raising=False)
        (tmp_path / "config.resolved.yaml").write_text(yaml.safe_dump(config.to_dict()))
        write_json(tmp_path / "instance.json", instance)
        write_json(tmp_path / "runtime.json", {"image": image})
        write_json(
            tmp_path / "agent" / "result.json",
            {
                "status": "not_run_handwritten_probe",
                "duration_seconds": 0,
                "usage": None,
            },
        )
        report = reevaluate(tmp_path)
        assert report.is_file()
        replay = read_json(tmp_path / "results.json")
        assert replay["matrix"] == result["matrix"]
        assert (
            replay["artifact_sha256"]
            == read_json(tmp_path / "generated" / "manifest.json")["sha256"]
        )
