# Plan 11.5: P11-FEAT-GATEWAY-COST-OBS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (or the
> reviewed equivalent `superpowers:subagent-driven-development`) to execute this plan task by
> task, and use `superpowers:test-driven-development` for every production behavior change. Do
> not mark a checkbox complete until its stated verification command has actually passed.

**Status:** Pending reviewer approval; this document authorizes no source, test, charter,
dependency, lockfile, or runtime mutation until the reviewer approves the plan.

**Goal:** Complete the pre-v1.0 COST-OBS cutover so provider-reported USD/native-unit usage is
persisted idempotently, evidence reconciles on `gateway_request_id`, structured agent telemetry
travels through the authenticated Gateway trace ingress to Phoenix over OTLP, all active runtime
surfaces use USD names, and real dependency evidence proves the one-key boundary.

**Architecture:** Keep `ProviderMessageResult` and the CORE request-path fail-closed boundary
unchanged. Enrich each accepted `GatewayUsage` at its caller with service/native-unit context,
persist an immutable `ProviderUsage` superset, join it with an expanded `EvidenceLedger`, and
write exactly-once USD/native-unit points to RedisTimeSeries. The agent emits typed, redacted trace
batches to the Gateway; the Gateway validates and redacts untrusted event data, maps it to
OpenTelemetry spans, exports OTLP HTTP/protobuf to the configured Phoenix endpoint, and records
delivery state without adding any usage or charge. The credit-named runtime contract is renamed
atomically before v1.0; `tavily_credits` remains a provider-native-unit literal under a narrow
allowlist.

**Tech Stack:** Python 3.14, Pydantic 2, stdlib `urllib`, Redis 5 with RedisTimeSeries,
OpenTelemetry API/SDK/exporter 1.44.x, OTLP HTTP/protobuf, pytest/pytest-asyncio/pytest-cov,
coverage.py, Ruff, local `ThreadingHTTPServer`, real Phoenix for trace-live evidence, real
TimeSeries-capable Redis for Redis evidence, real local Gateway/credentials for Gateway-live
evidence, and independently authored `acpx` for ACP protocol evidence.

## Global Constraints

- Baseline is `agent/codex/plan-11-5-gateway-cost-obs` at `67621c0`, forked from `origin/main`.
- The approved design spec is `docs/superpowers/specs/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-design.md`, SHA-256 `5608AD5520B8960E070A4A4F32C992D152A2CA19F21C177B44AC9805F371F3AA` at plan creation.
- Frozen HLD v2.16, LLD v2.39, Guardrails v1.1, and Test Strategy v1.5 are authoritative only from the committed blob digests recorded in the design spec.
- `ProviderMessageResult` in `src/optimus_gateway/upstream_client.py` and CORE request-path malformed-usage enforcement are consumed unchanged; a genuine gap is raised for review instead of extending either contract unilaterally.
- Provider-reported `cost_usd` and provider-native `billing_units` are the only settled accounting values; no token, price, or amortized observability estimate may populate persisted usage.
- `service` and `native_unit` are caller-supplied persistence context; they are not discard reasons when omitted from the optional `GatewayUsage` envelope. `price_snapshot_id` is optional diagnostic metadata.
- `optimus_credits_debited` is removed in the same atomic pre-v1.0 cutover as the other credit-named runtime fields; it is never dual-emitted or replaced by an estimate.
- `ledger_run_total_cost_usd` remains the ACP ledger total. Its companion is `ledger_run_total_billing_units`; no ACP result emits `ledger_run_total_credits`.
- Renaming `max_budget_credits`, `remaining_budget_credits`, `cost_credits`, and `credits_spent` to USD semantics preserves current loop comparisons and adds no budget-enforcement behavior. `P9.85-FU-3` remains parked.
- `tavily_credits` is an explicit allowlist entry only for the provider-native unit literal; it is not an Optimus credit balance and is not renamed.
- The Gateway reads `OTEL_EXPORTER_OTLP_ENDPOINT` only from Gateway-child configuration. The agent receives no OTLP/Phoenix endpoint or credential, and production has no Phoenix SDK/control-plane dependency.
- Use `opentelemetry-api>=1.44,<2`, `opentelemetry-sdk>=1.44,<2`, and `opentelemetry-exporter-otlp-proto-http>=1.44,<2` with one locked 1.44.x resolution in `uv.lock`; do not add `phoenix`, `phoenix-client`, or LangSmith packages.
- Trace delivery states are explicit: `delivered`, `queued`, `failed`, or `not_configured`. A missing endpoint is never reported as a successful delivery no-op.
- Trace failure never invents a model failure, reverses a completed mutation, or adds a model charge; final evidence exposes the delivery failure.
- Every production change follows RED test, focused failing run, minimum implementation, focused green run, then the next task. Unit fakes cannot stand in for Redis, Gateway, Phoenix, or ACP live evidence tiers.
- Before sign-off, run affected tests, the approved full suite, aggregate coverage at or above 80%, `python -m ruff check .`, the repo-wide retirement gate, and `git diff --check`.
- Commit, push, branch deletion, history rewrite, charter mutation, and dependency lock mutation are approval-gated execution actions. This plan records commit checkpoints but does not authorize them by itself.

---

## Frozen acceptance ledger

| Design requirement | Implementation task | Evidence artifact |
|---|---:|---|
| Fresh complete credit census and repo-wide allowlisted retirement gate | 0, 6, 8 | E0, E8 |
| ProviderUsage caller context, full attribution, USD/native-unit persistence | 2, 3 | E1, E2, E3 |
| EvidenceLedger join and divergent duplicate rejection | 2, 3 | E1, E3, E4 |
| RedisTimeSeries `TS.CREATE`/`TS.ALTER`, 30-day retention, labels, idempotence | 3 | E4 |
| Typed trace ingress, redaction, correlation, delivery states | 1, 4, 5 | E5 |
| Real OTLP HTTP/protobuf spans to Phoenix with parent/child relationships | 4, 8 | E6 |
| ACP USD result shapes and old credit-field absence | 6 | E7 |
| Charter correction and living documentation | 7 | E8 |
| Independent `acpx`, golden, Gateway-live, Redis-live, Phoenix-live, one-key evidence | 8 | E6, E7, E9 |
| Full release fitness and coverage | 8 | E9 |

## File and responsibility map

### Production files to modify or create

