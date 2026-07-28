from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.usage.errors import DuplicateGatewayRequestError


def usage(gateway_request_id: str = "gw-1", cost: str = "0.003", units: int = 3) -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id=gateway_request_id,
        provider="tavily",
        provider_request_id="provider-1",
        cache_hit=False,
        billing_units=units,
        cost_usd=Decimal(cost),
        model="tavily-search",
        model_version="v1",
        resolved_provider="tavily-resolved",
        resolved_model="tavily-search-v1",
    )


def build_entry(**overrides) -> EvidenceLedgerEntry:
    kwargs = dict(
        run_id="run-1",
        session_id="session-1",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        tool_class=ToolClass.WEB_SEARCH,
        sources=("https://docs.example.com/a",),
        gateway_usage=usage(),
        queried_at=datetime(2026, 7, 3, tzinfo=UTC),
    )
    kwargs.update(overrides)
    return EvidenceLedgerEntry.from_gateway_usage(**kwargs)


def test_entry_from_gateway_usage_copies_fields_verbatim():
    entry = build_entry()

    assert entry.run_id == "run-1"
    assert entry.session_id == "session-1"
    assert entry.gateway_request_id == "gw-1"
    assert entry.provider == "tavily"
    assert entry.provider_request_id == "provider-1"
    assert entry.cache_hit is False
    assert entry.billing_units == 3
    assert entry.cost_usd == Decimal("0.003")
    assert entry.sources == ("https://docs.example.com/a",)


def test_entry_carries_lld_required_identity_provenance_and_policy_fields():
    """LLD v2.39 SS9E: evidence entries carry evidence/run/session/request/Gateway/provider
    IDs, provider/model/version, resolved provider/model, cache, billing units, USD cost,
    provenance, trust, and the policy reason -- with no legacy credit-named field. The
    existing ``reason``/``policy_signal``/``tool_class`` fields are the preserved Plan 11.4
    policy-custody surface and are what this design treats as the "policy reason" fields
    named by the LLD -- they are not renamed.
    """
    entry = build_entry()

    assert entry.evidence_id
    assert entry.request_id
    assert entry.gateway_request_id == "gw-1"
    assert entry.provider == "tavily"
    assert entry.model == "tavily-search"
    assert entry.model_version == "v1"
    assert entry.resolved_provider == "tavily-resolved"
    assert entry.resolved_model == "tavily-search-v1"
    assert entry.trust == "untrusted"
    assert entry.reason is EvidenceReasonCode.USER_REQUESTED
    assert entry.policy_signal == ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value
    assert entry.tool_class is ToolClass.WEB_SEARCH
    assert entry.billing_units == 3
    assert entry.cost_usd == Decimal("0.003")
    assert not hasattr(entry, "credits_used")
    assert not hasattr(entry, "optimus_credits_debited")
    assert not hasattr(EvidenceLedger(), "total_credits")


def test_ledger_totals_reconcile_gateway_usage_fields():
    first = build_entry(gateway_usage=usage("gw-1", "0.003", 3))
    second = build_entry(
        run_id="run-1",
        session_id=None,
        reason=EvidenceReasonCode.CURRENT_FACT,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT.value,
        tool_class=ToolClass.WEB_EXTRACT,
        sources=("https://docs.example.com/a",),
        gateway_usage=usage("gw-2", "0.005", 5),
        queried_at=datetime(2026, 7, 3, 0, 0, 1, tzinfo=UTC),
    )

    ledger = EvidenceLedger().record(first).record(second)

    assert ledger.total_billing_units() == 8
    assert ledger.total_cost_usd() == Decimal("0.008")
    assert ledger.total_cost_usd(run_id="run-1") == Decimal("0.008")
    assert ledger.total_cost_usd(run_id="other-run") == Decimal("0")


def test_ledger_preserves_verbatim_billing_units_and_cost_without_fabrication():
    """The Gateway tool envelope is the only source of billing_units/cost_usd; nothing
    here estimates or invents a value beyond what the envelope reports (replaces the
    retired ``test_ledger_credits_used_stays_zero_when_gateway_envelope_carries_no_credit_field``,
    since ``credits_used`` no longer exists on this model)."""
    entry = build_entry(gateway_usage=usage("gw-1", "0.003", 3))

    ledger = EvidenceLedger().record(entry)

    assert ledger.total_billing_units() == 3
    assert ledger.total_cost_usd() == Decimal("0.003")


def test_ledger_record_returns_new_append_only_instance():
    ledger = EvidenceLedger()
    entry = build_entry()

    updated = ledger.record(entry)

    assert ledger.entries == ()
    assert updated.entries == (entry,)
    with pytest.raises(ValidationError):
        EvidenceLedgerEntry(
            evidence_id="ev-1",
            run_id="run-1",
            session_id=None,
            request_id="req-1",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
            tool_class=ToolClass.WEB_SEARCH,
            queried_at=datetime(2026, 7, 3, tzinfo=UTC),
            sources=(),
            billing_units=-1,
            cost_usd=Decimal("0"),
        )


def test_ledger_record_is_idempotent_and_rejects_divergence():
    entry = build_entry(gateway_usage=usage("gw-1", "0.001", 10))
    ledger = EvidenceLedger().record(entry)

    duplicate = build_entry(gateway_usage=usage("gw-1", "0.001", 10))
    assert ledger.record(duplicate) == ledger

    divergent = build_entry(gateway_usage=usage("gw-1", "0.002", 10))
    with pytest.raises(DuplicateGatewayRequestError, match="gw-1"):
        ledger.record(divergent)
