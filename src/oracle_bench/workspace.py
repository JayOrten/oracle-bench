"""Repository preparation, kept separate from Docker transport and image builds."""

from pathlib import Path

from oracle_bench.container import Sandbox
from oracle_bench.io import write_json


class RepositoryWorkspace:
    def __init__(self, sandbox: Sandbox, config):
        self.sandbox = sandbox
        self.config = config
        self.runtime = config.require_runtime()
        self.setup_timeout = config.limits.setup_seconds

    def prepare(self, base_commit: str, directory: Path, *, reference=False):
        """Build before hiding tests: some projects use test assets during install."""
        self.sandbox.run(["git", "reset", "--hard", base_commit], timeout=self.setup_timeout)
        self.sandbox.run(["git", "clean", "-fdx"], timeout=self.setup_timeout)
        self.rebuild()
        settings = directory / "workspace.json"
        write_json(
            settings,
            {
                "workdir": self.runtime.workdir,
                "generated_dir": self.config.task.generated_dir,
                "hide": self.config.task.existing_tests == "hide" and not reference,
                "existing_test_globs": self.runtime.existing_test_globs,
            },
        )
        self.sandbox.upload(settings, "/tmp/oracle-workspace.json")
        self.sandbox.run(
            [
                self.runtime.python,
                self.sandbox.helpers + "/prepare.py",
                "/tmp/oracle-workspace.json",
            ],
            timeout=self.config.limits.setup_seconds,
        )

    def rebuild(self):
        # A source adapter's installation recipe is intentionally a shell script.
        self.sandbox.run(
            ["/bin/bash", "-c", "set -euo pipefail\n" + self.runtime.rebuild],
            timeout=self.config.limits.setup_seconds,
        )

    def apply_patch(self, patch: str, path: Path):
        path.write_text(patch)
        self.sandbox.upload(path, "/tmp/oracle.patch")
        self.sandbox.run(
            ["git", "apply", "--check", "/tmp/oracle.patch"], timeout=self.setup_timeout
        )
        self.sandbox.run(["git", "apply", "/tmp/oracle.patch"], timeout=self.setup_timeout)
        self.sandbox.run(["rm", "/tmp/oracle.patch"])

    def baseline(self, path: Path) -> str:
        self.sandbox.run(["git", "rev-parse", "HEAD"], stdout=path)
        return path.read_text().strip()
