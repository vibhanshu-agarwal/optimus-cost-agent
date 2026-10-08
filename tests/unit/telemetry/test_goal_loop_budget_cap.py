"""Plan 12.2 Task 11: a goal-loop event carries a dollar cap only for an evaluation caller's explicit one.

A product run has no dollar stop, so its event has no cap key at all (Fable CP4 release review m5).
"""

from datetime import UTC, datetime
from decimal import Decimal

from optimus.telemetry.events import TelemetryEvent


def _event(**cap: Decimal) -> dict[str, object]:
    return TelemetryEvent.goal_loop(
        run_id="run-1",
        session_id="session-1",
        request_id="loop-1",
        occurred_at=datetime(2026, 7, 6, tzinfo=UTC),
        iteration=3,
        stop_reason="REPEATED_FAILURE",
        cost_usd_spent=Decimal("0.25"),
        summary="same failure repeated",
        **cap,
    ).to_json_dict()


def test_an_evaluation_callers_explicit_cap_is_recorded() -> None:
    assert _event(max_budget_usd=Decimal("1.00"))["max_budget_usd"] == "1.00"


def test_a_product_run_carries_no_budget_cap() -> None:
    encoded = _event()
    assert "max_budget_usd" not in encoded and encoded["cost_usd_spent"] == "0.25"