| File | Responsibility in this plan |
|---|---|
| `pyproject.toml`, `uv.lock` | Lock the OpenTelemetry API/SDK/OTLP HTTP exporter and add the `requires_phoenix` marker. |
| `src/optimus/gateway/models.py` | Keep optional caller-context fields; remove `optimus_credits_debited` from the client wire model and update the persistence docstring. |
| `src/optimus/usage/errors.py` | Stable divergent-duplicate exception shared by in-memory and Redis persistence tests. |
| `src/optimus/usage/models.py` | ProviderUsage superset, caller-supplied service/native unit, optional price snapshot, provider/model/token/cache attribution. |
| `src/optimus/usage/ledger.py` | Immutable provider ledger, same-ID idempotence, divergent duplicate rejection, USD/native-unit totals. |
| `src/optimus/usage/accounting.py` | Context-enriched GatewayUsage recording, telemetry emission, and EvidenceLedger/provider reconciliation. |
| `src/optimus/usage/__init__.py` | Public exports for the new exception and usage interfaces. |
| `src/optimus/evidence/ledger.py` | Expanded evidence schema, no local credit field, duplicate guard, billing/USD totals. |
| `src/optimus/evidence/models.py` | Remove response-level `credits_used` fields. |
| `src/optimus/evidence/acquisition.py`, `src/optimus/evidence/package_advisory.py` | Supply request IDs/service/native-unit context and record every accepted/provider-reported tool usage. |
| `src/optimus/gateway/errors.py` | Remove the obsolete `GatewayResponseError.credits_used` field. |
| `src/optimus/telemetry/events.py` | Add typed event/batch correlation fields and remove legacy credit payloads. |
| `src/optimus/telemetry/observability.py` | Agent-side typed `TraceBatch`, Gateway export result, bounded exporter retry, and flush contract. |
| `src/optimus/telemetry/fanout.py` | New local JSONL/Redis/Gateway fanout with run-final flush and isolated trace failures. |
| `src/optimus/telemetry/redis_adapter.py`, `src/optimus/telemetry/redis_sink.py` | Exact usage-series schema, request fingerprint idempotence, and settled usage event persistence. |
| `src/optimus/acp/bootstrap.py` | Construct the fanout with `.optimus/telemetry.jsonl`, Redis, and Gateway sinks. |
| `src/optimus/agent/runner.py` | Caller-context usage recording, Gateway usage events, fanout flush, and USD loop names. |
| `src/optimus/agent/planning_loop.py` | Rename loop cost/budget fields without changing comparisons or stop behavior. |
| `src/optimus/loops/models.py`, `src/optimus/loops/controller.py`, `src/optimus/loops/ledger.py`, `src/optimus/loops/completion.py` | Rename USD semantics and consume `GatewayUsage.cost_usd` instead of the deleted credit field. |
| `src/optimus/acp/dispatcher.py` | Remove credit fields from all four evidence result shapes and expose billing-unit totals. |
| `src/optimus_gateway/models.py` | Read Gateway-only OTLP endpoint configuration. |
| `src/optimus_gateway/observability.py` | Typed ingress validation, redaction, OTel span mapping, export, delivery state, and trace IDs. |
| `src/optimus_gateway/server.py` | Inject the trace exporter into the served observability handler. |
| `src/optimus_gateway/__main__.py` | Pass the Gateway OTLP configuration to `serve_gateway`. |

### Test and evidence files to modify or create

- Modify `tests/unit/gateway/test_usage_fields.py`, `tests/unit/gateway/test_models.py`, and
  `tests/unit/gateway/test_client.py` for the removed legacy field and caller-context boundary.
- Modify `tests/unit/usage/test_models.py`, `tests/unit/usage/test_ledger.py`,
  `tests/unit/usage/test_accounting.py`, and create `tests/unit/usage/test_persistence.py` for
  attribution, idempotence, divergence, and event emission.
- Modify `tests/unit/evidence/test_ledger.py`, `tests/unit/evidence/test_models.py`,
  `tests/unit/evidence/test_acquisition.py`, `tests/unit/evidence/test_package_advisory.py`, and
  `tests/integration/evidence/test_mocked_evidence_flow.py` for the expanded schema and no local
  credit field.
- Modify `tests/unit/telemetry/test_events.py`, `test_jsonl.py`, `test_observability.py`,
  `test_redis_adapter.py`, `test_redis_sink.py`, and create `tests/unit/telemetry/test_fanout.py`.
- Modify `tests/unit/optimus_gateway/test_server.py` and create
  `tests/unit/optimus_gateway/test_observability_export.py` for typed ingress, redaction, OTel
  span mapping, endpoint absence, retry, and delivery states.
- Modify `tests/unit/loops/test_models.py`, `test_controller.py`, `test_completion.py`,
  `test_ledger.py`, `tests/unit/agent/test_planning_loop.py`, `test_runner.py`, and
  `tests/unit/acp/test_dispatcher.py` for the atomic USD rename.
- Modify `tests/integration/usage/test_evidence_provider_reconciliation.py` and
  `tests/integration/telemetry/test_usage_telemetry_flow.py`; create a real Redis test under
  `tests/integration/telemetry/test_usage_redis_live.py` marked `requires_redis`.
- Modify `tests/integration/optimus_gateway/test_gateway_live_smoke.py`; create
  `tests/integration/telemetry/test_phoenix_live.py` marked `requires_phoenix` and
  `tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py` for the independent ACP evidence
  helper.
- Create `tools/run_plan115_acpx_cost_obs_evidence.py` to invoke the external `acpx` client and
  verify ACP result shapes without authoring a project ACP client.
- Modify `tests/unit/golden/test_json_harness.py`, `tests/integration/agent/test_golden_harness_real_runner.py`,
  and `tests/fixtures/golden_tasks/phase1_golden_tasks.json` only where the result contract names
  require USD/billing-unit assertions.

### Documentation files to modify

- `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`: correct both stale COST-OBS passages.
- `README.md`, `.env.example`, `.env.gateway.example`: describe USD/native-unit accounting and
  Gateway-only `OTEL_EXPORTER_OTLP_ENDPOINT`; do not add agent Phoenix credentials.
- `docs/superpowers/reviews/plan-11-5-review-checkpoints.md`: reviewer-owned ignored handoff log;
  never stage it.

## Task 0: Freeze approved inputs and re-derive the complete blast radius

**Files:** Read-only source/spec/docs; append-only ignored checkpoint log.

**Interfaces:**

- Consumes: approved design spec, frozen source blobs, current `HEAD`/`origin/main`, and current
  working tree.
- Produces: a rerunnable E0 baseline record containing digests, census output, file list, and
  evidence aliases. No source or test mutation is permitted in this task.

- [ ] **Step 1: Verify branch, baseline, spec digest, and clean source/test state**

Run:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
Get-FileHash -Algorithm SHA256 docs/superpowers/specs/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-design.md
git show 67621c0:docs/Optimus-Cost-Agent-Architecture-v2.16.pdf | sha256sum
git show 67621c0:docs/Optimus-Cost-Agent-LLD-v2.39.pdf | sha256sum
git show 67621c0:docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf | sha256sum
git show 67621c0:docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf | sha256sum
```

Expected: `HEAD` and `origin/main` are `67621c0`; the design spec digest is
`5608AD5520B8960E070A4A4F32C992D152A2CA19F21C177B44AC9805F371F3AA`; frozen source hashes match
the approved values in the spec; only the approved plan/spec/checkpoint-doc state is present.

- [ ] **Step 2: Re-run the exact mechanical census before any rename**

Run exactly:

```bash
rg -o -i --glob 'src/**' --glob 'tests/**' \
  '\b[A-Za-z_][A-Za-z0-9_]*\b' . \
  | awk -F: '{print $NF}' \
  | grep -i 'credit' \
  | sort | uniq -c
