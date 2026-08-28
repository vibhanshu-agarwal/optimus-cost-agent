# Usage Accounting, Evidence Ledger, and Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented (Phase 1). See README.md's "Phase 1 Usage Accounting and Observability" feature section and this plan's entry under Plan 7 in `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` for current build status. This plan predates this project's per-step checkbox-tracking convention, so its steps below were never intended to be individually ticked.

**Goal:** Persist and reconcile every billable gateway call from gateway response fields into provider usage, evidence audit records, Redis telemetry, JSONL events, and Gateway-managed observability traces.

**Architecture:** Extend the existing gateway/evidence seam instead of creating a parallel cost path. `GatewayUsage` remains the wire-level response envelope copied from the Optimus Gateway; `ProviderUsage` becomes the canonical persisted normalized cost record and joins to `EvidenceLedgerEntry` on `gateway_request_id`; telemetry writers emit append-only JSONL locally and send trace batches to the Optimus Gateway, which owns LangSmith credentials. Redis integration is isolated behind adapter boundaries so unit tests use fake clients while production can use Redis HASH and RedisTimeSeries commands.

**Tech Stack:** Python >=3.14, pydantic >=2.8, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `datetime`, stdlib `decimal`, stdlib `json`, stdlib `pathlib`, stdlib `typing`, existing `optimus.gateway`, `optimus.evidence`, `optimus.guardrails`, and `optimus.runtime` modules. No new runtime package is required for the Redis adapter boundary; production injects a Redis-compatible async client behind a local Protocol.

---

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 7: implement `GatewayUsage`, `ProviderUsage`, usage accounting service, Redis HASH/TimeSeries adapter boundaries, JSONL telemetry event schema, and reconciliation methods.
- `docs/superpowers/plans/drafts/2026-07-04-plan-7-working-notes.md`: branch-switch preservation note for the Plan 7 scope boundary and observed current code baseline.
- `docs/superpowers/plans/2026-07-04-plan-6-5-guardrail-hardening-mcp-runtime-trust.md`: Plan 6.5 emits stable guardrail/MCP audit events; Plan 7 records and exports those events but does not implement guardrail logic.
- `docs/superpowers/reviews/2026-07-04-plan-7-architect-review.md`: Plan 7 architect review confirming no blockers and asking implementation to fold in real provider-key hygiene, pricing fallback trigger coverage, YAGNI Redis dependency removal, and public ledger run-scoped accessors.
- `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf`, sections 4-5: Redis HASH stores structural metadata; RedisTimeSeries stores numeric performance histories; request-level cost attribution uses provider usage response objects and bypasses tokenizer estimators.
- `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf`, section 11: every model completion and tool call flows through the Optimus Gateway, and every response envelope records `gateway_request_id`, provider, cache hit, billing units, and cost.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 9E: `EvidenceLedger` records evidence/audit details and gateway usage fields copied directly from the response envelope; `total_credits()`, `total_billing_units()`, and `total_cost_usd()` are reconciliation methods.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 10: usage accounting owns RedisTimeSeries creation/alteration, metric writes, run metadata HASH writes, and 30-day retention/TTL policies.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 10A: `ProviderUsage` extends `GatewayUsage` with `service`, `native_unit`, `optimus_credits_debited`, and `price_snapshot_id`; observability traces are sent agent -> Gateway -> LangSmith with server-side LangSmith credentials.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, sections 8 and 8A: cost accounting tests must prove accurate reconciliation, pricing fallback audit signals, RedisTimeSeries behavior, run metadata HASH writes, trace fields, and the 80% aggregate coverage gate.
- `AGENTS.md`: parse usage and cost from gateway response fields; do not estimate tokens or cost post-hoc when provider usage is available; log every model/tool call with run/session IDs, token counts, model/provider/version, cache hit, and cost fields; never log secrets.

## Scope

### In Scope

- Backward-compatible `GatewayUsage` extension for optional normalized fields that the gateway may return:
  - `service`
  - `native_unit`
  - `optimus_credits_debited`
  - `model`
  - `model_version`
  - `price_snapshot_id`
- `ProviderUsage` and `ProviderUsageLedger` as immutable canonical normalized cost records.
- `UsageAccountingService` that records provider usage only from gateway response fields and rejects missing source-of-truth fields required for persisted normalized accounting.
- Reconciliation reports joining `EvidenceLedgerEntry` and `ProviderUsage` by `gateway_request_id`.
- Pricing snapshot fallback audit signals for local informational fallback paths, without populating `ProviderUsage` or overwriting gateway-provided `cost_usd`.
- Redis adapter boundary for:
  - idempotent `TS.CREATE` / `TS.ALTER`,
  - `TS.ADD` metric writes,
  - `HSET` run metadata writes,
  - `EXPIRE` run metadata TTL.
- JSONL telemetry event schema and append-only writer for model calls, tool calls, gateway usage, reconciliation, guardrail audit events, errors, and pricing fallback audit signals.
- Gateway observability trace export to `/v1/observability/traces`.
- Tests proving no local key from `LOCAL_PROVIDER_KEY_NAMES` is needed for trace export.
- Focused coverage for usage accounting, provider ledger, Redis adapter, telemetry events, and observability exporter.

### Out of Scope

- Plan 6.5 guardrail fixes: git bypass hardening, Unicode confusable upgrades, MCP runtime trust wiring, and missing manifest path handling.
- Retry/backoff, failure classification, golden task fixtures, release-gate runner, and one-key final release gate. Those belong to Plan 8.
- Context-window intelligent selection, scoring, compaction, ablations, and cost-saving promotion thresholds. Those remain Plan 11.
- Real Redis server E2E setup in unit tests. This plan uses fake Redis clients for deterministic unit/integration tests; staging Redis validation belongs to release-gate work.
- Direct LangSmith SDK or local LangSmith key use. The local agent sends trace events to the Optimus Gateway only.
- Local token/cost estimation when gateway usage exists. Missing gateway usage fails closed for persisted provider accounting.

### Dependency Notes

- Plan 3 already provides `GatewayClient`, `GatewayUsage`, and trusted gateway settings.
- Plan 4 already provides `EvidenceLedgerEntry`, `EvidenceLedger`, and gateway-backed evidence acquisition.
- Plan 6.5 is planning-approved, but its implementation should land before Plan 7 implementation so guardrail/MCP audit event field names are stable. Plan 7 only serializes those events.

## File Structure

