from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from optimus.usage.models import ProviderUsage


class ProviderUsageLedger(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: tuple[ProviderUsage, ...] = ()

    def record(self, usage: ProviderUsage) -> ProviderUsageLedger:
        return ProviderUsageLedger(entries=(*self.entries, usage))

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

    def total_optimus_credits(self, *, run_id: str | None = None) -> Decimal:
        return sum(
            (entry.optimus_credits_debited for entry in self.entries_for_run(run_id)),
            Decimal("0"),
        )