```

Expected baseline token counts are: `optimus_credits_debited` 43, `cost_credits` 39,
`credits_used` 37, `credits_spent` 22, `max_budget_credits` 21, `total_credits` 11,
`credits` 10, `ledger_run_total_credits` 7, `tavily_credits` 5, `remaining_budget_credits` 4,
`total_optimus_credits` 2, bare `credit` 1, and each named legacy test function 1.

- [ ] **Step 3: Record the path-level blast radius and ownership**

Run:

```powershell
rg -l -i 'credit' src tests | Sort-Object
rg -n 'GatewayUsage|ProviderUsage|EvidenceLedger|UsageAccountingService|TelemetryEvent|RedisTelemetryAdapter|GatewayObservabilityExporter' src tests
rg -n 'ledger_run_total_credits|optimus_credits_debited|cost_credits|credits_used|max_budget_credits|remaining_budget_credits' src tests
```

Record the output in the ignored checkpoint log. The implementation worker must not replace this
fresh list with the hand-list from memory; a newly surfaced identifier is assigned to Task 6 or
raised for reviewer disposition before code changes continue.

- [ ] **Step 4: Freeze the evidence alias ledger**

Record E0 as the digest/census artifact, E1 as contract unit evidence, E2 as provider/evidence
integration evidence, E3 as local Gateway accounting evidence, E4 as real Redis evidence, E5 as
trace contract unit evidence, E6 as real Phoenix evidence, E7 as independent ACP/golden evidence,
E8 as retirement/docs evidence, and E9 as final coverage/Ruff/release evidence.

- [ ] **Step 5: Leave a local checkpoint without committing**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: no source/test mutation and no staged checkpoint log. A commit is not allowed in this
baseline task without separate operator approval.

## Task 1: Add the locked OTel dependency seam and typed event/batch contract

**Files:**

- Modify: `pyproject.toml`, `uv.lock`
- Modify: `src/optimus/telemetry/events.py`, `src/optimus/telemetry/observability.py`,
  `src/optimus/telemetry/__init__.py`
- Test: `tests/unit/telemetry/test_events.py`, `tests/unit/telemetry/test_observability.py`

**Interfaces:**

- Consumes: existing immutable `TelemetryEvent` factories and JSONL serialization.
- Produces: agent-side `TraceBatch`, `TraceDeliveryState`, and `TraceExportResult` with stable IDs
  and serialization consumed by the Gateway exporter and fanout. The Gateway package duplicates
  the small wire DTOs in `optimus_gateway.observability` because it must remain independently
  importable and may not import `optimus.*`.

- [ ] **Step 1: Write RED tests for event identity and batch validation**

Add tests with these exact assertions:

```python
def test_event_serialization_has_schema_and_correlation_ids():
    event = TelemetryEvent.model_call(
        run_id="run-1", session_id="session-1", request_id="req-1",
        occurred_at=datetime(2026, 7, 28, tzinfo=UTC), model="glm-5.2",
        model_version="v1", provider="openrouter", cache_hit=False,
        billing_units=3, cost_usd=Decimal("0.001"), latency_ms=10,
        prompt="hello", response="done", input_tokens=1, output_tokens=2,
    )
    payload = event.to_json_dict()
    assert payload["schema_version"] == "1.0"
    assert payload["event_id"]
    assert payload["trace_id"] == "run-1"
    assert payload["parent_span_id"] is None
    assert payload["gateway_request_id"] is None


def _event_payload(*, event_id: str, trace_id: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "trace_id": trace_id,
        "parent_span_id": None,
        "kind": "model_call",
        "run_id": "run-1",
        "session_id": "session-1",
        "request_id": "req-1",
        "occurred_at": "2026-07-28T00:00:00+00:00",
        "gateway_request_id": "gw-1",
        "provider": "openrouter",
        "model": "glm-5.2",
        "billing_units": 3,
        "cost_usd": "0.001",
    }


def test_trace_batch_rejects_missing_identity_and_accepts_unknown_top_level():
    event = _event_payload(event_id="event-1", trace_id="trace-1")
    batch = TraceBatch.model_validate({
        "schema_version": "1.0",
        "batch_id": "batch-1",
        "events": [event],
        "future_hint": {"enabled": True},
    })
    assert batch.batch_id == "batch-1"
    with pytest.raises(ValidationError, match="event_id"):
        TraceBatch.model_validate({"schema_version": "1.0", "batch_id": "batch-1", "events": [{"kind": "model_call"}]})
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
uv run --frozen pytest tests/unit/telemetry/test_events.py tests/unit/telemetry/test_observability.py -q
```

Expected: failure because the correlation fields and `TraceBatch` contract do not yet exist.

- [ ] **Step 3: Add the dependency and minimum typed contract**

Add these project requirements and lock one compatible 1.44.x resolution:

```toml
"opentelemetry-api>=1.44,<2",
"opentelemetry-sdk>=1.44,<2",
"opentelemetry-exporter-otlp-proto-http>=1.44,<2",
```

Run `uv lock` and `uv sync --frozen --extra dev`. Extend `TelemetryEvent` with immutable
`schema_version="1.0"`, generated `event_id`, `trace_id` defaulting to `run_id`, and optional
`parent_span_id`, and optional `gateway_request_id`; keep factory call sites source-compatible
through defaults. Add `TraceBatch` as an immutable Pydantic model with required `schema_version`,
`batch_id`, and non-empty typed event tuple; ignore unknown top-level metadata without using it as
policy. Add:

```python
class TraceDeliveryState(StrEnum):
    DELIVERED = "delivered"
    QUEUED = "queued"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


class TraceExportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    trace_batch_id: str = Field(min_length=1)
    trace_ids: tuple[str, ...] = ()
    delivery_state: TraceDeliveryState
    retry_count: int = Field(ge=0)
    final_disposition: str = Field(min_length=1)
