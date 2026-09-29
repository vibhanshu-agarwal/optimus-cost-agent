# Plan 7 Architecture Review — Round 2 (post-revision)

**Reviewer role:** Senior Architect
**Plan:** `docs/superpowers/plans/2026-07-04-usage-accounting-evidence-ledger-observability.md`
**Prior review:** `docs/superpowers/reviews/2026-07-04-plan-7-architect-review.md`
**Verdict:** M1–M4 and both Low items are correctly resolved in substance. The M1 fix, however, was copy-pasted into three places and only wired correctly in one of them — this introduces two small but real, demonstrable bugs (a `NameError` in a new test and an unused import in production code that fails this repo's own configured ruff gate). Both are one-line fixes; neither is architectural.

---

## Confirmed resolved

- **M1 (stale provider-key list):** Both `tests/unit/telemetry/test_observability.py` and Task 7's final hygiene command now import and iterate `LOCAL_PROVIDER_KEY_NAMES` directly from `optimus.config.gateway` instead of a hand-typed 5-key subset. Scope wording updated to match ("Tests proving no local key from `LOCAL_PROVIDER_KEY_NAMES` is needed"). ✅ (see new findings below for a copy-paste side effect)
- **M2 (pricing fallback never triggered):** `UsageAccountingService.record_pricing_fallback_audit()` is now a real method that constructs and returns a `TelemetryEvent.pricing_fallback(...)` without touching `self.provider_ledger`. The new test `test_pricing_fallback_audit_signal_does_not_record_provider_usage` asserts `service.provider_ledger.entries == ()` and that the payload has no `cost_usd` key. This gives the fallback signal a real home on the accounting service rather than an orphaned constructor. ✅
- **M3 (unused `redis>=5` dependency):** `pyproject.toml`/`uv.lock` changes and the "Add Redis dependency" step are gone from Task 4 and the File Structure list. The Tech Stack line and a new inline note both state explicitly that the adapter deliberately never imports `redis` and that production injects a Redis-compatible client behind the `RedisTelemetryClient` Protocol. ✅
- **M4 (private cross-class attribute reach-through):** `ProviderUsageLedger._matching_entries()` is gone entirely; `entries_for_run()` now accepts `run_id: str | None = None` and is the single internal accessor used by `gateway_request_ids()`, `total_cost_usd()`, `total_billing_units()`, and `total_optimus_credits()`. `reconcile_evidence_provider_usage()` now calls `provider_ledger.gateway_request_ids(run_id=run_id)`, a public method, instead of reaching across the module boundary. ✅
- **Low (test_models.py label):** Task 1's Files list now says "Verify," not "Modify." ✅
- **Low (missing-field test coverage):** `test_provider_usage_requires_normalized_fields_for_persistence` is now parametrized over all four required fields (`service`, `native_unit`, `optimus_credits_debited`, `price_snapshot_id`), not just `native_unit`. ✅

---

## New findings (introduced by the M1 fix)

### N1 — the M1 fix was applied to three files but the import was only added to two of them

`LOCAL_PROVIDER_KEY_NAMES` is referenced in four places across the plan. I checked the import block accompanying each:

1. `tests/unit/telemetry/test_observability.py` (Task 6 Step 1) — imports `LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings` and uses it in two tests. Correct.
2. `src/optimus/telemetry/observability.py` (Task 6 Step 4) — imports `LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings`, but the name is **never referenced anywhere in the class body** (`GatewayObservabilityExporter.__init__`/`.export()` don't touch it). This is a dead, unused import in production code. This repo's own `pyproject.toml` runs Ruff with `select = ["E", "F", "I", "B"]` and does not ignore `F` — `F401` (unused import) would fail the lint gate this plan itself relies on for "diff hygiene."
3. `tests/integration/telemetry/test_usage_telemetry_flow.py` (Task 6 Step 5) — the test body does `for key in LOCAL_PROVIDER_KEY_NAMES: monkeypatch.delenv(key, raising=False)`, but the file's import block only has `from optimus.config.gateway import OptimusGatewaySettings` — **`LOCAL_PROVIDER_KEY_NAMES` is never imported in this file.** Running this test as written raises `NameError: name 'LOCAL_PROVIDER_KEY_NAMES' is not defined` on the first line of the test function. Task 6 Step 6's "Expected: PASS" for this file is not achievable as written.
4. Task 7 Step 5's one-liner `python -c "..."` command imports it inline correctly. Correct.

**Fix:** remove the unused import from `src/optimus/telemetry/observability.py` (point 2), and add `from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES` to `tests/integration/telemetry/test_usage_telemetry_flow.py`'s import block (point 3), matching what `test_observability.py` already does correctly.

---

## Recommendation

Two one-line fixes (drop an unused import, add a missing one) and this plan is ready to execute. Everything else from the first review — the substantive M1–M4 fixes and both Low items — is correctly and durably resolved; this is a copy-paste slip in mechanically propagating the same fix to three call sites, not a design problem.
