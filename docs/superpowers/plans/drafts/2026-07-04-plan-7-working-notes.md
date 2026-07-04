# Plan 7 Working Notes

These notes preserve the Plan 7 scoping discovered before switching away from the Plan 6 branch.

## Intended Plan File

`docs/superpowers/plans/2026-07-04-usage-accounting-evidence-ledger-observability.md`

## Scope Boundary

Plan 7 should stay focused on usage accounting, provider usage, evidence-ledger reconciliation, Redis/JSONL telemetry, and trace export.

Do not fold Plan 6.5 guardrail hardening into Plan 7. Plan 7 may record guardrail and MCP audit events emitted by Plan 5, Plan 6, and Plan 6.5, but it should not implement those guardrails.

## Source Anchors

- Roadmap Plan 7: `GatewayUsage`, `ProviderUsage`, usage accounting service, Redis HASH/TimeSeries adapter boundaries, JSONL telemetry event schema, and reconciliation methods.
- Architecture sections 4, 5, and 12: local storage boundaries, request-level cost attribution, gateway usage envelope, and trace observability.
- LLD sections 9E, 10, 10A, and 11A:
  - `EvidenceLedger` remains the evidence/audit trail.
  - `GatewayUsage` remains the wire-level envelope copied from gateway responses.
  - `ProviderUsage` is the canonical persisted normalized cost ledger and is a strict superset of `GatewayUsage`.
  - Evidence and cost ledgers join on `gateway_request_id`.
  - RedisTimeSeries keys follow `telemetry:run:{run_id}:metrics:{metric_name}`.
  - Run metadata HASH keys follow `run:{run_id}:metadata` with 30-day TTL.
  - Local agent sends observability events to Gateway `/v1/observability/traces`; Gateway owns LangSmith credentials.
- Test Strategy section 8 and 8A:
  - `EvidenceLedger.total_cost_usd()` reconciles against the sum of `GatewayUsage.cost_usd`.
  - `EvidenceLedger.total_billing_units()` reconciles against the sum of `GatewayUsage.billing_units`.
  - Missing or malformed gateway usage fields fail closed.
  - Coverage target remains 80% aggregate Python production-code coverage, with safety-critical accounting modules trending higher.

## Current Code Baseline Observed

- `src/optimus/gateway/models.py` already defines `GatewayUsage` with `gateway_request_id`, `provider`, `provider_request_id`, `cache_hit`, `billing_units`, and `cost_usd`.
- `src/optimus/evidence/ledger.py` already defines immutable `EvidenceLedgerEntry` and `EvidenceLedger` totals for credits, billing units, and cost.
- `src/optimus/evidence/acquisition.py` already records gateway usage for web search/extract, including parse failures when `GatewayResponseError.gateway_usage` is present.
- Plan 6 branch currently adds guardrail audit surfaces, but Plan 7 should not depend on Plan 6.5 implementation details beyond accepting audit events as telemetry input.

## Expected Plan 7 Deliverables

- Extend or wrap `GatewayUsage` to include model/version, service, native unit, price snapshot id, and normalized Optimus credit fields without local provider-key use.
- Add `ProviderUsage` and `ProviderUsageLedger` as the persisted normalized cost ledger.
- Add a `UsageAccountingService` that records provider usage from gateway response fields and refuses to estimate missing source-of-truth values.
- Add pricing snapshot fallback audit signals only for fallback metadata paths described by the LLD/Test Strategy; do not use fallback pricing to overwrite gateway-provided `cost_usd`.
- Add Redis adapter boundaries for idempotent `TS.CREATE`/`TS.ALTER`, `TS.ADD`, and run metadata `HSET`/`EXPIRE`.
- Add JSONL telemetry schema and append-only writer for model calls, tool calls, errors, gateway usage, reconciliation results, and guardrail audit events.
- Add Gateway observability export client for `/v1/observability/traces`; no local `LANGSMITH_API_KEY`.
- Add reconciliation tests joining `EvidenceLedgerEntry` and `ProviderUsage` on `gateway_request_id`.

## Plan 6.5 Dependency Note For Plan 7

Plan 6.5 should run before Plan 7 so guardrail/MCP trust events have stable fields. Plan 7 only persists or exports those events; it does not implement:

- `scan_manifest_path` missing-path handling.
- Git bypass hardening for `GIT_CONFIG_*`, aliases, or env-dict scanning.
- Unicode TR39/confusables scanner upgrades.
- MCP runtime registry bootstrap or real loader/descriptor wiring.
