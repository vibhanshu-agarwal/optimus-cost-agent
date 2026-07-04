# Plan 7 Architecture Review — Usage Accounting, Evidence Ledger, and Observability

**Reviewer role:** Senior Architect
**Plan under review:** `docs/superpowers/plans/2026-07-04-usage-accounting-evidence-ledger-observability.md`
**Verified against:** current `src/optimus/gateway/*` (models.py, client.py, errors.py), `src/optimus/config/gateway.py`, `src/optimus/evidence/*` (ledger.py, models.py), `src/optimus/tools/policy.py`, the actual test suite under `tests/unit/gateway/test_models.py`, and the Plan 6.5 architect reviews for cross-plan consistency. I traced the redaction logic by hand and then re-executed the exact function against the plan's own test fixtures to confirm it, the same way the Plan 6.5 confusable-detector claim was verified.
**Verdict:** No blockers. This is a solid, well-grounded plan — every source-anchor claim about the current codebase checks out, the redaction fix is real (verified by execution), and the pricing-fallback safety property holds structurally. Four Medium findings are worth fixing before or during execution; none of them require re-architecting anything.

---

## Confirmed correct (verified against real code, not just the plan text)

- `GatewayUsage` in `src/optimus/gateway/models.py` genuinely lacks `service`, `native_unit`, `optimus_credits_debited`, `model`, `model_version`, and `price_snapshot_id` today — Task 1 is a real, additive, backward-compatible extension. All new fields default to `None`, so `tests/unit/gateway/test_models.py`'s existing equality assertions (which construct `GatewayUsage` without these fields) keep passing unchanged.
- `EvidenceLedgerEntry.from_gateway_usage()` and `EvidenceLedger.total_cost_usd(*, run_id=None)` already exist in `src/optimus/evidence/ledger.py` with signatures that match the plan's tests exactly, including keyword-only args. `EvidenceLedger.gateway_request_ids()` genuinely does not exist yet, so Task 3's addition is correctly scoped as new, not duplicated.
- `GatewayClient` already has `post_tool_json()` as a sibling pattern (path-prefix check, `validate_trusted_gateway()`, same `GatewayRequest` shape); Task 6's `post_observability_json()` is a faithful, idiomatic extension of that existing pattern, not an invented shape.
- **Redaction fix, verified by execution, not just reading:** I extracted the plan's exact `_redact()` function and ran it against the plan's own `test_secret_values_are_redacted_from_event_payload` fixture. Result: `secret-token`, `nested-token`, and `result-token` are all absent from the serialized line; `authorization_outcome: "ALLOW"` survives untouched. The mechanism is sound: `_EXACT_SECRET_KEYS` catches the literal header key `"authorization"` (and only that key, not `"authorization_outcome"`, because the check is exact-set membership, not substring), while `_SECRET_KEY_PARTS` catches substring matches like `api_key`/`token`/`secret` in other key names, and the string-level bearer regex catches secrets embedded in free-text values like `result_summary`. This is exactly the nuance the revision claims to have fixed, and it holds.
- Pricing-fallback safety is structural, not just asserted: `TelemetryEvent.pricing_fallback()`'s payload has no `cost_usd` key at all (confirmed in the event constructor), and the only way to construct a `ProviderUsage` anywhere in the plan is `ProviderUsage.from_gateway_usage()`, which requires gateway-sourced fields. There is no code path in any task that could route a pricing-fallback signal into `ProviderUsage` or into `cost_usd`. The "must not populate ProviderUsage or overwrite cost_usd" claim is true by construction.
- The `UsageAccountingAuditSignal` reference is gone — confirmed by grep across `docs/superpowers`, zero remaining hits.
- Plan 6.5 sequencing is stated consistently in two places (Dependency Notes and Execution Handoff): Plan 6.5 is "planning-approved" but its *implementation* must land first because Plan 7 only serializes guardrail/MCP event field names, not their semantics. This matches the roadmap's existing Plan 6.5-before-Plan-7 ordering.
- Every JSONL event kind promised in Scope (`model_call`, `tool_call`, `gateway_usage`, `guardrail_audit`, `reconciliation`, `error`, `pricing_fallback`) has both a constructor and a test exercising its shape.

---

## Medium

### M1. Task 7's "one-key observability hygiene" check hardcodes a stale, incomplete key list

