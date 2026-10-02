# Oracle Bench: matplotlib__matplotlib-24627

## Run summary

Overall result: **completed with errors**.

Generation: **timeout**. Buggy evaluation: **completed**. Golden evaluation: **completed**. Generated-test judgment: **completed**.

Test-generation scope: **calculated localized target**.

Existing repository test modules visible to agent: **no**.

Calculated target: **lib/matplotlib/axes/_base.py (__clear)**.

Why this run completed with errors: generation ended with **timeout**. Any test files captured before it stopped were still evaluated.

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
| Pass on both | 46 |
| Fail on buggy, pass on golden | 0 |
| Pass on buggy, fail on golden | 0 |
| Fail on both | 2 |

Other/unmatched outcomes: 0.

Pass on both means the test did not distinguish these versions. It does not by itself establish an incorrect oracle.

### Failure causes

Call-phase failures are classified by the exception that escaped the test. This is diagnostic and does not change matrix scoring.

| Version | Assertion failures | Other exceptions | Unknown |
|---|---:|---:|---:|
| buggy | 1 | 1 | 0 |
| golden | 1 | 1 | 0 |

### Line coverage

| Version | Covered / executable lines | Coverage |
|---|---:|---:|
| buggy | 13401 / 47469 | 28.23% |
| golden | 13403 / 47471 | 28.23% |

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

> The issue requires clearing an Axes to unset the .axes and .figure attributes of deparented artists. The generated tests in oracle_tests/test_axes_base_clear.py thoroughly exercise nearby behavior of _AxesBase.__clear (such as clearing child lists, margins, spines, and callbacks), but none assert or test that removed artists have their .axes or .figure attributes cleared. The generation session shows standard repository exploration with no attempt to access unauthorized external or benchmark resources.

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

Generation wall time: 900.0s. Reported token usage: `{'input_tokens': 79177, 'output_tokens': 13700, 'reasoning_tokens': 21560}`. Harness-reported model cost: $0.7006.

Judge wall time: 128.3s. Reported token usage: `{'cache_write_input_tokens': 0, 'cached_input_tokens': 424258, 'input_tokens': 644709, 'output_tokens': 8985, 'reasoning_output_tokens': 5573}`. Monetary cost is unavailable unless supplied by the harness.
