# Plan 11.21 — P11.5-FU-1 OTLP FAILURE Delivery-State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task, and `superpowers:test-driven-development` for every production behavior change. Steps use checkbox syntax. Do not mark a checkbox complete until its stated verification command has passed.

**Goal:** Classify a real Gateway `OTLPSpanExporter.export()` return of `SpanExportResult.FAILURE` as retryable delivery exhaustion (`queued`) rather than a permanent failure, while retaining explicit `delivered`, `queued`, `failed`, and `not_configured` states.

**Architecture:** Keep `_RetryTrackingSpanExporter` as the sole observer of the delegate outcome behind `BatchSpanProcessor`. Extend its retryability classification to recognize the concrete, real `OTLPSpanExporter` result contract: the SDK returns `FAILURE` after its own bounded HTTP retry path rather than raising `TransientTraceExportError`. Non-OTLP injected exporter failures remain permanent unless they explicitly use the existing transient exception path, preserving a meaningful `failed` state and making the real-SDK special case narrow and executable.

**Tech Stack:** Python 3.14, OpenTelemetry API/SDK and `opentelemetry-exporter-otlp-proto-http` 1.44.x, existing `optimus_gateway.observability`, pytest, pytest-asyncio, coverage.py, Ruff, and the existing `requires_phoenix` real Gateway/Phoenix tier.

## Authority and source anchors

- `P11.5-FU-1` in `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:697-749` is the owning entry and acceptance boundary.
- At the drafting baseline, `src/optimus_gateway/observability.py:177-211` sets `exhausted_transient=True` only in the `except TransientTraceExportError` path. `OpenTelemetryTraceExporter.export()` maps that flag to `queued` at lines 279-280.
- The baseline unit proof in `tests/unit/optimus_gateway/test_observability_export.py` reaches `queued` only through `_AlwaysTransientSpanExporter`, which raises; `_AlwaysPermanentlyFailingSpanExporter` returns `SpanExportResult.FAILURE` and currently proves `failed`.
- `tests/integration/telemetry/test_phoenix_live.py` is a real `requires_phoenix` Gateway/Phoenix tier. It also owns the existing Task 8 multi-root trace-context watch described below; this plan does not alter `_emit_spans`.

## Global Constraints

- Start implementation in a new worktree/branch from refreshed `origin/main`, prove `HEAD == origin/main`, and do not use this planning branch or `optimus-cost-agent-wt-vibhanshu`.
- Do not change the agent’s runtime configuration, add agent-side OTLP/Phoenix endpoints or credentials, import a Phoenix SDK into production, or make an export result fabricate model failure, mutation reversal, `gateway_usage`, `billing_units`, or `cost_usd`.
- Preserve the four public states exactly: `delivered`, `queued`, `failed`, and `not_configured`. A missing endpoint with no injected exporter remains `not_configured`, never `delivered`.
- Preserve bounded retries (`_DEFAULT_MAX_TRANSIENT_RETRIES` unless separately configured), no automatic agent retry/replay, and the existing explicit `TransientTraceExportError` compatibility path.
- The new behavior must be limited to an actual `OTLPSpanExporter` whose `export()` returns `SpanExportResult.FAILURE`; do not convert every arbitrary `SpanExporter.FAILURE` to `queued`, because the existing injected permanent-failure contract must remain `failed`.
- Every test claim about the real SDK uses an object with the real `OTLPSpanExporter` type/production outcome boundary. A hand-written class that only exposes a different `export()` interface cannot prove the type-specific classification.
- The package that drafts this plan runs no Phoenix, paid, GUI, Gateway, or credential-store live call. A later implementer either runs the `requires_phoenix` tier in its real dependency environment or records an explicit named unrun/blocked disposition; a skipped/deselected marker is unrun, not a pass.
- Do not change frozen Plan 11.5/spec documents in place. Record all custody and closure progress in the pool and Plan 11.21 evidence only after the relevant evidence exists.

## File Map

| Path | Responsibility |
|---|---|
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Schedule P11.5-FU-1 to Plan 11.21 and close it only on its own evidence. |
| `tests/unit/docs/test_open_work_pool_hygiene.py` | Prevent cross-crediting Plan 11.5 Task 4 or the separate Task 8 watch as closure of P11.5-FU-1. |
| `src/optimus_gateway/observability.py` | Classify real SDK `FAILURE`, retain bounded retry count and all public result states. |
| `tests/unit/optimus_gateway/test_observability_export.py` | Build the deterministic real-type/return-value red and preserve success, raised transient, permanent-result, and missing-endpoint behavior. |
| `tests/integration/telemetry/test_phoenix_live.py` | Later real-tier proof or explicit documented disposition; no fake replaces Phoenix. |
| `reports/plan-11-21-p11-5-fu-1-*.md` | Baseline, live-tier disposition, and release claim-to-evidence records. |

