# Plan 11.21 P11.5-FU-1 — Phoenix-tier disposition

**Status:** Real Phoenix collector path **unrun**. P11.5-FU-1 remains **Promoted** to Plan 11.21 and is not Closed.

**Date:** 2026-08-18

No Docker, Phoenix, Gateway, or `optimus-trust` process was started. Pytest was attempted against the environment already present. This report records env-var presence (names only), marker outcomes, and `delivery_state` / `retry_count` / `final_disposition` enums. It does not record credentials, tokens, headers, arguments, endpoint URLs, or transcript bodies.

## Checkout

| Ref | Value |
|---|---|
| Worktree | Plan 11.21 implementation worktree |
| Branch | `agent/cursor/plan-11-21-otlp-failure-delivery-state` |
| `HEAD` | `9a8971a` (Task 2 GREEN) |
| `_emit_spans` | Unchanged this task (`git diff` empty for `src/optimus_gateway/observability.py`) |

## Environment presence (names only)

Checked with presence booleans only (no values printed):

| Name | Present |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset |
| `PHOENIX_TEST_BASE_URL` | unset |
| `PHOENIX_TEST_PROJECT` | unset |

Phoenix fixtures fail closed when the first two are unset. That fail-closed is **unrun**, not a pass and not a product classification failure.

## Claim-to-evidence

### Task 1/2 real-`OTLPSpanExporter` unit proof

Selector: `tests/unit/optimus_gateway/test_observability_export.py::test_exporter_reports_queued_when_real_otlp_exporter_returns_failure`

A real SDK subclass (`ReturnedFailureOtlpExporter(OTLPSpanExporter)`) returns `SpanExportResult.FAILURE` without raising and without calling `super().export()`. After Task 2 GREEN (`9a8971a`), the observed result is:

| Field | Enum / value |
|---|---|
| `delivery_state` | `queued` |
| `retry_count` | `1` |
| `final_disposition` | `transient_export_failure_retry_budget_exhausted` |

This is unit-tier type/result proof. It is not Phoenix collector evidence.

### Four-state counterexamples (same unit file)

| Selector | Observed `delivery_state` |
|---|---|
| `test_exporter_reports_delivered_on_first_time_success` | `delivered` |
| `test_exporter_reports_queued_when_transient_failures_exhaust_retry_budget` | `queued` (raised transient) |
| `test_exporter_reports_failed_after_bounded_retry_on_permanent_failure` | `failed` (generic non-OTLP returned `FAILURE`) |
| `test_exporter_reports_not_configured_when_endpoint_missing_and_no_exporter_injected` | `not_configured` |
| `test_exporter_not_configured_is_never_a_silent_successful_no_op` | never `delivered` |
| `test_exporter_reports_queued_when_real_otlp_exporter_returns_failure` | `queued` (real OTLP type, returned `FAILURE`) |

Task 2 GREEN rerun of that file: **29 passed**. The four public states remain meaningful. Export failure does not add cost/usage/mutation fields on `GatewayTraceExportResult`.

### Real Phoenix `requires_phoenix` tier

Exact attempt command:

```powershell
uv run --frozen pytest -o addopts= -m requires_phoenix tests/integration/telemetry/test_phoenix_live.py -q --strict-markers
```

Outcome: **1 passed, 1 error**. Named split:

| Selector | Marker outcome | Disposition |
|---|---|---|
| `test_live_phoenix_receives_real_otlp_batch_with_required_fields` | ERROR at fixture setup | **unrun** — `PHOENIX_TEST_BASE_URL` unset (fail-closed). Independent presence check also showed `OTEL_EXPORTER_OTLP_ENDPOINT` unset. |
| `test_live_otlp_returned_failure_against_loopback_non_listening_port` | passed | Loopback collector-outage probe (see below). Not Phoenix REST/collector evidence. |

The plan's brief command without `-o addopts=` was also executed:

```powershell
uv run --frozen pytest -m requires_phoenix tests/integration/telemetry/test_phoenix_live.py -q --strict-markers
```

Same split: **1 passed, 1 error**. CLI `-m requires_phoenix` overrode `pyproject.toml` addopts in this run rather than AND-deselecting the file. That is still not a Phoenix pass. A default addopts run that leaves `not requires_phoenix` in force would deselect the module; a skip/deselection is **unrun**, never a pass.

### Loopback returned-FAILURE probe (not Phoenix closure evidence)

Added in `tests/integration/telemetry/test_phoenix_live.py` only. Drives production `OpenTelemetryTraceExporter` with no injected fake. The production path constructs a real `OTLPSpanExporter` from a loopback port that has no listener, so Phoenix does not need to be killed and the operator's configured endpoint is not used.

Observed `GatewayTraceExportResult`:

| Field | Enum / value |
|---|---|
| `delivery_state` | `queued` |
| `retry_count` | `1` |
| `final_disposition` | `transient_export_failure_retry_budget_exhausted` |

Result dataclass fields remain `trace_batch_id`, `trace_ids`, `delivery_state`, `retry_count`, `final_disposition`. No `cost_usd`, `gateway_usage`, or `billing_units`.

This corroborates Task 1/2 against a real SDK exporter that actually attempts HTTP export. It does **not** replace the unrun Phoenix delivered-path / REST query, and it does **not** close P11.5-FU-1.

## Task 8 watch — named exclusion

The independent-root grouping watch remains a separate assertion inside `test_live_phoenix_receives_real_otlp_batch_with_required_fields`. That selector was **unrun** this session because Phoenix env was unset. `_emit_spans` was not modified. The Task 8 watch is **not** this FU's closure evidence.

## Residual (P11.5-FU-1 stays Promoted)

P11.5-FU-1 stays `Promoted -> Plan 11.21`. Exact residual:

- Real Phoenix collector delivered-path evidence is **unrun** because `PHOENIX_TEST_BASE_URL` and `OTEL_EXPORTER_OTLP_ENDPOINT` were unset. Operator owns machine-state; this task did not start Phoenix.
- Task 1/2 already hold the real-type returned-FAILURE unit proof.
- The loopback outage probe passed and records `queued` / `transient_export_failure_retry_budget_exhausted`, but it is not a live Phoenix collector.
- Task 8 multi-root grouping remains a named exclusion, unrun here, and not this FU's closure evidence.

## Later evidence

A later WP-3 run recorded the live Phoenix collector path in
[phoenix-evidence](plan-11-21-p11-5-fu-1-phoenix-evidence.md). This file remains the 2026-08-18
**unrun** disposition and is not rewritten.
