# Results and artifacts reference

Every `oracle-bench run` creates a timestamped attempt directory beneath the
configured `output` path. The directory is the complete record of one agent
attempt: its inputs, resolved dataset instance, runtime, agent activity, captured
submission, reference check, paired evaluations, and report.

## Directory layout

```text
runs/<run-id>/
├── config.resolved.yaml
├── instance.json
├── prompt.txt
├── runtime.json
├── status.json
├── report.md
├── results.json
├── build/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── images.json
│   └── output.log (when a pull or build runs)
├── reference/
│   ├── results.json
│   ├── buggy/<execution artifacts>
│   └── golden/<execution artifacts>
├── agent/
│   ├── command.json
│   ├── version.txt
│   ├── trace.jsonl
│   ├── session.log
│   ├── final.txt
│   ├── result.json
│   ├── stderr.log
│   ├── setup.log
│   ├── launch.log
│   ├── capture.log
│   ├── baseline.txt
│   ├── before.json
│   ├── after.json
│   └── workspace.diff
├── generated/
│   ├── manifest.json
│   └── files/<generated test paths>
├── buggy/<execution artifacts>
├── golden/<execution artifacts>
└── evaluations/<archived reevaluations>/
```

A run that stops early contains only the files produced before the failure. For
example, an image-build failure will not have generation or evaluation artifacts.
Consult `status.json` and the last stage log when expected files are absent.

## Primary results

### `report.md`

The human-readable summary. It shows agent and evaluation completion states,
submission compliance, the paired pass/fail matrix, non-binary outcomes, coverage,
important artifact links, agent duration, and provider-reported usage and cost.

`oracle-bench report runs/<run-id>` regenerates this file and
`agent/session.log` from saved data. It does not execute tests or call a model.

### `results.json`

The machine-readable aggregate for the generated tests.

| Field | Meaning |
|---|---|
| `schema_version` | Result schema version, currently `1` |
| `instance_id` | Dataset instance evaluated |
| `agent` | Copy of `agent/result.json` |
| `artifact_sha256` | Checksum over the generated-file manifest entries |
| `submission_compliant` | Whether the agent made only permitted changes |
| `forbidden_changes` | Paths changed outside the allowed submission policy |
| `diagnostic_only` | Whether violations make this a diagnostic result |
| `existing_tests` | `keep` or `hide`, matching the generation condition |
| `buggy_status`, `golden_status` | Overall execution status for each version |
| `matrix` | Counts and test IDs in each binary paired cell |
| `tests` | One paired row per test ID |
| `other_outcomes` | Tests excluded from the binary matrix |
| `has_fail_on_buggy_pass_on_golden` | Whether a test distinguishes the pair in the expected direction |
| `coverage` | Normalized coverage summaries for both versions |

Each `tests` row contains `test_id`, `buggy`, `golden`, and `cell`. `cell` is null
when either execution is incomplete or an outcome is not binary.

| Matrix key | Buggy | Golden | Meaning |
|---|---|---|---|
| `pass_on_both` | pass | pass | Test accepts both implementations |
| `fail_on_buggy_pass_on_golden` | fail | pass | Test detects behavior repaired by the golden patch |
| `pass_on_buggy_fail_on_golden` | pass | fail | Test prefers buggy behavior or rejects the repair |
| `fail_on_both` | fail | fail | Test rejects both implementations |

These cells describe behavior; they do not prove whether an oracle is correct.
Skips, expected failures, setup or teardown errors, collection failures, missing
test IDs, and incomplete runs remain in `other_outcomes`.

### `status.json`

The latest lifecycle checkpoint, containing `stage`, `state`, `updated_at`, and an
error when applicable. Stages progress through `resolve`, `build`, `reference`,
`generate`, `capture`, `evaluate`, and `finished`.

The final state is `completed` only when the agent and both evaluations completed
and the submission was compliant. `completed_with_errors` means the run retained
results but one of those conditions failed. An early exception records its stage
and a failed state.

## Inputs and reproducibility

### `config.resolved.yaml`

The schema-versioned run lock. It expands the small input configuration with the
source adapter's repository `runtime`, Oracle Bench's pinned `toolchain`, agent
defaults, dataset revision, and absolute host paths. During a run, `task.prompt`
points to this attempt's frozen `prompt.txt`. Credentials and credential values
are not stored. See the [configuration reference](configuration.md).

