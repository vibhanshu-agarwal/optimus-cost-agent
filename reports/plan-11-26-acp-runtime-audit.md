# Plan 11.26 ACP runtime audit

This report is deterministically regenerated from the canonical JSON artifact.

## Baselines

| Field | Value |
|---|---|
| Merged commit | `5ea8f8f71548eb05a8562a10e98667e3d2061c4d` |
| Overlay commit | `fac32284888850bacde93815265cbabe3afd4663` |
| Binding commit | `not nominated` |
| Reconciliation | `UNRESOLVED` |

## Status

| Surface | Status |
|---|---|
| Static Audit Status | `PARTIAL` |
| Runtime Characterization Status | `PARTIAL` |
| Live Redis Status | `UNRUN` |
| Acpx Status | `UNRUN` |
| Additional Client Status | `UNRUN` |
| Zed Status | `UNRUN` |
| Live Interoperability Status | `UNRUN` |
| Gate | `INCOMPLETE` |

## Finding counts

| Classification | Count |
|---|---:|
| `CANONICAL` | 4 |
| `CANONICAL_BYPASSED` | 3 |
| `DUPLICATED` | 0 |
| `CONTRADICTORY` | 4 |
| `MISSING` | 3 |
| `INTENTIONALLY_EXCEPTIONAL` | 1 |
| `PROVISIONAL_OVERLAY` | 2 |
| `NOT_PRESENT` | 1 |
| `SUPERSEDED` | 0 |
| `UNCLASSIFIED` | 0 |

## Discovered multipliers

| Multiplier | Count |
|---|---:|
| Cancellation Points | 8 |
| Close Paths | 15 |
| Queues | 0 |
| Sinks | 0 |

## Computed run cost

| Family | Count |
|---|---:|
| Cancellation controls | 2,048 |
| Cancellation races (levels 2/4/8) | 6,144 |
| Queue admissions | 0 |
| Sink failure runs | 0 |
| Idempotent close invocations | 225 |

Measured scenario durations:

| Scenario | p50 ms | p95 ms |
|---|---:|---:|
| not yet measured | 0.000 | 0.000 |

## Evidence records

### `H3` — Task supervision ownership and cancellation settlement

| Field | Value |
|---|---|
| Record | `ER-H3-TASK-SUPERVISION` |
| Baseline scope | `both-aligned` |
| Seed anchor (merged, not binding) | `5ea8f8f71548eb05a8562a10e98667e3d2061c4d` |
| Overlay identity | `fac32284888850bacde93815265cbabe3afd4663` |
| Binding commit | `not nominated` |
| Reviewer status | `PENDING_G2` |
| Derived cancellation points | 8 |
| Created task/thread/future units | 12 |

Inventory counts: `CANCELLATION_POINT`=16, `TASK_CREATE`=24

Ownership-role counts: `CALLBACK`=2, `CANCELLATION_CATCH`=12, `JOIN`=22, `REGISTRATION`=8, `TASK_GROUP`=0, `TASK_SET_MUTATION`=4, `TIMEOUT`=0

Ownership classifications: `ESCAPED_CHILD`=1, `OWNED`=11

TurnControl ruling: `merged`=`CANONICAL`, `overlay`=`CANONICAL`

Contradiction search: 0 contradictory site(s) across 40 mechanically discovered references. Independent syntax-family comparison found no cross-baseline ta[REDACTED] contradiction.

Schedule observations replayed 4 frozen literal seeds and 256 commit-derived seeds in each point/level family.

Derived terminal cost: 2,048 control schedules plus 6,144 race schedules.

Observation closure: 8,320/8,320 structurally closed records (`FULLY_STRUCTURALLY_CLOSED`). This is record-shape closure, not settled-vocabulary completeness.

Settled-vocabulary coverage: `PARTIAL_WITH_SCOPE_OUTS`.

| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |
|---|---|---|---|---|---|---|---|
| `child_work_state` | `ChildWorkState` | `SCOPED_OUT` | `failed_effect_unknown`, `succeeded`, `suppressed` | `failed_no_effect` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 per-group child-failure characterization | Task 5 executes success, suppression, and cancellation-freeze paths; it does not inject an operational failed_no_effect child result. |
| `conversation_commit` | `ConversationCommit` | `SCOPED_OUT` | `not_committed` | `committed` | P11-FEAT-ACP-RUNTIME-HARDENING | G5 cancellation-to-conversation persistence characterization | Task 5 terminates the request through cancellation and transport teardown and never executes conversation persistence. |
| `effect_state` | `EffectState` | `SCOPED_OUT` | `complete`, `indeterminate`, `none` | `partial` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 multi-work cancellation characterization | Each Task 5 schedule owns one effectful directive; the partial value requires a mixed multi-directive effect set. |
| `final_delivery` | `FinalDelivery` | `SCOPED_OUT` | `ambiguous`, `flushed`, `not_attempted` | `conclusive_failure`, `partial` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 per-group delivery-failure characterization | Task 5 cancellation schedules do not inject conclusive writer failure or a mixed multi-message terminal set, so those delivery values are unreachable here. |
| `invocation_outcomes` | `CancellationInvocationOutcome` | `SCOPED_OUT` | `accepted`, `ignored_after_cutoff`, `permission_already_resolved`, `permission_resolved`, `task_cancel_requested`, `teardown_ambiguous`, `teardown_flushed`, `teardown_not_attempted` | `task_already_terminal`, `teardown_conclusive_failure`, `teardown_partial` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 per-group pre-terminal and delivery-failure characterization | Task 5 starts an active request before cancellation and does not inject conclusive writer failure or mixed terminal sends, leaving pre-terminal task and those teardown outcomes unreachable. |
| `request_task_state` | `RequestTaskState` | `FULLY_OBSERVED` | `cancelled`, `completed` | none | not applicable | not applicable | All declared values were observed. |

Cancellation phase counts: `delivery`=1610, `pre-start`=1722, `running`=1679, `settlement`=1692, `teardown`=1617

Request task terminal states: `cancelled`=4975, `completed`=3345

Child work terminal states: `failed_effect_unknown`=2861, `succeeded`=3737, `suppressed`=1722

Schedule observation digest: `709e9ca0b836bae349ea37eb6b866625a13a60c004442ac8a4f2c0b57bf8909f`

Commands:

- `uv run --frozen pytest tests/unit/acp/test_plan1126_cancellation.py::test_task_supervision_inventory_is_independent_complete_and_receiver_safe -q`
- `uv run --frozen pytest tests/unit/acp/test_plan1126_cancellation.py::test_turn_cancellation_races_256_seed_matrix -q`

Ruling: TurnControl is canonical on merged and overlay baselines. Owned subordinate paths and any escaped child submissions are classified separately in the supervision inventory.

Content-free evidence:

- `H3-TASK-INVENTORY` (`both-aligned`): `dcf7b80ebb6d681da0da4dd4c576d513f07b7b32169da7a5690020e57c0e57e2`
- `H3-CANCELLATION-OBSERVATIONS` (`both-aligned`): `709e9ca0b836bae349ea37eb6b866625a13a60c004442ac8a4f2c0b57bf8909f`

### `H4` — Delivery settlement from queue admission through effect and conversation commit

| Field | Value |
|---|---|
| Record | `ER-H4-DELIVERY` |
| Baseline scope | `both-aligned` |
| Seed anchor (merged, not binding) | `5ea8f8f71548eb05a8562a10e98667e3d2061c4d` |
| Overlay identity | `fac32284888850bacde93815265cbabe3afd4663` |
| Binding commit | `not nominated` |
| Reviewer status | `PENDING_G2` |
| Discovered sites | 261 |

Settled vocabulary: `ConversationCommit`, `EffectState`, `FinalDelivery`, `RpcResponseDelivery`, `SendOutcome`, `SendState`, `Settlement`

Delivery-phase counts: `CANCELLATION`=45, `CONVERSATION_COMMIT`=15, `EFFECT_SETTLEMENT`=14, `FINAL_RESPONSE`=30, `FLUSH`=4, `PHYSICAL_WRITE`=23, `PUBLICATION`=92, `QUEUE_ADMISSION`=38

Site-classification counts: `CANONICAL`=247, `CANONICAL_BYPASSED`=1, `CONTRADICTORY`=5, `NOT_PRESENT`=3, `PROVISIONAL_OVERLAY`=5

Contradiction search: 5 contradictory site(s) across 261 mechanically discovered references. Mechanical role and control-flow comparison found classified contradictions; they remain findings pending G2.

