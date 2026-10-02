# Oracle Bench: matplotlib__matplotlib-24627

## Run summary

Overall result: **completed**.

Generation: **completed**. Buggy evaluation: **completed**. Golden evaluation: **completed**. Generated-test judgment: **completed**.

Test-generation scope: **calculated localized target**.

Existing repository test modules visible to agent: **no**.

Calculated target: **lib/matplotlib/axes/_base.py (__clear)**.

## Task classification

Status: **completed**.

Harness: `codex`. Provider: `openrouter`. Model: `openai/gpt-5-mini@preset/oracle-openai-first`. Limit: `wall_seconds=300.0`.

| Facet | Label |
|---|---|
| Task nature | `behavioral_bug` |
| Defect mechanisms | `data_state` |
| Primary assertion target | `state_mutation` |
| Required test setup | `existing_state` |
| Code-only oracle availability | `repository_pattern` |
| Required test scope | `unit` |
| Benchmark quality | `usable` |

Rationale:

> The Axes clear implementation simply resets `self._children = []` without unparenting existing child artists (`lib/matplotlib/axes/_base.py:1315`), whereas `Artist.remove` explicitly sets `self.axes = None` to decouple an artist (`lib/matplotlib/artist.py:220`); the intended behavior is to mutate the artists' in-memory state (unset `.axes`/`.figure`), which a unit test can verify after creating child artists (existing state).

## Ground truth

Private dataset evidence, retained for manual analysis and never exposed to the generation agent:

- [Original issue](ground-truth/issue.md)
- [Buggy-to-golden fix diff](ground-truth/fix.patch)

## Generated-test results

These outcomes describe the tests written by the generation agent, run unchanged against the buggy and golden repository versions.

### Paired outcomes

| Outcome | Tests |
|---|---:|
| Pass on both | 97 |
| Fail on buggy, pass on golden | 0 |
| Pass on buggy, fail on golden | 0 |
| Fail on both | 0 |

Other/unmatched outcomes: 0.

Pass on both means the test did not distinguish these versions. It does not by itself establish an incorrect oracle.

### Failure causes

Call-phase failures are classified by the exception that escaped the test. This is diagnostic and does not change matrix scoring.

| Version | Assertion failures | Other exceptions | Unknown |
|---|---:|---:|---:|
| buggy | 0 | 0 | 0 |
| golden | 0 | 0 | 0 |

### Line coverage

| Version | Covered / executable lines | Coverage |
|---|---:|---:|
| buggy | 14115 / 47469 | 29.74% |
| golden | 14117 / 47471 | 29.74% |

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

> The generated test suite thoroughly exercises general `Axes.clear()` and `cla()` behavior, including verifying that `ax._children` is emptied, but none of the tests retain deparented artists or assert that their `.axes` and `.figure` attributes are unset to `None`. The tests only target nearby clearing behavior, and the generation session contains no cheating attempts.

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

- [Classification result](/home/jay/repos/oracle-bench/classifications/matplotlib__matplotlib-24627/20260923T212358868886Z-30ccabd5/classification.json)
- [Raw classifier response](/home/jay/repos/oracle-bench/classifications/matplotlib__matplotlib-24627/20260923T212358868886Z-30ccabd5/classification.raw.txt)
- [Classifier rubric](/home/jay/repos/oracle-bench/classifications/matplotlib__matplotlib-24627/20260923T212358868886Z-30ccabd5/inputs/rubric.md)
- [Classifier trace](/home/jay/repos/oracle-bench/classifications/matplotlib__matplotlib-24627/20260923T212358868886Z-30ccabd5/agent/trace.jsonl)

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

Generation wall time: 149.8s. Reported token usage: `{'cache_creation': {'ephemeral_1h_input_tokens': 0, 'ephemeral_5m_input_tokens': 33687}, 'cache_creation_input_tokens': 33687, 'cache_read_input_tokens': 169257, 'inference_geo': 'global', 'input_tokens': 22, 'iterations': [], 'output_tokens': 16178, 'output_tokens_details': {'thinking_tokens': 2109}, 'server_tool_use': {'web_fetch_requests': 0, 'web_search_requests': 0}, 'service_tier': 'standard', 'speed': 'standard'}`. Monetary cost is unavailable unless supplied by the harness.

Judge wall time: 49.3s. Reported token usage: `{'cache_write_input_tokens': 0, 'cached_input_tokens': 114161, 'input_tokens': 194201, 'output_tokens': 4167, 'reasoning_output_tokens': 3376}`. Monetary cost is unavailable unless supplied by the harness.