- Modify: `src/optimus/gateway/models.py` - extend `GatewayUsage` and parser tests for normalized fields.
- Modify: `src/optimus/gateway/client.py` - add `post_observability_json()` for `/v1/observability/traces`.
- Create: `src/optimus/usage/__init__.py` - public usage exports.
- Create: `src/optimus/usage/models.py` - `ProviderUsage` and provider usage validation helpers.
- Create: `src/optimus/usage/ledger.py` - immutable `ProviderUsageLedger`.
- Create: `src/optimus/usage/accounting.py` - `UsageAccountingService`, provider usage recording, and evidence/provider reconciliation.
- Create: `src/optimus/telemetry/__init__.py` - public telemetry exports.
- Create: `src/optimus/telemetry/events.py` - JSONL-safe telemetry event models.
- Create: `src/optimus/telemetry/jsonl.py` - append-only JSONL writer with secret redaction.
- Create: `src/optimus/telemetry/redis_adapter.py` - RedisTimeSeries/HASH adapter boundary.
- Create: `src/optimus/telemetry/observability.py` - Gateway-managed trace export client.
- Modify: `src/optimus/evidence/ledger.py` - add helper for `gateway_request_ids()` if needed by reconciliation tests.
- Modify: `README.md` - add short Plan 7 usage accounting and observability note.
- Create: `tests/unit/gateway/test_usage_fields.py` - extended gateway usage parser tests.
- Create: `tests/unit/usage/test_models.py` - `ProviderUsage` validation tests.
- Create: `tests/unit/usage/test_ledger.py` - provider ledger immutability and totals tests.
- Create: `tests/unit/usage/test_accounting.py` - accounting service and reconciliation tests.
- Create: `tests/unit/telemetry/test_events.py` - event schema and redaction tests.
- Create: `tests/unit/telemetry/test_jsonl.py` - append-only JSONL writer tests.
- Create: `tests/unit/telemetry/test_redis_adapter.py` - Redis command boundary tests with fake client.
- Create: `tests/unit/telemetry/test_observability.py` - Gateway trace export tests.
- Create: `tests/integration/usage/test_evidence_provider_reconciliation.py` - mocked evidence/provider cost join flow.
- Create: `tests/integration/telemetry/test_usage_telemetry_flow.py` - mocked accounting -> JSONL -> Gateway trace flow.

## Human Agile Sizing

This plan is sized for roughly 2-3 weeks of human development effort:

- Days 1-2: `GatewayUsage` normalized fields and `ProviderUsage` models.
- Days 3-5: provider ledger, accounting service, and evidence/provider reconciliation.
- Days 6-8: Redis adapter boundaries and pricing fallback audit signals.
- Days 9-11: JSONL telemetry schema/writer and secret redaction.
- Days 12-13: Gateway observability export and one-key trace tests.
- Days 14-15: integration flows, coverage hardening, README, and review fixes.

## Commit Policy for Execution

Each task includes a commit step because the Superpowers workflow favors small reviewable checkpoints. In this repository, commit steps are approval-gated: do not run `git commit`, push, delete branches, or rewrite history unless the user explicitly approves that action. If commit approval has not been granted, treat each commit step as a local checkpoint: run the narrow tests, inspect `git diff --check`, leave changes unstaged or stage only with explicit approval, and continue.

## Task 1: Extend GatewayUsage With Normalized Fields

**Files:**
- Modify: `src/optimus/gateway/models.py`
- Test: `tests/unit/gateway/test_usage_fields.py`
- Verify: `tests/unit/gateway/test_models.py`

- [ ] **Step 1: Write failing gateway usage field tests**

Create `tests/unit/gateway/test_usage_fields.py`:

```python
from decimal import Decimal

import pytest

from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import GatewayUsage, parse_gateway_response


def test_gateway_usage_accepts_normalized_cost_fields():
    usage = GatewayUsage(
        gateway_request_id="gw-1",
        provider="glm",
        provider_request_id="provider-1",
        cache_hit=True,
        billing_units=123,
        cost_usd=Decimal("0.0123"),
        service="responses",
        native_unit="tokens",
        optimus_credits_debited=Decimal("1.23"),
        model="glm-5.2",
        model_version="2026-06-01",
        price_snapshot_id="prices-2026-07-04",
    )

    assert usage.service == "responses"
    assert usage.native_unit == "tokens"
    assert usage.optimus_credits_debited == Decimal("1.23")
    assert usage.model == "glm-5.2"
    assert usage.model_version == "2026-06-01"
    assert usage.price_snapshot_id == "prices-2026-07-04"


def test_parse_gateway_response_preserves_normalized_usage_fields():
    parsed = parse_gateway_response(
        {
            "id": "resp-1",
            "output_text": "done",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "provider_request_id": "provider-1",
                "cache_hit": True,
                "billing_units": 123,
                "cost_usd": "0.0123",
                "service": "responses",
                "native_unit": "tokens",
                "optimus_credits_debited": "1.23",
                "model": "glm-5.2",
                "model_version": "2026-06-01",
                "price_snapshot_id": "prices-2026-07-04",
            },
        }
    )

    assert parsed.gateway_usage.service == "responses"
    assert parsed.gateway_usage.native_unit == "tokens"
    assert parsed.gateway_usage.optimus_credits_debited == Decimal("1.23")
    assert parsed.gateway_usage.model == "glm-5.2"
    assert parsed.gateway_usage.model_version == "2026-06-01"
    assert parsed.gateway_usage.price_snapshot_id == "prices-2026-07-04"


@pytest.mark.parametrize("field", ["service", "native_unit", "optimus_credits_debited"])
def test_gateway_usage_normalized_fields_may_be_absent_for_legacy_tool_responses(field):
    body = {
        "id": "resp-1",
        "output_text": "done",
        "gateway_usage": {
            "gateway_request_id": "gw-1",
            "provider": "tavily",
            "cache_hit": False,
            "billing_units": 2,
            "cost_usd": "0.002",
            "service": "web.search",
            "native_unit": "tavily_credits",
            "optimus_credits_debited": "0.2",
        },
    }
    body["gateway_usage"].pop(field)

    parsed = parse_gateway_response(body)

    assert getattr(parsed.gateway_usage, field) is None


def test_gateway_usage_rejects_negative_optimus_credits():
    with pytest.raises(GatewayResponseError, match="optimus_credits_debited"):
        parse_gateway_response(
            {
                "id": "resp-1",
                "output_text": "done",
                "gateway_usage": {
                    "gateway_request_id": "gw-1",
                    "provider": "glm",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.001",
                    "optimus_credits_debited": "-1",
                },
            }
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/gateway/test_usage_fields.py -v
```

Expected: FAIL because `GatewayUsage` does not yet define the normalized fields.

- [ ] **Step 3: Extend GatewayUsage**

Modify `GatewayUsage` in `src/optimus/gateway/models.py`:

```python
class GatewayUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    gateway_request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_request_id: str | None = None
    cache_hit: bool = False
    billing_units: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    service: str | None = None
    native_unit: str | None = None
    optimus_credits_debited: Decimal | None = Field(default=None, ge=Decimal("0"))
    model: str | None = None
    model_version: str | None = None
    price_snapshot_id: str | None = None
```

- [ ] **Step 4: Run gateway tests**

Run:

```bash
pytest tests/unit/gateway/test_models.py tests/unit/gateway/test_usage_fields.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/gateway/models.py tests/unit/gateway/test_models.py tests/unit/gateway/test_usage_fields.py
git commit -m "Preserve normalized gateway usage fields."
```

## Task 2: ProviderUsage Models And Ledger

**Files:**
- Create: `src/optimus/usage/__init__.py`
- Create: `src/optimus/usage/models.py`
- Create: `src/optimus/usage/ledger.py`
- Test: `tests/unit/usage/test_models.py`
- Test: `tests/unit/usage/test_ledger.py`

- [ ] **Step 1: Write failing ProviderUsage model tests**

