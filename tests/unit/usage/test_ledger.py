from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.usage.errors import DuplicateGatewayRequestError
from optimus.usage.ledger import ProviderUsageLedger
from optimus.usage.models import ProviderUsage


def usage(gateway_request_id: str, cost: str, units: int) -> ProviderUsage:
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
        model="glm-5.2",
        model_version="2026-06-01",
        price_snapshot_id="prices-2026-07-04",
    )


def provider_usage(gateway_request_id: str, cost: str, units: int) -> ProviderUsage:
    return usage(gateway_request_id, cost, units)


def test_provider_usage_ledger_is_append_only_and_totals_reconcile():
    ledger = ProviderUsageLedger()
    first = usage("gw-1", "0.001", 10)
    second = usage("gw-2", "0.002", 20)

    updated = ledger.record(first).record(second)

    assert ledger.entries == ()
    assert updated.entries == (first, second)
    assert updated.total_cost_usd() == Decimal("0.003")
    assert updated.total_billing_units() == 30
    assert updated.entries_for_run(None) == (first, second)
    assert updated.entries_for_run("run-1") == (first, second)
    assert updated.gateway_request_ids() == frozenset({"gw-1", "gw-2"})
    assert updated.gateway_request_ids(run_id="run-1") == frozenset({"gw-1", "gw-2"})
    assert not hasattr(updated, "total_optimus_credits")


def test_provider_usage_ledger_is_idempotent_and_rejects_divergence():
    ledger = ProviderUsageLedger().record(provider_usage("gw-1", "0.001", 10))
    assert ledger.record(provider_usage("gw-1", "0.001", 10)) == ledger
    with pytest.raises(DuplicateGatewayRequestError, match="gw-1"):
        ledger.record(provider_usage("gw-1", "0.002", 10))


def test_provider_usage_ledger_replay_with_different_bookkeeping_is_idempotent():
    """A genuine Gateway-level retry reuses the same ``gateway_request_id`` and settled
    facts but is re-recorded by the caller with a fresh ``request_id``/``occurred_at``.
    That must be treated as the same settled fact, not a divergent duplicate."""
    first = usage("gw-1", "0.001", 10)
    ledger = ProviderUsageLedger().record(first)

    replay = first.model_copy(
        update={
            "request_id": "req-retry-2",
            "occurred_at": datetime(2026, 7, 5, tzinfo=UTC),
        }
    )

    assert ledger.record(replay) == ledger


def test_provider_usage_ledger_rejects_divergent_settled_facts():
    first = usage("gw-1", "0.001", 10)
    ledger = ProviderUsageLedger().record(first)

    with pytest.raises(DuplicateGatewayRequestError, match="gw-1"):
        ledger.record(first.model_copy(update={"provider": "openai"}))
    with pytest.raises(DuplicateGatewayRequestError, match="gw-1"):
        ledger.record(first.model_copy(update={"billing_units": 99}))
    with pytest.raises(DuplicateGatewayRequestError, match="gw-1"):
        ledger.record(first.model_copy(update={"provider_request_id": "provider-req-2"}))
