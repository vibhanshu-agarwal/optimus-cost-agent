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