Create `tests/unit/usage/test_models.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.gateway.models import GatewayUsage
from optimus.usage.models import ProviderUsage


def gateway_usage() -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id="gw-1",
        provider="glm",
        provider_request_id="provider-1",
        cache_hit=True,
        billing_units=123,
        cost_usd=Decimal("0.0123"),
        service="responses",
        native_unit="tokens",
        optimus_credits_debited=Decimal("1.23"),
        model="glm-5.2",
        model_version="2026-06-01",
        price_snapshot_id="prices-2026-07-04",
    )


def test_provider_usage_copies_gateway_fields_and_adds_run_attribution():
    usage = ProviderUsage.from_gateway_usage(
        gateway_usage(),
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
    )

    assert usage.run_id == "run-1"
    assert usage.session_id == "session-1"
    assert usage.request_id == "req-1"
    assert usage.gateway_request_id == "gw-1"
    assert usage.provider == "glm"
    assert usage.cache_hit is True
    assert usage.billing_units == 123
    assert usage.cost_usd == Decimal("0.0123")
    assert usage.service == "responses"
    assert usage.native_unit == "tokens"
    assert usage.optimus_credits_debited == Decimal("1.23")
    assert usage.model == "glm-5.2"
    assert usage.model_version == "2026-06-01"
    assert usage.price_snapshot_id == "prices-2026-07-04"


@pytest.mark.parametrize("field", ["service", "native_unit", "optimus_credits_debited", "price_snapshot_id"])
def test_provider_usage_requires_normalized_fields_for_persistence(field):
    incomplete = gateway_usage().model_copy(update={field: None})

    with pytest.raises(ValueError, match=field):
        ProviderUsage.from_gateway_usage(
            incomplete,
            run_id="run-1",
            session_id=None,
            request_id="req-1",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        )


def test_provider_usage_rejects_negative_values():
    with pytest.raises(ValidationError):
        ProviderUsage(
            run_id="run-1",
            session_id=None,
            request_id="req-1",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
            gateway_request_id="gw-1",
            provider="glm",
            cache_hit=False,
            billing_units=-1,
            cost_usd=Decimal("0"),
            service="responses",
            native_unit="tokens",
            optimus_credits_debited=Decimal("0"),
            price_snapshot_id="prices-2026-07-04",
        )
```

- [ ] **Step 2: Write failing ProviderUsageLedger tests**

Create `tests/unit/usage/test_ledger.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from optimus.usage.ledger import ProviderUsageLedger
from optimus.usage.models import ProviderUsage


def usage(gateway_request_id: str, cost: str, units: int, credits: str) -> ProviderUsage:
    return ProviderUsage(
        run_id="run-1",
        session_id="session-1",
        request_id=f"req-{gateway_request_id}",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        gateway_request_id=gateway_request_id,
        provider="glm",
        provider_request_id=None,
        cache_hit=False,
        billing_units=units,
        cost_usd=Decimal(cost),
        service="responses",
        native_unit="tokens",
        optimus_credits_debited=Decimal(credits),
        model="glm-5.2",
        model_version="2026-06-01",
        price_snapshot_id="prices-2026-07-04",
    )


def test_provider_usage_ledger_is_append_only_and_totals_reconcile():
    ledger = ProviderUsageLedger()
    first = usage("gw-1", "0.001", 10, "0.1")
    second = usage("gw-2", "0.002", 20, "0.2")

    updated = ledger.record(first).record(second)

    assert ledger.entries == ()
    assert updated.entries == (first, second)
    assert updated.total_cost_usd() == Decimal("0.003")
    assert updated.total_billing_units() == 30
    assert updated.total_optimus_credits() == Decimal("0.3")
    assert updated.entries_for_run(None) == (first, second)
    assert updated.entries_for_run("run-1") == (first, second)
    assert updated.gateway_request_ids() == frozenset({"gw-1", "gw-2"})
    assert updated.gateway_request_ids(run_id="run-1") == frozenset({"gw-1", "gw-2"})
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/usage/test_models.py tests/unit/usage/test_ledger.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.usage'`.

- [ ] **Step 4: Implement usage models**

Create `src/optimus/usage/models.py`:

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from optimus.gateway.models import GatewayUsage


class ProviderUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    request_id: str = Field(min_length=1)
    occurred_at: datetime
    gateway_request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_request_id: str | None = None
    cache_hit: bool = False
    billing_units: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    service: str = Field(min_length=1)
    native_unit: str = Field(min_length=1)
    optimus_credits_debited: Decimal = Field(ge=Decimal("0"))
    model: str | None = None
    model_version: str | None = None
    price_snapshot_id: str = Field(min_length=1)

    @classmethod
    def from_gateway_usage(
        cls,
        gateway_usage: GatewayUsage,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
    ) -> "ProviderUsage":
        missing = [
            name
            for name in ("service", "native_unit", "optimus_credits_debited", "price_snapshot_id")
            if getattr(gateway_usage, name) is None
        ]
        if missing:
            raise ValueError(f"gateway usage missing normalized fields: {','.join(missing)}")
        return cls(
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            gateway_request_id=gateway_usage.gateway_request_id,
            provider=gateway_usage.provider,
            provider_request_id=gateway_usage.provider_request_id,
            cache_hit=gateway_usage.cache_hit,
            billing_units=gateway_usage.billing_units,
            cost_usd=gateway_usage.cost_usd,
            service=gateway_usage.service or "",
            native_unit=gateway_usage.native_unit or "",
            optimus_credits_debited=gateway_usage.optimus_credits_debited or Decimal("0"),
            model=gateway_usage.model,
            model_version=gateway_usage.model_version,
            price_snapshot_id=gateway_usage.price_snapshot_id or "",
        )
```

Create `src/optimus/usage/ledger.py`:

```python
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from optimus.usage.models import ProviderUsage


class ProviderUsageLedger(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: tuple[ProviderUsage, ...] = ()

    def record(self, usage: ProviderUsage) -> "ProviderUsageLedger":
        return ProviderUsageLedger(entries=(*self.entries, usage))

    def entries_for_run(self, run_id: str | None = None) -> tuple[ProviderUsage, ...]:
        if run_id is None:
            return self.entries
        return tuple(entry for entry in self.entries if entry.run_id == run_id)

    def gateway_request_ids(self, *, run_id: str | None = None) -> frozenset[str]:
        return frozenset(entry.gateway_request_id for entry in self.entries_for_run(run_id))

    def total_cost_usd(self, *, run_id: str | None = None) -> Decimal:
        return sum((entry.cost_usd for entry in self.entries_for_run(run_id)), Decimal("0"))

    def total_billing_units(self, *, run_id: str | None = None) -> int:
        return sum(entry.billing_units for entry in self.entries_for_run(run_id))

    def total_optimus_credits(self, *, run_id: str | None = None) -> Decimal:
        return sum((entry.optimus_credits_debited for entry in self.entries_for_run(run_id)), Decimal("0"))
```

Create `src/optimus/usage/__init__.py`:

```python
from optimus.usage.ledger import ProviderUsageLedger
from optimus.usage.models import ProviderUsage

__all__ = [
    "ProviderUsage",
    "ProviderUsageLedger",
]
```

- [ ] **Step 5: Run usage model tests**

Run:

```bash
pytest tests/unit/usage/test_models.py tests/unit/usage/test_ledger.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/optimus/usage/__init__.py src/optimus/usage/models.py src/optimus/usage/ledger.py tests/unit/usage/test_models.py tests/unit/usage/test_ledger.py
git commit -m "Add provider usage ledger."
```

## Task 3: Usage Accounting Service And Evidence Reconciliation

**Files:**
- Create: `src/optimus/usage/accounting.py`
- Modify: `src/optimus/usage/__init__.py`
- Modify: `src/optimus/evidence/ledger.py`
- Test: `tests/unit/usage/test_accounting.py`
- Test: `tests/integration/usage/test_evidence_provider_reconciliation.py`

- [ ] **Step 1: Write failing accounting tests**

Create `tests/unit/usage/test_accounting.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.gateway.models import GatewayUsage
from optimus.telemetry.events import TelemetryEventKind
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.usage.accounting import UsageAccountingService, reconcile_evidence_provider_usage
from optimus.usage.ledger import ProviderUsageLedger


def gateway_usage(gateway_request_id: str, cost: str, units: int) -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id=gateway_request_id,
        provider="tavily",
        cache_hit=False,
        billing_units=units,
        cost_usd=Decimal(cost),
        service="web.search",
        native_unit="tavily_credits",
        optimus_credits_debited=Decimal("0.2"),
        price_snapshot_id="prices-2026-07-04",
    )


