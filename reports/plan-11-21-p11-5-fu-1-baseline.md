# Plan 11.21 P11.5-FU-1 — Task 0 baseline

**Status:** Pre-change characterization completed on a clean implementation branch.
Implementation of the real `OTLPSpanExporter` `FAILURE` → `queued` mapping has not started.
P11.5-FU-1 is Promoted to Plan 11.21 and is not Closed.

**Date:** 2026-08-18

## Checkout

| Ref | Value |
|---|---|
| Worktree | `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor-11-21` |
| Branch | `agent/cursor/plan-11-21-otlp-failure-delivery-state` |
| `HEAD` | `f40aa301c465aa6af207d8bceb3064bf83e39c98` |
| `origin/main` | `f40aa301c465aa6af207d8bceb3064bf83e39c98` |
| Status | hashes identical before Task 0 edits |

The plan's Step 1 `git worktree add` was already done. Kickoff used this existing worktree
and branch cut from `origin/main`.

Pool status uses the canonical token
`Promoted -> [Plan 11.21](2026-08-17-plan-11-21-p11-5-fu-1-otlp-failure-delivery-state.md)`
in both the Follow-up status index cell and the detail `**Status:**` line. Literal `Scheduled`
is not a `_status_token` form. Raising `_AlwaysTransientSpanExporter`, Plan 11.5 Task 4, and
the Task 8 trace-grouping watch are not this entry's closure evidence.

## Platform provenance

| Item | Value |
|---|---|
| `sys.platform` | `win32` |
| Python | `3.14.4` |
| pytest | `9.1.1` |
| `opentelemetry-exporter-otlp-proto-http` | `1.44.0` (`uv.lock` and `importlib.metadata`) |

No OTLP/Phoenix endpoints, credentials, or token values were invented or recorded.

## Current four-state contract (unchanged)

Command:

```powershell
uv run --frozen pytest tests/unit/optimus_gateway/test_observability_export.py -q
```

Result: **28 passed**.

Named selectors that record the current mapping:

| Selector | Injected exporter | Observed `delivery_state` |
|---|---|---|
| `test_exporter_reports_failed_after_bounded_retry_on_permanent_failure` | `_AlwaysPermanentlyFailingSpanExporter` returns `SpanExportResult.FAILURE` | `failed` |
| `test_exporter_reports_queued_when_transient_failures_exhaust_retry_budget` | `_AlwaysTransientSpanExporter` raises `TransientTraceExportError` | `queued` |
| `test_exporter_reports_delivered_on_first_time_success` | recording exporter succeeds | `delivered` |
| `test_exporter_reports_not_configured_when_endpoint_missing_and_no_exporter_injected` | no endpoint, no injected exporter | `not_configured` |
| `test_exporter_not_configured_is_never_a_silent_successful_no_op` | no endpoint, no injected exporter | never `delivered` |

Focused rerun of those five selectors: **5 passed**.

This is the Task 0 baseline: returned `FAILURE` is currently `failed`; only a raised transient
reaches `queued`. The four public states remain `delivered` / `queued` / `failed` /
`not_configured`. A missing endpoint is never `delivered`.

## Task 0 red / green

Command:

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py::test_plan_1121_keeps_p115_fu1_separate_scheduled_custody -q
```

Red (before pool promotion): **FAIL** `AssertionError: assert 'Open' == 'Promoted -> [Plan 11.21](2026-08-17-plan-11-21-p11-5-fu-1-otlp-failure-delivery-state.md)'`
on the P11.5-FU-1 index status. The parser observed P11.5-FU-1.

After promoting only P11.5-FU-1 to Plan 11.21:

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
```

Result: **50 passed**. P11.5-FU-1 is not Closed.
