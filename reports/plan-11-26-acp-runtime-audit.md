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
| `CANONICAL` | 2 |
| `CANONICAL_BYPASSED` | 1 |
| `DUPLICATED` | 0 |
| `CONTRADICTORY` | 1 |
| `MISSING` | 0 |
| `INTENTIONALLY_EXCEPTIONAL` | 0 |
| `PROVISIONAL_OVERLAY` | 1 |
| `NOT_PRESENT` | 1 |
| `SUPERSEDED` | 0 |
| `UNCLASSIFIED` | 0 |

## Discovered multipliers

| Multiplier | Count |
|---|---:|
| Cancellation Points | 0 |
| Close Paths | 0 |
| Queues | 0 |
| Sinks | 0 |

## Evidence records

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

## Finding index

| ID | Classification | Baseline | Owner |
|---|---|---|---|
| `H4-CANONICAL-both-aligned` | `CANONICAL` | `both-aligned` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-CANONICAL-both-divergent` | `CANONICAL` | `both-divergent` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-CANONICAL_BYPASSED-both-aligned` | `CANONICAL_BYPASSED` | `both-aligned` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-CONTRADICTORY-both-aligned` | `CONTRADICTORY` | `both-aligned` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-NOT_PRESENT-merged` | `NOT_PRESENT` | `merged` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
| `H4-PROVISIONAL_OVERLAY-overlay` | `PROVISIONAL_OVERLAY` | `overlay` | Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation |
