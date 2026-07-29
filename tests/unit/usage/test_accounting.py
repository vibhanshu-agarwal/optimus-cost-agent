from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.gateway.models import GatewayUsage
from optimus.telemetry.events import TelemetryEventKind
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.usage.accounting import UsageAccountingService, reconcile_evidence_provider_usage
from optimus.usage.errors import DuplicateGatewayRequestError
from optimus.usage.ledger import ProviderUsageLedger


def gateway_usage(gateway_request_id: str, cost: str, units: int) -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id=gateway_request_id,
        provider="tavily",
        cache_hit=False,
        billing_units=units,
        cost_usd=Decimal(cost),
    )


def evidence_entry(gateway_request_id: str, cost: str, units: int) -> EvidenceLedgerEntry:
    return EvidenceLedgerEntry.from_gateway_usage(
        run_id="run-1",
        session_id="session-1",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        tool_class=ToolClass.WEB_SEARCH,
        sources=("https://docs.example.com",),
        gateway_usage=gateway_usage(gateway_request_id, cost, units),
        queried_at=datetime(2026, 7, 4, tzinfo=UTC),
    )


def test_accounting_service_records_provider_usage_from_gateway_usage():
    service = UsageAccountingService()

    ledger = service.record_gateway_usage(
        gateway_usage("gw-1", "0.003", 3),
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    assert ledger.total_cost_usd() == Decimal("0.003")
    assert ledger.total_billing_units() == 3
    assert ledger.entries[0].gateway_request_id == "gw-1"
    assert ledger.entries[0].service == "web.search"
    assert ledger.entries[0].native_unit == "tavily_credits"


def test_accounting_service_is_idempotent_on_identical_gateway_request_id():
    service = UsageAccountingService()
    usage = gateway_usage("gw-1", "0.003", 3)
    common = dict(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    first = service.record_gateway_usage(usage, **common)
    second = service.record_gateway_usage(usage, **common)

    assert second == first
    assert len(second.entries) == 1


def test_accounting_service_rejects_divergent_duplicate_gateway_request_id():
    service = UsageAccountingService()
    common = dict(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )
    service.record_gateway_usage(gateway_usage("gw-1", "0.003", 3), **common)

    with pytest.raises(DuplicateGatewayRequestError, match="gw-1"):
        service.record_gateway_usage(gateway_usage("gw-1", "0.004", 3), **common)


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
        service="web.search",
        native_unit="tavily_credits",
    )
    provider = UsageAccountingService(provider_ledger=provider).record_gateway_usage(
        gateway_usage("gw-2", "0.004", 4),
        run_id="run-1",
        session_id="session-1",
        request_id="req-2",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    report = reconcile_evidence_provider_usage(evidence, provider, run_id="run-1")

    assert report.matched_gateway_request_ids == frozenset({"gw-1", "gw-2"})
    assert report.missing_provider_usage_ids == frozenset()
    assert report.missing_evidence_ids == frozenset()
    assert report.cost_delta_usd == Decimal("0.000")
    assert report.reconciled is True


def test_accounting_service_records_planning_wire_attempt_request_id():
    service = UsageAccountingService()

    ledger = service.record_gateway_usage(
        gateway_usage("gw-1", "0.003", 3),
        run_id="run-1",
        session_id="session-1",
        request_id="run-1:planning:2:1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="agent.model",
        native_unit="tokens",
    )

    assert ledger.entries[0].request_id == "run-1:planning:2:1"


def test_reconciliation_reports_missing_provider_usage():
    evidence = EvidenceLedger().record(evidence_entry("gw-1", "0.003", 3))

    report = reconcile_evidence_provider_usage(evidence, ProviderUsageLedger(), run_id="run-1")

    assert report.reconciled is False
    assert report.missing_provider_usage_ids == frozenset({"gw-1"})


def test_accounting_service_emits_gateway_usage_event_per_accepted_attempt():
    events: list = []
    service = UsageAccountingService(event_sink=events.append)
    common = dict(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    service.record_gateway_usage(gateway_usage("gw-1", "0.002", 10), **common)

    assert len(events) == 1
    event = events[0]
    assert event.kind is TelemetryEventKind.GATEWAY_USAGE
    payload = event.to_json_dict()
    assert payload["gateway_request_id"] == "gw-1"
    assert payload["provider"] == "tavily"
    assert payload["billing_units"] == 10
    assert payload["cost_usd"] == "0.002"
    assert payload["service"] == "web.search"
    assert payload["native_unit"] == "tavily_credits"


def test_accounting_service_emits_one_event_per_attempt_even_on_identical_replay():
    events: list = []
    service = UsageAccountingService(event_sink=events.append)
    usage = gateway_usage("gw-1", "0.003", 3)
    common = dict(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    service.record_gateway_usage(usage, **common)
    ledger = service.record_gateway_usage(usage, **common)

    assert len(events) == 2
    assert len(ledger.entries) == 1


def test_accounting_service_does_not_emit_event_for_rejected_divergent_duplicate():
    events: list = []
    service = UsageAccountingService(event_sink=events.append)
    common = dict(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )
    service.record_gateway_usage(gateway_usage("gw-1", "0.003", 3), **common)

    with pytest.raises(DuplicateGatewayRequestError):
        service.record_gateway_usage(gateway_usage("gw-1", "0.004", 3), **common)

    assert len(events) == 1


def test_accounting_service_records_web_extract_context():
    service = UsageAccountingService()

    ledger = service.record_gateway_usage(
        gateway_usage("gw-extract-1", "0.001", 1),
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.extract",
        native_unit="tavily_credits",
    )

    assert ledger.entries[0].service == "web.extract"
    assert ledger.entries[0].native_unit == "tavily_credits"


def test_accounting_service_records_zero_cost_package_advisory_context():
    service = UsageAccountingService()
    free_usage = GatewayUsage(
        gateway_request_id="gw-pkg-1",
        provider="package-registry",
        cache_hit=False,
        billing_units=0,
        cost_usd=Decimal("0"),
    )

    ledger = service.record_gateway_usage(
        free_usage,
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="package.lookup",
        native_unit="requests",
    )

    assert ledger.entries[0].service == "package.lookup"
    assert ledger.entries[0].native_unit == "requests"
    assert ledger.entries[0].cost_usd == Decimal("0")
    assert ledger.entries[0].billing_units == 0
