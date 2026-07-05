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