def evidence_entry(gateway_request_id: str, cost: str, units: int) -> EvidenceLedgerEntry:
    return EvidenceLedgerEntry(
        run_id="run-1",
        session_id="session-1",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        tool_class=ToolClass.WEB_SEARCH,
        queried_at=datetime(2026, 7, 4, tzinfo=UTC),
        sources=("https://docs.example.com",),
        credits_used=1,
        gateway_request_id=gateway_request_id,
        provider="tavily",
        cache_hit=False,
        billing_units=units,
        cost_usd=Decimal(cost),
    )


def test_accounting_service_records_provider_usage_from_gateway_usage():
    service = UsageAccountingService()

    ledger = service.record_gateway_usage(
        gateway_usage("gw-1", "0.003", 3),
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
    )

    assert ledger.total_cost_usd() == Decimal("0.003")
    assert ledger.total_billing_units() == 3
    assert ledger.entries[0].gateway_request_id == "gw-1"


def test_accounting_service_rejects_missing_normalized_fields():
    service = UsageAccountingService()
    incomplete = gateway_usage("gw-1", "0.003", 3).model_copy(update={"service": None})

    with pytest.raises(ValueError, match="service"):
        service.record_gateway_usage(
            incomplete,
            run_id="run-1",
            session_id=None,
            request_id="req-1",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        )


def test_pricing_fallback_audit_signal_does_not_record_provider_usage():
    service = UsageAccountingService()

    event = service.record_pricing_fallback_audit(
        run_id="run-1",
        session_id="session-1",
        request_id="req-fallback-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        provider="glm",
        service="responses",
        native_unit="tokens",
        price_snapshot_id="prices-local-2026-07-04",
        reason="gateway_price_snapshot_unavailable",
    )

    payload = event.to_json_dict()

    assert service.provider_ledger.entries == ()
    assert payload["kind"] == TelemetryEventKind.PRICING_FALLBACK.value
    assert payload["provider"] == "glm"
    assert payload["price_snapshot_id"] == "prices-local-2026-07-04"
    assert "cost_usd" not in payload


def test_reconciliation_matches_evidence_and_provider_costs_by_gateway_request_id():
    evidence = EvidenceLedger().record(evidence_entry("gw-1", "0.003", 3)).record(evidence_entry("gw-2", "0.004", 4))
    service = UsageAccountingService()
    provider = service.record_gateway_usage(
        gateway_usage("gw-1", "0.003", 3),
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
    )
    provider = UsageAccountingService(provider_ledger=provider).record_gateway_usage(
        gateway_usage("gw-2", "0.004", 4),
        run_id="run-1",
        session_id="session-1",
        request_id="req-2",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
    )

    report = reconcile_evidence_provider_usage(evidence, provider, run_id="run-1")

    assert report.matched_gateway_request_ids == frozenset({"gw-1", "gw-2"})
    assert report.missing_provider_usage_ids == frozenset()
    assert report.missing_evidence_ids == frozenset()
    assert report.cost_delta_usd == Decimal("0.000")
    assert report.reconciled is True


