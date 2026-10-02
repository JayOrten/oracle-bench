# Oracle Bench: psf__requests-1142

## Run summary

Overall result: **completed**.

Generation: **completed**. Buggy evaluation: **completed**. Golden evaluation: **completed**. Generated-test judgment: **completed**.

Test-generation scope: **calculated localized target**.

Existing repository test modules visible to agent: **no**.

Calculated target: **requests/models.py (prepare_body)**.

## Task classification

Status: **completed**.

Harness: `codex`. Provider: `openrouter`. Model: `openai/gpt-5-mini`. Limit: `wall_seconds=300.0`.

| Facet | Label |
|---|---|
| Task nature | `behavioral_bug` |
| Defect mechanisms | `control_logic, data_state` |
| Primary assertion target | `produced_output_or_artifact` |
| Required test setup | `none` |
| Code-only oracle availability | `repository_pattern` |
| Required test scope | `unit` |
| Benchmark quality | `usable` |

Rationale:

> The bug is a logic/initialization error in `prepare_content_length`: it unconditionally sets `self.headers['Content-Length'] = '0'` then only overwrites that when a body exists (requests/models.py:388-395), causing GET/HEAD requests with no body to still include a Content-Length header; the transport code treats presence of that header specially (`chunked = not (request.body is None or 'Content-Length' in request.headers)` in requests/adapters.py:157), so a test that asserts absence of the header on GET/HEAD (as in the reference test) cleanly exposes the behavioral bug.

## Ground truth

Private dataset evidence, retained for manual analysis and never exposed to the generation agent:

- [Original issue](ground-truth/issue.md)
- [Buggy-to-golden fix diff](ground-truth/fix.patch)

## Generated-test results

These outcomes describe the tests written by the generation agent, run unchanged against the buggy and golden repository versions.

### Paired outcomes

| Outcome | Tests |
|---|---:|
| Pass on both | 16 |
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
| buggy | 800 / 3459 | 23.13% |
| golden | 801 / 3460 | 23.15% |

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

> The generated tests exercise general body preparation, multipart encoding, and stream handling in PreparedRequest.prepare_body, but make no attempt to verify that GET or HEAD requests omit the Content-Length header. In fact, test_empty_body_has_zero_length_and_no_content_type asserts that an empty body sets Content-Length to '0'. No cheating was attempted in the generation session.

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

- [Classification result](/home/jay/repos/oracle-bench/classifications/psf__requests-1142/20260921T182131449388Z-442e6ff6/classification.json)
- [Raw classifier response](/home/jay/repos/oracle-bench/classifications/psf__requests-1142/20260921T182131449388Z-442e6ff6/classification.raw.txt)
- [Classifier rubric](/home/jay/repos/oracle-bench/classifications/psf__requests-1142/20260921T182131449388Z-442e6ff6/inputs/rubric.md)
- [Classifier trace](/home/jay/repos/oracle-bench/classifications/psf__requests-1142/20260921T182131449388Z-442e6ff6/agent/trace.jsonl)

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

Generation wall time: 49.9s. Reported token usage: `{'cache_write_input_tokens': 20523, 'cached_input_tokens': 82068, 'input_tokens': 103067, 'output_tokens': 3728, 'reasoning_output_tokens': 852}`. Monetary cost is unavailable unless supplied by the harness.

Judge wall time: 48.8s. Reported token usage: `{'cache_write_input_tokens': 0, 'cached_input_tokens': 85732, 'input_tokens': 139721, 'output_tokens': 3912, 'reasoning_output_tokens': 3423}`. Monetary cost is unavailable unless supplied by the harness.
