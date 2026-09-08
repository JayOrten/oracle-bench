# Configuration reference

Oracle Bench runs one benchmark instance from a YAML configuration passed to
`oracle-bench run`:

```sh
uv run oracle-bench run configs/smoke-claude.yaml
```

The configuration has six top-level keys: `dataset`, `environment`, `harness`,
`task`, `limits`, and `output`. Unknown keys are rejected so that misspellings do
not silently change a run. The fully resolved configuration is saved as
`config.resolved.yaml` in the run directory. Credentials are never stored in it.

## Complete example

```yaml
dataset:
  name: princeton-nlp/SWE-bench_Lite
  revision: 6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2
  split: test
  instance_id: psf__requests-2148

environment:
  image: swebench/sweb.eval.x86_64.psf_1776_requests-2148:latest
  platform: linux/amd64
  workdir: /testbed
  python: /opt/miniconda3/envs/testbed/bin/python
  source_roots: [requests]
  import_modules: [requests]
  existing_test_paths: [test_requests.py, tests]
  rebuild: python -m pip install --no-deps --no-build-isolation -e .
  pytest_version: 7.4.4
  coverage_version: 7.6.1
  reference_targets:
    - test_requests.py::RequestsTestCase::test_iter_content_handles_socket_error

harness:
  kind: claude
  provider: anthropic
  model: haiku
  version: 2.1.263
  node_image: node:22.14.0-bookworm-slim
  auth_mode: api_key
  api_key_env: ANTHROPIC_API_KEY
  multi_agent: false
  max_budget_usd: 0.25
  max_turns: 10
  wall_seconds: 300

task:
  prompt: ../prompts/smoke-tests.md
  existing_tests: keep
  generated_dir: oracle_tests

limits:
  evaluation_seconds: 600
  setup_seconds: 1800
  memory: 4g
  cpus: 2

output: ../runs
```

## Path and value rules

`task.prompt`, `dataset.record`, and `output` are host paths. Relative values are
resolved from the directory containing the YAML file, not necessarily the shell's
current directory.

Repository paths such as `source_roots`, `existing_test_paths`, and
`generated_dir` are relative to `environment.workdir` inside the container. They
must not be absolute, contain `..`, refer to `.git`, equal `.`, or begin with `-`.
The generated-test directory must also be separate from every production source
root: neither path may contain the other.

Container executable paths (`environment.python` and `environment.workdir`) must
be absolute. Package versions must be pinned version strings such as `2.1.263` or
`7.6.1`. The dataset revision must be a full lowercase 40-character commit SHA.
Timeouts, CPU allocation, Claude's budget, and its turn limit must be positive.

## `dataset`

This section selects and resolves one SWE-bench-compatible record.

### `dataset.instance_id`

- **Type:** string
- **Required:** yes

The exact `instance_id` to run, such as `psf__requests-2148`. Oracle Bench expects
exactly one matching record and rejects an empty value.

### `dataset.revision`

- **Type:** string
- **Required:** yes

An immutable 40-character Git commit SHA for the dataset repository. Pinning the
revision prevents the same benchmark configuration from resolving to different
data later.

### `dataset.name`

- **Type:** string
- **Default:** `princeton-nlp/SWE-bench_Lite`

The Hugging Face dataset identifier passed to `datasets.load_dataset`. This field
is retained as source metadata even when `dataset.record` supplies a local record.

### `dataset.split`

- **Type:** string
- **Default:** `test`

The Hugging Face dataset split to load. Oracle Bench searches this split for
`dataset.instance_id`.

### `dataset.record`

- **Type:** path or null
- **Default:** null

Optional path to a local JSON record. When set, Oracle Bench reads this file and
does not contact Hugging Face. This is useful for offline runs and fixtures. The
record must contain nonempty string values for `instance_id`, `repo`,
`base_commit`, `patch`, and `test_patch`. `base_commit` must be a full commit SHA.
`FAIL_TO_PASS` must be a list of test IDs or a JSON-encoded list. The record's
instance ID must match `dataset.instance_id`.

The resolved record is copied into `instance.json`, including the golden repair
patch and private reference-test patch. Do not expose that file to the generation
agent.

## `environment`

This section describes the target repository's container, Python runtime, setup,
test locations, and coverage scope.

### `environment.image`

- **Type:** Docker image reference
- **Required:** yes

The prepared repository image. It must contain a Git checkout at `workdir`, with
the configured base commit available. Oracle Bench currently relies on existing
SWE-bench images rather than building arbitrary repository environments.

The image is pulled if missing. Oracle Bench records its immutable image ID and
uses it as the base for a small runtime layer containing the agent CLI, pytest,
and coverage.

### `environment.platform`

- **Type:** string
- **Default:** `linux/amd64`

The Docker platform used for image pulls, builds, and containers. It must agree
with the selected repository image and the Docker host's emulation support.

### `environment.workdir`

