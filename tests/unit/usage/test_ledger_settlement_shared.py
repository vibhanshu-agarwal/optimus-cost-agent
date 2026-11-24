"""#341: the evidence and provider-usage ledgers settle a Gateway request by one rule.

A replay with the same ``gateway_request_id`` and the same settled facts is a no-op; the same id with
different settled facts raises ``DuplicateGatewayRequestError`` before anything is appended.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.usage import ledger as usage_ledger
from optimus.usage.errors import DuplicateGatewayRequestError
from optimus.usage.ledger import ProviderUsageLedger
from optimus.usage.models import ProviderUsage

_SETTLED = {"provider": "prov", "provider_request_id": "prov-1", "billing_units": 3, "cost_usd": Decimal("0.003")}
_SETTLED_OTHER = {"billing_units": 5, "cost_usd": Decimal("0.010")}


def _evidence(gateway_request_id: str = "gw-1", **changes: Any) -> EvidenceLedgerEntry:
    fields: dict[str, Any] = {
        "evidence_id": f"run-1:{gateway_request_id}",
        "run_id": "run-1",
        "session_id": "sess-1",
        "request_id": "req-1",
        "reason": EvidenceReasonCode.USER_REQUESTED,
        "policy_signal": ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        "tool_class": ToolClass.WEB_SEARCH,
        "queried_at": datetime(2026, 7, 3, tzinfo=UTC),
        "gateway_request_id": gateway_request_id,
        **_SETTLED,
    }
    return EvidenceLedgerEntry.model_validate({**fields, **changes})


def _usage(gateway_request_id: str = "gw-1", **changes: Any) -> ProviderUsage:
    fields: dict[str, Any] = {
        "run_id": "run-1",
        "session_id": "sess-1",
        "request_id": "req-1",
        "occurred_at": datetime(2026, 7, 3, tzinfo=UTC),
        "gateway_request_id": gateway_request_id,
        "service": "web.search",
        "native_unit": "request",
        **_SETTLED,
    }
    return ProviderUsage.model_validate({**fields, **changes})


# Caller-side bookkeeping each entry type carries; none of it is a settled fact. ``run_id`` is
# among them today: a same-id replay under another run is dropped, not counted in that run.
_EVIDENCE_BOOKKEEPING = {
    "evidence_id": "other",
    "run_id": "run-2",
    "session_id": None,
    "request_id": "req-retry",
    "queried_at": datetime(2026, 7, 4, tzinfo=UTC),
    "sources": ("https://docs.example.com/b",),
    "cache_hit": True,
    "model": "m",
}
_USAGE_BOOKKEEPING = {
    "run_id": "run-2",
    "session_id": None,
    "request_id": "req-retry",
    "occurred_at": datetime(2026, 7, 4, tzinfo=UTC),
    "service": "package.lookup",
    "cache_hit": True,
    "model": "m",
    "input_tokens": 7,
}

LEDGERS = pytest.mark.parametrize(
    ("ledger_type", "make", "bookkeeping"),
    [
        pytest.param(EvidenceLedger, _evidence, _EVIDENCE_BOOKKEEPING, id="evidence"),
        pytest.param(ProviderUsageLedger, _usage, _USAGE_BOOKKEEPING, id="provider_usage"),
    ],
)
Make = Callable[..., Any]

# ``gateway_request_id`` is the fifth settled field; differing in it is a different request, not a replay.
_DIVERGENT = [
    pytest.param({"provider": "other"}, id="provider"),
    pytest.param({"provider_request_id": "prov-2"}, id="provider_request_id"),
    pytest.param({"provider_request_id": None}, id="provider_request_id_none"),
    pytest.param({"billing_units": 4}, id="billing_units"),
    pytest.param({"cost_usd": Decimal("0.004")}, id="cost_usd"),
]


@LEDGERS
def test_first_record_appends_and_returns_a_new_ledger(ledger_type: Any, make: Make, bookkeeping: dict) -> None:
    empty = ledger_type()
    entry = make()

    recorded = empty.record(entry)

    assert type(recorded) is ledger_type
    assert recorded.entries == (entry,)
    assert empty.entries == ()


@LEDGERS
def test_exact_replay_returns_the_same_ledger_object(ledger_type: Any, make: Make, bookkeeping: dict) -> None:
    ledger = ledger_type().record(make())

    assert ledger.record(make()) is ledger


@LEDGERS
def test_replay_differing_only_in_bookkeeping_is_a_no_op(ledger_type: Any, make: Make, bookkeeping: dict) -> None:
    first = make()
    ledger = ledger_type().record(first)

    assert ledger.record(make(**bookkeeping)) is ledger
    assert ledger.entries == (first,)


@LEDGERS
@pytest.mark.parametrize("divergence", _DIVERGENT)
def test_divergent_settled_fact_raises_and_appends_nothing(ledger_type: Any, make: Make, bookkeeping: dict, divergence: dict) -> None:
    first = make()
    ledger = ledger_type().record(first)

    with pytest.raises(DuplicateGatewayRequestError) as raised:
        ledger.record(make(**divergence))

    assert raised.value.gateway_request_id == "gw-1"
    assert ledger.entries == (first,)


@LEDGERS
def test_equal_decimal_cost_with_another_exponent_is_a_replay(ledger_type: Any, make: Make, bookkeeping: dict) -> None:
    ledger = ledger_type().record(make())

    assert ledger.record(make(cost_usd=Decimal("0.0030"))) is ledger


@LEDGERS
def test_two_ids_are_both_recorded_in_order(ledger_type: Any, make: Make, bookkeeping: dict) -> None:
    first, second = make("gw-1"), make("gw-2", **_SETTLED_OTHER)

    ledger = ledger_type().record(first).record(second)

    assert ledger.entries == (first, second)


@LEDGERS
def test_totals_with_and_without_run_id(ledger_type: Any, make: Make, bookkeeping: dict) -> None:
    ledger = ledger_type().record(make("gw-1")).record(make("gw-2", run_id="run-2", **_SETTLED_OTHER))

    assert ledger.total_cost_usd() == Decimal("0.013")
    assert ledger.total_billing_units() == 8
    assert ledger.total_cost_usd(run_id="run-1") == Decimal("0.003")
    assert ledger.total_billing_units(run_id="run-1") == 3
    assert ledger.total_cost_usd(run_id="run-2") == Decimal("0.010")
    assert ledger.total_billing_units(run_id="run-2") == 5
    assert ledger.total_cost_usd(run_id="none") == Decimal("0")
    assert ledger.total_billing_units(run_id="none") == 0
    assert ledger_type().total_cost_usd() == Decimal("0")
    assert ledger_type().total_billing_units() == 0


@LEDGERS
def test_record_never_mutates_the_ledger_it_was_called_on(ledger_type: Any, make: Make, bookkeeping: dict) -> None:
    one = ledger_type().record(make("gw-1"))
    snapshot = one.model_dump()

    two = one.record(make("gw-2"))
    with pytest.raises(DuplicateGatewayRequestError):
        two.record(make("gw-1", billing_units=9))

    assert two is not one
    assert one.model_dump() == snapshot
    assert len(two.entries) == 2


@LEDGERS
def test_both_ledgers_settle_through_the_one_shared_fingerprint(
    ledger_type: Any, make: Make, bookkeeping: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A private copy of the rule in either ledger would ignore this patch and treat the replay as a no-op.
    ledger = ledger_type().record(make())
    monkeypatch.setattr(usage_ledger, "settled_fingerprint", lambda entry: (entry.request_id,))

    with pytest.raises(DuplicateGatewayRequestError):
        ledger.record(make(request_id="req-retry"))


def test_evidence_entries_with_the_default_empty_id_settle_against_each_other() -> None:
    # The evidence entry defaults gateway_request_id to ""; ProviderUsage rejects an empty id.
    first = _evidence(gateway_request_id="")
    ledger = EvidenceLedger().record(first)

    assert ledger.record(_evidence(gateway_request_id="", request_id="r2")) is ledger
    with pytest.raises(DuplicateGatewayRequestError):
        ledger.record(_evidence(gateway_request_id="", cost_usd=Decimal("1")))
    assert ledger.entries == (first,)


@LEDGERS
def test_the_first_entry_with_an_id_is_the_one_a_replay_is_compared_with(ledger_type: Any, make: Make, bookkeeping: dict) -> None:
    # Both models accept a tuple that already holds two entries with one id; the first one decides.
    first, second = make("gw-1"), make("gw-1", **_SETTLED_OTHER)
    ledger = ledger_type(entries=(first, second))

    assert ledger.record(first) is ledger
    with pytest.raises(DuplicateGatewayRequestError):
        ledger.record(second)


@LEDGERS
def test_empty_totals_are_a_decimal_zero_and_an_int_zero(ledger_type: Any, make: Make, bookkeeping: dict) -> None:
    ledger = ledger_type()

    cost, units = ledger.total_cost_usd(), ledger.total_billing_units()
    assert type(cost) is Decimal and cost == 0
    assert type(units) is int and units == 0