## Explicit Exceptions and Custody

| Excluded work | Disposition / named owner |
|---|---|
| `_emit_spans` starts an empty `Context()` for independent root events sharing a wire trace ID | Explicitly out of scope. The existing Plan 11.5 Task 8 / `tests/integration/telemetry/test_phoenix_live.py` watch owns its real-Phoenix proof or disposition. |
| Agent-side OTLP/Phoenix configuration or credentials | Forbidden by the Gateway-only endpoint architecture. |
| Phoenix startup, paid calls, live runs, or external service state during this package | Not run here; later Task 3 owns real-tier execution/disposition. |
| Broader retry policy, persistent export queue, delivery replay, or changes to model/mutation/cost accounting | Out of scope; this plan corrects delivery-state reporting only. |
| Frozen Plan 11.5 task checkboxes/design text | Immutable historical artifacts; no amendment is implied by this plan. |

## Tasks

### Task 0: Establish separate P11.5-FU-1 custody and baseline

**Files:** Modify `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`, `tests/unit/docs/test_open_work_pool_hygiene.py`; create `reports/plan-11-21-p11-5-fu-1-baseline.md`.

**Interfaces:** Consumes the detailed pool entry and current four-state behavior. Produces scheduled custody and a baseline that distinguishes a returned `FAILURE` from a raised transient error.

- [ ] **Step 1: Create and verify the clean implementation checkout.**

  ```powershell
  git fetch origin main
  git worktree add -b agent/cursor/plan-11-21-otlp-failure-delivery-state ..\optimus-cost-agent-wt-cursor-11-21 origin/main
  git -C ..\optimus-cost-agent-wt-cursor-11-21 status --short --branch
  git -C ..\optimus-cost-agent-wt-cursor-11-21 rev-parse HEAD
  git -C ..\optimus-cost-agent-wt-cursor-11-21 rev-parse origin/main
  ```

  Expected: clean and equal hashes; stop for drift or an unrelated review-checkpoint conflict.

- [ ] **Step 2: Add the custody-projection RED.**

  Parse the stable-ID index and P11.5-FU-1 detail section. Require a promoted Plan 11.21 link and reject a closure claim based only on raising `_AlwaysTransientSpanExporter`, Plan 11.5 Task 4, or the Task 8 trace-grouping watch.

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  ```

  Expected: FAIL before scheduling; a first-pass means the parser is not observing P11.5-FU-1.

- [ ] **Step 3: Schedule only the owning entry and capture the baseline.**

  Change P11.5-FU-1 to `Promoted ->` the new Plan 11.21 link in both required pool representations. Record base SHA, library version, current `FAILURE -> failed` result, raised-transient `-> queued` result, and the unchanged four-state contract.

- [ ] **Step 4: Verify and commit custody separately.**

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  git diff --check
  git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md tests/unit/docs/test_open_work_pool_hygiene.py reports/plan-11-21-p11-5-fu-1-baseline.md
  git commit -m "docs: schedule OTLP failure delivery-state fix"
  ```

### Task 1: Add the real-return-value RED at the exporter boundary

**Files:** Modify `tests/unit/optimus_gateway/test_observability_export.py`.

**Interfaces:** Consumes `_RetryTrackingSpanExporter(delegate, max_retries)` and `OpenTelemetryTraceExporter.export(batch)`. Produces deterministic coverage of `OTLPSpanExporter.export(...) -> SpanExportResult.FAILURE` as distinct from a raised transient and a generic permanent return.