```

`TelemetryEvent.to_json_dict()` must emit correlation fields alongside the flattened payload and
must continue using the existing redaction/JSON-safe pipeline. No event factory may emit a legacy
credit field.

- [ ] **Step 4: Run focused tests, lock validation, and Ruff**

Run:

```powershell
uv run --frozen pytest tests/unit/telemetry/test_events.py tests/unit/telemetry/test_observability.py -q
uv run --frozen python -c "import opentelemetry; from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter; print(opentelemetry.__version__)"
uv run --frozen ruff check src/optimus/telemetry
```

Expected: tests pass, the import succeeds from the locked environment, and Ruff is clean.

- [ ] **Step 5: Commit checkpoint only with separate approval**

If commit authority is granted, stage only `pyproject.toml`, `uv.lock`, and the Task 1 source/test
files and commit `feat: add typed cost observability trace contract`; otherwise leave the changes
unstaged for reviewer inspection.

## Task 2: Migrate ProviderUsage and EvidenceLedger to caller context and idempotent USD records

**Files:**

- Create: `src/optimus/usage/errors.py`
- Modify: `src/optimus/gateway/models.py`, `src/optimus/usage/models.py`,
  `src/optimus/usage/ledger.py`, `src/optimus/usage/accounting.py`, `src/optimus/usage/__init__.py`
- Modify: `src/optimus/evidence/ledger.py`, `src/optimus/evidence/models.py`,
  `src/optimus/evidence/acquisition.py`, `src/optimus/evidence/package_advisory.py`,
  `src/optimus/gateway/errors.py`
- Modify: `src/optimus/loops/completion.py`, `src/optimus/agent/runner.py`,
  `src/optimus/acp/dispatcher.py`
- Test: `tests/unit/gateway/test_usage_fields.py`, `tests/unit/usage/test_models.py`,
  `tests/unit/usage/test_ledger.py`, `tests/unit/usage/test_accounting.py`,
  `tests/unit/evidence/test_ledger.py`, `tests/unit/evidence/test_models.py`,
  `tests/unit/evidence/test_acquisition.py`, `tests/unit/evidence/test_package_advisory.py`,
  `tests/unit/loops/test_completion.py`, `tests/unit/agent/test_runner.py`,
  `tests/unit/acp/test_dispatcher.py`, `tests/integration/usage/test_evidence_provider_reconciliation.py`

**Interfaces:**

- Consumes: optional `GatewayUsage` caller-context fields and the existing `EvidenceLedgerEntry`
  policy/provenance fields.
- Produces: `ProviderUsage.from_gateway_usage(..., service, native_unit, price_snapshot_id=None)`,
  `ProviderUsageLedger.record`, `EvidenceLedger.record`, and
  `UsageAccountingService.record_gateway_usage(..., service, native_unit, price_snapshot_id=None)`;
  each is idempotent on an identical `gateway_request_id` and rejects divergent duplicates. Until
  Task 6 performs the atomic public-wire rename, `GatewayCompletionEvaluator` continues to write
  `CompletionEvaluation.cost_credits` from `GatewayUsage.cost_usd`, and all four ACP evidence
  payload builders retain the old `ledger_run_total_credits` key but source its value from
  `EvidenceLedger.total_billing_units`.

- [ ] **Step 1: Write RED tests for the contract inversion**

Replace the persistence-requires-all-normalized-fields test with:

```python
def test_provider_usage_uses_caller_context_when_gateway_fields_are_absent():
    usage = ProviderUsage.from_gateway_usage(
        GatewayUsage(
            gateway_request_id="gw-1", provider="openrouter", billing_units=10,
            cost_usd=Decimal("0.002"),
        ),
        run_id="run-1", session_id="session-1", request_id="req-1",
        occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
        service="agent.model", native_unit="tokens",
    )
    assert usage.service == "agent.model"
    assert usage.native_unit == "tokens"
    assert usage.price_snapshot_id is None
    assert not hasattr(usage, "optimus_credits_debited")


def test_provider_usage_copies_resolved_provider_model_and_token_detail():
    usage = ProviderUsage.from_gateway_usage(
        gateway_usage_with_resolved_fields(),
        run_id="run-1", session_id=None, request_id="req-1",
        occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
        service="agent.model", native_unit="tokens",
    )
    assert usage.resolved_provider == "provider-a"
    assert usage.resolved_model == "model-v1"
    assert usage.input_tokens == 3
    assert usage.output_tokens == 7
    assert usage.total_tokens == 10


def test_provider_usage_ledger_is_idempotent_and_rejects_divergence():
    ledger = ProviderUsageLedger().record(provider_usage("gw-1", "0.001", 10))
    assert ledger.record(provider_usage("gw-1", "0.001", 10)) == ledger
    with pytest.raises(DuplicateGatewayRequestError, match="gw-1"):
        ledger.record(provider_usage("gw-1", "0.002", 10))
```

Add evidence tests proving the entry has `evidence_id`, `request_id`, provider/model/version,
resolved provider/model, `trust`, `policy_reason`, `gateway_request_id`, `billing_units`, and
`cost_usd`; assert `credits_used`, `total_credits`, and `optimus_credits_debited` are absent.

Revise `test_gateway_completion_evaluator_routes_through_gateway_and_returns_usage` so its Gateway
fixture contains only provider-reported `cost_usd`/`billing_units` and assert the transitional
`result.cost_credits == Decimal("0.002")`. This locks the live completion path to the surviving
wire field while reserving the public `cost_credits` rename for Task 6.

For each existing dispatcher route test — evidence search, evidence extract, package lookup, and
security advisory — make its service return a one-entry `EvidenceLedger` for `run-1` with
`billing_units=7` and `cost_usd=Decimal("0.007")`, then assert:

```python
assert response["result"]["ledger_run_total_credits"] == 7
assert response["result"]["ledger_run_total_cost_usd"] == "0.007"
```

This is intentionally a short-lived compatibility assertion: Task 2 proves the four builders no
longer call the deleted `total_credits()` accessor; Task 6 renames the public ACP key atomically.
Update the existing retry-accounting runner tests to omit the deleted wire field and assert every
persisted entry has caller-owned `service == "agent.model"` and `native_unit == "tokens"`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
uv run --frozen pytest tests/unit/gateway/test_usage_fields.py tests/unit/usage tests/unit/evidence tests/unit/loops/test_completion.py tests/unit/agent/test_runner.py tests/unit/acp/test_dispatcher.py tests/integration/usage/test_evidence_provider_reconciliation.py -q
```

Expected: failures identify the deleted legacy field, missing caller-context parameters, missing
attribution fields, absent duplicate guard, stale completion access, stale ACP ledger access, or
any evidence/runner constructor still carrying the removed fields.

- [ ] **Step 3: Implement the immutable USD/native-unit contracts**

Implement `DuplicateGatewayRequestError(ValueError)` with the request ID and a stable
`"divergent gateway_request_id"` message fragment. Remove `GatewayUsage.optimus_credits_debited`
and update its docstring; leave `service`, `native_unit`, and `price_snapshot_id` optional at the
wire layer. Define `ProviderUsage` with required run/session/request/Gateway/provider IDs,
aggregator and resolved provider/model fields, cache/token detail, required caller `service` and
`native_unit`, optional `price_snapshot_id`, non-negative `billing_units`, and finite Decimal
`cost_usd`. `from_gateway_usage` copies only provider-reported fields and takes service/native unit
from explicit arguments.

Make both immutable ledgers compare a duplicate entry by the complete immutable record. An
identical duplicate returns the same ledger; a same-ID record with different cost, units, provider,
attribution, or model raises `DuplicateGatewayRequestError` before a second entry is appended.
Replace evidence `credits_used` with provider billing/USD fields and add the LLD-required IDs,
provenance/trust/policy fields. Preserve the existing policy reason, policy signal, and tool class
so Plan 11.4 policy custody remains intact.

Update both evidence services and their parse-failure paths to stop constructing or reading
`credits_used`, while preserving their current policy/provenance behavior. Change
`GatewayCompletionEvaluator` to obtain the transitional completion amount from `usage.cost_usd`.
Change `AgentRunner._record_gateway_usage` to record every valid usage envelope when accounting is
configured and pass `service="agent.model"`, `native_unit="tokens"`, and the optional wire
`price_snapshot_id` as diagnostic metadata; it must not use optional wire `service`/`native_unit`
as persistence input. In `_gateway_usage_payload`, remove `optimus_credits_debited`; in each of the
four ACP evidence payload builders, replace `ledger.total_credits(run_id=run_id)` with
`ledger.total_billing_units(run_id=run_id)` while deliberately retaining the legacy result key only
until Task 6.

- [ ] **Step 4: Run the contract tests and the existing evidence suite**

Run:

