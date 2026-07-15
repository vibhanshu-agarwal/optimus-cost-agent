# Plan 9.95 Usage, Telemetry, and Evidence-Tooling Correctness — Implementation Evidence

**Implementation SHA:** `41a9cddddbacad766d8a432b7129a18d8976b54a` (Tasks 1-6 complete, before
this closure-report commit)

**Watched-path statement:** At `PLAN995_IMPLEMENTATION_SHA`, `git status --short` shows only
pre-existing operator-owned noise (`uv.lock`, `.cursor/`, `.kiro/`, `.zed/`,
`reports/.plan98-*`, `reports/plan98-*`, `reports/plan985-*`, `reports/plan99-*`,
`tools/run_plan98*_live_evidence.py`). No Plan 9.95 scope file is dirty or missing.

## Claim-to-Evidence Table

| DoD Claim | Named Evidence |
|---|---|
| Reviewer-agent and operator approved this implementation plan before code work began | Plan file `Status` field ("Approved by the reviewer-agent and operator on 2026-07-14") and `Design approval` field; verified at Task 0 (commit `0b5a686`) |
| Every valid Gateway-reported failed-attempt usage envelope is aggregated exactly once | `test_reported_transient_failure_then_success_aggregates_both_wire_attempts`, `test_reported_permanent_failure_is_charged_before_gateway_stop`, `test_reported_failure_then_success_charges_both_attempts` (transport integration) |
| Normalized reported failed-attempt usage persists with stable settled-turn/wire-attempt IDs | `test_fitting_context_planning_retries_gateway_without_extra_settled_turn` (request_id sequence `planning:1:1`, `:1:2`, `:1:3`), transport integration (`:1:1`, `:1:2`) |
| An attempt without valid usage stops before another retry with PLANNING_GATEWAY_COST_UNKNOWN | `test_unknown_transport_cost_stops_before_retry`, `test_unknown_cost_stops_after_one_request` (transport integration), `test_unexpected_attempt_exception_logs_type_only_and_stops_cost_unknown` |
| Reported failed-attempt cost participates in the budget cap before another wire request | `test_reported_failed_attempt_at_budget_cap_stops_before_retry` |
| total_cost_usd is never presented as complete when any wire-attempt cost is unknown | `test_unknown_planning_cost_terminates_without_plan_or_usage_row` (runner), `test_unknown_cost_emits_end_turn_without_permission_request` (ACP) |
| Non-alphabetical multi-file telemetry preserves identity/hash/byte-count association | `test_non_alphabetical_multi_file_read_telemetry_preserves_association`, `test_non_alphabetical_read_telemetry_preserves_association_in_evidence_summary` (downstream) |
| ledger_digest() has fixed canonicalization, fixed vector, empty-ledger rejection, and report-order domain | `test_ledger_digest_has_fixed_canonical_vector`, `test_ledger_digest_preserves_record_and_list_order`, `test_ledger_digest_rejects_empty_ledger`, `test_plan988_extraction_keeps_all_eight_records_in_report_order` |
| Historical 9122... value retained as unpinned; pinned digest recorded with durable command | `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md` ceremony section (commit `24318af`) |
| FU-4B remains accepted-open and --require fu4b still fails | Verifier output: `fu4b claim missing` (exit 1) |
| Real urllib/local-HTTP integration passes without being mislabeled as a real Gateway tier | `tests/integration/gateway/test_failed_usage_transport_flow.py` — no `requires_gateway` marker |
| Plans 9.96 and 9.97 remain tracked-not-yet-scheduled with no implementation-plan files | Roadmap section headers unchanged; `git ls-files` shows no `plan-9-96-*` or `plan-9-97-*` implementation files |
| Plan 9.97 still says it must not absorb or be absorbed by Plan 11 | Roadmap line 501: verbatim sentence preserved |
| Full default tests pass; aggregate production coverage >= 80% | 959 passed; 85.20% coverage |
| uv run ruff check . and git diff --check are clean | Both exit 0 |