- [ ] **Step 1: Build a real-type controlled exporter test seam.**

  Define a test-only `ReturnedFailureOtlpExporter(OTLPSpanExporter)` whose overridden `export()` returns `SpanExportResult.FAILURE`, construct it with a harmless test endpoint, and inject it into `OpenTelemetryTraceExporter`. The double is an actual subclass of the real SDK class—not a lookalike implementation of `SpanExporter`—so it exercises the production type boundary without a network call. Assert the current baseline gives `failed`, `retry_count == 1`, and the permanent disposition; the intended assertion is `queued` and the transient-exhausted disposition, so this fails before production code changes.

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_observability_export.py -q
  ```

  Expected: one deterministic classification failure. If it passes first, stop and repair the test so it reaches the real type/result boundary.

- [ ] **Step 2: Preserve all counterexamples in the same RED suite.**

  Retain/extend assertions that a successful exporter is `delivered`; an existing raised `TransientTraceExportError` is `queued`; `_AlwaysPermanentlyFailingSpanExporter` still returns `failed`; and absent endpoint/no injected exporter is `not_configured`, never success. Assert the trace result dataclass still has no cost, usage, or mutation fields.

### Task 2: Classify real OTLP returned failures as retryable exhaustion

**Files:** Modify `src/optimus_gateway/observability.py`, `tests/unit/optimus_gateway/test_observability_export.py`.

**Interfaces:** Consumes a delegate export result and delegate type. Produces `tracker.exhausted_transient=True` only for the existing raised transient path or returned `FAILURE` from real `OTLPSpanExporter`; arbitrary non-OTLP returned `FAILURE` remains permanent.

- [ ] **Step 1: Make retryability explicit beside the existing retry tracker.**

  In `_RetryTrackingSpanExporter.export`, initialize per-attempt retryability from the current raised-transient exception branch. When `result is SpanExportResult.FAILURE`, additionally mark it retryable only if `isinstance(self._delegate, OTLPSpanExporter)`. Keep success, retry count, bounded loop, shutdown, and `force_flush` semantics unchanged. Do not inspect endpoint text, parse log output, add a retry, or catch/translate unrelated exceptions as transient.

- [ ] **Step 2: Map the tracker outcome through the unchanged public state switch.**

  Leave `OpenTelemetryTraceExporter.export`’s existing state mapping in place: `succeeded -> delivered`, `exhausted_transient -> queued`, otherwise `failed`; retain the earlier missing-endpoint `not_configured` return. The behavioral change is limited to setting the existing retryability signal from the concrete SDK outcome.

- [ ] **Step 3: Run green and prove the exact blast radius.**

  ```powershell
  rg -n "SpanExportResult\.FAILURE|exhausted_transient|TransientTraceExportError|TraceDeliveryState" src tests
  uv run --frozen pytest tests/unit/optimus_gateway/test_observability_export.py -q
  uv run --frozen pytest tests/unit/optimus_gateway -q
  git diff --check
  ```

  Expected: real OTLP-type returned failure is `queued`; generic returned failure remains `failed`; every pre-existing state assertion remains green. Review every census hit before modifying a caller.

- [ ] **Step 4: Commit the narrow production correction.**

  ```powershell
  git add src/optimus_gateway/observability.py tests/unit/optimus_gateway/test_observability_export.py
  git commit -m "fix: queue returned OTLP export failures"
  ```

### Task 3: Run or explicitly disposition the real Phoenix tier

**Files:** Modify `tests/integration/telemetry/test_phoenix_live.py` only if a returned-FAILURE collector-outage probe is missing; create `reports/plan-11-21-p11-5-fu-1-phoenix-disposition.md`.

**Interfaces:** Consumes a real configured Gateway-only OTLP endpoint and real Phoenix dependency. Produces real-dependency evidence or an explicit, reproducible unrun/blocked disposition.

- [ ] **Step 1: Add the real-tier assertion before executing it.**

  Ensure the test drives the production `OpenTelemetryTraceExporter`, not an injected fake, and records the returned `GatewayTraceExportResult.delivery_state`, retry count, and final disposition without exposing endpoint, credentials, raw event content, or token values. Keep the independent-root grouping watch as a separate assertion/disposition; do not alter `_emit_spans`.

- [ ] **Step 2: Execute only in the approved real environment.**

  ```powershell
  uv run --frozen pytest -m requires_phoenix tests/integration/telemetry/test_phoenix_live.py -q
  ```

  Record passed, failed, or unrun with the named missing dependency. A default-marker deselection, fake collector, or unit monkeypatch cannot count as this evidence.

- [ ] **Step 3: Publish the claim-to-evidence disposition.**

  Link the real SDK returned-result unit test, the four-state counterexamples, and the real Phoenix command/result. If real evidence cannot be obtained, leave P11.5-FU-1 promoted/open with its exact residual instead of closing it.

### Task 4: Close truthfully and audit current-state documents

**Files:** Modify the pool only when eligible; create `reports/plan-11-21-p11-5-fu-1-release.md`; audit README, roadmap, Plan 11 charter, runbooks, and current reports for claims made stale by the decision.

**Interfaces:** Consumes Tasks 0-3. Produces a closure with evidence or retained named open custody.

- [ ] **Step 1: Audit every live-state reference.**

  ```powershell
  rg -n "P11\.5-FU-1|OTLPSpanExporter|SpanExportResult\.FAILURE|transient_export_failure_retry_budget_exhausted|permanent_export_failure|Plan 11\.21" README.md docs reports
  ```

  Update only claims that the implemented evidence makes stale. Keep Plan 11.5, frozen specifications, and historical reports immutable.

- [ ] **Step 2: Apply the evidence-gated pool decision.**

  Mark P11.5-FU-1 `Closed` only when Task 2’s real-type return-value test, retained state counterexamples, selected real Phoenix tier, coverage, and fitness gates are all recorded. Otherwise retain the `Promoted -> Plan 11.21` row with an explicit unrun/failed dependency disposition.

- [ ] **Step 3: Run final fitness and immutable-artifact proof.**

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py tests/unit/optimus_gateway/test_observability_export.py -q
  uv run --frozen coverage run -m pytest
  uv run --frozen coverage report --fail-under=80
  uv run --frozen ruff check .
  git diff --check
  git diff --name-only origin/main...HEAD
  git show HEAD:docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md | sha256sum
  git status --short --branch
  ```

  Expected: coverage at least 80%, Ruff/diff hygiene clean, and the frozen Plan 11.5 digest is calculated from the committed blob. Record every unrun live tier honestly.