```powershell
uv run --frozen pytest tests/unit/gateway/test_usage_fields.py tests/unit/gateway/test_models.py tests/unit/usage tests/unit/evidence tests/unit/loops/test_completion.py tests/unit/agent/test_runner.py tests/unit/acp/test_dispatcher.py tests/integration/usage/test_evidence_provider_reconciliation.py -q
uv run --frozen ruff check src/optimus/gateway/models.py src/optimus/gateway/errors.py src/optimus/usage src/optimus/evidence src/optimus/loops/completion.py src/optimus/agent/runner.py src/optimus/acp/dispatcher.py
```

Expected: all focused tests pass; all live consumers of the removed wire/evidence fields are
working at the end of Task 2; only the intentionally transitional public ACP key and loop field
remain for Task 6's atomic rename.

- [ ] **Step 5: Commit checkpoint only with separate approval**

If authorized, stage Task 2 files and commit `feat: make usage and evidence ledgers USD-native`; otherwise leave the checkpoint unstaged.

## Task 3: Persist settled usage to RedisTimeSeries and wire every tool/model call

**Files:**

- Modify: `src/optimus/usage/accounting.py`, `src/optimus/telemetry/redis_adapter.py`,
  `src/optimus/telemetry/redis_sink.py`, `src/optimus/telemetry/events.py`
- Modify: `src/optimus/evidence/acquisition.py`, `src/optimus/evidence/package_advisory.py`
- Test: `tests/unit/usage/test_accounting.py`, `tests/unit/usage/test_persistence.py`,
  `tests/unit/telemetry/test_redis_adapter.py`, `tests/unit/telemetry/test_redis_sink.py`,
  `tests/unit/evidence/test_acquisition.py`, `tests/unit/evidence/test_package_advisory.py`,
  `tests/integration/usage/test_evidence_provider_reconciliation.py`,
  `tests/integration/telemetry/test_usage_telemetry_flow.py`

**Interfaces:**

- Consumes: Task 1 typed `TelemetryEvent` and Task 2 caller-context
  `UsageAccountingService.record_gateway_usage(..., service, native_unit, price_snapshot_id=None)`.
- Produces: a `gateway_usage` telemetry event and
  `RedisTelemetryAdapter.record_settled_usage(*, run_id, gateway_request_id, provider,
  provider_request_id, billing_units, cost_usd)` with exact-series idempotence.

- [ ] **Step 1: Write RED tests for caller wiring and exact Redis commands**

Retain Task 2's model-path assertion for `service="agent.model"`, `native_unit="tokens"`, and
request IDs such as `run-1:planning:1:1`. Add tests that web search supplies
`service="web.search"` and `native_unit="tavily_credits"`; web extract supplies
`service="web.extract"` and the same provider-native unit; package/advisory free calls supply their
fixed service and `native_unit="requests"` with zero cost/units. Verify the accounting service emits one
`TelemetryEventKind.GATEWAY_USAGE` event per accepted or provider-reported failed attempt.

For the Redis fake, assert the exact first-use command sequence contains:

```text
TS.CREATE optimus:usage:run-1:cost_usd RETENTION 2592000000 LABELS run_id run-1 metric cost_usd
TS.CREATE optimus:usage:run-1:billing_units RETENTION 2592000000 LABELS run_id run-1 metric billing_units
TS.ADD optimus:usage:run-1:cost_usd * 0.002
TS.ADD optimus:usage:run-1:billing_units * 10
```

Assert a repeated identical `gateway_request_id` writes no second `TS.ADD`, while a divergent
cost/units/provider record raises `DuplicateGatewayRequestError` and writes no second point.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
uv run --frozen pytest tests/unit/usage/test_accounting.py tests/unit/usage/test_persistence.py tests/unit/telemetry/test_redis_adapter.py tests/unit/telemetry/test_redis_sink.py tests/unit/evidence/test_acquisition.py tests/unit/evidence/test_package_advisory.py tests/integration/usage/test_evidence_provider_reconciliation.py -q
```

Expected: failures identify missing caller context, missing Gateway usage events, old
`telemetry:run:*` series, and absent duplicate handling.

- [ ] **Step 3: Implement accounting event emission and Redis persistence**

Extend `UsageAccountingService` with an optional synchronous `event_sink`. `record_gateway_usage`
must construct `ProviderUsage` with explicit context, update the immutable provider ledger, and
emit `TelemetryEvent.gateway_usage` containing every attribution field, provider-reported units,
and USD cost. It must emit for both successful responses and `GatewayHttpError.gateway_usage`
attempts, but never for unknown/malformed usage.

Replace the old telemetry metric keys with `record_settled_usage` that serializes a complete
fingerprint by `gateway_request_id`, protects the compare/write sequence with the adapter lock,
uses `HSETNX`/read-back to make identical duplicates no-ops, removes a claim if the subsequent
TimeSeries write fails, and raises on divergent fingerprints. Create/alter exactly these two
series with 30-day retention and labels; do not delete existing measurements. Keep the existing
run metadata HASH/TTL behavior for non-accounting telemetry.

Inject `UsageAccountingService` into both evidence services. Each service generates a stable
request ID once per transport attempt, records provider usage before propagating a malformed result
error when usage is present, and passes the owning service/native unit context. The agent runner
already supplies Task 2's caller-owned model context and needs no further context change here.

- [ ] **Step 4: Run unit and mocked integration evidence**

Run:

```powershell
uv run --frozen pytest tests/unit/usage tests/unit/telemetry/test_redis_adapter.py tests/unit/telemetry/test_redis_sink.py tests/unit/evidence/test_acquisition.py tests/unit/evidence/test_package_advisory.py tests/integration/usage/test_evidence_provider_reconciliation.py tests/integration/telemetry/test_usage_telemetry_flow.py -q
uv run --frozen ruff check src/optimus/usage src/optimus/telemetry src/optimus/evidence
```

Expected: provider/evidence costs reconcile by Gateway request ID, malformed usage has no side
effects, and the mocked telemetry flow contains both local JSONL/Redis and Gateway usage events.

- [ ] **Step 5: Commit checkpoint only with separate approval**

If authorized, stage Task 3 files and commit `feat: persist settled usage idempotently`; otherwise leave the checkpoint unstaged.

## Task 4: Implement Gateway typed trace ingress and OTLP Phoenix export

**Files:**

- Modify: `src/optimus_gateway/models.py`, `src/optimus_gateway/observability.py`,
  `src/optimus_gateway/server.py`, `src/optimus_gateway/__main__.py`
- Modify: `src/optimus/telemetry/observability.py`
- Test: `tests/unit/optimus_gateway/test_server.py`,
  `tests/unit/optimus_gateway/test_observability_export.py`,
  `tests/unit/telemetry/test_observability.py`

**Interfaces:**

- Consumes: Task 1 `TraceBatch` JSON and Gateway-only `OTEL_EXPORTER_OTLP_ENDPOINT`.
- Produces: Gateway-side wire DTOs matching the agent-side `TraceBatch`/result field names, a
  `TraceExporter` protocol, `OpenTelemetryTraceExporter`, and a served response with
  `status`, `gateway_request_id`, `trace_batch_id`, `trace_ids`, `delivery_state`, `retry_count`,
  and `final_disposition`, never `gateway_usage`, `billing_units`, or `cost_usd`.

- [ ] **Step 1: Write RED tests for mapping, redaction, and delivery state**

Add unit tests that inject a recording `SpanExporter` and assert:

```python
result = exporter.export(trace_batch_with_root_and_child_events())
assert result.delivery_state is TraceDeliveryState.DELIVERED
assert result.trace_batch_id == "batch-1"
assert len(result.trace_ids) == 1
assert recorded_spans[1].parent.span_id == recorded_spans[0].context.span_id
assert recorded_spans[0].attributes["run_id"] == "run-1"
assert recorded_spans[0].attributes["cost_usd"] == "0.001"
assert "provider_api_key" not in recorded_spans[0].attributes
assert recorded_redaction_reason("provider_api_key") == "secret"
```

Add tests for exporter success, one bounded transient retry then success, permanent export failure,
missing endpoint as `NOT_CONFIGURED`, malformed batch with no spans exported, hostile URL/command
content not executed/fetched/echoed, and accepted response fields containing no cost claim.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
uv run --frozen pytest tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_observability_export.py tests/unit/telemetry/test_observability.py -q
```

