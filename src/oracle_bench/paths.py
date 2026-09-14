"""Stable, lifecycle-oriented paths for run artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunPaths:
    """Resolve lifecycle-oriented paths for one benchmark run."""

    root: Path

    @classmethod
    def create(cls, root: Path) -> "RunPaths":
        paths = cls(root)
        for directory in (
            paths.inputs,
            paths.build,
            paths.reference,
            paths.generation,
            paths.submission,
            paths.evaluation,
            paths.ground_truth,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return paths

    @classmethod
    def open(cls, root: Path) -> "RunPaths":
        return cls(root)

    @property
    def inputs(self) -> Path:
        return self.root / "inputs"

    @property
    def build(self) -> Path:
        return self.root / "image-build"

    @property
    def reference(self) -> Path:
        return self.root / "reference-check"

    @property
    def generation(self) -> Path:
        return self.root / "generation"

    @property
    def submission(self) -> Path:
        return self.root / "submission"

    @property
    def evaluation(self) -> Path:
        return self.root / "evaluation"

    @property
    def config(self) -> Path:
        return self.inputs / "config.resolved.yaml"

    @property
    def instance(self) -> Path:
        return self.inputs / "instance.json"

    @property
    def prompt(self) -> Path:
        return self.inputs / "prompt.txt"

    @property
    def runtime(self) -> Path:
        return self.build / "runtime.json"

    @property
    def results(self) -> Path:
        return self.evaluation / "results.json"

    @property
    def report(self) -> Path:
        return self.root / "report.md"

    @property
    def evaluation_history(self) -> Path:
        return self.root / "evaluation-history"

    @property
    def ground_truth(self) -> Path:
        return self.root / "ground-truth"
