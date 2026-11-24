from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from optimus.usage.errors import DuplicateGatewayRequestError
from optimus.usage.models import ProviderUsage


class SettledEntry(Protocol):
    """The settled Gateway facts a ledger entry carries (``ProviderUsage``, ``EvidenceLedgerEntry``)."""

    @property
    def gateway_request_id(self) -> str: ...
    @property
    def provider(self) -> str: ...
    @property
    def provider_request_id(self) -> str | None: ...
    @property
    def billing_units(self) -> int: ...
    @property
    def cost_usd(self) -> Decimal: ...


_Entry = TypeVar("_Entry", bound=SettledEntry)


def settled_fingerprint(entry: SettledEntry) -> tuple[str, str, str | None, int, Decimal]:
    """Settled-facts fingerprint mirroring Redis ``record_settled_usage``'s claim fields."""
    return (
        entry.gateway_request_id,
        entry.provider,
        entry.provider_request_id,
        entry.billing_units,
        entry.cost_usd,
    )


def append_settled(entries: tuple[_Entry, ...], entry: _Entry) -> tuple[_Entry, ...] | None:
    """Append ``entry`` keyed by ``gateway_request_id``, idempotently; ``None`` means a replay.

    Same-ID replays are compared on the settled-facts fingerprint alone --
    ``gateway_request_id``, ``provider``, ``provider_request_id``, ``billing_units``,
    ``cost_usd`` -- mirroring the Redis ``record_settled_usage`` claim. Caller-side
    bookkeeping fields such as ``request_id``/``occurred_at``/``queried_at`` legitimately
    differ across a genuine Gateway-level retry and must not trigger a false divergence. A
    same-ID record whose settled facts diverge raises ``DuplicateGatewayRequestError`` before
    a second entry is ever appended. Shared by ``ProviderUsageLedger`` and ``EvidenceLedger``.
    """
    existing = next((e for e in entries if e.gateway_request_id == entry.gateway_request_id), None)
    if existing is not None:
        if settled_fingerprint(existing) == settled_fingerprint(entry):
            return None
        raise DuplicateGatewayRequestError(entry.gateway_request_id)
    return (*entries, entry)


def sum_cost_usd(entries: Iterable[SettledEntry]) -> Decimal:
    return sum((entry.cost_usd for entry in entries), Decimal("0"))


def sum_billing_units(entries: Iterable[SettledEntry]) -> int:
    return sum(entry.billing_units for entry in entries)


class ProviderUsageLedger(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: tuple[ProviderUsage, ...] = ()

    def record(self, usage: ProviderUsage) -> ProviderUsageLedger:
        """Append ``usage`` idempotently by the settled-facts rule of :func:`append_settled`."""
        entries = append_settled(self.entries, usage)
        return self if entries is None else ProviderUsageLedger(entries=entries)

    def entries_for_run(self, run_id: str | None = None) -> tuple[ProviderUsage, ...]:
        if run_id is None:
            return self.entries
        return tuple(entry for entry in self.entries if entry.run_id == run_id)

    def gateway_request_ids(self, *, run_id: str | None = None) -> frozenset[str]:
        return frozenset(entry.gateway_request_id for entry in self.entries_for_run(run_id))

    def total_cost_usd(self, *, run_id: str | None = None) -> Decimal:
        return sum_cost_usd(self.entries_for_run(run_id))

    def total_billing_units(self, *, run_id: str | None = None) -> int:
        return sum_billing_units(self.entries_for_run(run_id))
