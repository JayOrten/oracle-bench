# Oracle Bench

Generate unit tests with an agent, then run the same tests against buggy and golden versions of a real repository. Stage 1 supports a single SWE-bench task, Codex CLI or Claude Code inside Docker, pytest outcomes, and generated-test line coverage.

Claude Code is also available as a separate harness:

```sh
# Set ANTHROPIC_API_KEY in .env, then:
uv run oracle-bench run configs/smoke-claude.yaml
```

The Claude smoke configuration uses Haiku, a $0.25 CLI budget setting, at most 10 agentic turns, and the small smoke prompt. The budget is enforced by Claude Code, not an account billing cap. Reported model cost and usage are saved in `agent/result.json`. To use a Claude Code subscription token instead of an API key, generate it with `claude setup-token`, place it in `.env` as `CLAUDE_CODE_OAUTH_TOKEN`, and set `harness.auth_mode: oauth` and `harness.api_key_env: CLAUDE_CODE_OAUTH_TOKEN`. The selected credential alone is passed into the container; the host's Claude login and settings are not copied.

## Run the smoke configuration

Requirements: Python 3.11+, Docker with a running Linux daemon, internet access for image/package downloads, and an OpenAI or OpenRouter API key with access to the configured model. The host does not need Node or Codex; the image installs the pinned agent runtime separately from the repository's Python environment.

```sh
uv sync --extra dataset --extra dev

# Set OPENAI_API_KEY in .env or your shell, then:
uv run oracle-bench run configs/smoke.yaml
```

The first run downloads a SWE-bench instance image and builds a reusable runtime layer; allow several GB of disk space and time for the initial download. The sample permits one generation attempt of up to five minutes. This uses your API account and incurs model charges; Stage 1 enforces time limits, not a dollar budget.

For a free initial pipeline check, use the same Codex harness through OpenRouter:

```sh
# Set OPENROUTER_API_KEY in .env or your shell, then:
uv run oracle-bench run configs/smoke-openrouter.yaml
```

Copy `.env.example` to `.env` and fill in the key for your chosen provider. The `run` command loads `.env` from your current working directory; run the commands above from the repository root. Existing environment variables take precedence, and values are loaded literally without variable expansion. `.env` is ignored by Git; `.env.example` contains only blank placeholders. `evaluate` and `report` do not load the file or require keys.

This separate configuration selects `cohere/north-mini-code:free` and keeps the five-minute generation limit. Its smaller smoke prompt requests 2–4 tests, and subagents are disabled to conserve requests. It never switches to a paid model. Free endpoint availability and rate limits can interrupt a run; automatic request/stream retries are disabled for this provider to conserve the allowance. This is for checking the pipeline, not full evaluation. The original `smoke.yaml` continues to use OpenAI with the general test-generation prompt. Provider selection is saved with each run. Codex may warn about fallback model metadata when using this environment-key authentication; live compatibility must be checked with the configured model.

The sample uses `psf__requests-2148` from a pinned SWE-bench Lite revision. It first checks a private developer regression test against both versions. If that check fails, generation does not start. The agent receives the buggy repository and an ordinary test-generation prompt, without the issue, repair, or reference test patch.

For Docker permissions, check `docker info` without sudo. If you just joined the `docker` group, `newgrp docker` enables access in that shell; logging out and back in updates your full login session.

## Keep or hide existing tests

Edit [configs/smoke.yaml](configs/smoke.yaml):

```yaml
task:
  prompt: ../prompts/unit-tests.md
  existing_tests: keep  # or hide
  generated_dir: oracle_tests
```

`keep` is the default. `hide` removes only the explicit `environment.existing_test_paths` from the working tree. Both evaluation versions use the same setting. Ordinary documentation remains available. The private reference-pair check retains the existing suite so its developer test can run.

In either condition, the evaluated submission consists only of new tests and fixtures under `oracle_tests/`. Existing tests are not execution targets. Source edits, edits to existing tests, deletions, and symlinks are recorded as forbidden changes; any paired results from such a submission are labeled diagnostic. The complete workspace diff and file snapshots are retained for inspection.

## Inspect and reevaluate

Each attempt prints its directory under `runs/`. Start with `report.md`, then inspect `results.json` and the test files in `generated/files/`.

