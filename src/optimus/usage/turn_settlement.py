"""Exactly-once stage receipts and turn settlement (Plan 12.2 Task 11; design spec 11; Task 1 contracts 6).

Every actual provider attempt of a turn - planning, answer or summarization - is one `StageReceipt`,
recorded on arrival and independently of the conversation commit or checkpoint acceptance. Identity is
the attempt itself: an identical replay adds nothing; a conflicting duplicate, or a second attempt
claiming the same Gateway request, is an integrity error. An unknown cost stays `None`, never zero, and
the known subtotal keeps every known cost before and after it. A turn's summary is a projection over
its receipts, never a second debit.

Known receipts are also the existing usage ledger's entries (the runner records them through
`UsageAccountingService`); an unknown attempt is a correlation fact, never a fake zero-cost
`ProviderUsage`. Completing the shared telemetry schema remains `P11.26-CAND-2-TELEMETRY-CONTRACT`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optimus.context.maintenance import MaintenanceReceipt

STAGES = frozenset({"planning", "answer", "summarization"})
OUTCOMES = frozenset({"completed", "failed", "not_sent", "rejected", "uncertain"})
_ZERO_COST_OUTCOMES = frozenset({"not_sent", "rejected"})


class ReceiptConflictError(ValueError):
    """A receipt that contradicts one already recorded for the same attempt or Gateway request."""


@dataclass(frozen=True, slots=True)
class StageReceipt:
    """One provider attempt. `reported_cost_usd` is None when unknown, never a stand-in zero."""

    session_id: str | None
    turn_id: str
    stage: str
    attempt_id: str
    gateway_request_id: str | None
    outcome: str
    reported_cost_usd: Decimal | None
    recorded_at: datetime
    requested_model: str | None = None
    resolved_model: str | None = None
    provider: str | None = None
    resolved_provider: str | None = None
    strategy: str | None = None
    revision_digest: str | None = None
    registry_hash: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    post_teardown: bool = False

    def __post_init__(self) -> None:
        if not self.turn_id or not self.attempt_id:
            raise ValueError("a receipt needs its turn and attempt identity")
        if self.stage not in STAGES or self.outcome not in OUTCOMES:
            raise ValueError(f"unknown stage {self.stage!r} or outcome {self.outcome!r}")
        cost = self.reported_cost_usd
        if cost is not None and (not cost.is_finite() or cost < 0):
            raise ValueError("a reported cost must be finite and non-negative")
        if self.outcome == "uncertain" and cost is not None:
            raise ValueError("an uncertain attempt's cost is unknown")
        if self.outcome in _ZERO_COST_OUTCOMES and cost != Decimal("0"):
            raise ValueError("an attempt that was never sent or was refused before any model ran costs nothing")

    def facts(self) -> tuple[object, ...]:
        """What must agree for two receipts of one attempt to be the same attempt. Arrival time and
        caller bookkeeping may differ."""
        return (
            self.session_id,
            self.turn_id,
            self.stage,
            self.attempt_id,
            self.gateway_request_id,
            self.outcome,
            self.reported_cost_usd,
            self.resolved_model,
            self.resolved_provider,
        )


@dataclass(frozen=True, slots=True)
class TurnCostSummary:
    """A turn's settled cost: the known subtotal, every unknown attempt and every receipt."""

    turn_id: str
    known_subtotal_usd: Decimal
    unknown_attempt_ids: tuple[str, ...]
    receipt_ids: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.unknown_attempt_ids


class TurnSettlement:
    """The exactly-once receipt store for one session's turns. Thread-safe: maintenance receipts
    arrive from worker threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._receipts: dict[str, StageReceipt] = {}
        self._attempt_for_gateway: dict[str, str] = {}

    def record_attempt(self, receipt: StageReceipt) -> None:
        with self._lock:
            existing = self._receipts.get(receipt.attempt_id)
            if existing is not None:
                if existing.facts() != receipt.facts():
                    raise ReceiptConflictError(f"attempt {receipt.attempt_id} was already recorded differently")
                return
            gateway_id = receipt.gateway_request_id
            if gateway_id is not None and self._attempt_for_gateway.get(gateway_id, receipt.attempt_id) != receipt.attempt_id:
                raise ReceiptConflictError(f"Gateway request {gateway_id} already belongs to another attempt")
            self._receipts[receipt.attempt_id] = receipt
            if gateway_id is not None:
                self._attempt_for_gateway[gateway_id] = receipt.attempt_id

    def receipts(self, turn_id: str) -> tuple[StageReceipt, ...]:
        with self._lock:
            return tuple(receipt for receipt in self._receipts.values() if receipt.turn_id == turn_id)

    def settle_turn(self, turn_id: str) -> TurnCostSummary:
        return _summary(turn_id, self.receipts(turn_id))

    def settle_all(self) -> TurnCostSummary:
        """Every turn of this store's session together (`turn_id` "*")."""
        with self._lock:
            receipts = tuple(self._receipts.values())
        return _summary("*", receipts)


def _summary(turn_id: str, receipts: tuple[StageReceipt, ...]) -> TurnCostSummary:
    known = sum((r.reported_cost_usd for r in receipts if r.reported_cost_usd is not None), Decimal("0"))
    return TurnCostSummary(
        turn_id=turn_id,
        known_subtotal_usd=known,
        unknown_attempt_ids=tuple(r.attempt_id for r in receipts if r.reported_cost_usd is None),
        receipt_ids=tuple(r.attempt_id for r in receipts),
    )


def receipt_from_maintenance(receipt: MaintenanceReceipt) -> StageReceipt:
    """The stage receipt for one summarization attempt, keyed to the turn it served."""
    identity = receipt.identity
    return StageReceipt(
        session_id=identity.session_id,
        turn_id=f"{identity.session_id}:{identity.turn_seq}",
        stage="summarization",
        attempt_id=receipt.attempt_id,
        gateway_request_id=receipt.gateway_request_id,
        outcome=receipt.outcome,
        reported_cost_usd=receipt.cost_usd,
        recorded_at=receipt.recorded_at,
        requested_model=identity.model_id,
        strategy=identity.strategy,
        revision_digest=identity.revision_digest,
    )
