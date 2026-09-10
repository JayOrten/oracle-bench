# Internal image recipes

These Dockerfiles are implementation details used by
[`prepare_image`](../container/images.py). Users do not build them directly.

Oracle Bench expects the configured project image to already contain the
repository checkout, its dependencies, and the configured Python interpreter.
The image preparation workflow then:

1. builds a harness image containing the configured version of Codex or Claude
   Code;
2. extends the project image with the harness, pytest, coverage, and Oracle
   Bench's container helpers.

The resulting image is used to create disposable generation, reference, and
evaluation containers. Image inputs and resolved IDs are recorded with each run,
and content-derived tags allow identical builds to reuse the local Docker cache.

## Trust boundary

Build contexts contain only these checked-in recipes and public container
helpers. Dataset records, repair patches, private reference tests, generated
tests, credentials, and the host run directory must never enter an image build.

Credentials and task-specific patches are supplied only to the appropriate
disposable containers. Evaluation and reference containers run without network
access.

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
`/opt/oracle-bench/container-helpers/`. The agent CLI version and test-tool
versions come from the resolved run configuration; models and credentials are
execution inputs, not image build arguments.
