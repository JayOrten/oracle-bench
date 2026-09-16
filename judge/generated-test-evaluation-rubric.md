# Oracle Bench generated-test evaluation rubric

Use this rubric after a test-generation run to judge a generated **submission**:
all new test files captured from one agent run for one SWE-bench instance.

When a submission contains several tests, focus on the test or tests most
plausibly intended to address the issue. Unrelated extra tests do not make an
otherwise relevant submission unrelated. For Facet E, consider only outcomes
from issue-relevant tests.

The normal pass/fail matrix shows whether tests distinguish the buggy and gold
revisions. This rubric answers a different question: **do the generated tests
address the problem described by the SWE-bench issue?**

Do not treat an F→P result as sufficient evidence by itself. A test can fail on
the buggy revision and pass after the repair for a reason unrelated to the
issue. Conversely, an F→F test can exercise the intended bug and express a
plausible assertion, yet fail to construct a valid oracle.

## Materials provided to the judge

The judge receives:

- the SWE-bench instance: `problem_statement`, `patch`, `test_patch`,
  `FAIL_TO_PASS`, and `PASS_TO_PASS`;
- the buggy and gold repository revisions;
- the captured generated test files and, when available, their diff;
- the execution results for each generated test on both revisions, including
  stdout, stderr, collection errors, timeouts, and the pass/fail matrix.

Use the issue, repair, and reference-test changes to identify the intended
behavior. Use the generated tests and execution evidence to judge what the
submission actually exercises and asserts.

## Procedure

1. Identify the issue's central behavior: the condition that should be tested
   and the behavior that should differ between buggy and gold revisions.
2. Read the generated submission before looking at its execution result.
3. Classify its relation to the issue using Facets A through D.
4. Use the execution result to choose the final verdict in Facet E.
5. Return the required JSON. Cite concrete test code or execution evidence in
   the rationale.

## Facet A: Issue-target alignment

Choose one label. Ask: **does the submission try to test the behavior described
by the issue?**

- `direct`: it tests the issue's central behavior and relevant condition.
- `partial`: it tests a meaningful part of the issue, but misses an essential
  condition or outcome.
- `adjacent`: it tests the same subsystem or a related concern, but not the
  reported behavior.
- `unrelated`: it does not address the issue.
- `indeterminate`: the generated code cannot be understood well enough to
  decide, usually because it is incomplete or does not execute.

## Facet B: Trigger alignment

Choose one label. Ask: **does the test set up and exercise conditions that can
reach the reported defect?** Compare its setup and calls with the issue,
reference test, and relevant production path. A different trigger counts as a
match when it reaches the same behavior under equivalent conditions.

- `matches`: the test reaches the relevant behavior under the required or
  equivalent conditions.
- `misses_required_condition`: the test is related to the issue but leaves out
  a condition needed to reach the defect.
- `wrong_path`: the test does not exercise the code path or behavior involved
  in the issue.
- `not_assessable`: the test cannot be inspected or run well enough to decide.

## Facet C: Oracle alignment

Choose one label. Ask: **does the test's assertion express the correct behavior
for the reported issue?** Judge the assertion's meaning, not only whether the
test happens to pass or fail.

- `behaviorally_aligned`: the assertion agrees with the expected behavior
  established by the issue, repair, and reference test, and checks an
  observable consequence of that behavior.
- `behaviorally_misaligned`: the assertion expects behavior that conflicts with
  the established expected behavior.
- `implementation_coupled`: the assertion checks a repair detail, private
  implementation structure, or a tautology instead of the required behavior.
- `no_clear_oracle`: the test reaches relevant code but makes no meaningful
  assertion about the issue.
- `not_assessable`: the assertion cannot be interpreted because the test is
  incomplete or invalid.

An assertion may be `behaviorally_aligned` even if the test is F→F because a
fixture, setup assumption, or unrelated test error prevents it from passing on
the gold revision. Use Facet A to record a partial issue target and Facet B to
record a missing trigger condition; do not use a separate "incomplete" oracle
label.

## Facet D: Test strategy

Choose one label. This records how the submission attempts to establish the
behavior, which helps compare successful and unsuccessful approaches.

- `return_value_or_status`: asserts a returned value, response, result, or
  status.
- `exception_behavior`: asserts an exception or failure status.
- `state_or_artifact`: asserts state, persisted data, rendered output, a file,
  serialized data, or another produced artifact.
- `external_interaction`: asserts a call, request, event, command, or other
  interaction with a dependency.
- `resource_or_nondeterminism`: asserts a resource bound or a property across
  repeated executions.
- `implementation_inspection`: inspects private implementation details rather
  than observable behavior.
- `no_meaningful_assertion`: has no assertion that could distinguish behavior.

## Facet E: Final verdict

Choose one label after considering the execution result along with Facets A
through C.

- `confirmed_issue_reproduction`: the submission is `direct`, has a
  `behaviorally_aligned` oracle, and contains at least one relevant F→P test.
- `issue_relevant_not_confirmed`: the submission is `direct` or `partial` and
  makes a meaningful attempt, but no relevant test is F→P. This includes F→F,
  P→P, and P→F outcomes when they still target the issue.
- `issue_relevant_but_invalid`: the submission targets the issue, but syntax,
  collection, setup, or another mechanical error prevents a meaningful test
  execution.
- `not_issue_relevant`: the submission is `adjacent` or `unrelated`, even if a
  test happens to be F→P.
- `unassessable`: the available code and execution evidence cannot support a
  reliable judgment.

## Required output

Return JSON in this form. Keep `rationale` to two or three sentences. Identify
the generated test or assertion that supports the judgment and state the
relevant execution outcome.

```json
{
  "issue_target_alignment": "direct",
  "trigger_alignment": "matches",
  "oracle_alignment": "behaviorally_aligned",
  "test_strategy": "exception_behavior",
  "final_verdict": "confirmed_issue_reproduction",
  "rationale": "test_generated.py::test_rejects_invalid_config reaches the nested invalid input described in the issue and asserts ValueError. It fails on the buggy revision and passes on the gold revision."
}
```