Expected: failures identify the absent exporter seam, typed delivery result, span mapping, and
Gateway-only endpoint configuration.

- [ ] **Step 3: Implement the Gateway exporter and handler boundary**

Add `otlp_endpoint: str | None` to `GatewayServiceConfig`, read only
`OTEL_EXPORTER_OTLP_ENDPOINT` in `from_env`, and pass it through `serve_gateway` into a handler
class attribute or explicit handler argument. Keep agent `OptimusGatewaySettings` unaware of this
variable.

Implement `TraceExporter.export(batch: GatewayTraceBatch) -> GatewayTraceExportResult` with an injectable
OpenTelemetry `SpanExporter` for tests. The production exporter uses
`TracerProvider`, `BatchSpanProcessor`, and `OTLPSpanExporter` over HTTP/protobuf; call
`force_flush` before returning the delivery state. Map each event to a span named
`optimus.{event.kind}`, preserve `trace_id`/`parent_span_id`, and attach required attribution,
retry, validation, policy, and final-disposition attributes. Convert prompt/response/tool/error
content into redacted span events while preserving field names and redaction reasons.

The handler authenticates first, validates the typed batch before any export, redacts untrusted
content, generates a Gateway request ID, invokes the exporter, and returns the explicit delivery
state/result. Invalid auth or malformed batch returns sanitized 401/400 with no partial export.
Exporter unavailability yields `queued` or `failed` with retry count; it never fabricates cost or
changes the model result. No LangSmith import/key/endpoint is permitted.

- [ ] **Step 4: Run unit server/export tests and inspect the wire response**

Run:

```powershell
uv run --frozen pytest tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_observability_export.py tests/unit/telemetry/test_observability.py -q
uv run --frozen ruff check src/optimus_gateway src/optimus/telemetry/observability.py
```

Expected: all auth/shape/redaction/delivery tests pass; every observability response lacks usage
and cost fields; the mocked exporter sees parent/child spans and no secret values.

- [ ] **Step 5: Commit checkpoint only with separate approval**

If authorized, stage Task 4 files and commit `feat: export redacted traces to Phoenix over OTLP`; otherwise leave the checkpoint unstaged.

## Task 5: Fan out model/tool/error/retry/final telemetry and flush at run completion

**Files:**

- Create: `src/optimus/telemetry/fanout.py`
- Modify: `src/optimus/telemetry/jsonl.py`, `src/optimus/telemetry/redis_sink.py`,
  `src/optimus/telemetry/__init__.py`, `src/optimus/acp/bootstrap.py`, `src/optimus/agent/runner.py`
- Test: `tests/unit/telemetry/test_fanout.py`, `tests/unit/agent/test_runner.py`,
  `tests/integration/telemetry/test_usage_telemetry_flow.py`

**Interfaces:**

- Consumes: Task 1 typed events, Task 3 usage events, Task 4 `GatewayObservabilityExporter`.
- Produces: `TelemetryFanout.__call__(event)` and `TelemetryFanout.flush()` that retain local
  JSONL/Redis sinks, batch Gateway export, and isolate trace failure from the agent result.

- [ ] **Step 1: Write RED tests for fanout ordering and isolation**

Add tests asserting:

```python
# `writer`, `redis_sink`, `recording_exporter`, `event_one`, and `event_two` are
# test fixtures constructed from the production JSONL, Redis, exporter, and
# TelemetryEvent constructors.
fanout = TelemetryFanout(
    jsonl_writer=writer,
    redis_sink=redis_sink,
    gateway_exporter=recording_exporter,
    batch_size=2,
)
fanout(event_one)
assert recording_exporter.batches == []
fanout(event_two)
assert len(recording_exporter.batches) == 1
fanout.flush()
assert all(event.run_id == "run-1" for event in recording_exporter.batches[0])
```

Add a second test with an injected exporter that raises `TimeoutError`: call `fanout(event_one)`,
`fanout.flush()`, assert `fanout.delivery_results[0].delivery_state is TraceDeliveryState.FAILED`,
then run an `AgentRunner` with the same fanout and assert its completed result retains its original
status, USD total, and mutation count. Also assert local JSONL and Redis sinks receive every model,
tool, error, retry, policy, and final event exactly once, and `AgentRunner.run` invokes `flush()`
after the final `agent_run` event even when an inner run raises a controlled failure.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
uv run --frozen pytest tests/unit/telemetry/test_fanout.py tests/unit/agent/test_runner.py tests/integration/telemetry/test_usage_telemetry_flow.py -q
```

Expected: failures identify the missing fanout, flush hook, batch behavior, and trace-failure
isolation.

- [ ] **Step 3: Implement the fanout and bootstrap wiring**

Implement a synchronous fanout that writes the redacted event to JSONL, forwards it to Redis, and
buffers it for Gateway export. Flush when the batch reaches the configured size and at run final;
flush remaining events in a `finally` path. Catch only Gateway export failures at the fanout boundary,
record the returned `TraceExportResult` for final evidence, and do not mutate `AgentRunResult`.
Local JSONL defaults to `workspace_root / ".optimus" / "telemetry.jsonl"`, which is already
gitignored; Redis remains the existing `RedisTelemetryAdapter` sink.

Update `build_agent_runner_for_harness` to construct one fanout with the existing Redis sink,
JSONL writer, and Gateway exporter. Add no Phoenix/LangSmith credential to the agent environment.
Update `AgentRunner.run` to call a narrow `flush()` protocol after emitting the final event, while
preserving all existing direct callable test sinks.

- [ ] **Step 4: Run fanout, runner, and integration tests**

Run:

```powershell
uv run --frozen pytest tests/unit/telemetry tests/unit/agent/test_runner.py tests/integration/telemetry/test_usage_telemetry_flow.py -q
uv run --frozen ruff check src/optimus/telemetry src/optimus/acp/bootstrap.py src/optimus/agent/runner.py
```

Expected: local sinks remain available, Gateway batching/flush is deterministic, and trace export
failure is visible in telemetry without changing model completion/mutation state.

- [ ] **Step 5: Commit checkpoint only with separate approval**

If authorized, stage Task 5 files and commit `feat: fan out and flush cost observability telemetry`; otherwise leave the checkpoint unstaged.

## Task 6: Execute the atomic USD field migration and update every active consumer

**Files:**

- Modify: `src/optimus/loops/models.py`, `src/optimus/loops/controller.py`,
  `src/optimus/loops/ledger.py`, `src/optimus/loops/completion.py`
- Modify: `src/optimus/agent/planning_loop.py`, `src/optimus/agent/runner.py`,
  `src/optimus/acp/dispatcher.py`, `src/optimus/evidence/acquisition.py`,
  `src/optimus/evidence/package_advisory.py`, `src/optimus/evidence/models.py`,
  `src/optimus/gateway/errors.py`, `src/optimus/usage/ledger.py`, `src/optimus/telemetry/events.py`
- Modify: every active source/test file returned by Task 0's census, including
  `tests/unit/gateway/test_usage_fields.py`, `tests/unit/evidence/test_ledger.py`,
  `tests/unit/loops/test_completion.py`, `tests/unit/loops/test_models.py`,
  `tests/unit/loops/test_controller.py`, `tests/unit/loops/test_ledger.py`,
  `tests/unit/agent/test_planning_loop.py`, `tests/unit/agent/test_runner.py`, and
  `tests/unit/acp/test_dispatcher.py`
- Test: add `tests/unit/test_credit_surface_retirement.py` for the machine gate helper.

**Interfaces:**

- Consumes: Task 2 USD/native-unit ledgers and Task 3 cost events.
- Produces: USD-named loop state, billing-unit ACP totals, and zero legacy credit identifiers in
  active source/test/runtime surfaces except the explicit `tavily_credits` provider-native unit.

- [ ] **Step 1: Write RED tests for all four ACP shapes and the live completion consumer**

Change tests first so the expected contract is explicit:

```python
assert response["result"]["ledger_run_total_cost_usd"] == "0"
assert response["result"]["ledger_run_total_billing_units"] == 0
assert "ledger_run_total_credits" not in response["result"]
assert "optimus_credits_debited" not in response["result"]["gateway_usage"]