The canonical JSON `evidence_records[].discovered_sites` array contains every phase, classification, line, symbol, reference, invariant, and content-free AST digest; `contradiction_search.contradictory_citations` is the exact contradictory subset.

Schedule observations replayed 4 frozen literal seeds first, then 1,000 commit-derived seeds anchored to `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`.

Observation closure: 1,004/1,004 structurally closed records (`FULLY_STRUCTURALLY_CLOSED`). This is record-shape closure, not settled-vocabulary completeness.

Settled-vocabulary coverage: `PARTIAL_WITH_SCOPE_OUTS`.

| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |
|---|---|---|---|---|---|---|---|
| `conversation_commit` | `ConversationCommit` | `FULLY_OBSERVED` | `committed`, `not_committed` | none | not applicable | not applicable | All declared values were observed. |
| `effect_state` | `EffectState` | `FULLY_OBSERVED` | `complete`, `indeterminate`, `none`, `partial` | none | not applicable | not applicable | All declared values were observed. |
| `final_delivery` | `FinalDelivery` | `SCOPED_OUT` | `not_attempted` | `ambiguous`, `conclusive_failure`, `flushed`, `partial` | P11-FEAT-ACP-RUNTIME-HARDENING | G5 terminal-message characterization | These H4 scenarios execute start_response_send and never start_terminal_message, so terminal-message states are unreachable. |
| `rpc_response_delivery` | `RpcResponseDelivery` | `FULLY_OBSERVED` | `ambiguous`, `conclusive_failure`, `flushed`, `not_attempted` | none | not applicable | not applicable | All declared values were observed. |
| `send_outcome` | `SendOutcome` | `FULLY_OBSERVED` | `ambiguous`, `conclusive_failure`, `flushed`, `suppressed` | none | not applicable | not applicable | All declared values were observed. |
| `send_state` | `SendState` | `SCOPED_OUT` | `ambiguous`, `conclusive_failure`, `flushed`, `suppressed` | `queued`, `write_started` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 per-group transient-state observation review | Queued and write_started are transient states absent from terminal observation snapshots. |
| `settlement` | `Settlement` | `SCOPED_OUT` | `completed`, `transport_abandoned` | `cancelled`, `failed`, `rejected` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 per-group settlement-producer review | The reviewed _placeholder_settlement two-branch producer does not emit cancelled, failed, or rejected. |

Constant metadata dimensions are not vocabulary-coverage claims:

- `classification` = `CANONICAL` (`NOT_A_VOCABULARY_CLAIM`): Classification is static-site lineage represented by discovered sites and findings; schedule rows do not claim classification-vocabulary coverage.
- `complete` = `True` (`NOT_A_VOCABULARY_CLAIM`): Complete means closed observation-record shape only; it is not a settled-vocabulary coverage claim.
- `contradiction` = `None` (`NOT_A_VOCABULARY_CLAIM`): Contradiction belongs to the static contradiction search; no schedule row executes a contradictory site.

Primary scenario counts: `cancel-after-publication`=135, `flush-failure`=133, `preparation-failure`=115, `session-cancel-before-protocol-write`=123, `success-known-effect`=111, `success-unknown-effect`=129, `transport-teardown`=141, `write-failure`=117

Primary attempts: write attempted=748, write not attempted=256, flush attempted=631, flush not attempted=373.

Cancellation timing counts: `after-publication`=490, `before-write`=264, `during-flush`=133, `during-write`=117

Primary conversation states: `committed`/records=1: 375, `not_committed`/records=0: 629

Schedule observation digest: `224ca11abf53aa6b498e4baf14068fe909a0c21ef5471780c68bf442ec6a5e14`

Commands:

- `uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_ast_covers_all_send_sites -q`
- `uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_model_1000_seed_schedule -q`

Ruling: The seven source-derived settled delivery types remain the canonical vocabulary. Bypasses, divergence, and contradictions remain audit findings pending external G2 review.

Content-free evidence:

- `H4-AST-INVENTORY` (`both-aligned`): `6ab2c07940dcf47c456adc43a30f9beb9e4074ed5dea3b97ecf213fbbf7489ca`
- `H4-SCHEDULE-OBSERVATIONS` (`both-aligned`): `224ca11abf53aa6b498e4baf14068fe909a0c21ef5471780c68bf442ec6a5e14`

