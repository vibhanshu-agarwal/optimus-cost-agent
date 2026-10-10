"""Exactly-once stage receipts and turn settlement (Plan 12.2 Task 11; design spec 11; Task 1 contracts 6).

Every actual provider attempt of a turn - planning, answer or summarization - is one `StageReceipt`,
recorded on arrival and independently of the conversation commit or checkpoint acceptance. Identity is
the attempt itself: an identical replay adds nothing; a duplicate that differs in any reported or
captured fact, or a second attempt claiming the same Gateway request with different facts, is an
integrity error. Only arrival bookkeeping (arrival time, post-teardown arrival) may differ on a replay,
and the first arrival is kept; nothing is enriched later. An unknown cost stays `None`, never zero,
and the known subtotal keeps every known cost before and after it.

A turn's cost is one projection over its receipts, never a second debit. It is published to
subscribers (the conversation's projection) under the store's lock whenever a receipt arrives or a
worker invocation for the turn starts or ends, so a receipt that arrives after the turn's terminal
finalization still updates it, and concurrent publications cannot reorder (Codex CP3 ruling R2). An
invocation still running - for example a worker left behind by transport teardown - keeps its turn
incomplete until it ends, because its attempt may still be billed.

Known receipts keep the Gateway's original normalized usage, so the existing usage ledger can record
them exactly (`UsageLedgerAdapter`); an unknown attempt is a correlation fact, never a fake zero-cost
`ProviderUsage`. Completing the shared telemetry schema remains `P11.26-CAND-2-TELEMETRY-CONTRACT`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from optimus.gateway.models import GatewayUsage

if TYPE_CHECKING:
    from optimus.context.maintenance import MaintenanceReceipt
    from optimus.usage.accounting import UsageAccountingService

STAGES = frozenset({"planning", "answer", "summarization"})
# `unattributed`: usage the Gateway reported but did not attribute to a single completed attempt. Its
# reported cost is known and counts once; its turn is never complete (Codex CP3 correction ruling C1/C2).
OUTCOMES = frozenset({"completed", "failed", "not_sent", "rejected", "uncertain", "unattributed"})
_ZERO_COST_OUTCOMES = frozenset({"not_sent", "rejected"})
# Arrival bookkeeping: may differ between two arrivals of one attempt; the first arrival is kept.
_BOOKKEEPING = frozenset({"recorded_at", "post_teardown"})
# Facts the original usage settles; a receipt carrying that usage repeats them or leaves them unset.
_USAGE_FACTS = ("provider", "resolved_provider", "resolved_model", "input_tokens", "output_tokens", "cached_tokens", "provider_request_id")


class ReceiptConflictError(ValueError):
    """A receipt that contradicts one already recorded for the same attempt or Gateway request."""


@dataclass(frozen=True, slots=True)
class StageReceipt:
    """One provider attempt. `reported_cost_usd` is None when unknown, never a stand-in zero.

    `gateway_usage` is the Gateway's original normalized usage, set only on the attempt that settled
    it; the flattened provider, model and token fields then repeat it. The captured identity -
    requested model, role, route, reasoning, quantizations, registry hash, strategy and history
    revision - is what the request was bound to when it was sent."""

    session_id: str | None
    turn_id: str
    stage: str
    attempt_id: str
    gateway_request_id: str | None
    outcome: str
    reported_cost_usd: Decimal | None
    recorded_at: datetime
    requested_model: str | None = None
    role: str | None = None
    route: tuple[str, ...] = ()
    reasoning: str | None = None
    quantizations: tuple[str | None, ...] = ()
    resolved_model: str | None = None
    provider: str | None = None
    resolved_provider: str | None = None
    strategy: str | None = None
    revision_digest: str | None = None
    registry_hash: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    provider_request_id: str | None = None
    http_status: int | None = None
    gateway_usage: GatewayUsage | None = None
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
        usage = self.gateway_usage
        if self.outcome == "unattributed" and usage is None:
            raise ValueError("an unattributed record is the reported usage itself")
        if usage is None:
            return
        if self.outcome not in {"completed", "unattributed"} or cost != usage.cost_usd or self.gateway_request_id != usage.gateway_request_id:
            raise ValueError("only a completed attempt carries the usage that settled it, with its cost and request")
        for name in _USAGE_FACTS:
            settled = getattr(usage, name)
            current = getattr(self, name)
            if current is None:
                object.__setattr__(self, name, settled)
            elif current != settled:
                raise ValueError(f"a receipt's {name} contradicts the usage it carries")

    def facts(self) -> tuple[object, ...]:
        """Every reported and captured fact of this attempt: what two arrivals of one attempt must
        agree on. Only arrival bookkeeping is left out (Codex CP3 ruling M1)."""
        return tuple(getattr(self, field.name) for field in fields(self) if field.name not in _BOOKKEEPING)

    def settled_facts(self) -> tuple[object, ...]:
        """What a Gateway replay of one request must repeat whichever host attempt carried it: every
        fact except the host attempt's own identity. The existing usage ledger likewise keys a replay
        by its Gateway request."""
        return tuple(
            getattr(self, field.name) for field in fields(self) if field.name not in _BOOKKEEPING and field.name != "attempt_id"
        )


@dataclass(frozen=True, slots=True)
class TurnCostSummary:
    """A turn's settled cost: the known subtotal, every unknown attempt, every receipt, how many
    worker invocations for the turn are still running and how many accounting-integrity failures it
    had (an unattributed usage record, a receipt the store refused as conflicting, or a charge another
    sink - the existing ledger - refused). Any of those keeps it incomplete; known charges still count."""

    turn_id: str
    known_subtotal_usd: Decimal
    unknown_attempt_ids: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    pending_invocations: int = 0
    integrity_failures: int = 0

    @property
    def complete(self) -> bool:
        return not self.unknown_attempt_ids and not self.pending_invocations and not self.integrity_failures


CostSubscriber = Callable[[str, TurnCostSummary], None]


class Invocation:
    """One worker invocation that may make model attempts for a turn (Codex CP3 ruling R2).

    Open it before handing work to a worker thread. The worker calls `start()` first and runs only
    when it returns True, then `end()`. The caller calls `abandon_unstarted()` once it stops waiting:
    a worker that never started is then closed and can never start, so a cancelled hand-off leaves no
    turn pending forever, and a started worker keeps its turn pending until it really ends."""

    def __init__(self, settlement: TurnSettlement, turn_id: str) -> None:
        self._settlement = settlement
        self.turn_id = turn_id
        self.state = "open"

    def start(self) -> bool:
        return self._settlement._transition(self, "open", "started")

    def end(self) -> None:
        self._settlement._transition(self, "started", "ended")

    def abandon_unstarted(self) -> None:
        self._settlement._transition(self, "open", "abandoned")


class TurnSettlement:
    """The exactly-once receipt store for one session's turns. Thread-safe: receipts arrive from
    worker threads."""

    def __init__(self) -> None:
        # Reentrant: a subscriber may read a summary while one is being published.
        self._lock = threading.RLock()
        self._receipts: dict[str, StageReceipt] = {}
        self._attempt_for_gateway: dict[str, str] = {}
        self._pending: dict[str, int] = {}
        self._refused: dict[str, int] = {}
        self._subscribers: list[CostSubscriber] = []

    def subscribe(self, subscriber: CostSubscriber) -> None:
        """Receive a turn's summary whenever it changes, under this store's lock, in order. A
        subscriber must be quick and must not wait on another thread."""
        with self._lock:
            self._subscribers.append(subscriber)

    def open_invocation(self, turn_id: str) -> Invocation:
        with self._lock:
            invocation = Invocation(self, turn_id)
            self._pending[turn_id] = self._pending.get(turn_id, 0) + 1
            self._publish(turn_id)
            return invocation

    def _transition(self, invocation: Invocation, expected: str, new: str) -> bool:
        with self._lock:
            if invocation.state != expected:
                return False
            invocation.state = new
            if new in {"ended", "abandoned"}:
                remaining = self._pending[invocation.turn_id] - 1
                if remaining:
                    self._pending[invocation.turn_id] = remaining
                else:
                    del self._pending[invocation.turn_id]
                self._publish(invocation.turn_id)
            return True

    def record_attempt(self, receipt: StageReceipt) -> None:
        with self._lock:
            existing = self._receipts.get(receipt.attempt_id)
            if existing is not None:
                if existing.facts() != receipt.facts():
                    self.record_integrity_failure(receipt.turn_id)
                    raise ReceiptConflictError(f"attempt {receipt.attempt_id} was already recorded differently")
                return
            gateway_id = receipt.gateway_request_id
            owner = self._attempt_for_gateway.get(gateway_id) if gateway_id is not None else None
            if owner is not None:
                # A host retry that the Gateway answered from the same settled request is a replay:
                # one charge. Different facts for one Gateway request are an integrity error (Fable
                # CP3 review MINOR-7; mirrors ProviderUsageLedger).
                if self._receipts[owner].settled_facts() != receipt.settled_facts():
                    self.record_integrity_failure(receipt.turn_id)
                    raise ReceiptConflictError(f"Gateway request {gateway_id} was already settled differently")
                return
            self._receipts[receipt.attempt_id] = receipt
            if gateway_id is not None:
                self._attempt_for_gateway[gateway_id] = receipt.attempt_id
            self._publish(receipt.turn_id)

    def record_integrity_failure(self, turn_id: str) -> None:
        """The turn's accounting failed: a conflicting receipt this store refused, or a charge another
        sink (the existing ledger) refused. It can never read as complete; what was already settled
        keeps counting, and nothing is charged twice (Fable CP3 correction-2 review MINOR-1)."""
        with self._lock:
            self._refused[turn_id] = self._refused.get(turn_id, 0) + 1
            self._publish(turn_id)

    def project(self, turn_id: str, subscriber: CostSubscriber) -> None:
        """Publish one turn's current summary to `subscriber` alone, ordered with every other
        publication. Idempotent: the summary is recomputed from the receipts each time."""
        with self._lock:
            subscriber(turn_id, self.settle_turn(turn_id))

    def _publish(self, turn_id: str) -> None:
        if self._subscribers:
            summary = self.settle_turn(turn_id)
            for subscriber in self._subscribers:
                subscriber(turn_id, summary)

    def receipts(self, turn_id: str) -> tuple[StageReceipt, ...]:
        with self._lock:
            return tuple(receipt for receipt in self._receipts.values() if receipt.turn_id == turn_id)

    def settle_turn(self, turn_id: str) -> TurnCostSummary:
        with self._lock:
            return _summary(turn_id, self.receipts(turn_id), self._pending.get(turn_id, 0), self._refused.get(turn_id, 0))

    def settle_all(self) -> TurnCostSummary:
        """Every turn of this store's session together (`turn_id` "*")."""
        with self._lock:
            return _summary("*", tuple(self._receipts.values()), sum(self._pending.values()), sum(self._refused.values()))


