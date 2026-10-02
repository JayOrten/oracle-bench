# Oracle Bench batch: expanded-validation-five-repos

Planned: **15**. Attempted: **15**. Completed with results: **15**. Completed paired evaluations: **13**.

Matrix detections: **2** of **13** completed paired evaluations (**15.4%**). The rate over all attempted instances is **13.3%**.

An instance is detected when a compliant submission has at least one test that fails on buggy and passes on golden. Incomplete and diagnostic-only runs never count as detected.

Judge says tests attempt the issue: **2** of **14** valid judgments (**14.3%**).

| Instance | Run ID | State | Matrix detection | Attempts issue? | Attempt detail | No-attempt reason | Cheating | Generation cost | Judge cost |
|---|---|---|---:|---|---|---|---|---:|---:|
| [matplotlib__matplotlib-24627](/home/jay/repos/oracle-bench/runs/20260923T220231Z-a70d9896/report.md) | `20260923T220231Z-a70d9896` | completed | no | failed | — | — | — | — | — |
| [matplotlib__matplotlib-24627](/home/jay/repos/oracle-bench/runs/20260923T220632Z-d17a8ee1/report.md) | `20260923T220632Z-d17a8ee1` | completed | no | no | — | nearby_behavior | no | — | — |
| [matplotlib__matplotlib-24627](/home/jay/repos/oracle-bench/runs/20260923T220922Z-7f620552/report.md) | `20260923T220922Z-7f620552` | completed_with_errors | no | no | — | nearby_behavior | no | $0.7006 | — |
| [pytest-dev__pytest-10051](/home/jay/repos/oracle-bench/runs/20260924T020840Z-9fb8430d/report.md) | `20260924T020840Z-9fb8430d` | completed | yes | yes | correct_assertion | — | no | — | — |
| [pytest-dev__pytest-10051](/home/jay/repos/oracle-bench/runs/20260924T021233Z-b3a816df/report.md) | `20260924T021233Z-b3a816df` | completed | no | no | — | nearby_behavior | no | — | — |
| [pytest-dev__pytest-10051](/home/jay/repos/oracle-bench/runs/20260924T021449Z-a34935b3/report.md) | `20260924T021449Z-a34935b3` | completed_with_errors | no | no | — | nearby_behavior | no | $0.3937 | — |
| [pydata__xarray-6744](/home/jay/repos/oracle-bench/runs/20260923T222725Z-978c132f/report.md) | `20260923T222725Z-978c132f` | completed | no | no | — | nearby_behavior | no | — | — |
| [pydata__xarray-6744](/home/jay/repos/oracle-bench/runs/20260923T222959Z-6c266cf6/report.md) | `20260923T222959Z-6c266cf6` | completed | no | no | — | nearby_behavior | no | — | — |
| [pydata__xarray-6744](/home/jay/repos/oracle-bench/runs/20260923T223150Z-f1dc6eda/report.md) | `20260923T223150Z-f1dc6eda` | completed | no | no | — | nearby_behavior | no | $0.2224 | — |
| [sphinx-doc__sphinx-11510](/home/jay/repos/oracle-bench/runs/20260923T223820Z-164bc58c/report.md) | `20260923T223820Z-164bc58c` | completed | no | no | — | nearby_behavior | no | — | — |
| [sphinx-doc__sphinx-11510](/home/jay/repos/oracle-bench/runs/20260923T224050Z-9cb2ecb5/report.md) | `20260923T224050Z-9cb2ecb5` | completed | no | no | — | nearby_behavior | no | — | — |
| [sphinx-doc__sphinx-11510](/home/jay/repos/oracle-bench/runs/20260923T224306Z-1bb6e1c6/report.md) | `20260923T224306Z-1bb6e1c6` | completed_with_errors | no | no | — | nearby_behavior | no | $0.6380 | — |
| [scikit-learn__scikit-learn-14710](/home/jay/repos/oracle-bench/runs/20260924T023059Z-ca32a5ff/report.md) | `20260924T023059Z-ca32a5ff` | completed | yes | yes | correct_assertion | — | no | — | — |
| [scikit-learn__scikit-learn-14710](/home/jay/repos/oracle-bench/runs/20260924T023530Z-dea5ce4b/report.md) | `20260924T023530Z-dea5ce4b` | completed | no | no | — | nearby_behavior | no | — | — |
| [scikit-learn__scikit-learn-14710](/home/jay/repos/oracle-bench/runs/20260924T023734Z-053e0297/report.md) | `20260924T023734Z-053e0297` | completed | no | no | — | nearby_behavior | no | $0.3374 | — |

Aggregate paired-test counts: `pass_on_both`=407, `fail_on_buggy_pass_on_golden`=6, `pass_on_buggy_fail_on_golden`=12, `fail_on_both`=2.

## Judge label frequencies

### `tests_issue`

| Label | Count |
|---|---:|
| `no` | 12 |
| `yes` | 2 |

### `attempt_detail`

| Label | Count |
|---|---:|
| `correct_assertion` | 2 |
| `null` | 12 |

### `no_attempt_reason`

| Label | Count |
|---|---:|
| `nearby_behavior` | 12 |
| `null` | 2 |

### `cheating`

| Label | Count |
|---|---:|
| `no` | 14 |

See [summary.json](summary.json) for machine-readable per-instance details.