- **Type:** absolute container path
- **Default:** `/testbed`

The repository checkout inside the container. Docker commands execute here, and
all repository-relative paths are interpreted beneath it.

### `environment.python`

- **Type:** absolute container path
- **Default:** `/opt/miniconda3/envs/testbed/bin/python`

The target repository's Python interpreter. Oracle Bench installs the pinned
pytest and coverage versions with this interpreter, tells the agent to use it,
and uses it for reference and generated-test evaluation.

### `environment.source_roots`

- **Type:** nonempty list of repository-relative paths
- **Default:** `[requests]`

Production files or directories measured by coverage. These are passed to
coverage's `--source` behavior by the benchmark runner. Generated tests must live
outside these roots.

### `environment.import_modules`

- **Type:** list of Python module names
- **Default:** `[requests]`

Modules imported in a separate probe before evaluation. The recorded import paths
help confirm that tests loaded the code from the intended repository environment.
These names are Python imports, not filesystem paths.

### `environment.existing_test_paths`

- **Type:** list of repository-relative paths
- **Default:** `[test_requests.py, tests]`

Existing test files or directories that are removed from the agent workspace when
`task.existing_tests` is `hide`. Missing paths are harmless. They remain present
during the private reference-pair check, even in `hide` mode.

### `environment.rebuild`

- **Type:** shell command string
- **Default:** `python -m pip install --no-deps -e .`

Command run from `workdir` after resetting the checkout to the task's base commit.
It should install or rebuild the repository in its prepared environment without
requiring interactive input. It is run again after applying the golden patch.
Failures stop that workspace or evaluation.

This command runs through Bash inside a disposable container. Treat configuration
files as trusted code.

### `environment.pytest_version`

- **Type:** pinned version string
- **Default:** `7.4.4`

The pytest version installed into `environment.python` when the runtime image is
built. Pin a version compatible with the target repository and the Oracle Bench
pytest plugin.

### `environment.coverage_version`

- **Type:** pinned version string
- **Default:** `7.6.1`

The coverage.py version installed into the repository environment. Coverage is
collected separately for buggy and golden code. Coverage failure is reported but
does not erase collected test outcomes.

### `environment.reference_targets`

- **Type:** list of pytest node IDs
- **Default:** `[]`

Tests from the private reference patch used to verify that the configured pair
really reproduces a fail-on-buggy/pass-on-golden change before model spending.
When empty, Oracle Bench uses the dataset record's `FAIL_TO_PASS` IDs. At least one
target must exist, and the paired reference results must contain a buggy failure
and golden pass.

## `harness`

This section selects the agent CLI and model provider. Supported combinations are:

| `kind` | `provider` | Agent CLI | Credential normally used |
|---|---|---|---|
| `codex` | `openai` | Codex | `OPENAI_API_KEY` |
| `codex` | `openrouter` | Codex | `OPENROUTER_API_KEY` |
| `claude` | `anthropic` | Claude Code | `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` |

Other combinations are rejected.

### `harness.kind`

- **Type:** `codex` or `claude`
- **Default:** `codex`

The agent harness installed in the runtime image and launched during generation.
Changing it changes the runtime-image recipe and therefore produces a distinct
cached image.

### `harness.provider`

- **Type:** `openai`, `openrouter`, or `anthropic`
- **Default:** `openai`

The model API provider. It must form one of the supported pairs above. OpenRouter
is configured as a custom provider for Codex using its Responses-compatible API.

### `harness.model`

- **Type:** string
- **Required:** yes

The model name passed directly to the selected CLI, for example `gpt-5.4`,
`cohere/north-mini-code:free`, or `haiku`. Aliases may change meaning upstream;
use a full provider model ID when exact model reproducibility matters.

### `harness.version`

- **Type:** pinned version string
- **Default:** `0.153.4`

The npm version of `@openai/codex` or `@anthropic-ai/claude-code`, depending on
`harness.kind`. Do not rely on the default when using Claude: the default is a
Codex version. The resolved CLI version is also captured in the agent artifacts.

### `harness.node_image`

- **Type:** Docker image reference
- **Default:** `node:22.14.0-bookworm-slim`

The image that supplies Node.js and installs the pinned agent CLI. Its immutable
digest is recorded in `build/images.json`.

### `harness.api_key_env`

- **Type:** environment-variable name
- **Default:** `OPENAI_API_KEY`

The host environment variable containing the selected credential. This field is
only its name; never put a secret value in YAML. `oracle-bench run` loads the
gitignored `.env` file from the shell's current directory without overriding an
already-set environment variable.

Only the selected value is passed to the agent process. It is passed through the
process environment rather than Docker command arguments and is redacted from
captured agent files. `evaluate` and `report` do not load credentials.

### `harness.auth_mode`

- **Type:** `api_key` or `oauth`
- **Default:** `oauth`
- **Applies to:** Claude Code