def _summary(turn_id: str, receipts: tuple[StageReceipt, ...], pending: int, refused: int) -> TurnCostSummary:
    known = sum((r.reported_cost_usd for r in receipts if r.reported_cost_usd is not None), Decimal("0"))
    return TurnCostSummary(
        turn_id=turn_id,
        known_subtotal_usd=known,
        unknown_attempt_ids=tuple(r.attempt_id for r in receipts if r.reported_cost_usd is None),
        receipt_ids=tuple(r.attempt_id for r in receipts),
        pending_invocations=pending,
        integrity_failures=refused + sum(1 for r in receipts if r.outcome == "unattributed"),
    )


def receipt_from_maintenance(receipt: MaintenanceReceipt) -> StageReceipt:
    """The stage receipt for one summarization attempt, keyed to the turn it served, with the
    identity it was bound to and the usage that settled it."""
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
        role=identity.role,
        route=identity.route,
        reasoning=identity.reasoning,
        quantizations=identity.quantizations,
        provider=receipt.provider,
        resolved_provider=receipt.resolved_provider,
        resolved_model=receipt.resolved_model,
        strategy=identity.strategy,
        revision_digest=identity.revision_digest,
        registry_hash=identity.registry_hash,
        provider_request_id=receipt.provider_request_id,
        http_status=receipt.http_status,
        gateway_usage=receipt.gateway_usage,
    )