## Terminal Matrix — Observed Outputs

| Last wire outcome | Stop reason | cost_complete | total_cost_usd | Gateway attempts |
|---|---|---|---|---|
| Reported transient failure then success | None (settled) | True | 0.003 | 2 |
| Reported permanent failure | PLANNING_GATEWAY_FAILURE | True | 0.001 | 1 |
| Failure without valid usage | PLANNING_GATEWAY_COST_UNKNOWN | False | 0 | 1 |
| Reported failure then unknown | PLANNING_GATEWAY_COST_UNKNOWN | False | 0.001 (lower bound) | 2 |
| Reported failure at budget cap | PLANNING_BUDGET_EXHAUSTED | True | 0.005 | 1 |
| Unexpected non-Gateway exception | PLANNING_GATEWAY_COST_UNKNOWN | False | 0 | 1 |

## Local HTTP Integration

```bash
uv run pytest tests/integration/gateway/test_failed_usage_transport_flow.py -v
```

Result: 2 passed. Uses `ThreadingHTTPServer` on `127.0.0.1` with real `GatewayClient` +
`UrllibGatewayTransport`. No monkeypatch, no fake transport, no `requires_gateway` marker.
Does not claim real-provider behavior.

## Fixed-Vector and Ceremony Digest

- Fixed vector: `[{"a":"alpha","z":2},{"a":1}]` →
  `083d33790eef3a46cebde05f11206acfe01598a08bc3ab610d81c9fafe6bf2ec`
- Ceremony digest (8 P9.88-FU4B records):
  `e265065147f505e56ed1ad8d60571f9d1f212fb8f8d192ec407121c0e7ac4195`

Durable verifier command:

```bash
uv run python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --check-fu4b-ledger-status exhausted \
  --check-fu4b-ledger-digest e265065147f505e56ed1ad8d60571f9d1f212fb8f8d192ec407121c0e7ac4195 \
  --max-completed-replan-attempts 3
```

Result: PASS. `--require fu4b` correctly FAILS with `fu4b claim missing`.

## Pre-Existing fu4a/fu5 Implementation-Drift Disclosure

`--require fu4a` and `--require fu5` independently fail with `implementation drift after
4bf20fffd9b067afa4db34d5ae021aca665f3acb` (fu4a) and `implementation drift after
bfcea0dab056bd42f793851ae042a214b24d4b64` (fu5). This is caused by 34 files/1135 lines of
unrelated `src/optimus` changes (Plan 9.9 and others) that landed between those pinned SHAs
and origin/main before Plan 9.95's branch-cut. Re-establishing that freshness requires
re-capturing live evidence, which is out of scope (Global Constraint 1, Explicit Exceptions)
and tracked separately in the roadmap as a backlog item.

## No Real Provider Failure Provoked

No deliberate billable provider failure was provoked. The local HTTP integration uses a
standard-library `ThreadingHTTPServer` returning deterministic canned responses. Existing live
Gateway tests remain regression coverage; this plan does not add or claim live-provider evidence
for injected error cases (Global Constraint 16).

## Redaction Scan and No-Secret Statement

```bash
rg -n "(sk-[A-Za-z0-9]|Bearer [A-Za-z0-9]|OPTIMUS_API_KEY=|ANTHROPIC_API_KEY=|OPENAI_API_KEY=)" \
  reports/plan-9-95-usage-telemetry-evidence.md \
  reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
```

Result: this regex is broad enough to coincidentally match ordinary English phrasing — for
example, any word beginning "task-" followed by a letter. All matches were manually inspected;
none are real credential or key values. No actual secret appears in either report.

The string `"test-key-local"` in the integration test is a non-secret placeholder used only
against a local loopback server.

## Final Gate Outputs

- **pytest -q:** 959 passed, 2 skipped, 22 deselected
- **Coverage:** 85.20% (threshold 80%)
- **Ruff:** All checks passed
- **git diff --check:** Clean