Controls how the Claude credential is named inside the container. `api_key`
passes the selected value as `ANTHROPIC_API_KEY`; `oauth` passes it as
`CLAUDE_CODE_OAUTH_TOKEN`. For OAuth, generate a long-lived token with
`claude setup-token`. The host's normal Claude login files are not copied into the
container.

Codex ignores this field. Set it accurately in Claude configurations so the
credential type matches the variable Claude Code reads.

### `harness.multi_agent`

- **Type:** boolean
- **Default:** `true`

Whether the agent may use built-in subagent capabilities. For Codex, `false`
disables its multi-agent feature. For Claude Code, `false` supplies an explicit
tool list that omits agent/task tools. Disable it for cheap smoke runs or enable it
when subagents are part of the harness being evaluated.

### `harness.wall_seconds`

- **Type:** positive number
- **Default:** `900`

Hard wall-clock limit for the complete agent process. On timeout, the process gets
`TERM`, followed by a forced kill after a grace period. Partial files and traces
are still captured when possible.

### `harness.max_budget_usd`

- **Type:** positive number
- **Default:** `0.25`
- **Applies to:** Claude Code

Passed to Claude Code as `--max-budget-usd`. It limits model spending reported by
that CLI for one generation attempt, including subagents. It is not an account
billing cap. Codex currently ignores this field and has no equivalent cost limit.

### `harness.max_turns`

- **Type:** positive integer
- **Default:** `10`
- **Applies to:** Claude Code

Passed to Claude Code as `--max-turns`. If the limit is reached before completion,
the agent run is recorded as failed and any generated files are still captured for
diagnosis. Codex currently ignores this field.

## `task`

This section defines what the agent sees and where its submission may be written.

### `task.prompt`

- **Type:** host file path
- **Required:** yes

Path to the public prompt. Oracle Bench appends instructions naming
`generated_dir`, forbidding edits outside it, identifying the repository Python,
and showing the test command. The resulting exact prompt is saved as `prompt.txt`
in the run directory.

The agent does not receive the dataset issue description, golden repair patch, or
private reference-test patch through this mechanism.

### `task.existing_tests`

- **Type:** `keep` or `hide`
- **Default:** `keep`

Controls whether `environment.existing_test_paths` remain visible in the agent's
buggy workspace. This allows experiments both with and without existing tests.
The same visibility choice is reproduced in buggy and golden evaluation
containers. Existing tests are not evaluation targets; only captured generated
tests run during scoring.

### `task.generated_dir`

- **Type:** repository-relative path
- **Default:** `oracle_tests`

The only directory in which the agent may add tests and fixtures. It must not
exist after the workspace reset; Oracle Bench creates it immediately before the
agent starts. New regular files beneath it are captured. Symlinks, deletions,
production edits, and changes elsewhere are recorded as forbidden changes and
make the submission diagnostic-only.

## `limits`

This optional section controls container resources and non-agent timeouts. If the
whole section is omitted, all defaults below apply.

### `limits.evaluation_seconds`

- **Type:** positive number
- **Default:** `600`

Maximum duration of each pytest evaluation, including its coverage collection.
Buggy and golden evaluations receive separate limits. A timeout is reported as a
non-binary outcome rather than a test failure.

### `limits.setup_seconds`

- **Type:** positive number
- **Default:** `1800`

Timeout used for image pulls/builds and repository preparation operations such as
resetting, rebuilding, and applying patches. It applies to each setup command,
not as one shared budget for the entire run.

### `limits.memory`

- **Type:** Docker memory string
- **Default:** `4g`

Passed to `docker run --memory`. Use Docker-supported forms such as `512m`, `4g`,
or a byte count. The current loader does not independently validate this string;
Docker reports invalid values when the container starts.

### `limits.cpus`

- **Type:** positive number
- **Default:** `2`

Passed to `docker run --cpus` for generation, reference checks, and evaluation.
Fractional allocations such as `1.5` are allowed.

## `output`

- **Type:** host directory path
- **Default:** `runs`

Parent directory for timestamped run directories. Relative values resolve from
the YAML file's directory. Oracle Bench creates one immutable attempt directory
per `run`; it does not overwrite earlier attempts.

## Sample configurations

- [`configs/smoke-claude.yaml`](../configs/smoke-claude.yaml) uses Claude Code,
  Anthropic, Haiku, and the small smoke prompt.
- [`configs/smoke.yaml`](../configs/smoke.yaml) uses Codex, OpenAI, and the general
  test-generation prompt.
- [`configs/smoke-openrouter.yaml`](../configs/smoke-openrouter.yaml) uses Codex
  with an explicitly free OpenRouter model and a request-conserving smoke setup.

These samples all run the same pinned SWE-bench Lite Requests instance. Copy one
before adapting it; a new repository may require coordinated changes to the image,
Python interpreter, rebuild command, test paths, import probes, coverage roots,
and reference targets.
