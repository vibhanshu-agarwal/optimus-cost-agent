# Plan 11.21 P11.5-FU-1 — release / close-out evidence

**Date:** 2026-08-18
**Branch:** `agent/cursor/plan-11-21-otlp-failure-delivery-state`
**HEAD at Task 4 start:** `9a8971a` (`fix: queue returned OTLP export failures`)

**Pool decision:** P11.5-FU-1 remains **Promoted** to [Plan 11.21](../docs/superpowers/plans/2026-08-17-plan-11-21-p11-5-fu-1-otlp-failure-delivery-state.md). **Not Closed.**

No Docker, Phoenix, Gateway, or `optimus-trust` process was started. This report records claim-to-evidence, unrun live tiers, fitness gates, and the frozen Plan 11.5 committed-blob digest. It does not record credentials, tokens, headers, arguments, endpoint URLs, or transcript bodies.

## Outcome

| Item | Status | Reason |
|---|---|---|
| `P11.5-FU-1` | **Promoted -> Plan 11.21** (unresolved) | Task 1/2 real-type returned-`FAILURE` unit proof is green. Selected Phoenix collector delivered-path is **unrun**. Closing on a skipped/deselected/unrun live tier is forbidden. |
| Task 8 independent-root grouping | Named exclusion | `_emit_spans` unchanged. Watch lives in the unrun Phoenix delivered-path selector. Not this FU's closure evidence. |

## Claim-to-evidence

| Claim | Required evidence | Result |
|---|---|---|
| P11.5-FU-1 has independent custody | Task 0 pool RED/green and Plan 11.21 link | Index and detail status are `Promoted -> [Plan 11.21](2026-08-17-plan-11-21-p11-5-fu-1-otlp-failure-delivery-state.md)`. Hygiene `test_plan_1121_keeps_p115_fu1_separate_scheduled_custody` requires Promoted (not Closed) and rejects Plan 11.5 Task 4 / raising-transient / Task 8 as closure. |
| Real SDK outcome, not a raised-only fake, reaches `queued` | Task 1/2 real-`OTLPSpanExporter` type with `export() -> FAILURE` selector | `tests/unit/optimus_gateway/test_observability_export.py::test_exporter_reports_queued_when_real_otlp_exporter_returns_failure`. `ReturnedFailureOtlpExporter(OTLPSpanExporter)` returns `SpanExportResult.FAILURE` without raising. After Task 2 GREEN (`9a8971a`): `delivery_state=queued`, `retry_count=1`, `final_disposition=transient_export_failure_retry_budget_exhausted`. |
| Generic permanent rejection remains `failed` | Task 1/2 `_AlwaysPermanentlyFailingSpanExporter` assertion | `test_exporter_reports_failed_after_bounded_retry_on_permanent_failure`: non-OTLP returned `FAILURE` stays `failed` / `permanent_export_failure`. |
| All four states remain meaningful | Task 1/2 success, raised transient, generic permanent, missing endpoint, and real-return tests | See four-state table below. |
| Export failure does not affect model/mutation/cost accounting | Existing result-field assertions | `GatewayTraceExportResult` fields remain `trace_batch_id`, `trace_ids`, `delivery_state`, `retry_count`, `final_disposition`. Tests assert no `cost_usd`, `gateway_usage`, or `billing_units`. |
| Real dependency claim is not faked | Task 3 `requires_phoenix` result or explicit unrun disposition | Phoenix collector delivered-path **unrun**. See Unrun section and [phoenix disposition](plan-11-21-p11-5-fu-1-phoenix-disposition.md). |
| Task 8 trace grouping is not silently folded in | Named exclusion and unchanged `_emit_spans` | Task 3 recorded `_emit_spans` diff empty. Task 8 assertion remains inside the unrun Phoenix REST selector. |
| No frozen/doc/safety regression | Task 4 freshness audit, coverage, Ruff, diff check, committed-blob digest | Frozen Plan 11.5/spec and Plan 11.21 were not edited. README, roadmap, charter, and `docs/runbooks/local-live-dependencies.md` have no P11.5-FU-1 live-status hits. Fitness recorded below. |

## Four states (unit proof)

Selectors in `tests/unit/optimus_gateway/test_observability_export.py`:

| Selector | Observed `delivery_state` |
|---|---|
| `test_exporter_reports_delivered_on_first_time_success` | `delivered` |
| `test_exporter_reports_queued_when_transient_failures_exhaust_retry_budget` | `queued` (raised `TransientTraceExportError`) |
| `test_exporter_reports_failed_after_bounded_retry_on_permanent_failure` | `failed` (generic non-OTLP returned `FAILURE`) |
| `test_exporter_reports_not_configured_when_endpoint_missing_and_no_exporter_injected` | `not_configured` |
| `test_exporter_not_configured_is_never_a_silent_successful_no_op` | never `delivered` |
| `test_exporter_reports_queued_when_real_otlp_exporter_returns_failure` | `queued` (real `OTLPSpanExporter` type, returned `FAILURE`) |

Production classification (Task 2, `src/optimus_gateway/observability.py`): after the raised-transient branch, a returned `SpanExportResult.FAILURE` is retryable only when `isinstance(self._delegate, OTLPSpanExporter)`. Public mapping is unchanged: succeeded → `delivered`, exhausted_transient → `queued`, otherwise `failed`; missing endpoint → `not_configured`.

## Unrun Phoenix collector