- [ ] **Step 4: Commit only reviewable evidence and closure material.**

  ```powershell
  git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-21-p11-5-fu-1-release.md
  git commit -m "docs: record OTLP delivery-state evidence"
  git push -u origin agent/cursor/plan-11-21-otlp-failure-delivery-state
  ```

## Definition of Done and Evidence Map

| Claim | Required evidence |
|---|---|
| P11.5-FU-1 has independent custody | Task 0 pool RED/green and Plan 11.21 link |
| Real SDK outcome, not a raised-only fake, reaches `queued` | Task 1/2 real-`OTLPSpanExporter` type with `export() -> FAILURE` selector |
| Generic permanent rejection remains `failed` | Task 1/2 `_AlwaysPermanentlyFailingSpanExporter` assertion |
| All four states remain meaningful | Task 1/2 success, raised transient, generic permanent, missing endpoint, and real-return tests |
| Export failure does not affect model/mutation/cost accounting | Existing result-field and ingress route assertions retained in Task 1/2 suite |
| Real dependency claim is not faked | Task 3 `requires_phoenix` result or explicit unrun disposition |
| Task 8 trace grouping is not silently folded in | Task 3/4 named exclusion and unchanged `_emit_spans` diff |
| No frozen/doc/safety regression | Task 4 freshness audit, coverage, Ruff, diff check, and committed-blob digest |

## Plan Self-Review

- **Acceptance coverage:** Task 1 supplies the missing returned-`FAILURE` RED; Task 2 changes only the existing bounded retry classification; Task 3 specifies the named live/Phoenix evidence or honest disposition; Task 4 preserves separate closure custody and current-state truthfulness.
- **Resolved classification decision:** `SpanExportResult` does not encode an HTTP cause. This plan treats a returned failure as retryable only for the concrete production `OTLPSpanExporter`, whose documented behavior absorbs its own retry path and returns `FAILURE`; generic injected `FAILURE` remains the permanent `failed` control. This is deliberately narrower than mapping every `SpanExporter.FAILURE` to queued and preserves the four-state contract.
- **Real-interface review:** The regression test requires the actual `OTLPSpanExporter` type and its `SpanExportResult.FAILURE` boundary. Raising-only doubles remain compatibility coverage, not proof of the real behavior.
- **Safety and scope review:** No retry count/default, endpoint ownership, Phoenix SDK import, cost/usage field, mutation state, or `_emit_spans` context behavior changes. The Task 8 watch remains named and out of scope.
- **Evidence and digest review:** The Phoenix tier is never represented as passed when deselected or skipped. The frozen Plan 11.5 hash comes from `git show HEAD:<path>`, not a Windows worktree read. The `rg` census occurs with the contract change, before final gate claims.
- **Placeholder scan:** No unnamed owner or deferred closure exists. The one intentional limitation—opaque SDK failures cannot be sub-classified by HTTP cause—is made explicit by the narrow concrete-type policy and its retained permanent-return control.
