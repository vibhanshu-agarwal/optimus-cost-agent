from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal


def usage() -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id="gw-1",
        provider="tavily",
        provider_request_id="provider-1",
        cache_hit=False,
        billing_units=3,
        cost_usd=Decimal("0.003"),
    )


def test_entry_from_gateway_usage_copies_fields_verbatim():
    entry = EvidenceLedgerEntry.from_gateway_usage(
        run_id="run-1",
        session_id="session-1",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        tool_class=ToolClass.WEB_SEARCH,
        sources=("https://docs.example.com/a",),
        gateway_usage=usage(),
        credits_used=3,
        queried_at=datetime(2026, 7, 3, tzinfo=UTC),
    )

    assert entry.run_id == "run-1"
    assert entry.session_id == "session-1"
    assert entry.gateway_request_id == "gw-1"
    assert entry.provider == "tavily"
    assert entry.provider_request_id == "provider-1"
    assert entry.cache_hit is False
    assert entry.billing_units == 3
    assert entry.cost_usd == Decimal("0.003")
    assert entry.credits_used == 3
    assert entry.sources == ("https://docs.example.com/a",)


def test_ledger_totals_reconcile_gateway_usage_fields():
    first = EvidenceLedgerEntry.from_gateway_usage(
        run_id="run-1",
        session_id=None,
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        tool_class=ToolClass.WEB_SEARCH,
        sources=("https://docs.example.com/a",),
        gateway_usage=usage(),
        credits_used=3,
        queried_at=datetime(2026, 7, 3, tzinfo=UTC),
    )
    second = EvidenceLedgerEntry(
        run_id="run-1",
        session_id=None,
        reason=EvidenceReasonCode.CURRENT_FACT,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT.value,
        tool_class=ToolClass.WEB_EXTRACT,
        queried_at=datetime(2026, 7, 3, 0, 0, 1, tzinfo=UTC),
        sources=("https://docs.example.com/a",),
        credits_used=4,
        gateway_request_id="gw-2",
        provider="tavily",
        provider_request_id=None,
        cache_hit=True,
        billing_units=5,
        cost_usd=Decimal("0.005"),
    )

    ledger = EvidenceLedger().record(first).record(second)

    assert ledger.total_credits() == 7
    assert ledger.total_billing_units() == 8
    assert ledger.total_cost_usd() == Decimal("0.008")
    assert ledger.total_credits(run_id="run-1") == 7
    assert ledger.total_cost_usd(run_id="run-1") == Decimal("0.008")
    assert ledger.total_cost_usd(run_id="other-run") == Decimal("0")


def test_ledger_record_returns_new_append_only_instance():
    ledger = EvidenceLedger()
    entry = EvidenceLedgerEntry.from_gateway_usage(
        run_id="run-1",
        session_id=None,
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        tool_class=ToolClass.WEB_SEARCH,
        sources=("https://docs.example.com/a",),
        gateway_usage=usage(),
        credits_used=0,
        queried_at=datetime(2026, 7, 3, tzinfo=UTC),
    )

    updated = ledger.record(entry)

    assert ledger.entries == ()
    assert updated.entries == (entry,)
    with pytest.raises(ValidationError):
        EvidenceLedgerEntry(
            run_id="run-1",
            session_id=None,
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
            tool_class=ToolClass.WEB_SEARCH,
            queried_at=datetime(2026, 7, 3, tzinfo=UTC),
            sources=(),
            billing_units=-1,
            cost_usd=Decimal("0"),
        )
