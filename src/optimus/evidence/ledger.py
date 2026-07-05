from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolClass


class EvidenceLedgerEntry(BaseModel):
    """Immutable audit record for one authorized evidence tool call.

    Captures why the call was made (reason, policy signal, tool class), what
    sources were touched, and gateway-reported usage/cost fields copied verbatim
    from ``GatewayUsage`` — never estimated after the fact.
    """

    model_config = ConfigDict(frozen=True)

    # Run attribution
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    # Policy context at authorization time
    reason: EvidenceReasonCode
    policy_signal: str = Field(min_length=1)
    tool_class: ToolClass
    queried_at: datetime
    sources: tuple[str, ...] = ()
    credits_used: int = Field(default=0, ge=0)
    # Gateway usage envelope (populated from response, not derived locally)
    gateway_request_id: str = ""
    provider: str = ""
    provider_request_id: str | None = None
    cache_hit: bool = False
    billing_units: int = Field(default=0, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))

    @classmethod
    def from_gateway_usage(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        reason: EvidenceReasonCode,
        policy_signal: str,
        tool_class: ToolClass,
        sources: tuple[str, ...],
        gateway_usage: GatewayUsage,
        credits_used: int,
        queried_at: datetime,
    ) -> EvidenceLedgerEntry:
        """Build an entry by copying gateway usage fields without transformation."""
        return cls(
            run_id=run_id,
            session_id=session_id,
            reason=reason,
            policy_signal=policy_signal,
            tool_class=tool_class,
            queried_at=queried_at,
            sources=sources,
            credits_used=credits_used,
            gateway_request_id=gateway_usage.gateway_request_id,
            provider=gateway_usage.provider,
            provider_request_id=gateway_usage.provider_request_id,
            cache_hit=gateway_usage.cache_hit,
            billing_units=gateway_usage.billing_units,
            cost_usd=gateway_usage.cost_usd,
        )


class EvidenceLedger(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: tuple[EvidenceLedgerEntry, ...] = ()

    def record(self, entry: EvidenceLedgerEntry) -> EvidenceLedger:
        return EvidenceLedger(entries=(*self.entries, entry))

    def entries_for_run(self, run_id: str) -> tuple[EvidenceLedgerEntry, ...]:
        return tuple(entry for entry in self.entries if entry.run_id == run_id)

    def _matching_entries(self, run_id: str | None) -> tuple[EvidenceLedgerEntry, ...]:
        if run_id is None:
            return self.entries
        return self.entries_for_run(run_id)

    def total_credits(self, *, run_id: str | None = None) -> int:
        return sum(entry.credits_used for entry in self._matching_entries(run_id))

    def total_billing_units(self, *, run_id: str | None = None) -> int:
        return sum(entry.billing_units for entry in self._matching_entries(run_id))

    def total_cost_usd(self, *, run_id: str | None = None) -> Decimal:
        return sum((entry.cost_usd for entry in self._matching_entries(run_id)), Decimal("0"))

    def gateway_request_ids(self, *, run_id: str | None = None) -> frozenset[str]:
        entries = self.entries if run_id is None else self.entries_for_run(run_id)
        return frozenset(entry.gateway_request_id for entry in entries if entry.gateway_request_id)
