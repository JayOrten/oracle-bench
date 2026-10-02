# Oracle Bench: pydata__xarray-6744

## Run summary

Overall result: **completed**.

Generation: **completed**. Buggy evaluation: **completed**. Golden evaluation: **completed**. Generated-test judgment: **completed**.

Test-generation scope: **calculated localized target**.

Existing repository test modules visible to agent: **no**.

Calculated target: **xarray/core/rolling.py (__init__)**.

## Task classification

Status: **completed**.

Harness: `codex`. Provider: `openrouter`. Model: `openai/gpt-5-mini@preset/oracle-openai-first`. Limit: `wall_seconds=300.0`.

| Facet | Label |
|---|---|
| Task nature | `behavioral_bug` |
| Defect mechanisms | `control_logic, computation_algorithm` |
| Primary assertion target | `return_value_or_status` |
| Required test setup | `special_input` |
| Code-only oracle availability | `local_contract` |
| Required test scope | `unit` |
| Benchmark quality | `usable` |

Rationale:

> The buggy `__iter__` in `xarray/core/rolling.py` computes `stops = np.arange(1, ...)` and `starts = stops - int(self.window[0])`, which produces uncentered windows (wrong offset logic); tests in `xarray/tests/test_rolling.py` assert that iterating yields windows whose means equal the centered `rolling(...).mean()` values, making this a behavioral bug in window-calculation logic.

## Ground truth

Private dataset evidence, retained for manual analysis and never exposed to the generation agent:

- [Original issue](ground-truth/issue.md)
- [Buggy-to-golden fix diff](ground-truth/fix.patch)

## Generated-test results

These outcomes describe the tests written by the generation agent, run unchanged against the buggy and golden repository versions.

### Paired outcomes

| Outcome | Tests |
|---|---:|
| Pass on both | 21 |
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
| buggy | 5212 / 20018 | 26.04% |
| golden | 5212 / 20021 | 26.03% |

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

> The generated tests only verify constructor behavior in `Rolling.__init__`, such as attribute assignment and parameter validation, without attempting to exercise iteration over `DataArrayRolling` where the `center` argument was reported to be ignored. Because they target initialization properties rather than window iteration, they address nearby behavior. The agent session log contains standard repository exploration with no cheating attempts.

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

- [Classification result](/home/jay/repos/oracle-bench/classifications/pydata__xarray-6744/20260923T215040958989Z-631ebde1/classification.json)
- [Raw classifier response](/home/jay/repos/oracle-bench/classifications/pydata__xarray-6744/20260923T215040958989Z-631ebde1/classification.raw.txt)
- [Classifier rubric](/home/jay/repos/oracle-bench/classifications/pydata__xarray-6744/20260923T215040958989Z-631ebde1/inputs/rubric.md)
- [Classifier trace](/home/jay/repos/oracle-bench/classifications/pydata__xarray-6744/20260923T215040958989Z-631ebde1/agent/trace.jsonl)

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

Generation wall time: 41.8s. Reported token usage: `{'cache_write_input_tokens': 19127, 'cached_input_tokens': 77951, 'input_tokens': 97554, 'output_tokens': 2760, 'reasoning_output_tokens': 497}`. Monetary cost is unavailable unless supplied by the harness.

Judge wall time: 38.2s. Reported token usage: `{'cache_write_input_tokens': 0, 'cached_input_tokens': 58188, 'input_tokens': 120998, 'output_tokens': 2816, 'reasoning_output_tokens': 2216}`. Monetary cost is unavailable unless supplied by the harness.
