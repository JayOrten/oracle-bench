# Oracle Bench: scikit-learn__scikit-learn-14710

## Run summary

Overall result: **completed**.

Generation: **completed**. Buggy evaluation: **completed**. Golden evaluation: **completed**. Generated-test judgment: **completed**.

Test-generation scope: **calculated localized target**.

Existing repository test modules visible to agent: **no**.

Calculated target: **sklearn/ensemble/_hist_gradient_boosting/gradient_boosting.py (_check_early_stopping_scorer)**.

## Task classification

Status: **completed**.

Harness: `codex`. Provider: `openrouter`. Model: `openai/gpt-5-mini@preset/oracle-openai-first`. Limit: `wall_seconds=300.0`.

| Facet | Label |
|---|---|
| Task nature | `behavioral_bug` |
| Defect mechanisms | `data_state, interface_contract` |
| Primary assertion target | `exception_behavior` |
| Required test setup | `special_input` |
| Code-only oracle availability | `local_contract` |
| Required test scope | `unit` |
| Benchmark quality | `usable` |

Rationale:

> The classifier encodes targets to a numeric dtype in `_encode_y` (`sklearn/ensemble/_hist_gradient_boosting/gradient_boosting.py:1022-1035`) but `_check_early_stopping_scorer` passes those encoded values directly to the scorer (`sklearn/ensemble/_hist_gradient_boosting/gradient_boosting.py:423-436`), which expects original class labels; this mismatch produces a runtime TypeError (mixing strings and floats) and shows the bug is a state/interface mismatch triggered by string targets.

## Ground truth

Private dataset evidence, retained for manual analysis and never exposed to the generation agent:

- [Original issue](ground-truth/issue.md)
- [Buggy-to-golden fix diff](ground-truth/fix.patch)

## Generated-test results

These outcomes describe the tests written by the generation agent, run unchanged against the buggy and golden repository versions.

### Paired outcomes

| Outcome | Tests |
|---|---:|
| Pass on both | 8 |
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
| buggy | 3047 / 32721 | 9.31% |
| golden | 3050 / 32725 | 9.32% |

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

> The issue reports that HistGradientBoostingClassifier fails during early stopping when targets are strings because integer-encoded targets are passed to the scorer instead of mapped class labels. The generated tests only test nearby behavior within _check_early_stopping_scorer on HistGradientBoostingRegressor, using mock scorers and numeric data to check score appending and stopping logic. They make no identifiable attempt to test classification, string targets, or target label decoding.

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

- [Classification result](/home/jay/repos/oracle-bench/classifications/scikit-learn__scikit-learn-14710/20260925T192900351766Z-b8584c16/classification.json)
- [Raw classifier response](/home/jay/repos/oracle-bench/classifications/scikit-learn__scikit-learn-14710/20260925T192900351766Z-b8584c16/classification.raw.txt)
- [Classifier rubric](/home/jay/repos/oracle-bench/classifications/scikit-learn__scikit-learn-14710/20260925T192900351766Z-b8584c16/inputs/rubric.md)
- [Classifier trace](/home/jay/repos/oracle-bench/classifications/scikit-learn__scikit-learn-14710/20260925T192900351766Z-b8584c16/agent/trace.jsonl)

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

Generation wall time: 55.6s. Reported token usage: `{'cache_write_input_tokens': 19599, 'cached_input_tokens': 81506, 'input_tokens': 101581, 'output_tokens': 2856, 'reasoning_output_tokens': 682}`. Monetary cost is unavailable unless supplied by the harness.

Judge wall time: 43.4s. Reported token usage: `{'cache_write_input_tokens': 0, 'cached_input_tokens': 89827, 'input_tokens': 148089, 'output_tokens': 3251, 'reasoning_output_tokens': 2452}`. Monetary cost is unavailable unless supplied by the harness.