def test_reconciliation_reports_missing_provider_usage():
    evidence = EvidenceLedger().record(evidence_entry("gw-1", "0.003", 3))

    report = reconcile_evidence_provider_usage(evidence, ProviderUsageLedger(), run_id="run-1")

    assert report.reconciled is False
    assert report.missing_provider_usage_ids == frozenset({"gw-1"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/usage/test_accounting.py -v
```

Expected: FAIL because `optimus.usage.accounting` does not exist.

- [ ] **Step 3: Add evidence helper**

Modify `EvidenceLedger` in `src/optimus/evidence/ledger.py`:

```python
    def gateway_request_ids(self, *, run_id: str | None = None) -> frozenset[str]:
        entries = self.entries if run_id is None else self.entries_for_run(run_id)
        return frozenset(entry.gateway_request_id for entry in entries if entry.gateway_request_id)
```

- [ ] **Step 4: Implement accounting service**

Create `src/optimus/usage/accounting.py`:

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from optimus.evidence.ledger import EvidenceLedger
from optimus.gateway.models import GatewayUsage
from optimus.telemetry.events import TelemetryEvent
from optimus.usage.ledger import ProviderUsageLedger
from optimus.usage.models import ProviderUsage


class UsageReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None
    matched_gateway_request_ids: frozenset[str]
    missing_provider_usage_ids: frozenset[str]
    missing_evidence_ids: frozenset[str]
    evidence_cost_usd: Decimal
    provider_cost_usd: Decimal
    cost_delta_usd: Decimal

    @property
    def reconciled(self) -> bool:
        return not self.missing_provider_usage_ids and not self.missing_evidence_ids and self.cost_delta_usd == Decimal("0")


class UsageAccountingService:
    def __init__(self, *, provider_ledger: ProviderUsageLedger | None = None) -> None:
        self.provider_ledger = provider_ledger or ProviderUsageLedger()

    def record_gateway_usage(
        self,
        gateway_usage: GatewayUsage,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
    ) -> ProviderUsageLedger:
        usage = ProviderUsage.from_gateway_usage(
            gateway_usage,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
        )
        self.provider_ledger = self.provider_ledger.record(usage)
        return self.provider_ledger

    def record_pricing_fallback_audit(
        self,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        provider: str,
        service: str,
        native_unit: str,
        price_snapshot_id: str,
        reason: str,
    ) -> TelemetryEvent:
        return TelemetryEvent.pricing_fallback(
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            provider=provider,
            service=service,
            native_unit=native_unit,
            price_snapshot_id=price_snapshot_id,
            reason=reason,
        )


def reconcile_evidence_provider_usage(
    evidence_ledger: EvidenceLedger,
    provider_ledger: ProviderUsageLedger,
    *,
    run_id: str | None = None,
) -> UsageReconciliationReport:
    evidence_ids = evidence_ledger.gateway_request_ids(run_id=run_id)
    provider_ids = provider_ledger.gateway_request_ids(run_id=run_id)
    matched = evidence_ids & provider_ids
    evidence_cost = evidence_ledger.total_cost_usd(run_id=run_id)
    provider_cost = provider_ledger.total_cost_usd(run_id=run_id)
    return UsageReconciliationReport(
        run_id=run_id,
        matched_gateway_request_ids=matched,
        missing_provider_usage_ids=evidence_ids - provider_ids,
        missing_evidence_ids=provider_ids - evidence_ids,
        evidence_cost_usd=evidence_cost,
        provider_cost_usd=provider_cost,
        cost_delta_usd=evidence_cost - provider_cost,
    )
```

Update `src/optimus/usage/__init__.py`:

```python
from optimus.usage.accounting import UsageAccountingService, UsageReconciliationReport, reconcile_evidence_provider_usage
from optimus.usage.ledger import ProviderUsageLedger
from optimus.usage.models import ProviderUsage

__all__ = [
    "ProviderUsage",
    "ProviderUsageLedger",
    "UsageAccountingService",
    "UsageReconciliationReport",
    "reconcile_evidence_provider_usage",
]
```

- [ ] **Step 5: Add integration reconciliation test**

Create `tests/integration/usage/test_evidence_provider_reconciliation.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.usage.accounting import UsageAccountingService, reconcile_evidence_provider_usage


def test_mocked_evidence_and_provider_ledgers_reconcile():
    gateway_usage = GatewayUsage(
        gateway_request_id="gw-search-1",
        provider="tavily",
        cache_hit=False,
        billing_units=2,
        cost_usd=Decimal("0.002"),
        service="web.search",
        native_unit="tavily_credits",
        optimus_credits_debited=Decimal("0.2"),
        price_snapshot_id="prices-2026-07-04",
    )
    evidence = EvidenceLedger().record(
        EvidenceLedgerEntry.from_gateway_usage(
            run_id="run-1",
            session_id="session-1",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
            tool_class=ToolClass.WEB_SEARCH,
            sources=("https://docs.example.com",),
            gateway_usage=gateway_usage,
            credits_used=1,
            queried_at=datetime(2026, 7, 4, tzinfo=UTC),
        )
    )
    provider = UsageAccountingService().record_gateway_usage(
        gateway_usage,
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
    )

    report = reconcile_evidence_provider_usage(evidence, provider, run_id="run-1")

    assert report.reconciled is True
```

- [ ] **Step 6: Run accounting tests**

Run:

```bash
pytest tests/unit/usage/test_accounting.py tests/integration/usage/test_evidence_provider_reconciliation.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/optimus/evidence/ledger.py src/optimus/usage/__init__.py src/optimus/usage/accounting.py tests/unit/usage/test_accounting.py tests/integration/usage/test_evidence_provider_reconciliation.py
git commit -m "Reconcile evidence and provider usage."
```

## Task 4: Redis Telemetry Adapter Boundary

**Files:**
- Create: `src/optimus/telemetry/__init__.py`
- Create: `src/optimus/telemetry/redis_adapter.py`
- Test: `tests/unit/telemetry/test_redis_adapter.py`

- [ ] **Step 1: Write failing Redis adapter tests**

Create `tests/unit/telemetry/test_redis_adapter.py`:

```python
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter, RunMetadata


class FakeRedis:
    def __init__(self, fail_create_existing: bool = False) -> None:
        self.fail_create_existing = fail_create_existing
        self.commands: list[tuple[object, ...]] = []

    async def execute_command(self, *args: object):
        self.commands.append(args)
        if self.fail_create_existing and args[0] == "TS.CREATE":
            raise RuntimeError("TSDB: key already exists")
        return "OK"

    async def hset(self, key: str, mapping: dict[str, str]):
        self.commands.append(("HSET", key, mapping))
        return len(mapping)

    async def expire(self, key: str, ttl_seconds: int):
        self.commands.append(("EXPIRE", key, ttl_seconds))
        return True


async def test_ensure_series_alters_existing_key():
    client = FakeRedis(fail_create_existing=True)
    adapter = RedisTelemetryAdapter(client=client)

    await adapter.ensure_series("telemetry:run:run-1:metrics:cost_usd")

    assert ("TS.CREATE", "telemetry:run:run-1:metrics:cost_usd", "RETENTION", 2_592_000_000) in client.commands
    assert ("TS.ALTER", "telemetry:run:run-1:metrics:cost_usd", "RETENTION", 2_592_000_000) in client.commands


async def test_record_metric_writes_timeseries_value():
    client = FakeRedis()
    adapter = RedisTelemetryAdapter(client=client)

    await adapter.record_metric(run_id="run-1", metric_name="cost_usd", value="0.003")

    assert ("TS.ADD", "telemetry:run:run-1:metrics:cost_usd", "*", "0.003") in client.commands


async def test_write_run_metadata_sets_hash_and_ttl():
    client = FakeRedis()
    adapter = RedisTelemetryAdapter(client=client)

    await adapter.write_run_metadata(
        RunMetadata(
            run_id="run-1",
            execution_mode="PLAN",
            generation_scope="INLINE_SNIPPET",
            rigor_level="LOW",
            user_approval_id="unauthorized_direct_run",
            assumption_count=2,
        )
    )

    assert (
        "HSET",
        "run:run-1:metadata",
        {
            "execution_mode": "PLAN",
            "generation_scope": "INLINE_SNIPPET",
            "rigor_level": "LOW",
            "user_approval_id": "unauthorized_direct_run",
            "assumption_count": "2",
        },
    ) in client.commands
    assert ("EXPIRE", "run:run-1:metadata", 2_592_000) in client.commands
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/telemetry/test_redis_adapter.py -v
```

Expected: FAIL because `optimus.telemetry.redis_adapter` does not exist.

- [ ] **Step 3: Implement Redis adapter**

Create `src/optimus/telemetry/redis_adapter.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

RETENTION_MS_30_DAYS = 2_592_000_000
RETENTION_SECONDS_30_DAYS = 2_592_000


class RedisTelemetryClient(Protocol):
    async def execute_command(self, *args: object): ...
    async def hset(self, key: str, mapping: dict[str, str]): ...
    async def expire(self, key: str, ttl_seconds: int): ...


@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    execution_mode: str
    generation_scope: str
    rigor_level: str
    user_approval_id: str
    assumption_count: int


class RedisTelemetryAdapter:
    def __init__(self, *, client: RedisTelemetryClient, retention_ms: int = RETENTION_MS_30_DAYS) -> None:
        self._client = client
        self._retention_ms = retention_ms

    async def ensure_series(self, key: str) -> None:
        try:
            await self._client.execute_command("TS.CREATE", key, "RETENTION", self._retention_ms)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                raise
            await self._client.execute_command("TS.ALTER", key, "RETENTION", self._retention_ms)

    async def record_metric(self, *, run_id: str, metric_name: str, value: str) -> None:
        if not run_id:
            raise ValueError("Access constraint violation: Missing telemetry run_id key.")
        key = f"telemetry:run:{run_id}:metrics:{metric_name}"
        await self.ensure_series(key)
        await self._client.execute_command("TS.ADD", key, "*", value)

    async def write_run_metadata(self, metadata: RunMetadata) -> None:
        key = f"run:{metadata.run_id}:metadata"
        await self._client.hset(
            key,
            mapping={
                "execution_mode": metadata.execution_mode,
                "generation_scope": metadata.generation_scope,
                "rigor_level": metadata.rigor_level,
                "user_approval_id": metadata.user_approval_id,
                "assumption_count": str(metadata.assumption_count),
            },
        )
        await self._client.expire(key, RETENTION_SECONDS_30_DAYS)
```

This module deliberately does not import `redis`. Production code injects a Redis-compatible async client, while unit tests use fakes that satisfy `RedisTelemetryClient`.

Create `src/optimus/telemetry/__init__.py`:

```python
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter, RunMetadata

__all__ = [
    "RedisTelemetryAdapter",
    "RunMetadata",
]
```

- [ ] **Step 4: Run Redis adapter tests**

Run:

```bash
pytest tests/unit/telemetry/test_redis_adapter.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/telemetry/__init__.py src/optimus/telemetry/redis_adapter.py tests/unit/telemetry/test_redis_adapter.py
git commit -m "Add Redis telemetry adapter boundary."
```

## Task 5: JSONL Telemetry Event Schema And Writer

**Files:**
- Create: `src/optimus/telemetry/events.py`
- Create: `src/optimus/telemetry/jsonl.py`
- Modify: `src/optimus/telemetry/__init__.py`
- Test: `tests/unit/telemetry/test_events.py`
- Test: `tests/unit/telemetry/test_jsonl.py`

- [ ] **Step 1: Write failing event schema tests**

Create `tests/unit/telemetry/test_events.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from optimus.telemetry.events import TelemetryEvent, TelemetryEventKind


def test_model_call_event_contains_required_usage_fields():
    event = TelemetryEvent.model_call(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        model="glm-5.2",
        model_version="2026-06-01",
        provider="glm",
        cache_hit=True,
        billing_units=123,
        cost_usd=Decimal("0.0123"),
        latency_ms=250,
        prompt="hello",
        response_summary="done",
    )

    payload = event.to_json_dict()

    assert payload["kind"] == TelemetryEventKind.MODEL_CALL.value
    assert payload["run_id"] == "run-1"
    assert payload["session_id"] == "session-1"
    assert payload["model"] == "glm-5.2"
    assert payload["model_version"] == "2026-06-01"
    assert payload["provider"] == "glm"
    assert payload["cache_hit"] is True
    assert payload["billing_units"] == 123
    assert payload["cost_usd"] == "0.0123"
    assert payload["prompt"] == "hello"


def test_gateway_reconciliation_and_pricing_fallback_events_have_json_payloads():
    gateway_event = TelemetryEvent.gateway_usage(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        gateway_request_id="gw-1",
        provider="glm",
        cache_hit=False,
        billing_units=123,
        cost_usd=Decimal("0.0123"),
        service="responses",
        native_unit="tokens",
        optimus_credits_debited=Decimal("1.23"),
        model="glm-5.2",
        model_version="2026-06-01",
        price_snapshot_id="prices-2026-07-04",
    )
    reconciliation_event = TelemetryEvent.reconciliation(
        run_id="run-1",
        session_id="session-1",
        request_id="req-2",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        matched_gateway_request_ids=frozenset({"gw-1"}),
        missing_provider_usage_ids=frozenset(),
        missing_evidence_ids=frozenset(),
        evidence_cost_usd=Decimal("0.0123"),
        provider_cost_usd=Decimal("0.0123"),
        cost_delta_usd=Decimal("0"),
        reconciled=True,
    )
    fallback_event = TelemetryEvent.pricing_fallback(
        run_id="run-1",
        session_id="session-1",
        request_id="req-3",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        provider="glm",
        service="responses",
        native_unit="tokens",
        price_snapshot_id="prices-local-2026-07-04",
        reason="gateway_price_snapshot_unavailable",
    )

    assert gateway_event.to_json_dict()["kind"] == TelemetryEventKind.GATEWAY_USAGE.value
    assert gateway_event.to_json_dict()["cost_usd"] == "0.0123"
    assert reconciliation_event.to_json_dict()["matched_gateway_request_ids"] == ["gw-1"]
    assert reconciliation_event.to_json_dict()["reconciled"] is True
    assert fallback_event.to_json_dict()["kind"] == TelemetryEventKind.PRICING_FALLBACK.value
    assert "cost_usd" not in fallback_event.to_json_dict()


def test_secret_values_are_redacted_from_event_payload():
    event = TelemetryEvent.tool_call(
        run_id="run-1",
        session_id=None,
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        tool_name="web.search",
        parameters={
            "query": "pytest",
            "api_key": "secret-token",
            "nested": {"Authorization": "Bearer nested-token"},
        },
        result_summary="Authorization: Bearer result-token",
        latency_ms=10,
        policy_reason="USER_REQUESTED",
        authorization_outcome="ALLOW",
    )

    assert "secret-token" not in event.to_json_line()
    assert "nested-token" not in event.to_json_line()
    assert "result-token" not in event.to_json_line()
    assert "**********" in event.to_json_line()
    assert event.to_json_dict()["authorization_outcome"] == "ALLOW"
```

- [ ] **Step 2: Write failing JSONL writer tests**

Create `tests/unit/telemetry/test_jsonl.py`:

```python
from datetime import UTC, datetime

from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.jsonl import JsonlTelemetryWriter


def test_jsonl_writer_appends_one_event_per_line(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    writer = JsonlTelemetryWriter(path)

    writer.append(
        TelemetryEvent.tool_call(
            run_id="run-1",
            session_id="session-1",
            request_id="req-1",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
            tool_name="web.search",
            parameters={"query": "pytest"},
            result_summary="2 results",
            latency_ms=100,
            policy_reason="USER_REQUESTED",
            authorization_outcome="ALLOW",
        )
    )
    writer.append(
        TelemetryEvent.guardrail_audit(
            run_id="run-1",
            session_id="session-1",
            request_id="req-2",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
            tool_surface="mcp",
            verdict="HOLD",
            rule_id="mcp.server_not_registered",
            failed_checks=("mcp.server_not_registered",),
            requires_human_approval=True,
        )
    )

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert '"kind":"tool_call"' in lines[0]
    assert '"kind":"guardrail_audit"' in lines[1]
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/telemetry/test_events.py tests/unit/telemetry/test_jsonl.py -v
```

Expected: FAIL because telemetry events and writer do not exist.

- [ ] **Step 4: Implement telemetry events**

Create `src/optimus/telemetry/events.py`:

```python
from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TelemetryEventKind(StrEnum):
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    GATEWAY_USAGE = "gateway_usage"
    GUARDRAIL_AUDIT = "guardrail_audit"
    RECONCILIATION = "reconciliation"
    ERROR = "error"
    PRICING_FALLBACK = "pricing_fallback"


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: TelemetryEventKind
    run_id: str = Field(min_length=1)
    session_id: str | None
    request_id: str = Field(min_length=1)
    occurred_at: datetime
    payload: dict[str, Any]

    @classmethod
    def model_call(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        model: str,
        model_version: str | None,
        provider: str,
        cache_hit: bool,
        billing_units: int,
        cost_usd: Decimal,
        latency_ms: int,
        prompt: str,
        response_summary: str,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.MODEL_CALL,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "model": model,
                "model_version": model_version,
                "provider": provider,
                "cache_hit": cache_hit,
                "billing_units": billing_units,
                "cost_usd": cost_usd,
                "latency_ms": latency_ms,
                "prompt": prompt,
                "response_summary": response_summary,
            },
        )

    @classmethod
    def gateway_usage(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        gateway_request_id: str,
        provider: str,
        cache_hit: bool,
        billing_units: int,
        cost_usd: Decimal,
        service: str,
        native_unit: str,
        optimus_credits_debited: Decimal,
        model: str | None,
        model_version: str | None,
        price_snapshot_id: str,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.GATEWAY_USAGE,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "gateway_request_id": gateway_request_id,
                "provider": provider,
                "cache_hit": cache_hit,
                "billing_units": billing_units,
                "cost_usd": cost_usd,
                "service": service,
                "native_unit": native_unit,
                "optimus_credits_debited": optimus_credits_debited,
                "model": model,
                "model_version": model_version,
                "price_snapshot_id": price_snapshot_id,
            },
        )

    @classmethod
    def reconciliation(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        matched_gateway_request_ids: frozenset[str],
        missing_provider_usage_ids: frozenset[str],
        missing_evidence_ids: frozenset[str],
        evidence_cost_usd: Decimal,
        provider_cost_usd: Decimal,
        cost_delta_usd: Decimal,
        reconciled: bool,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.RECONCILIATION,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "matched_gateway_request_ids": sorted(matched_gateway_request_ids),
                "missing_provider_usage_ids": sorted(missing_provider_usage_ids),
                "missing_evidence_ids": sorted(missing_evidence_ids),
                "evidence_cost_usd": evidence_cost_usd,
                "provider_cost_usd": provider_cost_usd,
                "cost_delta_usd": cost_delta_usd,
                "reconciled": reconciled,
            },
        )

    @classmethod
    def pricing_fallback(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        provider: str,
        service: str,
        native_unit: str,
        price_snapshot_id: str,
        reason: str,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.PRICING_FALLBACK,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "provider": provider,
                "service": service,
                "native_unit": native_unit,
                "price_snapshot_id": price_snapshot_id,
                "reason": reason,
            },
        )

    @classmethod
    def tool_call(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        tool_name: str,
        parameters: dict[str, Any],
        result_summary: str,
        latency_ms: int,
        policy_reason: str,
        authorization_outcome: str,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.TOOL_CALL,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "tool_name": tool_name,
                "parameters": parameters,
                "result_summary": result_summary,
                "latency_ms": latency_ms,
                "policy_reason": policy_reason,
                "authorization_outcome": authorization_outcome,
            },
        )

    @classmethod
    def guardrail_audit(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        tool_surface: str,
        verdict: str,
        rule_id: str,
        failed_checks: tuple[str, ...],
        requires_human_approval: bool,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.GUARDRAIL_AUDIT,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "tool_surface": tool_surface,
                "verdict": verdict,
                "rule_id": rule_id,
                "failed_checks": failed_checks,
                "requires_human_approval": requires_human_approval,
            },
        )

    @classmethod
    def error(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        error_type: str,
        message: str,
        disposition: str,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.ERROR,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={"error_type": error_type, "message": message, "disposition": disposition},
        )

    def to_json_dict(self) -> dict[str, Any]:
        encoded = {
            "kind": self.kind.value,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "occurred_at": self.occurred_at.isoformat(),
            **self.payload,
        }
        return _json_safe(_redact(encoded))

    def to_json_line(self) -> str:
        return json.dumps(self.to_json_dict(), sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


_EXACT_SECRET_KEYS = {
    "authorization",
    "auth_header",
    "x-api-key",
}

_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "optimus_api_key",
)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in _EXACT_SECRET_KEYS or any(part in key_text for part in _SECRET_KEY_PARTS):
                redacted[key] = "**********"
            else:
                redacted[key] = _redact(child)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact(child) for child in value]
    if isinstance(value, str):
        return re.sub(r"(?i)(authorization:\s*bearer\s+|bearer\s+)[^\s]+", r"\1**********", value)
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe(child) for child in value]
    if isinstance(value, Decimal):
        return str(value)
    return value
```

- [ ] **Step 5: Implement JSONL writer**

Create `src/optimus/telemetry/jsonl.py`:

```python
from __future__ import annotations

from pathlib import Path

from optimus.telemetry.events import TelemetryEvent


class JsonlTelemetryWriter:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def append(self, event: TelemetryEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(event.to_json_line())
            file.write("\n")
```

Update `src/optimus/telemetry/__init__.py`:

```python
from optimus.telemetry.events import TelemetryEvent, TelemetryEventKind
from optimus.telemetry.jsonl import JsonlTelemetryWriter
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter, RunMetadata

__all__ = [
    "JsonlTelemetryWriter",
    "RedisTelemetryAdapter",
    "RunMetadata",
    "TelemetryEvent",
    "TelemetryEventKind",
]
```

- [ ] **Step 6: Run telemetry tests**

Run:

```bash
pytest tests/unit/telemetry/test_events.py tests/unit/telemetry/test_jsonl.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/optimus/telemetry/__init__.py src/optimus/telemetry/events.py src/optimus/telemetry/jsonl.py tests/unit/telemetry/test_events.py tests/unit/telemetry/test_jsonl.py
git commit -m "Add append-only JSONL telemetry events."
```

## Task 6: Gateway-Managed Observability Trace Export

**Files:**
- Modify: `src/optimus/gateway/client.py`
- Create: `src/optimus/telemetry/observability.py`
- Modify: `src/optimus/telemetry/__init__.py`
- Test: `tests/unit/telemetry/test_observability.py`
- Test: `tests/integration/telemetry/test_usage_telemetry_flow.py`

- [ ] **Step 1: Write failing observability export tests**

Create `tests/unit/telemetry/test_observability.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.gateway.client import GatewayRequest
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.observability import GatewayObservabilityExporter


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest):
        self.requests.append(request)
        return {"accepted": True, "trace_batch_id": "trace-batch-1"}


def test_observability_export_posts_to_gateway_trace_endpoint(monkeypatch):
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    transport = FakeTransport()
    settings = OptimusGatewaySettings(gateway_url="https://gateway.optimus.ai", optimus_api_key="opt-test")
    exporter = GatewayObservabilityExporter(settings=settings, transport=transport)
    event = TelemetryEvent.model_call(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        model="glm-5.2",
        model_version="2026-06-01",
        provider="glm",
        cache_hit=False,
        billing_units=10,
        cost_usd=Decimal("0.001"),
        latency_ms=20,
        prompt="hello",
        response_summary="done",
    )

    response = exporter.export((event,))

    assert response == {"accepted": True, "trace_batch_id": "trace-batch-1"}
    assert transport.requests[0].url == "https://gateway.optimus.ai/v1/observability/traces"
    assert transport.requests[0].payload["events"][0]["run_id"] == "run-1"


def test_observability_export_does_not_require_local_provider_keys(monkeypatch):
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    transport = FakeTransport()
    settings = OptimusGatewaySettings(gateway_url="https://gateway.optimus.ai", optimus_api_key="opt-test")
    exporter = GatewayObservabilityExporter(settings=settings, transport=transport)

    response = exporter.export(())

    assert response == {"accepted": True, "trace_batch_id": "trace-batch-1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/telemetry/test_observability.py -v
```

Expected: FAIL because `optimus.telemetry.observability` and `GatewayClient.post_observability_json()` do not exist.

- [ ] **Step 3: Add Gateway observability method**

Modify `GatewayClient` in `src/optimus/gateway/client.py`:

```python
    def post_observability_json(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not path.startswith("/v1/observability/"):
            raise ValueError("observability path must start with /v1/observability/")
        self._settings.validate_trusted_gateway()
        return self._transport.post_json(
            GatewayRequest(
                method="POST",
                url=self._url(path),
                headers=self._json_headers(),
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        )
```

- [ ] **Step 4: Add observability exporter**

Create `src/optimus/telemetry/observability.py`:

```python
from __future__ import annotations

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayTransport
from optimus.telemetry.events import TelemetryEvent


class GatewayObservabilityExporter:
    def __init__(
        self,
        *,
        settings: OptimusGatewaySettings,
        transport: GatewayTransport | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = GatewayClient(settings=settings, transport=transport, timeout_seconds=timeout_seconds)

    def export(self, events: tuple[TelemetryEvent, ...]) -> dict[str, object]:
        return self._client.post_observability_json(
            path="/v1/observability/traces",
            payload={"events": [event.to_json_dict() for event in events]},
        )
```

Update `src/optimus/telemetry/__init__.py`:

```python
from optimus.telemetry.observability import GatewayObservabilityExporter
```

Append to `__all__`:

```python
    "GatewayObservabilityExporter",
```

- [ ] **Step 5: Add integration telemetry flow test**

Create `tests/integration/telemetry/test_usage_telemetry_flow.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.gateway.client import GatewayRequest
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.jsonl import JsonlTelemetryWriter
from optimus.telemetry.observability import GatewayObservabilityExporter


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest):
        self.requests.append(request)
        return {"accepted": True}


def test_usage_event_is_written_to_jsonl_and_exported_to_gateway(tmp_path, monkeypatch):
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    event = TelemetryEvent.model_call(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        model="glm-5.2",
        model_version="2026-06-01",
        provider="glm",
        cache_hit=True,
        billing_units=10,
        cost_usd=Decimal("0.001"),
        latency_ms=30,
        prompt="hello",
        response_summary="done",
    )
    writer = JsonlTelemetryWriter(tmp_path / "telemetry.jsonl")
    writer.append(event)
    transport = FakeTransport()
    exporter = GatewayObservabilityExporter(
        settings=OptimusGatewaySettings(gateway_url="https://gateway.optimus.ai", optimus_api_key="opt-test"),
        transport=transport,
    )

    response = exporter.export((event,))

    assert response == {"accepted": True}
    assert (tmp_path / "telemetry.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert transport.requests[0].payload["events"][0]["cost_usd"] == "0.001"
```

- [ ] **Step 6: Run observability tests**

Run:

```bash
pytest tests/unit/telemetry/test_observability.py tests/integration/telemetry/test_usage_telemetry_flow.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/optimus/gateway/client.py src/optimus/telemetry/__init__.py src/optimus/telemetry/observability.py tests/unit/telemetry/test_observability.py tests/integration/telemetry/test_usage_telemetry_flow.py
git commit -m "Export telemetry through the Optimus Gateway."
```

## Task 7: Documentation And Focused Verification

**Files:**
- Modify: `README.md`
- Verify: Plan 7 usage and telemetry files

- [ ] **Step 1: Add README note**

Append a Phase 1 usage accounting note:

```markdown
### Phase 1 Usage Accounting and Observability

Gateway response usage remains the source of truth for billable calls.
`GatewayUsage` captures the response envelope returned by the Optimus Gateway,
while `ProviderUsage` persists the normalized provider/native-unit cost record
joined by `gateway_request_id`. `EvidenceLedger` remains the audit trail for
external evidence and reconciles against the provider usage ledger by cost,
billing units, and request IDs. Local telemetry is append-only JSONL and Redis
adapter writes are isolated behind TimeSeries/HASH boundaries. Trace export
uses the Optimus Gateway `/v1/observability/traces` endpoint; LangSmith and
provider credentials stay server-side and are never required locally.
```

- [ ] **Step 2: Run focused Plan 7 tests**

Run:

```bash
pytest tests/unit/gateway/test_usage_fields.py tests/unit/usage tests/unit/telemetry tests/integration/usage tests/integration/telemetry -v
```

Expected: PASS.

- [ ] **Step 3: Run focused usage/telemetry coverage**

Run:

```bash
pytest tests/unit/usage tests/unit/telemetry tests/integration/usage tests/integration/telemetry --cov=optimus.usage --cov=optimus.telemetry --cov=optimus.gateway --cov=optimus.evidence --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Expected: PASS with usage and telemetry modules above the aggregate coverage threshold.

- [ ] **Step 4: Run full package coverage gate**

Run:

```bash
pytest --cov=optimus --cov-branch --cov-report=term-missing -v
```

Expected: PASS with aggregate Python production-code coverage at or above 80%.

- [ ] **Step 5: Verify one-key observability hygiene**

Run:

```bash
python -c "import os; from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES; found=sorted(k for k in LOCAL_PROVIDER_KEY_NAMES if os.environ.get(k)); print('FOUND=' + ','.join(found)); raise SystemExit(1 if found else 0)"
```

Expected: PASS with output `FOUND=`.

- [ ] **Step 6: Check diff hygiene**

Run:

```bash
git status --short
git diff --check
```

Expected: only intentional Plan 7 implementation, tests, lockfile, and README files are modified or added; no whitespace errors.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "Document usage accounting and observability."
```

## Self-Review

- Spec coverage: The plan maps every Plan 7 roadmap deliverable to executable tasks: `GatewayUsage` extension in Task 1, `ProviderUsage` and provider ledger in Task 2, usage accounting and reconciliation in Task 3, Redis HASH/TimeSeries adapter boundaries in Task 4, JSONL telemetry schema in Task 5, Gateway-managed observability export in Task 6, and focused verification in Task 7.
- Source-of-truth discipline: Provider usage records are created from gateway response fields and reject missing normalized fields instead of estimating cost or units locally.
- Plan 6.5 separation: Guardrail hardening and MCP runtime trust wiring are out of scope. Plan 7 records guardrail/MCP audit events only as telemetry payloads.
- One-key model: Observability export goes to the Optimus Gateway and does not introduce local LangSmith, Tavily, OpenAI, OpenRouter, GLM, or provider credentials.
- Telemetry completeness: `TelemetryEvent` has concrete constructors and tests for every promised JSONL event kind in scope: model calls, tool calls, gateway usage, guardrail audit, reconciliation, errors, and pricing fallback audit signals.
- Secret hygiene: telemetry redaction masks bearer-token strings and secret-looking payload keys recursively before JSONL write or Gateway export.
- Architect-review fixes: one-key hygiene imports `LOCAL_PROVIDER_KEY_NAMES`; pricing fallback is triggered by `UsageAccountingService.record_pricing_fallback_audit()` without mutating `ProviderUsageLedger`; Redis remains a Protocol boundary with no unused runtime dependency; reconciliation uses public ledger methods only.
- Type consistency: `GatewayUsage` optional normalized fields feed required `ProviderUsage` fields; `ProviderUsageLedger` is immutable like `EvidenceLedger`; reconciliation joins by `gateway_request_id`.
- Red-flag scan: The plan contains concrete test code, implementation code, commands, expected outcomes, and no unresolved placeholders.
- TDD compliance: Every production change starts with a failing unit or integration test, followed by minimal implementation and verification.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-04-usage-accounting-evidence-ledger-observability.md`. Two execution options:

**1. Subagent-Driven (recommended when available)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session task-by-task with checkpoints. Use `superpowers:executing-plans` if available; otherwise follow this plan directly with the same red/green/refactor discipline.

Plan 6.5 is planning-approved. Execute Plan 6.5 implementation first, then start Plan 7 implementation after Plan 6.5 is accepted or merged, because Plan 7 serializes guardrail/MCP audit events but does not define their trust semantics.
