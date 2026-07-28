from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolClass
from optimus.usage.errors import DuplicateGatewayRequestError


def _settled_fingerprint(
    entry: EvidenceLedgerEntry,
) -> tuple[str, str, str | None, int, Decimal]:
    """Settled-facts fingerprint mirroring Redis ``record_settled_usage``'s claim fields."""
    return (
        entry.gateway_request_id,
        entry.provider,
        entry.provider_request_id,
        entry.billing_units,
        entry.cost_usd,
    )


class EvidenceLedgerEntry(BaseModel):
    """Immutable audit record for one authorized evidence tool call.

    Captures why the call was made (``reason`` -- the policy reason code --,
    ``policy_signal``, ``tool_class``), what sources were touched, and
    gateway-reported usage/cost fields copied verbatim from ``GatewayUsage``
    -- never estimated after the fact. ``evidence_id`` and ``request_id`` are
    derived deterministically from ``run_id``/``gateway_request_id`` so an
    identical replay of the same call produces a byte-identical entry,
    which is what makes idempotent ledger recording possible.
    """

    model_config = ConfigDict(frozen=True)

    # Identity (LLD v2.39 SS9E)
    evidence_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    request_id: str = Field(min_length=1)
    # Policy context at authorization time
    reason: EvidenceReasonCode
    policy_signal: str = Field(min_length=1)
    tool_class: ToolClass
    queried_at: datetime
    sources: tuple[str, ...] = ()
    trust: Literal["untrusted"] = "untrusted"
    # Gateway usage envelope (populated from response, not derived locally)
    gateway_request_id: str = ""
    provider: str = ""
    provider_request_id: str | None = None
    cache_hit: bool = False
    billing_units: int = Field(default=0, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    model: str | None = None
    model_version: str | None = None
    resolved_provider: str | None = None
    resolved_model: str | None = None

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
        queried_at: datetime,
    ) -> EvidenceLedgerEntry:
        """Build an entry by copying gateway usage fields without transformation."""
        return cls(
            evidence_id=f"{run_id}:{gateway_usage.gateway_request_id}",
            run_id=run_id,
            session_id=session_id,
            request_id=gateway_usage.gateway_request_id,
            reason=reason,
            policy_signal=policy_signal,
            tool_class=tool_class,
            queried_at=queried_at,
            sources=sources,
            gateway_request_id=gateway_usage.gateway_request_id,
            provider=gateway_usage.provider,
            provider_request_id=gateway_usage.provider_request_id,
            cache_hit=gateway_usage.cache_hit,
            billing_units=gateway_usage.billing_units,
            cost_usd=gateway_usage.cost_usd,
            model=gateway_usage.model,
            model_version=gateway_usage.model_version,
            resolved_provider=gateway_usage.resolved_provider,
            resolved_model=gateway_usage.resolved_model,
        )


class EvidenceLedger(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: tuple[EvidenceLedgerEntry, ...] = ()

    def record(self, entry: EvidenceLedgerEntry) -> EvidenceLedger:
        """Append ``entry`` keyed by ``gateway_request_id``, idempotently.

        Same-ID replays are compared on the settled-facts fingerprint alone --
        ``gateway_request_id``, ``provider``, ``provider_request_id``, ``billing_units``,
        ``cost_usd`` -- mirroring the Redis ``record_settled_usage`` claim. Caller-side
        bookkeeping fields such as ``request_id``/``queried_at`` legitimately differ across
        a genuine Gateway-level retry and must not trigger a false divergence. A same-ID
        record whose settled facts diverge raises ``DuplicateGatewayRequestError`` before a
        second entry is ever appended.
        """
        existing = self._entry_for_gateway_request(entry.gateway_request_id)
        if existing is not None:
            if _settled_fingerprint(existing) == _settled_fingerprint(entry):
                return self
            raise DuplicateGatewayRequestError(entry.gateway_request_id)
        return EvidenceLedger(entries=(*self.entries, entry))

    def _entry_for_gateway_request(self, gateway_request_id: str) -> EvidenceLedgerEntry | None:
        for entry in self.entries:
            if entry.gateway_request_id == gateway_request_id:
                return entry
        return None

    def entries_for_run(self, run_id: str) -> tuple[EvidenceLedgerEntry, ...]:
        return tuple(entry for entry in self.entries if entry.run_id == run_id)

    def _matching_entries(self, run_id: str | None) -> tuple[EvidenceLedgerEntry, ...]:
        if run_id is None:
            return self.entries
        return self.entries_for_run(run_id)

    def total_billing_units(self, *, run_id: str | None = None) -> int:
        return sum(entry.billing_units for entry in self._matching_entries(run_id))

    def total_cost_usd(self, *, run_id: str | None = None) -> Decimal:
        return sum((entry.cost_usd for entry in self._matching_entries(run_id)), Decimal("0"))

    def gateway_request_ids(self, *, run_id: str | None = None) -> frozenset[str]:
        entries = self.entries if run_id is None else self.entries_for_run(run_id)
        return frozenset(entry.gateway_request_id for entry in entries if entry.gateway_request_id)