### `instance.json`

The resolved dataset record and provenance. It includes the base commit, golden
repair patch, private reference-test patch and IDs, source dataset metadata, a
record hash, and the original record. This is private evaluator data that may
reveal the defect and repair; it must not be exposed to the generation agent.

### `prompt.txt`

The exact prompt delivered to the agent. It combines the selected prompt file
with instructions identifying the allowed output directory, repository Python,
and generated-test command.

### `runtime.json`

The exact locally built Docker image ID used by the run. Reevaluation requires
this image to remain available. Its source images are detailed in
`build/images.json`.

## `build/`

### `build/Dockerfile`

The generated runtime recipe. It starts from resolved source and Node images,
installs the pinned agent CLI, copies Node into the repository image, installs
pytest and coverage in the repository environment, and creates the non-root agent
user.

### `build/.dockerignore`

Restricts the build context to the Dockerfile and ignore file. Run data and
credentials do not enter the Docker build context.

### `build/images.json`

Configured references and resolved IDs or digests for the repository, Node, and
final runtime images. This is the image-provenance record.

### `build/output.log`

Combined output from pulls and the runtime build. It may be short, empty, or
absent when the image is already cached and no build command runs.

## `agent/`

### `agent/session.log`

The readable agent transcript generated from `trace.jsonl`: prompt, agent
messages, exposed tool calls and results, errors, standard error, and the harness
result. This is the best file for reviewing what the agent did.

It cannot include hidden reasoning that the provider did not expose. Tool output
may already be truncated by the CLI. `oracle-bench report` can rebuild it without
a model call.

### `agent/trace.jsonl`

Raw newline-delimited events emitted by Codex or Claude Code. Event shapes depend
on the pinned CLI version. This is the authoritative low-level transcript used to
extract completion, errors, usage, cost, and `session.log`.

### `agent/command.json`

The exact agent CLI argument vector, including model, isolation flags, provider
overrides, and configured budget or turn limit. Credential values are absent.

### `agent/version.txt`

Output of `codex --version` or `claude --version` inside the container.

### `agent/final.txt`

The agent's final natural-language response. It may be empty when generation
fails or times out.

### `agent/result.json`

Normalized generation metadata.

| Field | Meaning |
|---|---|
| `status` | `completed`, `failed`, or `timeout` |
| `exit_code` | Agent process exit code |
| `duration_seconds` | Agent process wall time |
| `timed_out` | Whether the harness timeout terminated it |
| `turn_completed`, `turn_failed` | Terminal event flags parsed from the trace |
| `errors` | Structured errors extracted from the trace |
| `unparsed_trace_lines` | Lines that were not valid JSON |
| `usage` | Provider/CLI token data, or null |
| `cost_usd` | CLI-reported cost for Claude, otherwise null |
| `model_usage` | Claude's optional per-model breakdown |

Provider usage structures are semi-structured and may change between CLI
versions.

### Agent logs

| File | Contents |
|---|---|
| `stderr.log` | Agent CLI standard error; often empty on success |
| `setup.log` | Generation-container creation, repository reset/rebuild, test visibility, and initial snapshot diagnostics |
| `launch.log` | Prompt copy, agent launch, and output-copy Docker diagnostics |
| `capture.log` | Final snapshot, workspace diff, and generated-file copy diagnostics |

Agent stdout goes to `trace.jsonl`, so `launch.log` is not the transcript. Docker
copy and snapshot tools are normally silent, making `launch.log` and
`capture.log` commonly empty on success.

### `agent/baseline.txt`

The Git commit created immediately before generation. It includes the selected
existing-test visibility and empty generated-test directory and anchors the final
workspace diff.

### `agent/before.json` and `agent/after.json`

Complete filesystem metadata snapshots before and after generation. Every
repository-relative path maps to its entry kind, Unix mode, size, and SHA-256.
Their comparison determines allowed files and forbidden changes independently of
Git status. These can be large, but contain metadata rather than every file's
contents.

### `agent/workspace.diff`

The complete Git-oriented diff from `baseline.txt` through the final agent state,
including staged, unstaged, and untracked changes. Use it to inspect policy
violations and production edits.

## `generated/`

### `generated/files/`

The frozen submission. Each allowed new regular file is copied here while
preserving its repository-relative path. Evaluations copy these exact files into
fresh buggy and golden workspaces. The directory may be absent for an empty
submission.

