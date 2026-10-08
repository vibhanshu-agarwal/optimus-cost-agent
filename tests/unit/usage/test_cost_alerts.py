"""Plan 12.2 Task 11: cost alerts, never cost stops (design spec 11; Task 1 contracts 6; operator ruling
2026-09-30, "alerts not limits").

Thresholds are explicit operator configuration; nothing here invents an amount. Each crossing is
reported once per scope/threshold identity, and a higher threshold can still report. An incomplete
total still crosses on its known subtotal, labelled as incomplete. Daily alerts need an explicit IANA
timezone and a reconciled durable ledger; without them the daily scope is unavailable, never a fake
zero. No alert refuses or stops anything.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from optimus.usage.cost_alerts import AlertPolicy, AlertTracker, CostScopeSummary, evaluate_alerts


def session(known: str, *, complete: bool = True, scope_id: str = "s") -> CostScopeSummary:
    return CostScopeSummary(scope="session", scope_id=scope_id, known_subtotal_usd=Decimal(known), complete=complete)


POLICY = AlertPolicy(scope="session", thresholds_usd=(Decimal("1"), Decimal("5")))


def test_no_threshold_crossed_reports_nothing():
    assert evaluate_alerts(session("0.99"), POLICY) == ()


def test_each_crossed_threshold_reports_with_its_identity():
    notices = evaluate_alerts(session("5.20"), POLICY)

    assert [notice.threshold_usd for notice in notices] == [Decimal("1"), Decimal("5")]
    assert notices[0].identity == ("session", "s", Decimal("1"))
    assert "5.20" in notices[1].text and "incomplete" not in notices[1].text


def test_a_crossing_is_reported_once_and_a_higher_one_still_reports():
    tracker = AlertTracker()

    first = tracker.new_notices(session("1.10"), POLICY)
    again = tracker.new_notices(session("1.50"), POLICY)
    higher = tracker.new_notices(session("5.00"), POLICY)

    assert [n.threshold_usd for n in first] == [Decimal("1")]
    assert again == ()
    assert [n.threshold_usd for n in higher] == [Decimal("5")]
    assert tracker.new_notices(session("1.10", scope_id="other"), POLICY)[0].identity == ("session", "other", Decimal("1"))


def test_an_incomplete_total_crosses_on_its_known_subtotal_and_says_so():
    [notice] = evaluate_alerts(session("1.00", complete=False), POLICY)

    assert notice.threshold_usd == Decimal("1") and not notice.complete
    assert "at least" in notice.text and "unknown" in notice.text


DAY = AlertPolicy(scope="day", thresholds_usd=(Decimal("2"),), day_timezone="Asia/Kolkata")


def day(known: str, *, reconciled: bool = True, timezone: str | None = "Asia/Kolkata") -> CostScopeSummary:
    return CostScopeSummary(
        scope="day", scope_id="2026-10-03", known_subtotal_usd=Decimal(known), complete=True,
        day=date(2026, 10, 3), timezone=timezone, reconciled=reconciled,
    )  # fmt: skip


def test_a_daily_alert_needs_a_reconciled_ledger_and_the_policy_timezone():
    assert [n.threshold_usd for n in evaluate_alerts(day("2.50"), DAY)] == [Decimal("2")]
    assert evaluate_alerts(day("9.00", reconciled=False), DAY) == ()  # a process-local counter is no daily total
    assert evaluate_alerts(day("9.00", timezone="UTC"), DAY) == ()
    assert evaluate_alerts(day("9.00", timezone=None), DAY) == ()


@pytest.mark.parametrize(
    "bad",
    [
        {"scope": "session", "thresholds_usd": ()},
        {"scope": "session", "thresholds_usd": (Decimal("5"), Decimal("1"))},
        {"scope": "session", "thresholds_usd": (Decimal("0"),)},
        {"scope": "session", "thresholds_usd": (Decimal("Infinity"),)},
        {"scope": "day", "thresholds_usd": (Decimal("1"),)},
        {"scope": "day", "thresholds_usd": (Decimal("1"),), "day_timezone": "Not/AZone"},
        {"scope": "week", "thresholds_usd": (Decimal("1"),)},
    ],
)
def test_a_policy_outside_the_contract_is_refused(bad):
    with pytest.raises(ValueError):
        AlertPolicy(**bad)


def test_a_summary_for_another_scope_is_refused():
    with pytest.raises(ValueError):
        evaluate_alerts(session("3"), DAY)


def test_the_turn_scope_reports_like_the_session_scope():
    turn = CostScopeSummary(scope="turn", scope_id="s:4", known_subtotal_usd=Decimal("0.5"), complete=True)
    [notice] = evaluate_alerts(turn, AlertPolicy(scope="turn", thresholds_usd=(Decimal("0.25"),)))
    assert notice.identity == ("turn", "s:4", Decimal("0.25"))