Exact Task 3 attempt (values not printed): `OTEL_EXPORTER_OTLP_ENDPOINT` unset, `PHOENIX_TEST_BASE_URL` unset, `PHOENIX_TEST_PROJECT` unset.

```powershell
uv run --frozen pytest -o addopts= -m requires_phoenix tests/integration/telemetry/test_phoenix_live.py -q --strict-markers
```

Outcome: **1 passed, 1 error**. Named split:

| Selector | Marker outcome | Disposition |
|---|---|---|
| `test_live_phoenix_receives_real_otlp_batch_with_required_fields` | ERROR at fixture setup | **unrun** — `PHOENIX_TEST_BASE_URL` unset (fail-closed). `OTEL_EXPORTER_OTLP_ENDPOINT` also unset. Task 8 watch lives here, so it is unrun too. |
| `test_live_otlp_returned_failure_against_loopback_non_listening_port` | passed | Loopback collector-outage probe. Records `queued` / `retry_count=1` / `transient_export_failure_retry_budget_exhausted`. Not Phoenix REST/collector evidence. |

Default addopts include `not requires_phoenix`. `coverage run -m pytest` is the default (non-live) suite. A skip/deselection is **unrun**, never a pass. This close-out does **not** claim `requires_phoenix` passed.

Operator owns machine-state. This task did not start Phoenix/Docker/`optimus-trust`.

## Task 8 exclusion

The independent-root grouping watch remains a separate assertion inside `test_live_phoenix_receives_real_otlp_batch_with_required_fields`. That selector was unrun because Phoenix env was unset. `_emit_spans` was not modified in Tasks 1–4. Task 8 is **not** this FU's closure evidence.

## Freshness audit

Census command (Windows; `rg` unavailable):

```powershell
git grep -n "P11\.5-FU-1\|OTLPSpanExporter\|SpanExportResult\.FAILURE\|transient_export_failure_retry_budget_exhausted\|permanent_export_failure\|Plan 11\.21" -- README.md docs reports
```

| Document | Action |
|---|---|
| Living pool Feature slices row for `P11-FEAT-GATEWAY-COST-OBS` | Updated close-time ``P11.5-FU-1` open`` so it does not claim unscheduled Open. Now: Promoted to Plan 11.21, Phoenix collector unrun. `P11.5-FU-2` remains closed via Plan 11.6. Feature identity stays Closed. |
| Living pool P11.5-FU-1 index + detail | Status remains Promoted (not Closed). Detail Status prose and evidence column record the unrun Phoenix collector residual and link this report plus the Phoenix disposition. |
| `README.md`, phase-1 roadmap, Plan 11 charter, `docs/runbooks/local-live-dependencies.md` | No P11.5-FU-1 hits. README four-state `TraceDeliveryState` prose remains accurate. Not edited. |
| Frozen Plan 11.5 implementation plan and design spec | Immutable. Not edited. Digest from committed blob below. |
| Frozen Plan 11.21 | Immutable. Checkboxes not set. |
| Historical Plan 11.6, Plan 11.8 status-normalization plan/spec, Task 0 baseline report | Historical. Not rewritten. |

## Frozen Plan 11.5 digest

Computed from the committed blob, not the worktree file:

```powershell
git cat-file blob HEAD:docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md
```

Python `hashlib.sha256` of those bytes:

`0BAC146974984EA663B7A59802A1B5ED74F90EB682F855C0E05AAAB5B9A2C396` (58248 bytes)

Matches the pool hygiene `PROTECTED_BLOB_SHA256` pin.

## Fitness

Recorded after this session's gate commands. Default `coverage run -m pytest` uses addopts that exclude live markers (`requires_phoenix`, `requires_redis`, `requires_gateway`, `requires_mcp_http`, `requires_mcp_stdio`, `e2e`, `requires_live_gateway`, `requires_os_keyring`, `requires_os_keyring_write`, `requires_acpx`, `requires_zed`, `requires_windows_desktop`, `evidence_investigation`, `requires_evidence_handoff_postgres`, `requires_evidence_handoff_service`, `requires_real_agents`). Those live tiers are **unrun** here, not passed. This close-out does **not** claim `requires_phoenix` passed.

| Command | Result |
|---|---|
| `uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py tests/unit/optimus_gateway/test_observability_export.py -q` | **79 passed** in 1.19s |
| `uv run --frozen coverage run -m pytest` | **3223 passed**, 28 skipped, **111 deselected**, 1 warning in 123.55s (exit 0). Deselected = default live-marker exclusion, including `requires_phoenix`. |
| `uv run --frozen coverage report --fail-under=80` | **TOTAL 82%** (19002 stmts, 2891 miss, 5288 branch, 936 partial). Fail-under=80 passed. |
| `uv run --frozen ruff check .` | All checks passed |
| `git diff --check` | clean |

## Residual (P11.5-FU-1 stays Promoted)

Exact residual retained on the pool entry:

- Real Phoenix collector delivered-path evidence is **unrun** because `PHOENIX_TEST_BASE_URL` and `OTEL_EXPORTER_OTLP_ENDPOINT` were unset.
- Task 1/2 hold the real-type returned-FAILURE unit proof (`queued` / `transient_export_failure_retry_budget_exhausted`).
- The loopback outage probe passed and is not a live Phoenix collector.
- Task 8 multi-root grouping remains a named exclusion and is not this FU's closure evidence.