evaluation = gateway_completion_result(cost_usd="0.03")
assert evaluation.cost_usd == Decimal("0.03")
assert not hasattr(evaluation, "cost_credits")
```

Add parametrized loop tests proving `max_budget_usd`, `remaining_budget_usd`, and
`cost_usd_spent` preserve the exact previous stop comparison and arithmetic for the same Decimal
inputs. Rename the two legacy test functions rather than retaining credit-named active tests.

- [ ] **Step 2: Run the migration tests and verify RED**

Run:

```powershell
uv run --frozen pytest tests/unit/acp/test_dispatcher.py tests/unit/loops tests/unit/agent/test_planning_loop.py tests/unit/agent/test_runner.py tests/unit/evidence tests/unit/gateway/test_usage_fields.py -q
```

Expected: failures identify every old constructor/accessor and the four old ACP result keys.

- [ ] **Step 3: Rename fields mechanically, preserving behavior**

Apply the following exact mapping to active runtime/test surfaces:

| Retired name | Replacement or disposition |
|---|---|
| `cost_credits` | `cost_usd` |
| `credits_spent` | `cost_usd_spent` |
| `max_budget_credits` | `max_budget_usd` |
| `remaining_budget_credits` | `remaining_budget_usd` |
| `credits_used` | remove; use `billing_units`/`cost_usd` from `GatewayUsage` |
| `ledger_run_total_credits` | `ledger_run_total_billing_units` |
| `total_credits` | `total_billing_units` |
| `total_optimus_credits` | remove; use `total_cost_usd` |
| `optimus_credits_debited` | remove; completion evaluation reads `usage.cost_usd` |
| `credit`/`credits` active prose/test names | rename to USD, billing units, or provider-native units |
| `tavily_credits` | retain only as the provider-native-unit allowlist literal |

Update all four dispatcher evidence payloads, loop JSONL serialization, controller stop checks,
planning budget prompts/returns, runner callbacks, completion evaluator, error objects, evidence
responses, telemetry factories, and test fixtures. Do not alter the arithmetic, thresholds, retry
classification, or budget comparison behavior. `ledger_run_total_cost_usd` remains unchanged.

- [ ] **Step 4: Run the exact census and the focused behavior suite**

Run:

```powershell
$tokens = rg -o -i --glob 'src/**' --glob 'tests/**' '\b[A-Za-z_][A-Za-z0-9_]*\b' . 2>$null | ForEach-Object { ($_ -split ':')[-1] } | Where-Object { $_ -match 'credit' }
$violations = $tokens | Where-Object { $_ -ne 'tavily_credits' }
if ($violations) { $violations | Group-Object | Sort-Object Name | ForEach-Object { "{0,5} {1}" -f $_.Count,$_.Name }; exit 1 }
uv run --frozen pytest tests/unit/acp/test_dispatcher.py tests/unit/loops tests/unit/agent/test_planning_loop.py tests/unit/agent/test_runner.py tests/unit/evidence tests/unit/gateway/test_usage_fields.py -q
uv run --frozen pytest tests/integration/gateway/test_failed_usage_transport_flow.py tests/integration/evidence/test_mocked_evidence_flow.py -q
```

Expected: no active source/test identifier containing `credit` remains; the allowlisted
`tavily_credits` literal is deliberately excluded from the failure assertion by the implementation
test helper; all USD behavior and failed-attempt accounting tests pass.

- [ ] **Step 5: Commit checkpoint only with separate approval**

If authorized, stage the complete mechanical migration and commit `refactor: cut runtime accounting over to USD`; otherwise leave it unstaged for review.

## Task 7: Correct the charter and living configuration/documentation

**Files:**

- Modify: `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`
- Modify: `README.md`, `.env.example`, `.env.gateway.example`
- Test: `tests/unit/tools/test_plan115_docs.py` (create)

**Interfaces:**

- Consumes: Task 6 final field names and Task 4 Gateway-only OTLP configuration.
- Produces: charter scope/sequencing text that no longer names LangSmith or amortized request cost,
  living docs that place the OTLP endpoint on the Gateway side, and E8 documentation evidence.

- [ ] **Step 1: Write RED documentation assertions**

Add a test that reads the committed working-tree text and asserts both stale locations are absent
from the charter, while the replacement text appears at the same capability/ownership passages:

```python
charter = Path("docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md").read_text(encoding="utf-8")
assert "LangSmith trace export" not in charter
assert "amortized observability cost" not in charter
assert "authenticated structured agent-to-Gateway trace ingress" in charter
assert "OTel/OTLP export with Phoenix as the local default" in charter
assert "no allocated or amortized per-request charge" in charter
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```powershell
uv run --frozen pytest tests/unit/tools/test_plan115_docs.py -q
```

Expected: failure against the two stale charter phrases.

- [ ] **Step 3: Apply the exact approved charter correction**

At charter lines 39–40 and 100–102, state that COST-OBS owns provider-native usage persistence and
reconciliation, the wire-aware USD field migration, authenticated structured **agent-to-Gateway
trace ingress**, Gateway validation/redaction and OTel/OTLP export with Phoenix as the local
default, Plan 7 telemetry compatibility, and observability-field compatibility. State that trace
export has no allocated or amortized per-request charge and LangSmith is not part of the
architecture. Keep “authenticated” attached to the agent-to-Gateway ingress; do not imply
Phoenix-side authentication.

