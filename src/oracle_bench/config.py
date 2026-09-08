from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path, PurePosixPath

import yaml


def repo_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or str(path) == "."
        or ".git" in path.parts
        or value.startswith("-")
    ):
        raise ValueError(f"Expected a relative repository path, got {value!r}")
    return str(path)


@dataclass
class DatasetConfig:
    instance_id: str
    revision: str
    name: str = "princeton-nlp/SWE-bench_Lite"
    split: str = "test"
    record: str | None = None


@dataclass
class EnvironmentConfig:
    image: str
    python: str = "/opt/miniconda3/envs/testbed/bin/python"
    workdir: str = "/testbed"
    source_roots: list[str] = field(default_factory=lambda: ["requests"])
    import_modules: list[str] = field(default_factory=lambda: ["requests"])
    existing_test_paths: list[str] = field(default_factory=lambda: ["test_requests.py", "tests"])
    rebuild: str = "python -m pip install --no-deps -e ."
    pytest_version: str = "7.4.4"
    coverage_version: str = "7.6.1"
    platform: str = "linux/amd64"
    reference_targets: list[str] = field(default_factory=list)


@dataclass
class HarnessConfig:
    model: str
    kind: str = "codex"
    provider: str = "openai"
    multi_agent: bool = True
    version: str = "0.153.4"
    node_image: str = "node:22.14.0-bookworm-slim"
    api_key_env: str = "OPENAI_API_KEY"
    wall_seconds: int = 900
    max_budget_usd: float = 0.25
    max_turns: int = 10
    auth_mode: str = "oauth"


@dataclass
class TaskConfig:
    prompt: str
    existing_tests: str = "keep"
    generated_dir: str = "oracle_tests"


@dataclass
class LimitsConfig:
    evaluation_seconds: int = 600
    setup_seconds: int = 1800
    memory: str = "4g"
    cpus: float = 2


@dataclass
class RunConfig:
    dataset: DatasetConfig
    environment: EnvironmentConfig
    harness: HarnessConfig
    task: TaskConfig
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    output: str = "runs"

    def to_dict(self) -> dict:
        return asdict(self)


def _construct(cls, values):
    if not isinstance(values, dict):
        raise ValueError(f"{cls.__name__} must be a mapping")
    unknown = values.keys() - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f"Unknown {cls.__name__} settings: {sorted(unknown)}")
    return cls(**values)


def load_config(path: Path) -> RunConfig:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("Configuration must be a YAML mapping")
    raw = dict(raw)
    for name, cls in [
        ("dataset", DatasetConfig),
        ("environment", EnvironmentConfig),
        ("harness", HarnessConfig),
        ("task", TaskConfig),
        ("limits", LimitsConfig),
    ]:
        raw[name] = _construct(cls, raw.get(name, {}))
    config = _construct(RunConfig, raw)
    if (config.harness.kind, config.harness.provider) not in {
        ("codex", "openai"),
        ("codex", "openrouter"),
        ("claude", "anthropic"),
    }:
        raise ValueError("Use codex with openai/openrouter, or claude with anthropic")
    if (
        isinstance(config.harness.max_turns, bool)
        or not isinstance(config.harness.max_turns, int)
        or config.harness.max_turns <= 0
    ):
        raise ValueError("harness.max_turns must be a positive integer")
    if not isinstance(config.harness.multi_agent, bool):
        raise ValueError("harness.multi_agent must be a boolean")
    if config.harness.auth_mode not in {"oauth", "api_key"}:
        raise ValueError("harness.auth_mode must be oauth or api_key")
    if config.task.existing_tests not in {"keep", "hide"}:
        raise ValueError("task.existing_tests must be keep or hide")
    config.task.generated_dir = repo_path(config.task.generated_dir)
    for name in ["source_roots", "existing_test_paths"]:
        values = getattr(config.environment, name)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"environment.{name} must be a list of paths")
        setattr(config.environment, name, [repo_path(v) for v in values])
    if not config.environment.source_roots:
        raise ValueError("environment.source_roots cannot be empty")
    generated = PurePosixPath(config.task.generated_dir)
    for source in config.environment.source_roots:
        root = PurePosixPath(source)
        if generated == root or generated in root.parents or root in generated.parents:
            raise ValueError("Generated tests must be outside production source roots")
    for value in [
        config.harness.wall_seconds,
        config.harness.max_budget_usd,
        config.limits.evaluation_seconds,
        config.limits.setup_seconds,
        config.limits.cpus,
    ]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError("Timeouts and CPU limits must be positive numbers")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config.harness.api_key_env):
        raise ValueError("api_key_env must name an environment variable, not contain a key")
    if not re.fullmatch(r"[0-9a-f]{40}", config.dataset.revision):
        raise ValueError("dataset.revision must be an immutable 40-character commit SHA")
    for version in [
        config.harness.version,
        config.environment.pytest_version,
        config.environment.coverage_version,
    ]:
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)?", version):
            raise ValueError(f"Expected a pinned package version, got {version!r}")
    for value in [config.environment.image, config.harness.node_image]:
        if not re.fullmatch(r"[A-Za-z0-9_./:@-]+", value):
            raise ValueError(f"Invalid container image reference {value!r}")
    for value in [config.environment.python, config.environment.workdir]:
        if not value.startswith("/") or "\n" in value:
            raise ValueError("Container Python and workdir must be absolute paths")
    for value in [config.harness.model, config.dataset.instance_id]:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Model and instance ID cannot be empty")
    base = path.resolve().parent
    config.task.prompt = str((base / config.task.prompt).resolve())
    config.output = str((base / config.output).resolve())
    if config.dataset.record:
        config.dataset.record = str((base / config.dataset.record).resolve())
    return config