Task 7 Step 5 checks a hand-typed tuple: `('LANGSMITH_API_KEY','TAVILY_API_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','GLM_API_KEY')`. The actual canonical source, `optimus.config.gateway.LOCAL_PROVIDER_KEY_NAMES`, has eight entries — it also includes `ANTHROPIC_API_KEY`, `LANGCHAIN_API_KEY`, and `ZHIPUAI_API_KEY`. As written, the hygiene check would report `FOUND=` (pass) even if a local `ANTHROPIC_API_KEY` were set. Plan 6.5's equivalent check got this right by importing the frozenset directly:
```python
python -c "import os; from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES; found=[k for k in LOCAL_PROVIDER_KEY_NAMES if os.environ.get(k)]; ..."
```
**Fix:** use the same import-based pattern instead of a duplicated literal list.

### M2. "Pricing snapshot fallback audit signals" is scoped as delivered, but nothing triggers it

Scope lists "Pricing snapshot fallback audit signals for local informational fallback paths" as in-scope. What's actually implemented is an isolated, well-tested event constructor (`TelemetryEvent.pricing_fallback()`) — there is no task anywhere that decides *when* a pricing fallback occurs and calls it. `UsageAccountingService.record_gateway_usage()` only ever raises `ValueError` on missing normalized fields; it never falls back to a local price snapshot and never emits this event. That may be entirely correct given this repo's "never estimate cost locally when gateway usage exists" philosophy (AGENTS.md) — but if so, the Scope bullet should say "event shape only, no local fallback path is implemented in this plan" rather than reading as a delivered fallback mechanism. If a real caller is expected later, name it explicitly (e.g., "Plan 8 wires the trigger").

### M3. `redis>=5` is added as a runtime dependency but is never imported anywhere in the plan

Task 4's Redis surface is entirely a `Protocol` (`RedisTelemetryClient`) satisfied by a hand-written `FakeRedis` in tests. I grepped the whole plan for `redis` usage: `import redis` never appears in any implementation step. There is no factory method (e.g. `RedisTelemetryAdapter.for_production(url)`) that actually constructs a real `redis.asyncio.Redis` instance. This is consistent with "Out of Scope: real Redis server E2E setup," but it does mean the plan asks to add a hard runtime dependency that the shipped code never touches. Either add a minimal production constructor that genuinely uses `redis>=5`, or note explicitly that the dependency is being pre-provisioned for a later plan.

### M4. `reconcile_evidence_provider_usage()` reaches into a private method across a class boundary

`src/optimus/usage/accounting.py`'s free function calls `provider_ledger._matching_entries(run_id)` — a leading-underscore method of `ProviderUsageLedger` accessed from a different module. `ProviderUsageLedger` already exposes `entries` and `entries_for_run()` publicly; there's no need to reach past them. This is the same shape of issue as M3 in the Plan 6.5 round-1 review (`self.ingestion_guard._scanner`), which was fixed there by adding a public method. Worth the same treatment here: either use `entries_for_run()` / `entries` directly, or add a public `matching_entries()` alongside the private one.

---

## Low / polish

- Two independent secret-redaction implementations now exist: `optimus.guardrails.pre_tool._redact_secret_values` (regex over a flattened command/action string — bearer, password, api_key, token) and the new `optimus.telemetry.events._redact` (recursive, key-and-value-based, adds `secret`/`credential`/`optimus_api_key`). Different data shapes justify different mechanics, but the keyword coverage should be kept in sync deliberately rather than by accident — consider a shared constant list in a common module.
- `_EXACT_SECRET_KEYS` matches are naming-format-brittle: a key spelled `Auth-Header` or `auth-token` (hyphen instead of underscore) would not hit the exact-match set and would only be caught if its *value* happens to look like a bearer string. Not a bug against any current test, just a heads-up for future key names.
- Task 1's "Files:" list marks `tests/unit/gateway/test_models.py` as "Modify," but no step changes it — I confirmed by reading the file that its existing assertions are unaffected by the new optional fields. Label it "Verify," matching the convention Task 7 already uses for verification-only files.
- `ProviderUsage.from_gateway_usage()`'s missing-field guard checks four fields (`service`, `native_unit`, `optimus_credits_debited`, `price_snapshot_id`), but the test suite only exercises the `native_unit` case. Consider parametrizing across all four, mirroring Task 1's own parametrized absence test for `GatewayUsage`.

---

## Recommendation

Ship it with M1–M4 folded in during implementation — none of them change the plan's architecture or require new tasks, they're all same-task tightening. No blockers found; the redaction and pricing-fallback safety claims specifically called out as fixed in this revision both check out under direct execution, not just re-reading.
