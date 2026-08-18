# Plan 11.21 P11.5-FU-1 — Phoenix collector evidence (WP-3)

**Date:** 2026-08-18
**Branch:** `agent/cursor/plan-11-21-p11-5-fu-1-closure`
**Base:** `origin/main` `2fca470`
**Executor:** Cursor (this run is committed evidence; reviewer verification runs are not substituted)

This report records env-var **names**, marker outcomes, and `delivery_state` / `retry_count` / `final_disposition` enums. It does not record credentials, tokens, headers, arguments, endpoint URLs, or transcript bodies.

The earlier unrun record remains in [phoenix-disposition](plan-11-21-p11-5-fu-1-phoenix-disposition.md) and is not rewritten.

## Environment presence (names only)

| Name | Present for this run |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | set |
| `PHOENIX_TEST_BASE_URL` | set |
| `PHOENIX_TEST_PROJECT` | unset (fixture default `default`) |

No Docker, Phoenix, Gateway, or `optimus-trust` process was started or stopped. The operator-owned Phoenix container was left running.

## Command

`-o addopts=` is required so default `pyproject.toml` `not requires_phoenix` does not deselect the module. A deselection would be **unrun**, never a pass.

```powershell
uv run --frozen pytest -o addopts= -m requires_phoenix tests/integration/telemetry/test_phoenix_live.py -q --strict-markers
```

## Outcome

**2 passed** in 20.49s. Neither selector was skipped, deselected, or errored.

| Selector | Marker outcome | Observed enums |
|---|---|---|
| `test_live_phoenix_receives_real_otlp_batch_with_required_fields` | **passed** | ingress `delivery_state=delivered`, `retry_count=0`, `final_disposition=exported_to_otlp_collector`. No `cost_usd` / `gateway_usage` / `billing_units` on the ingress body. |
| `test_live_otlp_returned_failure_against_loopback_non_listening_port` | **passed** | `delivery_state=queued`, `retry_count=1`, `final_disposition=transient_export_failure_retry_budget_exhausted`. Loopback outage probe; not Phoenix REST evidence. |

Production path: `OpenTelemetryTraceExporter` with a real `OTLPSpanExporter` (no injected fake). `_emit_spans` was not modified in this package (no `src/` change).

## Task 8 watch — proven, not fixed

`test_live_phoenix_receives_real_otlp_batch_with_required_fields` asserts `root_a_real_trace_id != root_b_real_trace_id`. That **codifies the multi-root split as expected behavior**: two root events sharing one wire `trace_id` land in two different real Phoenix traces. This package does **not** close or fix that watch. Ownership remains **Plan 11.5 Task 8**.

## Unit proof retained

Unchanged selectors in `tests/unit/optimus_gateway/test_observability_export.py`:

| Selector | `delivery_state` |
|---|---|
| `test_exporter_reports_delivered_on_first_time_success` | `delivered` |
| `test_exporter_reports_queued_when_transient_failures_exhaust_retry_budget` | `queued` (raised transient) |
| `test_exporter_reports_failed_after_bounded_retry_on_permanent_failure` | `failed` (generic non-OTLP returned `FAILURE`) |
| `test_exporter_reports_not_configured_when_endpoint_missing_and_no_exporter_injected` | `not_configured` |
| `test_exporter_reports_queued_when_real_otlp_exporter_returns_failure` | `queued` (real `OTLPSpanExporter` type, returned `FAILURE`) |
| `test_exporter_reports_failed_when_real_otlp_exporter_raises` | `failed` (raising OTLP type) |
