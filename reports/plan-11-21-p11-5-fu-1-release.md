# Plan 11.21 P11.5-FU-1 — release / close-out evidence (WP-3)

**Date:** 2026-08-18
**Branch:** `agent/cursor/plan-11-21-p11-5-fu-1-closure`
**Base:** `origin/main` `2fca470`

**Pool decision:** P11.5-FU-1 is **Closed**. Plan 11.21. No `src/` change in this package (fix merged in PR #164).

This report does not record credentials, tokens, headers, arguments, endpoint URLs, or transcript bodies. The 2026-08-18 **unrun** Phoenix record is preserved in [phoenix-disposition](plan-11-21-p11-5-fu-1-phoenix-disposition.md).

## Outcome

| Item | Status | Reason |
|---|---|---|
| `P11.5-FU-1` | **Closed** | Task 1/2 real-type returned-`FAILURE` unit proof green; four-state counterexamples retained; selected Phoenix collector path **passed** (2 passed); coverage ≥ 80%; Ruff/diff hygiene clean. |
| Task 8 independent-root grouping | **Not closed** | Live test **proves** the split (`root_a_real_trace_id != root_b_real_trace_id`) as expected behavior. Ownership remains Plan 11.5 Task 8. This FU does not claim that watch is fixed. |

## Claim-to-evidence

| Claim | Required evidence | Result |
|---|---|---|
| P11.5-FU-1 has independent custody | Pool index and detail agree | Both **Closed**. Hygiene `_lane_state` accepts scheduled/closed and still requires `_AlwaysTransientSpanExporter`, `Task 4`, and `Task 8` in the detail. |
| Real SDK outcome, not a raised-only fake, reaches `queued` | Task 1/2 real-`OTLPSpanExporter` returned-`FAILURE` selector | `test_exporter_reports_queued_when_real_otlp_exporter_returns_failure` — unit **passed** |
| Generic permanent rejection remains `failed` | `_AlwaysPermanentlyFailingSpanExporter` | `test_exporter_reports_failed_after_bounded_retry_on_permanent_failure` — unit **passed** |
| All four states remain meaningful | retained unit selectors | See four-state table below |
| Export failure does not affect model/mutation/cost accounting | result-field assertions | No `cost_usd` / `gateway_usage` / `billing_units` on `GatewayTraceExportResult` |
| Real dependency claim is not faked | Task 3 `requires_phoenix` | **passed** — [phoenix evidence](plan-11-21-p11-5-fu-1-phoenix-evidence.md). Not inherited from a reviewer terminal. |
| Task 8 trace grouping is not silently folded in | named exclusion | Proven as expected split; still Plan 11.5 Task 8. `_emit_spans` untouched (no `src/` in this package). |
| No frozen/doc/safety regression | Task 4 audit, coverage, Ruff, digest | Frozen Plan 11.5/spec and Plan 11.21 not edited. Parent slice phrase updated only. |

## Four states (unit proof)

| Selector | Observed `delivery_state` |
|---|---|
| `test_exporter_reports_delivered_on_first_time_success` | `delivered` |
| `test_exporter_reports_queued_when_transient_failures_exhaust_retry_budget` | `queued` (raised `TransientTraceExportError`) |
| `test_exporter_reports_failed_after_bounded_retry_on_permanent_failure` | `failed` (generic non-OTLP returned `FAILURE`) |
| `test_exporter_reports_not_configured_when_endpoint_missing_and_no_exporter_injected` | `not_configured` |
| `test_exporter_reports_queued_when_real_otlp_exporter_returns_failure` | `queued` (real `OTLPSpanExporter` type, returned `FAILURE`) |
| `test_exporter_reports_failed_when_real_otlp_exporter_raises` | `failed` (raising OTLP type) |

## Phoenix collector (this package)

Exact command and 2-passed outcome: [phoenix evidence](plan-11-21-p11-5-fu-1-phoenix-evidence.md). Env-var **names** `OTEL_EXPORTER_OTLP_ENDPOINT` and `PHOENIX_TEST_BASE_URL` were set; values are not recorded here.

Default `coverage run -m pytest` still deselects `requires_phoenix`. That default-suite deselection is **unrun of the coverage command's live marker**, not a contradiction of the dedicated live run above.

## Freshness audit

```powershell
git grep -n "P11\.5-FU-1\|OTLPSpanExporter\|SpanExportResult\.FAILURE\|transient_export_failure_retry_budget_exhausted\|permanent_export_failure\|Plan 11\.21" -- README.md docs reports
```

| Document | Action |
|---|---|
| Living pool Feature slices row for `P11-FEAT-GATEWAY-COST-OBS` | Phrase only: `P11.5-FU-1` Closed via Plan 11.21. Status remains Closed. `P11.5-FU-2` untouched. |
| Living pool P11.5-FU-1 index + detail | Both Closed. Task 8 watch named as remaining Plan 11.5 Task 8. |
| Historical [phoenix-disposition](plan-11-21-p11-5-fu-1-phoenix-disposition.md) | Preserved; forward pointer only |
| `README.md`, phase-1 roadmap, Plan 11 charter, `docs/runbooks/local-live-dependencies.md` | No live-status P11.5-FU-1 hits requiring edit |
| Frozen Plan 11.5 / spec / Plan 11.21 | Immutable. Not edited |
| Task 0 baseline report | Historical. Not rewritten |

## Frozen Plan 11.5 digest

From committed blob, not the worktree file:

```powershell
git cat-file blob HEAD:docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md
```

Python `hashlib.sha256` of those bytes: `0BAC146974984EA663B7A59802A1B5ED74F90EB682F855C0E05AAAB5B9A2C396` (58248 bytes). Matches the pool hygiene `PROTECTED_BLOB_SHA256` pin.

## Fitness

Recorded after Task 4 Step 3 on this branch. Default `coverage run -m pytest` deselects live markers including `requires_phoenix`; that deselection is **unrun** for those markers and is not a substitute for the dedicated live command above.

| Command | Result |
|---|---|
| Dedicated `requires_phoenix` (this package) | **2 passed** in 20.49s |
| `uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py tests/unit/optimus_gateway/test_observability_export.py -q` | **81 passed** |
| `uv run --frozen coverage run -m pytest` | **3231 passed**, 28 skipped, **111 deselected** |
| `uv run --frozen coverage report --fail-under=80` | **TOTAL 82%** |
| `uv run --frozen ruff check .` | All checks passed |
| `git diff --check` | clean |
| Frozen Plan 11.5 blob digest | `0BAC146974984EA663B7A59802A1B5ED74F90EB682F855C0E05AAAB5B9A2C396` |