class UsageLedgerAdapter:
    """Records known summarization receipts in the existing usage ledger (`UsageAccountingService`
    and its `ProviderUsageLedger`), exactly once per Gateway request (Codex CP3 ruling R5).

    Only a receipt carrying the Gateway's original usage becomes a `ProviderUsage`, copied from that
    usage, never reconstructed; an unknown or zero-cost attempt is a correlation fact the settlement
    keeps and the ledger never sees. A replay is idempotent and a divergent same-request record raises,
    both by the ledger's own rule. It records the same facts a second time, in the ledger's existing
    schema; it is never a second debit or a separate spend authority.

    Summaries only: planning and answer usage reaches the same service through the runner's own
    existing path, and accepting those receipts here too would emit their usage telemetry twice. It is
    an injection seam (an attachment's `record_receipt`); no production composition wires it yet."""

    def __init__(self, usage_accounting: UsageAccountingService) -> None:
        self._usage = usage_accounting

    def record(self, receipt: StageReceipt) -> None:
        if receipt.stage != "summarization":
            raise ValueError("planning and answer usage is recorded by the runner's own ledger path")
        usage = receipt.gateway_usage
        if usage is None:
            return
        self._usage.record_gateway_usage(
            usage,
            run_id=receipt.turn_id,
            session_id=receipt.session_id,
            request_id=receipt.attempt_id,
            occurred_at=receipt.recorded_at,
            service="context.summary",
            native_unit="tokens",
            price_snapshot_id=usage.price_snapshot_id,
            turn_seq=_turn_seq(receipt.turn_id),
            post_teardown=receipt.post_teardown,
        )

    def record_maintenance(self, receipt: MaintenanceReceipt) -> None:
        """An attachment's `record_receipt` sink for its summarization attempts."""
        self.record(receipt_from_maintenance(receipt))


def _turn_seq(turn_id: str) -> int | None:
    try:
        return int(turn_id.rsplit(":", 1)[-1])
    except ValueError:
        return None
