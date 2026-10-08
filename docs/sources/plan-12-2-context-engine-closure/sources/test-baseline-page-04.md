| LLD Section | Design Claim | Test Category (§) | Tier |
| --- | --- | --- | --- |
| §4A — State Machine | AwaitingApproval gate cannot be bypassed | §6 — Mode/State | Unit + Integration |
| §6 — Gateway Layer | POST /v1/responses uses input field, not messages | §8 — Gateway | Unit + Integration |
| §6 — Gateway Layer | No provider key present in local environment during run | §8 — Gateway | E2E (Release Gate) |
| §9 — Tool Policy | EvidenceRequest.query sent verbatim (not substituted) | §7 — Tools | Unit |
| §9 — Tool Policy | EvidenceExtractRequest rejects out-of-set URLs | §7 — Tools | Unit |
| §9 — Evidence Ledger | total_cost_usd() reconciles against gateway response | §9 — Cost | Unit + Integration |
| §9D — Gateway Policy | Gateway revalidates domain allowlist independently | §8 — Gateway | Integration |
| §10 — Telemetry | RedisTimeSeries TS.CREATE idempotent with TS.ALTER fallback | §10 — Telemetry | Integration |
| §11 — Sprint 1 Gate | One-key setup: full run with only OPTIMUS_* env vars | §12 — Release Gate | E2E |

# 5. Mode and State Transition Tests

LLD reference: §4 Behavioral Governance, §4A Agent State Model. These tests prove the state machine is deterministic and that no path bypasses the mode enforcement primitives.

Unit Tests — assert_mutation_allowed()
- [ ] In Plan/Chat mode: calling assert_mutation_allowed() raises Code -32002 with message "mutation forbidden in Plan/Chat mode".
- [ ] In Agent mode before AwaitingApproval: assert_mutation_allowed() raises Code -32002.
- [ ] In Agent mode after approval granted: assert_mutation_allowed() returns None (no exception).
- [ ] Calling any mutation tool (write_file, shell_exec, shadow_apply) in Plan/Chat mode raises -32002 before any I/O occurs.

Unit Tests — State Transitions
- [ ] Idle → Planning: valid on any user request.
- [ ] PlanReady → Executing (direct): rejected with -32002; must pass through AwaitingApproval.
- [ ] AwaitingApproval → ChatOnly on timeout: confirmed after configurable timeout_ms expires.
- [ ] Failed → Planning: retry counter increments; failure context injected into next prompt payload.
- [ ] Failed → Terminated: at the configured finite work boundary, state transitions truthfully and a stop report is emitted. Pin the current three planning rounds, 30 minutes and two repeated failures separately.

Integration Tests — Mode Boundary
- [ ] Full Plan/Chat run: agent completes discussion and returns plan text; no file in working tree is modified; telemetry records 0 mutation calls.