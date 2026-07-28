from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from optimus.usage.errors import DuplicateGatewayRequestError
from optimus.usage.models import ProviderUsage


def _settled_fingerprint(usage: ProviderUsage) -> tuple[str, str, str | None, int, Decimal]:
    """Settled-facts fingerprint mirroring Redis ``record_settled_usage``'s claim fields."""
    return (
        usage.gateway_request_id,
        usage.provider,
        usage.provider_request_id,
        usage.billing_units,
        usage.cost_usd,
    )


class ProviderUsageLedger(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: tuple[ProviderUsage, ...] = ()

    def record(self, usage: ProviderUsage) -> ProviderUsageLedger:
        """Append ``usage`` keyed by ``gateway_request_id``, idempotently.

        Same-ID replays are compared on the settled-facts fingerprint alone --
        ``gateway_request_id``, ``provider``, ``provider_request_id``, ``billing_units``,
        ``cost_usd`` -- mirroring the Redis ``record_settled_usage`` claim. Caller-side
        bookkeeping fields such as ``request_id``/``occurred_at`` legitimately differ across
        a genuine Gateway-level retry and must not trigger a false divergence. A same-ID
        record whose settled facts diverge raises ``DuplicateGatewayRequestError`` before a
        second entry is ever appended.
        """
        existing = self._entry_for_gateway_request(usage.gateway_request_id)
        if existing is not None:
            if _settled_fingerprint(existing) == _settled_fingerprint(usage):
                return self
            raise DuplicateGatewayRequestError(usage.gateway_request_id)
        return ProviderUsageLedger(entries=(*self.entries, usage))

    def _entry_for_gateway_request(self, gateway_request_id: str) -> ProviderUsage | None:
        for entry in self.entries:
            if entry.gateway_request_id == gateway_request_id:
                return entry
        return None

    def entries_for_run(self, run_id: str | None = None) -> tuple[ProviderUsage, ...]:
        if run_id is None:
            return self.entries
        return tuple(entry for entry in self.entries if entry.run_id == run_id)

    def gateway_request_ids(self, *, run_id: str | None = None) -> frozenset[str]:
        return frozenset(entry.gateway_request_id for entry in self.entries_for_run(run_id))

    def total_cost_usd(self, *, run_id: str | None = None) -> Decimal:
        return sum((entry.cost_usd for entry in self.entries_for_run(run_id)), Decimal("0"))

    def total_billing_units(self, *, run_id: str | None = None) -> int:
        return sum(entry.billing_units for entry in self.entries_for_run(run_id))
