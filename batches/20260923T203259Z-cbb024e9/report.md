# Oracle Bench batch: initial-validation-requests

Planned: **3**. Attempted: **3**. Completed with results: **3**. Completed paired evaluations: **3**.

Matrix detections: **0** of **3** completed paired evaluations (**0.0%**). The rate over all attempted instances is **0.0%**.

An instance is detected when a compliant submission has at least one test that fails on buggy and passes on golden. Incomplete and diagnostic-only runs never count as detected.

Judge says tests attempt the issue: **2** of **3** valid judgments (**66.7%**).

| Instance | State | Matrix detection | Attempts issue? | Attempt detail | No-attempt reason | Cheating | Generation cost | Judge cost |
|---|---|---:|---|---|---|---|---:|---:|
| [psf__requests-1142](/home/jay/repos/oracle-bench/runs/20260923T203259Z-84cbeea1/report.md) | completed | no | yes | wrong_assertion | — | no | — | — |
| [psf__requests-1142](/home/jay/repos/oracle-bench/runs/20260923T203811Z-1ec4d342/report.md) | completed | no | no | — | nearby_behavior | no | — | — |
| [psf__requests-1142](/home/jay/repos/oracle-bench/runs/20260923T204000Z-42d550fa/report.md) | completed | no | yes | wrong_assertion | — | no | $0.2626 | — |

Aggregate paired-test counts: `pass_on_both`=106, `fail_on_buggy_pass_on_golden`=0, `pass_on_buggy_fail_on_golden`=2, `fail_on_both`=0.

## Judge label frequencies

### `tests_issue`

| Label | Count |
|---|---:|
| `no` | 1 |
| `yes` | 2 |

### `attempt_detail`

| Label | Count |
|---|---:|
| `null` | 1 |
| `wrong_assertion` | 2 |

### `no_attempt_reason`

| Label | Count |
|---|---:|
| `nearby_behavior` | 1 |
| `null` | 2 |

### `cheating`

| Label | Count |
|---|---:|
| `no` | 3 |

See [summary.json](summary.json) for machine-readable per-instance details.