### `H5` — Resource ownership, shutdown ordering, and repeated close settlement

| Field | Value |
|---|---|
| Record | `ER-H5-RESOURCE-SHUTDOWN` |
| Baseline scope | `both-divergent` |
| Reviewer status | `PENDING_G2` |
| Derived close paths | 15 |
| Scheduled merged close paths | 13 |
| Raw observations | 6,500 |

S1 serving RedisRuntime: `merged`=`MISSING`, `overlay`=`PROVISIONAL_OVERLAY`

Shutdown order: `merged`: `adapter` → `client_mcp_runtime` → `dedicated_writer` → `reader_task`; `overlay`: `adapter` → `client_mcp_runtime` → `dedicated_writer` → `reader_task` → `redis_runtime`

Overlay-only close-path scope-outs:

- `RedisLoopOwner.close` (`h5-0135c920fce9819c`): This close contract exists only on the non-binding overlay and cannot be executed as merged runtime evidence. Owner: P11-FEAT-ZED-RESUME. Next gate: G3 binding baseline reconciliation and overlay runtime characterization.
- `AcpDuplexAdapter.aclose` (`h5-74ea3e4d816e69cb`): This close contract exists only on the non-binding overlay and cannot be executed as merged runtime evidence. Owner: P11-FEAT-ZED-RESUME. Next gate: G3 binding baseline reconciliation and overlay runtime characterization.

Observation closure: 6,500/6,500 structurally closed records (`FULLY_STRUCTURALLY_CLOSED`). This is record-shape closure, not settled-vocabulary completeness.

Settled-vocabulary coverage: `PARTIAL_WITH_SCOPE_OUTS`.

| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |
|---|---|---|---|---|---|---|---|
| `close_outcome` | `CloseOutcome` | `SCOPED_OUT` | `CLOSED_ONCE`, `DOUBLE_CLOSE_OBSERVED`, `IDEMPOTENT_NOOP` | `ERROR` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 per-group shutdown fault-injection characterization | Task 6 invokes valid offline close owners and does not manufacture a close exception; ERROR remains a named fault-injection obligation. |
| `repeat_latency_class` | `RepeatLatencyClass` | `SCOPED_OUT` | `WITHIN_100MS` | `ABOVE_100MS` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 per-group bounded slow-close characterization | Task 6 records measured close latency but does not add an artificial slow-close delay solely to populate the above-threshold value. |
| `terminal_cause` | `TerminalCause` | `FULLY_OBSERVED` | `orderly_eof`, `partial_startup_failure`, `request_cancellation`, `server_cancellation`, `transport_failure` | none | not applicable | not applicable | All declared values were observed. |

Terminal-cause counts: `orderly_eof`=1300, `partial_startup_failure`=1300, `request_cancellation`=1300, `server_cancellation`=1300, `transport_failure`=1300

Close-outcome counts: `CLOSED_ONCE`=5400, `DOUBLE_CLOSE_OBSERVED`=1000, `IDEMPOTENT_NOOP`=100

Schedule observation digest: `f5c57b058e6de024aecd5f31f1a2478547afc1f043430c977f8e519f9870562f`

Commands:

- `uv run --frozen pytest tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_inventory_is_independent_complete_and_receiver_safe -q`
- `uv run --frozen pytest tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist -q`

Ruling: S1 is MISSING on merged because the serving graph does not own RedisRuntime shutdown; the overlay fix remains PROVISIONAL_OVERLAY until baseline reconciliation.

### `H6` — Plan 11.18 raw ACP error-code ownership authority

| Field | Value |
|---|---|
| Record | `ER-H6-ERROR-CODE-AUTHORITY` |
| Baseline scope | `merged` |
| Schema oracle | `PASS` |
| AST oracle | `PASS` |
| Legacy allowlist entries | 0 |
| Reviewer status | `PENDING_G2` |

Ruling: H6 remains accepted canon: the schema and AST oracles pass and the legacy allowlist remains empty.

### `H7` — Semantic outcome and exception-to-wire selection

| Field | Value |
|---|---|
| Record | `ER-H7-SEMANTIC-SELECTION` |
| Baseline scope | `merged` |
| Derived semantic sites | 83 |
| Seeded expected site count | `null` |
| Sanitizer observations | 800 |
| Reviewer status | `PENDING_G2` |

