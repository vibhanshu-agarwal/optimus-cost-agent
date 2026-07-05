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
