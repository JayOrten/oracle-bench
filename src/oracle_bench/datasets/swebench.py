from __future__ import annotations

import json
import re
from pathlib import Path

from oracle_bench.config import RuntimeConfig, SourceConfig
from oracle_bench.io import digest

# Image naming/environment conventions are checked against this upstream revision.
UPSTREAM_REVISION = "3947b299c121bb1f45f5094180c0f39fa0c599a0"


REPOSITORY_LAYOUTS = {
    "astropy/astropy": ("astropy", "astropy", ["astropy/**/tests"]),
    "django/django": ("django", "django", ["tests"]),
    "matplotlib/matplotlib": ("lib/matplotlib", "matplotlib", ["lib/matplotlib/tests"]),
    "mwaskom/seaborn": ("seaborn", "seaborn", ["tests"]),
    "pallets/flask": ("src/flask", "flask", ["tests"]),
    "psf/requests": ("requests", "requests", ["test_requests.py", "tests"]),
    "pydata/xarray": ("xarray", "xarray", ["xarray/tests"]),
    "pytest-dev/pytest": ("src/_pytest", "_pytest", ["testing"]),
    "scikit-learn/scikit-learn": ("sklearn", "sklearn", ["sklearn/**/tests"]),
    "sphinx-doc/sphinx": ("sphinx", "sphinx", ["tests"]),
    "sympy/sympy": ("sympy", "sympy", ["sympy/**/tests"]),
}


def image_for(instance_id: str, platform: str = "linux/amd64") -> str:
    architecture = "x86_64" if platform == "linux/amd64" else "arm64"
    image_id = instance_id.lower().replace("__", "_1776_")
    if not re.fullmatch(r"[a-z0-9_.-]+", image_id):
        raise ValueError(f"Cannot derive a SWE-bench image for {instance_id!r}")
    return f"swebench/sweb.eval.{architecture}.{image_id}:latest"


def runtime_for(record: dict) -> RuntimeConfig:
    repo = record["repo"]
    if repo not in REPOSITORY_LAYOUTS:
        raise ValueError(f"No tested SWE-bench runtime profile for repository {repo!r}")
    source_root, import_module, existing_test_globs = REPOSITORY_LAYOUTS[repo]
    return RuntimeConfig(
        image=image_for(record["instance_id"]),
        source_roots=[source_root],
        import_modules=[import_module],
        existing_test_globs=existing_test_globs,
    )


def resolve(config: SourceConfig) -> tuple[dict, RuntimeConfig]:
    if config.record:
        record = json.loads(Path(config.record).read_text())
    else:
        try:
            from datasets import load_dataset
        except ImportError as exc:
            raise RuntimeError("Install oracle-bench[dataset] or set dataset.record") from exc
        rows = load_dataset(config.dataset_name, split=config.split, revision=config.revision)
        matches = [row for row in rows if row["instance_id"] == config.instance]
        if len(matches) != 1:
            raise ValueError(f"Expected one record for {config.instance}, found {len(matches)}")
        record = matches[0]
    for key in ["instance_id", "repo", "base_commit", "patch", "test_patch"]:
        if not isinstance(record.get(key), str) or not record[key]:
            raise ValueError(f"SWE-bench record is missing {key}")
    if record["instance_id"] != config.instance:
        raise ValueError("Local record does not match configured instance ID")
    if not re.fullmatch(r"[0-9a-f]{40}", record["base_commit"]):
        raise ValueError("base_commit must be immutable")
    fail_to_pass = record.get("FAIL_TO_PASS", [])
    if isinstance(fail_to_pass, str):
        fail_to_pass = json.loads(fail_to_pass)
    if not isinstance(fail_to_pass, list) or not all(isinstance(v, str) for v in fail_to_pass):
        raise ValueError("FAIL_TO_PASS must be a list of test IDs")
    instance = {
        "schema_version": 1,
        "instance_id": record["instance_id"],
        "repo": record["repo"],
        "base_commit": record["base_commit"],
        "golden_patch": record["patch"],
        "reference_test_patch": record["test_patch"],
        "reference_test_ids": fail_to_pass,
        "source": {
            "kind": config.kind,
            "dataset": config.dataset,
            "name": config.dataset_name,
            "revision": config.revision,
            "split": config.split,
            "upstream_revision": UPSTREAM_REVISION,
            "record_sha256": digest(json.dumps(record, sort_keys=True).encode()),
        },
        "original_record": record,
    }
    return instance, runtime_for(record)