Site categories: `CANCELLATION_DEADLINE`=4, `DELIVERY`=3, `DEPENDENCY_AVAILABILITY`=9, `INTEGRITY`=4, `INVARIANT_PROGRAMMING`=14, `OWNERSHIP_CONCURRENCY`=6, `PROTOCOL_INPUT`=41, `RESOURCE_LIFECYCLE`=2

Site classifications: `CANONICAL`=70, `CANONICAL_BYPASSED`=2, `CONTRADICTORY`=8, `INTENTIONALLY_EXCEPTIONAL`=2, `MISSING`=1

Observation closure: 800/800 structurally closed records (`FULLY_STRUCTURALLY_CLOSED`). This is record-shape closure, not settled-vocabulary completeness.

Settled-vocabulary coverage: `PARTIAL_WITH_SCOPE_OUTS`.

Semantic category coverage and all other settled observation vocabularies:

| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |
|---|---|---|---|---|---|---|---|
| `category` | `SemanticCategory` | `FULLY_OBSERVED` | `CANCELLATION_DEADLINE`, `DELIVERY`, `DEPENDENCY_AVAILABILITY`, `INTEGRITY`, `INVARIANT_PROGRAMMING`, `OWNERSHIP_CONCURRENCY`, `PROTOCOL_INPUT`, `RESOURCE_LIFECYCLE` | none | not applicable | not applicable | All declared values were observed. |
| `error_code_name` | `NamedErrorCode` | `FULLY_OBSERVED` | `AUTHENTICATION_REQUIRED`, `DUPLICATE_REQUEST_ID`, `INTERNAL_ERROR`, `INVALID_PARAMS`, `INVALID_REQUEST`, `METHOD_NOT_FOUND`, `MUTATION_FORBIDDEN`, `PARSE_ERROR`, `REQUEST_CANCELLED`, `RESOURCE_NOT_FOUND` | none | not applicable | not applicable | All declared values were observed. |
| `retryability` | `Retryability` | `FULLY_OBSERVED` | `BACKOFF_REQUIRED`, `NEVER`, `NOT_APPLICABLE`, `SAFE_RETRY`, `STATE_CHECK_REQUIRED` | none | not applicable | not applicable | All declared values were observed. |
| `effect_certainty` | `EffectCertainty` | `FULLY_OBSERVED` | `KNOWN_LOCAL_EFFECT`, `NOT_APPLICABLE`, `NO_EFFECT`, `UNKNOWN_POST_WRITE` | none | not applicable | not applicable | All declared values were observed. |
| `public_output` | `PublicOutput` | `FULLY_OBSERVED` | `FAIL_CLOSED_SANITIZED`, `NO_WIRE_OUTPUT`, `SANITIZED_DYNAMIC_ERROR`, `SANITIZED_NAMED_ERROR` | none | not applicable | not applicable | All declared values were observed. |
| `telemetry_disposition` | `TelemetryDisposition` | `FULLY_OBSERVED` | `CONTAINED_DIAGNOSTIC`, `NO_ADDITIONAL_EVENT`, `SEMANTIC_EVENT_REQUIRED` | none | not applicable | not applicable | All declared values were observed. |
| `cleanup_obligation` | `CleanupObligation` | `FULLY_OBSERVED` | `CANCEL_AND_JOIN`, `CLOSE_OWNER`, `NONE`, `PRESERVE_STATE`, `REQUEST_LOCAL`, `SETTLE_DELIVERY` | none | not applicable | not applicable | All declared values were observed. |
| `leakage_result` | `LeakageResult` | `SCOPED_OUT` | `CLEAN` | `LEAKED` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 semantic negative-outcome fault-injection characterization | The 800 real sanitizer cases exercised every category without producing this failure outcome; G4 must use reviewed fault injection and retain the raw result if it becomes reachable. |
| `divergence_result` | `DivergenceResult` | `SCOPED_OUT` | `MATCH` | `DIVERGED` | P11-FEAT-ACP-RUNTIME-HARDENING | G4 semantic negative-outcome fault-injection characterization | The 800 real sanitizer cases exercised every category without producing this failure outcome; G4 must use reviewed fault injection and retain the raw result if it becomes reachable. |

Observation digest: `d4472f12b731e6e3cf958cc87cdb93caeae9cb5d72ff81cc66121582d3c9a8d8`

