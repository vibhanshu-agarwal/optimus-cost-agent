# Plan 11.26 Terminal Characterization Cost Proposal

## Authorization boundary

| Item | Status |
| --- | --- |
| Windows offline narrow tier | COMPLETE |
| Windows offline task-group tier | COMPLETE |
| WSL2/Linux task-group tier | UNRUN_WSL2 |
| WSL2/Linux owner | operator / Plan 11.26 |
| Live run count | 0 |
| Live rows | UNRUN |

## Exact terminal workload

| Workload | Count |
| --- | ---: |
| Cancellation race schedules | 6,144 |
| Cancellation control schedules | 2,048 |
| Queue admissions | 30,000 |
| Sink-failure runs | 500 |
| Idempotent-close invocations | 225 |

## Repeatability disposition

| Tier | Scenario | Generation | Pass | Fail | Timeout | Disposition |
| --- | --- | --- | ---: | ---: | ---: | --- |
| narrow | task2_audit_tooling | legacy | 10 | 0 | 0 | STABLE |
| narrow | task3_clients | legacy | 10 | 0 | 0 | STABLE |
| narrow | task4_delivery | legacy | 10 | 0 | 0 | STABLE |
| narrow | task5_cancellation | legacy | 10 | 0 | 0 | STABLE |
| narrow | task6_shutdown | c18-latest-complete-v1 | 6 | 0 | 4 | HARNESS_UNSTABLE |
| narrow | task7_semantic_errors | legacy | 10 | 0 | 0 | STABLE |
| narrow | task8_telemetry | legacy | 10 | 0 | 0 | STABLE |
| narrow | task9_queue_policy | legacy | 10 | 0 | 0 | STABLE |
| narrow | task10_session_lease_gate | legacy | 10 | 0 | 0 | STABLE |
| group | task4_delivery_group | legacy | 25 | 0 | 0 | STABLE |
| group | task5_cancellation_group | legacy | 24 | 1 | 0 | FLAKY |
| group | task6_shutdown_group | c18-latest-complete-v1 | 15 | 0 | 10 | HARNESS_UNSTABLE |
| group | task7_semantic_errors_group | legacy | 25 | 0 | 0 | STABLE |
| group | task8_telemetry_group | legacy | 25 | 0 | 0 | STABLE |
| group | task9_queue_policy_group | legacy | 25 | 0 | 0 | STABLE |

## Measured Windows task-group durations

| Scenario | Generation | Repeats | Timeouts | p50 ms | p95 ms including timeouts | p95 excluding timeouts |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| task4_delivery_group | legacy | 25 | 0 | 118986.444 | 124741.255 | 124741.255 |
| task5_cancellation_group | legacy | 25 | 0 | 28161.255 | 28765.604 | 28765.604 |
| task6_shutdown_group | c18-latest-complete-v1 | 25 | 10 | 59274.574 | 120330.834 | 61289.263 |
| task7_semantic_errors_group | legacy | 25 | 0 | 63794.051 | 68962.552 | 68962.552 |
| task8_telemetry_group | legacy | 25 | 0 | 174348.250 | 184751.957 | 184751.957 |
| task9_queue_policy_group | legacy | 25 | 0 | 145286.297 | 146468.847 | 146468.847 |

One terminal pass across measured groups: p50 sum 589850.871 ms; p95 including timeouts 674021.049 ms; p95 excluding timeouts 614979.478 ms.
Harness-timeout p95 contribution: 59041.571 ms (8.8% of the including-timeouts p95 sum).

The Linux half remains scoped out because distro-native Redis/TimeSeries is not installed; installation is an operator authorization decision. No host-forwarded Windows Redis is treated as Linux evidence.

Terminal execution is not authorized by this report. Operator cost approval is required before Step 4.
