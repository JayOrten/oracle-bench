# Oracle Bench: sphinx-doc__sphinx-11510

## Run summary

Overall result: **completed**.

Generation: **completed**. Buggy evaluation: **completed**. Golden evaluation: **completed**. Generated-test judgment: **completed**.

Test-generation scope: **calculated localized target**.

Existing repository test modules visible to agent: **no**.

Calculated target: **sphinx/directives/other.py (Include)**.

## Task classification

Status: **completed**.

Harness: `codex`. Provider: `openrouter`. Model: `openai/gpt-5-mini@preset/oracle-openai-first`. Limit: `wall_seconds=300.0`.

| Facet | Label |
|---|---|
| Task nature | `behavioral_bug` |
| Defect mechanisms | `control_logic, interface_contract` |
| Primary assertion target | `external_interaction` |
| Required test setup | `existing_state` |
| Code-only oracle availability | `repository_documentation` |
| Required test scope | `component` |
| Benchmark quality | `usable` |

Rationale:

> The bug is a behavioral one: the `Include` directive in `sphinx/directives/other.py` (checked) does not emit or invoke the Sphinx `source-read` event for included RST text, while `sphinx/io.py` shows Sphinx emits `source-read` for top-level file reads and the documentation (`doc/extdev/appapi.rst` and `sphinx/events.py`) describes the event and its handler signature; the gold patch and reference tests both target `Include.run` and add tests that connect a `source-read` handler, so the issue, repair, and tests form one coherent task.

## Ground truth

Private dataset evidence, retained for manual analysis and never exposed to the generation agent:

- [Original issue](ground-truth/issue.md)
- [Buggy-to-golden fix diff](ground-truth/fix.patch)

## Generated-test results

These outcomes describe the tests written by the generation agent, run unchanged against the buggy and golden repository versions.

### Paired outcomes

| Outcome | Tests |
|---|---:|
| Pass on both | 22 |
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
| buggy | 9828 / 37547 | 26.18% |
| golden | 9832 / 37559 | 26.18% |

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

> The generated tests in `oracle_tests/test_directive_include.py` target standard functionality of `sphinx.directives.other.Include`, such as relative/absolute path resolution, options, and dependency tracking, without testing `source-read` event emission or modification for included files. The session logs show standard repository exploration without any attempt to access unauthorized external or private benchmark resources.

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

- [Classification result](/home/jay/repos/oracle-bench/classifications/sphinx-doc__sphinx-11510/20260923T215902802161Z-2fe61a3b/classification.json)
- [Raw classifier response](/home/jay/repos/oracle-bench/classifications/sphinx-doc__sphinx-11510/20260923T215902802161Z-2fe61a3b/classification.raw.txt)
- [Classifier rubric](/home/jay/repos/oracle-bench/classifications/sphinx-doc__sphinx-11510/20260923T215902802161Z-2fe61a3b/inputs/rubric.md)
- [Classifier trace](/home/jay/repos/oracle-bench/classifications/sphinx-doc__sphinx-11510/20260923T215902802161Z-2fe61a3b/agent/trace.jsonl)

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

Generation wall time: 89.4s. Reported token usage: `{'cache_creation': {'ephemeral_1h_input_tokens': 0, 'ephemeral_5m_input_tokens': 25449}, 'cache_creation_input_tokens': 25449, 'cache_read_input_tokens': 101831, 'inference_geo': 'global', 'input_tokens': 18, 'iterations': [], 'output_tokens': 8853, 'output_tokens_details': {'thinking_tokens': 1844}, 'server_tool_use': {'web_fetch_requests': 0, 'web_search_requests': 0}, 'service_tier': 'standard', 'speed': 'standard'}`. Monetary cost is unavailable unless supplied by the harness.

Judge wall time: 40.7s. Reported token usage: `{'cache_write_input_tokens': 0, 'cached_input_tokens': 141605, 'input_tokens': 207932, 'output_tokens': 2677, 'reasoning_output_tokens': 2092}`. Monetary cost is unavailable unless supplied by the harness.
