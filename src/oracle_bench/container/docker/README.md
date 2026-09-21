# Internal image recipes

These Dockerfiles are implementation details used by
[`prepare_image`](../container/images.py). Users do not build them directly.

Oracle Bench expects the configured project image to already contain the
repository checkout, its dependencies, and the configured Python interpreter.
The image preparation workflow then:

1. builds one locked toolchain image containing the pinned Codex, Claude Code,
   and OpenCode CLIs;
2. extends the project image with those harnesses, pytest, coverage, and Oracle
   Bench's container helpers.

The resulting image is used to create disposable generation, reference,
evaluation, and judge containers, and the interactive human-judge workspace. Image inputs and resolved IDs are recorded with each run,
and content-derived tags allow identical builds to reuse the local Docker cache.

## Trust boundary

Build contexts contain only these checked-in recipes and public container
helpers. Dataset records, repair patches, private reference tests, generated
tests, credentials, and the host run directory must never enter an image build.

Credentials and task-specific patches are supplied only to the appropriate
disposable containers. Generation, evaluation, reference, and judge containers
use Docker's outbound bridge network so legitimate network-dependent tests and
the judge's model call can run. Human-judge workspaces receive no model
credential and no network.

## Project image requirements

The project image must provide:

- Linux with glibc compatible with the configured Node image;
- bash, Git, `useradd`, and `chown`;
- Python 3.9 or newer with pip;
- an available UID and GID `10001` for the non-root `oracle` user.

Oracle Bench does not currently construct arbitrary project environments. The
configured project image is responsible for satisfying the repository's native
and Python dependencies.

Container helpers are installed at
`/opt/oracle-bench/container-helpers/`. The judge uploads its own helper instead,
so it can run against the exact image that produced the evidence it reads. Harness CLI versions come from the
checked-in package lock and are copied into the resolved run toolchain; test-tool
versions also come from that resolved configuration. Models and credentials are
execution inputs, not image build arguments.