`agent/session.log` is the readable agent transcript: prompt, messages, tool inputs and outputs, errors, and the harness result. It is generated after the run from `agent/trace.jsonl`; running `oracle-bench report RUN_DIR` also creates it for older runs without calling a model. It contains what the CLI exposes, not hidden reasoning or output the CLI truncated. Raw events remain in `trace.jsonl`. `agent/launch.log` and `agent/capture.log` contain Docker command diagnostics and can be empty on success.

```sh
uv run oracle-bench evaluate runs/<run-id>
uv run oracle-bench report runs/<run-id>
```

`evaluate` verifies the saved artifact hashes and reruns it in two fresh containers. It does not read API credentials or call a model. Previous evaluation results are archived under `evaluations/`. Keep the saved runtime image locally for reevaluation; its exact ID is in `runtime.json`.

`report` only reads saved results and regenerates Markdown. A completed pipeline means results were recorded, not that the agent found a bug; inspect agent status, both execution statuses, and submission compliance.

| Buggy | Golden | Matrix label |
|---|---|---|
| Pass | Pass | Pass on both |
| Fail | Pass | Fail on buggy, pass on golden |
| Pass | Fail | Pass on buggy, fail on golden |
| Fail | Fail | Fail on both |

Skips, expected failures, setup/collection errors, unmatched IDs, and incomplete runs are outside the matrix. Empty submissions do not count as passing. Pass on both means a test does not distinguish these versions, not necessarily that its oracle is wrong.

Line coverage is measured from the generated test targets over configured production source roots, separately for each version. Reports retain covered/executable line counts and per-file data. Coverage failure does not discard test results. Test bodies that raise unexpected exceptions count as failures; fixture and collection errors remain distinct.

```text
runs/<run-id>/
  config.resolved.yaml     # no credential values
  instance.json           # private source record and repair/reference patches
  prompt.txt
  runtime.json            # exact runtime image ID
  status.json
  build/                  # Dockerfile, resolved base images, build log
  reference/              # private developer regression-test check
  agent/                  # JSONL trace, stderr, final response, usage, snapshots, diff
  generated/
    manifest.json         # artifact hashes and policy violations
    files/oracle_tests/
  buggy/                  # test outcomes, coverage, import paths, execution log
  golden/
  results.json
  report.md
```

The host controls image preparation and scoring. Only the public prompt and workspace enter generation; the full run directory is never mounted. The agent runs as a non-root container user, with its API credential injected for that process. No host Docker socket is mounted. Evaluation containers have networking disabled. Generation retains network access; internet-use checks and history sanitization remain deferred.

## Development

```sh
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

The default tests need neither Docker nor an API key. They execute the actual pytest runner in fresh Python processes and cover the four matrix cells, non-binary outcomes, coverage, artifact checks, visibility settings, and lifecycle behavior.

After a smoke run has prepared an image, run the optional container checks without making model calls:

```sh
ORACLE_BENCH_SMOKE_RUN=runs/<run-id> uv run pytest -q -m docker
```

These checks use explicitly handwritten probes on the Requests pair to verify all four matrix cells, artifact copying, and coverage with existing tests both kept and hidden. They are evaluator checks, not agent benchmark results.

CLI exit codes are `0` for successful execution, `1` for a setup/configuration failure, `2` for recorded results with agent/execution/submission problems, and `130` for interruption. Failing test assertions are expected benchmark outcomes and do not by themselves make the CLI fail.

The implementation deliberately supports a narrow first path: a configured pytest repository in an existing SWE-bench image. It does not yet build arbitrary repository environments, run experiment matrices, classify bugs, audit upstream retrieval, or reconstruct discarded tests. New repositories may need different Python paths, rebuild commands, test paths, or runner support.

The SWE-bench image conventions were checked against [v4.0.4](https://github.com/SWE-bench/SWE-bench/tree/3947b299c121bb1f45f5094180c0f39fa0c599a0); paired evaluation follows the idea in [SWT-Bench](https://github.com/logic-star-ai/swt-bench). Codex is launched using its [noninteractive CLI](https://learn.chatgpt.com/docs/non-interactive-mode).

See [the spec](docs/spec.md), [design feedback](docs/spec-feedback.md), and [staged implementation plan](docs/implementation-plan.md).