### `generated/manifest.json`

The artifact inventory and compliance decision.

| Field | Meaning |
|---|---|
| `schema_version` | Manifest schema version, currently `1` |
| `files` | Allowed paths mapped to SHA-256 and Unix mode |
| `forbidden_changes` | Changed paths that violated capture policy |
| `compliant` | Whether `forbidden_changes` is empty |
| `empty` | Whether no allowed files were captured |
| `sha256` | Hash of the canonical `files` mapping |

Before evaluation, Oracle Bench verifies the manifest checksum and every captured
file's checksum. It rejects silent modification of the frozen artifact.

## Evaluation directories

`buggy/`, `golden/`, `reference/buggy/`, and `reference/golden/` use the same
layout. The top-level pair evaluates generated tests; the `reference/` pair checks
the private developer regression before generation. Golden directories also have
`repair.patch`; reference directories have `reference.patch`.

### `tests.json`

Normalized pytest results.

| Field | Meaning |
|---|---|
| `schema_version` | Test-result schema version, currently `1` |
| `status` | Overall execution status |
| `exit_code` | pytest exit code |
| `collected` | Number of collected tests |
| `collection_errors` | Structured collection failures |
| `tests` | Pytest node IDs mapped to outcomes and phase records |

Each test records its normalized outcome and available setup, call, and teardown
phases, including phase outcome, duration, and failure details. Outcomes preserve
passes, failures, skips, expected failures, unexpected passes, and setup or
teardown errors.

Incomplete statuses include `no_tests`, `timeout`, `runner_error`, and
`infrastructure_error`, with an `error` explanation. A failing assertion is an
ordinary per-test failure and does not make the overall execution incomplete.

### Coverage files

| File | Contents |
|---|---|
| `coverage.json` | Stable normalized status, totals, percentage, and per-file data used by Oracle Bench |
| `coverage.raw.json` | Detailed unmodified JSON emitted by the configured coverage.py version |
| `.coverage` | Binary coverage.py data file, requiring a compatible coverage version to inspect |

When coverage is unavailable, `coverage.json` contains `status: unavailable` and
a reason. Coverage failure does not discard test results.

### Other execution files

| File | Contents |
|---|---|
| `imports.json` | Configured modules mapped to imported file paths, detecting accidental use of another installed copy |
| `runner.json` | Inputs to the in-container runner: workdir, output, targets, source roots, and imports |
| `command.json` | Concrete pytest command; distinct from the agent command |
| `execution.json` | Runner exit code, duration, and timeout flag |
| `output.log` | Workspace setup, patching, pytest, coverage, and Docker diagnostics |
| `repair.patch` | Exact golden source patch, only in golden executions |
| `reference.patch` | Private test patch, only in reference executions |

Start with `output.log` when `tests.json` reports a runner or infrastructure
failure.

## `reference/results.json`

The paired private-regression result. It has the same matrix shape as the paired
portion of `results.json`. Generation begins only when
`has_fail_on_buggy_pass_on_golden` is true, verifying the base commit, repair,
private test, and environment before model spending.

## Reevaluation archives

Running:

```sh
uv run oracle-bench evaluate runs/<run-id>
```

moves the current `buggy/`, `golden/`, `results.json`, and `report.md` into
`evaluations/<UTC timestamp>/`, verifies the frozen manifest, and evaluates it in
fresh containers. Generation evidence, provenance, runtime identity, and frozen
tests remain unchanged. Earlier reevaluations therefore remain available for
comparison.

`agent/session.log` is regenerated from the original trace when the new report is
rendered. It is generation evidence rather than an evaluation result and is not
archived.

## Empty, optional, and absent files

Several files are expected to be empty or absent in normal circumstances:

- `agent/launch.log`, `agent/capture.log`, and sometimes `agent/stderr.log` are
  empty when normally silent commands succeed;
- `build/output.log` may be minimal or absent when the runtime is cached;
- `agent/final.txt` may be empty after an agent failure;
- `generated/files/` may be absent for an empty submission;
- raw and binary coverage files may be absent when coverage fails;
- `results.json` and `report.md` are absent if the pipeline stops before final
  evaluation.

Interpret absence together with `status.json`, the relevant `execution.json`, and
the closest stage log.
