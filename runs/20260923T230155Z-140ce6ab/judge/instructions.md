You are evaluating one generated-test submission for a SWE-bench instance.

Inspect these materials:

- `$root/instructions.md` guides you through the workspace and summarizes the saved outcomes.
- `$root/instance/` contains the issue, repair, reference-test patch, and metadata.
- `$root/buggy/` contains the buggy repository and generated submission.
- `$root/golden/` contains the repaired repository and the identical submission.
- `$root/evidence/` contains the submission manifest and saved execution evidence.

Read the issue, both relevant code versions, the generated tests, and the execution evidence.
Do not modify either repository. Do not rerun broad test suites; the saved results are the
authoritative execution evidence. Return exactly one JSON object matching the rubric's required
output. Do not wrap it in a Markdown fence and do not include any other text.

The rubric follows verbatim:
