"""Managed SDK containers with the benchmark's lifecycle and output policy."""

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import docker
from docker.errors import DockerException, NotFound
from requests.exceptions import RequestException

from oracle_bench.container import files
from oracle_bench.container.lifecycle import execution_watchdog
from oracle_bench.container.output import RedactedOutput
from oracle_bench.io import read_json

HELPER_DIR = "/opt/oracle-bench/container-helpers"
ORACLE_USER = "10001:10001"


class Profile(Enum):
    GENERATION = "generation"
    EVALUATION = "evaluation"
    REFERENCE = "reference"


@dataclass
class CommandResult:
    exit_code: int
    duration_seconds: float
    timed_out: bool = False


class Sandbox:
    """A running container. Use open_sandbox to own its lifetime."""

    def __init__(self, container, runtime, log: Path):
        self.container = container
        self.runtime = runtime
        self.log = log
        self.helpers = HELPER_DIR

    def upload(self, source: Path, destination: str, *, contents=False):
        files.upload(self.container, source, destination, contents=contents)

    def download(
        self, source: str, destination: Path, *, contents=False, required=True, secrets=()
    ):
        try:
            files.download(self.container, source, destination, contents=contents, secrets=secrets)
        except NotFound:
            if required:
                raise
            # Only a missing path is optional. API and archive failures propagate.
            self.log.parent.mkdir(parents=True, exist_ok=True)
            with self.log.open("a") as stream:
                stream.write(f"Optional artifact missing: {source}\n")
            return False
        return True

    def run(
        self,
        argv,
        *,
        timeout=60,
        user="root",
        environment=None,
        stdin=None,
        stdout=None,
        stderr=None,
        log=None,
        check=True,
        secrets=(),
    ) -> CommandResult:
        """Execute argv, stream redacted output, and retain explicit process status.

        Credentials travel only in the exec environment. Do not log SDK request
        objects or raw SDK exceptions, which may contain that environment.
        """
        log = log or self.log
        token = uuid4().hex
        input_path = "/dev/null"
        status_path = f"/tmp/oracle-exec-{token}.json"
        if stdin is not None:
            input_path = f"/tmp/oracle-input-{token}"
            self.upload(stdin, input_path)
        command = [
            self.runtime.python,
            self.helpers + "/execute.py",
            str(timeout),
            input_path,
            status_path,
            *argv,
        ]
        try:
            with execution_watchdog(self.container, timeout) as watchdog_fired:
                supervisor_code = self._stream_command(
                    command,
                    user=user,
                    environment=environment,
                    stdout=stdout,
                    stderr=stderr,
                    log=log,
                    secrets=secrets,
                )
                if watchdog_fired.is_set() or supervisor_code != 0:
                    raise RuntimeError(f"Container supervisor did not finish; see {log}")
                result = self._read_command_result(status_path)
        except (DockerException, RequestException):
            raise RuntimeError(f"Container execution transport failed; see {log}") from None
        if check and result.exit_code:
            raise RuntimeError(f"Container command failed (exit {result.exit_code}); see {log}")
        return result

    def _stream_command(self, command, *, user, environment, stdout, stderr, log, secrets):
        """Keep SDK stream handling separate from the command's lifecycle."""
        api = self.container.client.api
        execution = api.exec_create(
            self.container.id,
            command,
            user=user,
            workdir=self.runtime.workdir,
            environment=environment or {},
        )
        with (
            RedactedOutput(stdout or log, secrets, append=stdout is None) as out,
            RedactedOutput(stderr or log, secrets, append=stderr is None) as err,
        ):
            for output, error in api.exec_start(execution["Id"], stream=True, demux=True):
                if output:
                    out.write(output)
                if error:
                    err.write(error)
        return api.exec_inspect(execution["Id"])["ExitCode"]

    def _read_command_result(self, status_path: str) -> CommandResult:
        # Supervisor completion and command completion are different outcomes.
        # Read the helper's status to distinguish a deadline from an ordinary exit.
        with TemporaryDirectory(prefix="oracle-exec-") as directory:
            status = Path(directory) / "status.json"
            self.download(status_path, status)
            return CommandResult(**read_json(status))

    def stop_background_processes(self):
        """Restart before capture to terminate even detached agent descendants."""
        self.container.stop(timeout=1)
        self.container.start()


@contextmanager
def open_sandbox(client, image: str, config, profile: Profile, log: Path):
    """Create explicitly before starting, so failed starts are cleaned up too."""
    runtime = config.require_runtime()
    limits = config.limits
    container = client.containers.create(
        image,
        command=["-c", "sleep infinity"],
        entrypoint="/bin/bash",
        name="oracle-bench-" + uuid4().hex[:16],
        detach=True,
        init=True,
        platform=runtime.platform,
        user="root",
        mem_limit=limits.memory,
        nano_cpus=int(limits.cpus * 1_000_000_000),
        security_opt=["no-new-privileges"],
        network_mode="bridge" if profile is Profile.GENERATION else "none",
        labels={"oracle-bench.profile": profile.value},
        use_config_proxy=False,
    )
    failure = None
    try:
        container.start()
        sandbox = Sandbox(container, runtime, log)
        yield sandbox
    except BaseException as exc:
        failure = exc
        raise
    finally:
        try:
            container.remove(force=True)
        except DockerException as exc:
            if failure is None:
                raise RuntimeError("Could not remove benchmark container") from exc
            failure.add_note(
                "Container cleanup also failed; inspect Docker for leftover containers."
            )


@contextmanager
def docker_client():
    """Own the SDK connection at the host workflow boundary."""
    client = None
    try:
        client = docker.from_env(timeout=60)
        if client.info()["OSType"] != "linux":
            raise RuntimeError("A Linux Docker daemon is required")
        yield client
    except DockerException:
        raise RuntimeError("Docker operation failed; check the daemon and stage log") from None
    finally:
        if client is not None:
            client.close()
