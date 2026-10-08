"""Cost alerts over settled receipts - alerts, never stops (Plan 12.2 Task 11; design spec 11; Task 1
contracts 6; operator ruling 2026-09-30).

Thresholds are explicit operator configuration in increasing USD amounts; nothing here invents one.
`evaluate_alerts` reports every threshold the known subtotal has reached. An incomplete total still
crosses on what is known - the real cost is at least that - and its notice says the total is
incomplete. `AlertTracker` reports each scope/threshold crossing once; a higher threshold still
reports. A daily scope needs an explicit IANA timezone and a reconciled durable ledger
(`P9.85-FU-3`); without them it is unavailable, never a fake zero. No alert refuses, stops or delays
any product request.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCOPES = frozenset({"turn", "session", "day"})


@dataclass(frozen=True, slots=True)
class AlertPolicy:
    scope: str
    thresholds_usd: tuple[Decimal, ...]
    day_timezone: str | None = None

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise ValueError(f"unknown alert scope {self.scope!r}")
        values = self.thresholds_usd
        if not values or any(not value.is_finite() or value <= 0 for value in values):
            raise ValueError("thresholds must be positive finite amounts")
        if any(later <= earlier for earlier, later in zip(values, values[1:], strict=False)):
            raise ValueError("thresholds must strictly increase")
        if self.scope == "day":
            if not self.day_timezone:
                raise ValueError("a daily alert needs an explicit IANA timezone")
            try:
                ZoneInfo(self.day_timezone)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"unknown timezone {self.day_timezone!r}") from exc


@dataclass(frozen=True, slots=True)
class CostScopeSummary:
    """A scope's settled cost. A daily summary names its day and timezone and whether it comes from a
    reconciled durable ledger."""

    scope: str
    scope_id: str
    known_subtotal_usd: Decimal
    complete: bool
    day: date | None = None
    timezone: str | None = None
    reconciled: bool = False


@dataclass(frozen=True, slots=True)
class CostNotice:
    scope: str
    scope_id: str
    threshold_usd: Decimal
    known_subtotal_usd: Decimal
    complete: bool
    text: str

    @property
    def identity(self) -> tuple[str, str, Decimal]:
        return (self.scope, self.scope_id, self.threshold_usd)


def _notice_text(scope: str, threshold: Decimal, known: Decimal, complete: bool) -> str:
    if complete:
        return f"Cost alert: this {scope}'s model costs have reached ${threshold} (now ${known})."
    return (
        f"Cost alert: this {scope}'s model costs have reached ${threshold} (at least ${known}; some "
        "costs are unknown, so the total is incomplete)."
    )


def evaluate_alerts(summary: CostScopeSummary, policy: AlertPolicy) -> tuple[CostNotice, ...]:
    """Every threshold `summary` has reached, or nothing when its scope is unavailable."""
    if summary.scope != policy.scope:
        raise ValueError("the summary and the policy are for different scopes")
    if summary.scope == "day" and (not summary.reconciled or summary.day is None or summary.timezone != policy.day_timezone):
        return ()
    known = summary.known_subtotal_usd
    return tuple(
        CostNotice(
            scope=summary.scope,
            scope_id=summary.scope_id,
            threshold_usd=threshold,
            known_subtotal_usd=known,
            complete=summary.complete,
            text=_notice_text(summary.scope, threshold, known, summary.complete),
        )
        for threshold in policy.thresholds_usd
        if known >= threshold
    )


class AlertTracker:
    """Reports each scope/threshold crossing once."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reported: set[tuple[str, str, Decimal]] = set()

    def new_notices(self, summary: CostScopeSummary, policy: AlertPolicy) -> tuple[CostNotice, ...]:
        with self._lock:
            fresh = tuple(notice for notice in evaluate_alerts(summary, policy) if notice.identity not in self._reported)
            self._reported.update(notice.identity for notice in fresh)
            return fresh