Ruling: H7 records every mechanically discovered selection, preserves cancellation as distinct, and retains semantic gaps and S3 exceptions without production repair.

## Running scope-out register

| Hypothesis | Field | Missing values | Owning gate | Reachability | Owner | Reason |
|---|---|---|---|---|---|---|
| `H3` | `child_work_state` | `failed_no_effect` | G4 per-group child-failure characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 per-group child-failure characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H3` | `conversation_commit` | `committed` | G5 cancellation-to-conversation persistence characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G5 cancellation-to-conversation persistence characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H3` | `effect_state` | `partial` | G4 multi-work cancellation characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 multi-work cancellation characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H3` | `final_delivery` | `conclusive_failure`, `partial` | G4 per-group delivery-failure characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 per-group delivery-failure characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H3` | `invocation_outcomes` | `task_already_terminal`, `teardown_conclusive_failure`, `teardown_partial` | G4 per-group pre-terminal and delivery-failure characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 per-group pre-terminal and delivery-failure characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H4` | `final_delivery` | `ambiguous`, `conclusive_failure`, `flushed`, `partial` | G5 terminal-message characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G5 terminal-message characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H4` | `send_state` | `queued`, `write_started` | G4 per-group transient-state observation review | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 per-group transient-state observation review remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H4` | `settlement` | `cancelled`, `failed`, `rejected` | G4 per-group settlement-producer review | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 per-group settlement-producer review remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H5` | `close_outcome` | `ERROR` | G4 per-group shutdown fault-injection characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 per-group shutdown fault-injection characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H5` | `repeat_latency_class` | `ABOVE_100MS` | G4 per-group bounded slow-close characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 per-group bounded slow-close characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H7` | `divergence_result` | `DIVERGED` | G4 semantic negative-outcome fault-injection characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 semantic negative-outcome fault-injection characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |
| `H7` | `leakage_result` | `LEAKED` | G4 semantic negative-outcome fault-injection characterization | `NOT_YET_ASSESSED` | P11-FEAT-ACP-RUNTIME-HARDENING | Reachability against G4 semantic negative-outcome fault-injection characterization remains an explicit open obligation; the owning gate must prove it from raw observations. |

## Finding index

| ID | Classification | Baseline | Owner |
|---|---|---|---|
| `H3-TASK-ESCAPED_CHILD-both-aligned` | `CANONICAL_BYPASSED` | `both-aligned` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H3-TASK-OWNED-both-aligned` | `CANONICAL` | `both-aligned` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H3-TURN-CONTROL-both-aligned` | `CANONICAL` | `both-aligned` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H4-CANONICAL-both-aligned` | `CANONICAL` | `both-aligned` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-CANONICAL-both-divergent` | `CANONICAL` | `both-divergent` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-CANONICAL_BYPASSED-both-aligned` | `CANONICAL_BYPASSED` | `both-aligned` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-CONTRADICTORY-both-aligned` | `CONTRADICTORY` | `both-aligned` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-NOT_PRESENT-merged` | `NOT_PRESENT` | `merged` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-PROVISIONAL_OVERLAY-overlay` | `PROVISIONAL_OVERLAY` | `overlay` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H5-REPEATED-CLOSE-UNDERLYING-merged` | `MISSING` | `merged` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H5-S1-REDIS-RUNTIME-merged` | `MISSING` | `merged` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H5-S1-REDIS-RUNTIME-overlay` | `PROVISIONAL_OVERLAY` | `overlay` | P11-FEAT-ZED-RESUME |
| `H7-CANONICAL_BYPASSED-01` | `CANONICAL_BYPASSED` | `merged` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H7-CONTRADICTORY-02` | `CONTRADICTORY` | `merged` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H7-CONTRADICTORY-03` | `CONTRADICTORY` | `merged` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H7-CONTRADICTORY-04` | `CONTRADICTORY` | `merged` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H7-INTENTIONALLY_EXCEPTIONAL-05` | `INTENTIONALLY_EXCEPTIONAL` | `merged` | P11-FEAT-ACP-RUNTIME-HARDENING |
| `H7-MISSING-06` | `MISSING` | `merged` | P11-FEAT-ACP-RUNTIME-HARDENING |
