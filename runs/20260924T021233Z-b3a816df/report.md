# Oracle Bench: pytest-dev__pytest-10051

## Run summary

Overall result: **completed**.

Generation: **completed**. Buggy evaluation: **completed**. Golden evaluation: **completed**. Generated-test judgment: **completed**.

Test-generation scope: **calculated localized target**.

Existing repository test modules visible to agent: **no**.

Calculated target: **src/_pytest/logging.py (messages, reset)**.

## Task classification

Status: **completed**.

Harness: `codex`. Provider: `openrouter`. Model: `openai/gpt-5-mini@preset/oracle-openai-first`. Limit: `wall_seconds=300.0`.

| Facet | Label |
|---|---|
| Task nature | `behavioral_bug` |
| Defect mechanisms | `data_state, interface_contract` |
| Primary assertion target | `return_value_or_status` |
| Required test setup | `sequence` |
| Code-only oracle availability | `local_contract` |
| Required test scope | `unit` |
| Benchmark quality | `usable` |

Rationale:

> The handler method `reset` replaces the `records` list (`src/_pytest/logging.py:344-346`) while the test-run code stores the handler's `records` list object in the node stash (`item.stash[caplog_records_key]`) (`src/_pytest/logging.py:699` and stash creation at `:712`), so replacing the list breaks the expected in-place mutation contract and causes get_records() to diverge from handler.records; this is a mutable state / API-contract bug visible in the code.

## Ground truth

Private dataset evidence, retained for manual analysis and never exposed to the generation agent:

- [Original issue](ground-truth/issue.md)
- [Buggy-to-golden fix diff](ground-truth/fix.patch)

## Generated-test results

These outcomes describe the tests written by the generation agent, run unchanged against the buggy and golden repository versions.

### Paired outcomes

| Outcome | Tests |
|---|---:|
| Pass on both | 6 |
| Fail on buggy, pass on golden | 0 |
| Pass on buggy, fail on golden | 1 |
| Fail on both | 0 |

Other/unmatched outcomes: 0.

Pass on both means the test did not distinguish these versions. It does not by itself establish an incorrect oracle.

### Failure causes

Call-phase failures are classified by the exception that escaped the test. This is diagnostic and does not change matrix scoring.

| Version | Assertion failures | Other exceptions | Unknown |
|---|---:|---:|---:|
| buggy | 0 | 0 | 0 |
| golden | 1 | 0 | 0 |

### Line coverage

| Version | Covered / executable lines | Coverage |
|---|---:|---:|
| buggy | 3566 / 13939 | 25.58% |
| golden | 4063 / 13942 | 29.14% |

## Generated-test judgment

Status: **completed**.

Harness: `codex`. Provider: `openrouter`. Model: `google/gemini-3.8-flash`. CLI version: `0.153.4`. Limit: `wall_seconds=300.0`.

| Facet | Label |
|---|---|
| Do the generated tests attempt to test the issue? | `no` |
| Attempt detail | `null` |
| No-attempt reason | `nearby_behavior` |
| Cheating attempt | `no` |

Rationale:

> The reported issue is that calling `caplog.clear()` decouples and freezes `caplog.get_records()`. The generated tests cover nearby behaviors including `caplog.messages`, `caplog.clear()`, and handler reset methods, but none attempt to exercise `get_records()` or stage-specific records. The generation session shows standard repository inspection with no attempt to access external resources or unauthorized evidence.

## Supporting files

These are the underlying machine-readable results, logs, prompts, and traces.

### Generated tests and execution

- [Paired outcomes and test IDs](evaluation/results.json)
- [Frozen test manifest](submission/manifest.json)
- [Image provenance](image-build/images.json)
- [Readable agent session](generation/session.log)
- [Raw agent events](generation/trace.jsonl)
- [Workspace diff](generation/workspace.diff)
- [Buggy results](evaluation/buggy/tests.json)
- [Buggy log](evaluation/buggy/output.log)
- [Golden results](evaluation/golden/tests.json)
- [Golden log](evaluation/golden/output.log)

### Task classification

- [Classification result](/home/jay/repos/oracle-bench/classifications/pytest-dev__pytest-10051/20260923T212923326438Z-bf89ea06/classification.json)
- [Raw classifier response](/home/jay/repos/oracle-bench/classifications/pytest-dev__pytest-10051/20260923T212923326438Z-bf89ea06/classification.raw.txt)
- [Classifier rubric](/home/jay/repos/oracle-bench/classifications/pytest-dev__pytest-10051/20260923T212923326438Z-bf89ea06/inputs/rubric.md)
- [Classifier trace](/home/jay/repos/oracle-bench/classifications/pytest-dev__pytest-10051/20260923T212923326438Z-bf89ea06/agent/trace.jsonl)

### Generated-test judgment

- [Normalized judgment](judge/judgment.json)
- [Raw judge response](judge/judgment.raw.txt)
- [Exact judge prompt](judge/prompt.md)
- [Frozen judge rubric](judge/rubric.md)
- [Judge workspace contents](judge/workspace-spec.json)
- [Judge trace](judge/agent/trace.jsonl)
- [Judge stderr](judge/agent/stderr.log)

## Limits of this exploratory run

Git history and upstream retrieval have not been audited. The paired counts include only completed test executions on both versions. Skips, expected failures, setup/collection errors, and incomplete runs are separate. Coverage excludes existing tests as execution targets. Existing test modules were removed from both final evaluation workspaces.

## Model usage and cost

Generation wall time: 57.1s. Reported token usage: `{'cache_write_input_tokens': 23862, 'cached_input_tokens': 151326, 'input_tokens': 175868, 'output_tokens': 3836, 'reasoning_output_tokens': 1291}`. Monetary cost is unavailable unless supplied by the harness.

Judge wall time: 66.5s. Reported token usage: `{'cache_write_input_tokens': 0, 'cached_input_tokens': 66451, 'input_tokens': 132182, 'output_tokens': 7600, 'reasoning_output_tokens': 6880}`. Monetary cost is unavailable unless supplied by the harness.
