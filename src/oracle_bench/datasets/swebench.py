from __future__ import annotations

import json
import re
from pathlib import Path

from oracle_bench.config import DatasetConfig
from oracle_bench.io import digest

# Image naming/environment conventions are checked against this upstream revision.
UPSTREAM_REVISION = "3947b299c121bb1f45f5094180c0f39fa0c599a0"


def resolve(config: DatasetConfig) -> dict:
    if config.record:
        record = json.loads(Path(config.record).read_text())
    else:
        try:
            from datasets import load_dataset
        except ImportError as exc:
            raise RuntimeError("Install oracle-bench[dataset] or set dataset.record") from exc
        rows = load_dataset(config.name, split=config.split, revision=config.revision)
        matches = [row for row in rows if row["instance_id"] == config.instance_id]
        if len(matches) != 1:
            raise ValueError(f"Expected one record for {config.instance_id}, found {len(matches)}")
        record = matches[0]
    for key in ["instance_id", "repo", "base_commit", "patch", "test_patch"]:
        if not isinstance(record.get(key), str) or not record[key]:
            raise ValueError(f"SWE-bench record is missing {key}")
    if record["instance_id"] != config.instance_id:
        raise ValueError("Local record does not match configured instance ID")
    if not re.fullmatch(r"[0-9a-f]{40}", record["base_commit"]):
        raise ValueError("base_commit must be immutable")
    fail_to_pass = record.get("FAIL_TO_PASS", [])
    if isinstance(fail_to_pass, str):
        fail_to_pass = json.loads(fail_to_pass)
    if not isinstance(fail_to_pass, list) or not all(isinstance(v, str) for v in fail_to_pass):
        raise ValueError("FAIL_TO_PASS must be a list of test IDs")
    return {
        "schema_version": 1,
        "instance_id": record["instance_id"],
        "repo": record["repo"],
        "base_commit": record["base_commit"],
        "golden_patch": record["patch"],
        "reference_test_patch": record["test_patch"],
        "reference_test_ids": fail_to_pass,
        "source": {
            "name": config.name,
            "revision": config.revision,
            "split": config.split,
            "upstream_revision": UPSTREAM_REVISION,
            "record_sha256": digest(json.dumps(record, sort_keys=True).encode()),
        },
        "original_record": record,
    }