Update README Phase 1 accounting text to describe `cost_usd`, `billing_units`, RedisTimeSeries,
typed OTLP delivery state, and no LangSmith/amortized charge. Add a commented
`OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:6006/v1/traces` example only to `.env.gateway.example`;
do not add it to `.env.example` or project it to the agent. Keep `.gitignore` secret/runtime
coverage unchanged.

- [ ] **Step 4: Run docs tests and diff hygiene**

Run:

```powershell
uv run --frozen pytest tests/unit/tools/test_plan115_docs.py -q
rg -n 'LangSmith trace export|amortized observability cost|authenticated structured agent-to-Gateway trace ingress|OTEL_EXPORTER_OTLP_ENDPOINT' docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md README.md .env.example .env.gateway.example
git diff --check
```

Expected: stale phrases are absent from both charter passages; the corrected wording and
Gateway-only endpoint are present; no agent env example contains `OTEL_EXPORTER_OTLP_ENDPOINT`.

- [ ] **Step 5: Commit checkpoint only with separate approval**

If authorized, stage only the charter/README/example/test files and commit `docs: align Plan 11 COST-OBS charter and OTLP setup`; otherwise leave the checkpoint unstaged.

## Task 8: Produce real Redis, Gateway, Phoenix, ACP, golden, and release evidence

**Files:**

- Modify: `tests/integration/telemetry/test_usage_telemetry_flow.py`,
  `tests/integration/optimus_gateway/test_gateway_live_smoke.py`,
  `tests/integration/agent/test_golden_harness_real_runner.py`,
  `tests/unit/golden/test_json_harness.py`
- Create: `tests/integration/telemetry/test_usage_redis_live.py`,
  `tests/integration/telemetry/test_phoenix_live.py`,
  `tools/run_plan115_acpx_cost_obs_evidence.py`,
  `tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py`
- Modify: `pyproject.toml` marker registration and the ignored checkpoint log only.

**Interfaces:**

- Consumes: all Task 1–7 contracts and the named real dependencies.
- Produces: E4/E6/E7/E8/E9 artifacts; no source/test behavior is accepted on fake evidence alone.

- [ ] **Step 1: Write RED live/evidence assertions before running dependencies**

Add a `requires_redis` test that writes two identical provider records and one divergent record,
then reads both `optimus:usage:{run_id}:cost_usd` and
`optimus:usage:{run_id}:billing_units` with `TS.RANGE` and asserts one point per accepted request,
30-day retention, `run_id`/`metric` labels, and response/ProviderUsage/EvidenceLedger/TimeSeries
USD and billing-unit equality.

Add a `requires_phoenix` test that sends a batch through the real Gateway OTLP path, queries the
configured Phoenix project through its documented trace REST endpoint with `include_spans=true`,
and asserts the run/session/request IDs, provider/model/cache/billing/USD attributes,
parent-child relationships, redaction markers, retry/validation/policy/final-disposition events,
and one trace per batch. Production code must not import a Phoenix SDK.

Add the independent ACP helper test asserting the script invokes an external `acpx` executable,
never imports a project ACP client, and rejects any ACP result containing
`ledger_run_total_credits` or `optimus_credits_debited`.

- [ ] **Step 2: Run the focused evidence tests and verify RED or dependency-gated skips**

Run:

```powershell
uv run --frozen pytest tests/integration/telemetry/test_usage_redis_live.py -m requires_redis -q
uv run --frozen pytest tests/integration/telemetry/test_phoenix_live.py -m requires_phoenix -q
uv run --frozen pytest tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py -q
```

Expected: unit/helper failures identify incomplete evidence assertions; live tiers fail closed with
an explicit missing-dependency message if Redis, Phoenix, or `acpx` is not provisioned. A deselected
default run is not release evidence.

- [ ] **Step 3: Implement the real dependency fixtures and independent ACP driver**

Register `requires_phoenix` in `pyproject.toml`. The Redis fixture uses the existing
`run_preflight(..., require_timeseries=True)` path and cleans only its run namespace. The Phoenix
fixture reads the Gateway-only `OTEL_EXPORTER_OTLP_ENDPOINT`, plus test-only
`PHOENIX_TEST_BASE_URL` and `PHOENIX_TEST_PROJECT` values, waits for the Phoenix HTTP health/UI
endpoint, and queries the documented project trace REST endpoint; it never becomes a runtime
production dependency. Pin the Phoenix container image/operator setup in the evidence report
rather than silently treating a missing server as a pass.

Implement `tools/run_plan115_acpx_cost_obs_evidence.py` as a subprocess wrapper around the external
`acpx`, capturing sanitized stdout/stderr and the ACP result JSON. It must verify the agent-facing
environment contains only the approved Gateway/Redis runtime names, preserve the independent ACP
client role, and write a content-safe E7 report with USD/billing-unit fields and old-field absence.

- [ ] **Step 4: Run the complete approved release fitness gate**

Run the narrow suites first:

```powershell
uv run --frozen pytest tests/unit/usage tests/unit/evidence tests/unit/telemetry tests/unit/loops tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop.py tests/unit/acp/test_dispatcher.py tests/unit/optimus_gateway -q
uv run --frozen pytest tests/integration/usage tests/integration/evidence tests/integration/telemetry/test_usage_telemetry_flow.py -q
uv run --frozen ruff check .
uv run --frozen pytest --cov=src/optimus --cov=src/optimus_gateway --cov=src/optimus_security --cov-report=term-missing --cov-fail-under=80
```

Then run the named live tiers with real dependencies: `requires_redis`, local
`requires_live_gateway`, `requires_gateway`, `requires_phoenix`, and the independent `acpx`
capture. Run the Plan 9.6 live-verification authority exactly as its reviewed plan requires; do
not replace it with a project-authored ACP harness.

- [ ] **Step 5: Execute the mechanical retirement gate and final scope audit**

Run:

```powershell
rg -n -i --hidden --glob '!.git/**' '\b[A-Za-z_][A-Za-z0-9_]*credit[A-Za-z0-9_]*\b|\bcredit\w*\b' .
```

Classify every hit by exact path and reason. Any hit in `src`, `tests`, runtime configuration,
package metadata, release scripts, or active README/runtime examples is a failure, except the
narrow provider-native `tavily_credits` literal and the explicit census/retirement documentation
rows in this plan, the approved design, and the ignored checkpoint log. Frozen PDFs and historical
reports/plans may be allowlisted only by exact path and reason; a broad `docs/**` exemption is
invalid. Save the raw output, allowlist, filtered output, and zero-unallowlisted-hit assertion as
E8.

- [ ] **Step 6: Record release evidence and stop before integration**

Record E4/E6/E7/E8/E9 in the checkpoint log with command outputs, dependency identities, digests,
and final dispositions. Run `git status --short --branch`, `git diff --check`, and
`git diff --stat`. Do not commit, push, merge, or declare the plan closed until the reviewer and
operator approve the evidence artifacts.

## Review handoff

This implementation plan is intentionally separate from the approved design spec. It creates no
source/test/charter mutation and does not authorize execution. The next gate is reviewer review of
this task decomposition, especially the fresh Task 0 blast radius, the exact caller-context values,
the Redis duplicate protocol, the OTLP/Phoenix live evidence contract, and the active-surface
retirement allowlist.
