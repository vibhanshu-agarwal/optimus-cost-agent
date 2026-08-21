"""Turn-owned ACP lifecycle control (Plan 11.25 Task 2).

NoticeControl and capability handles land in Task 3. No asyncio or I/O here.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from optimus.acp.settlement import (
    ConversationCommit,
    EffectState,
    FinalDelivery,
    RpcResponseDelivery,
    SendOutcome,
    SendState,
    Settlement,
    TurnSettlementSnapshot,
    compute_effect_state,
)


class TerminalLane(StrEnum):
    UNDECIDED = "undecided"
    GRANTED = "granted"
    DECLINED = "declined"


class CancelResult(StrEnum):
    ACCEPTED = "accepted"
    IGNORED_AFTER_CUTOFF = "ignored_after_cutoff"


class DirectiveKind(StrEnum):
    PLANNING_READ = "planning_read"
    GATEWAY = "gateway"
    READ = "read"
    WRITE = "write"
    TEST = "test"
    PLAN_PERSISTENCE = "plan_persistence"


class SendKind(StrEnum):
    PROGRESS = "progress"
    PROVISIONAL_PLAN = "provisional_plan"
    PERMISSION = "permission"


@dataclass(frozen=True, slots=True)
class TerminalDecision:
    lane: TerminalLane
    cancellation_accepted: bool


@dataclass(frozen=True, slots=True)
class TurnSendKey:
    kind: str
    message_id: str


@dataclass(frozen=True, slots=True)
class StartLease:
    granted: bool
    send_key: TurnSendKey | None = None
    operation_id: str | None = None


@dataclass(slots=True)
class SendSlot:
    send_key: TurnSendKey
    authoritative: SendState
    diagnostic: SendOutcome | None = None
    writer_tokens: int = 0
    work_class: str = ""


_FREEZE_TERMINAL: dict[DirectiveKind, str] = {
    DirectiveKind.GATEWAY: "cost_unknown",
    DirectiveKind.WRITE: "failed_effect_unknown",
    DirectiveKind.TEST: "failed_effect_unknown",
    DirectiveKind.READ: "abandoned_no_effect",
    DirectiveKind.PLANNING_READ: "abandoned_no_effect",
    DirectiveKind.PLAN_PERSISTENCE: "persistence_partial",
}


class TurnControl:
    """Single-lock turn lifecycle and turn-owned send-owner half."""

    def __init__(self, *, session_id: str, turn_seq: int) -> None:
        self.session_id = session_id
        self.turn_seq = turn_seq
        self._lock = threading.Lock()
        self._execution_gate_open = True
        self._terminal_lane = TerminalLane.UNDECIDED
        self._cancellation_accepted = False
        self._transport_abandoned = False
        self._terminal_decision: TerminalDecision | None = None
        self._directives: dict[tuple[DirectiveKind, str], str] = {}
        self._directive_diagnostics: dict[tuple[DirectiveKind, str], str] = {}
        self._directives_frozen = False
        self._send_slots: dict[TurnSendKey, SendSlot] = {}
        self._teardown_classification: FinalDelivery | None = None
        self._frozen_snapshot: TurnSettlementSnapshot | None = None
        self._final_delivery = FinalDelivery.NOT_ATTEMPTED
        self._rpc_response_delivery = RpcResponseDelivery.NOT_ATTEMPTED
        self._prior_history_flush = False
        self._delivery_indeterminate = False
        self._effect_state = EffectState.NONE
        self._cost_complete = True
        self._permission_handle: Any | None = None
        self._finalized = False
        self._final_outcome: TurnSettlementSnapshot | None = None
        self._active_map_remover: Callable[[str, int, TurnControl], bool] | None = None
        self._settlement_callback: Callable[[TurnSettlementSnapshot], None] | None = None
        self._response_started = False

    def set_finalization_hooks(
        self,
        *,
        active_map_remover: Callable[[str, int, TurnControl], bool] | None = None,
        settlement_callback: Callable[[TurnSettlementSnapshot], None] | None = None,
    ) -> None:
        self._active_map_remover = active_map_remover
        self._settlement_callback = settlement_callback

    def set_permission_handle(self, handle: Any | None) -> None:
        with self._lock:
            self._permission_handle = handle

    @property
    def final_delivery(self) -> FinalDelivery:
        with self._lock:
            return self._final_delivery

    @property
    def rpc_response_delivery(self) -> RpcResponseDelivery:
        with self._lock:
            return self._rpc_response_delivery

    @property
    def prior_history_flush(self) -> bool:
        with self._lock:
            return self._prior_history_flush

    @property
    def delivery_indeterminate(self) -> bool:
        with self._lock:
            return self._delivery_indeterminate

    @property
    def effect_state(self) -> EffectState:
        with self._lock:
            return self._effect_state

    @property
    def cost_complete(self) -> bool:
        with self._lock:
            return self._cost_complete

    @property
    def frozen_snapshot(self) -> TurnSettlementSnapshot | None:
        with self._lock:
            return self._frozen_snapshot

    def directive_state(self, kind: DirectiveKind, operation_id: str) -> str | None:
        with self._lock:
            return self._directives.get((kind, operation_id))

    def directive_diagnostic(self, kind: DirectiveKind, operation_id: str) -> str | None:
        with self._lock:
            return self._directive_diagnostics.get((kind, operation_id))

    def send_slot(self, send_key: TurnSendKey) -> SendSlot:
        with self._lock:
            return self._send_slots[send_key]

    def transport_abandoned(self) -> bool:
        with self._lock:
            return self._transport_abandoned

    def halt_requested(self) -> bool:
        with self._lock:
            return self._cancellation_accepted or self._transport_abandoned

    def register_operations(self, directives: Sequence[tuple[DirectiveKind, str]]) -> None:
        with self._lock:
            initial = "not_started" if self._execution_gate_open else "suppressed"
            for kind, operation_id in directives:
                key = (kind, operation_id)
                if key not in self._directives:
                    self._directives[key] = initial

    def try_start(self, operation_kind: DirectiveKind | SendKind, operation_id: str) -> StartLease:
        with self._lock:
            if isinstance(operation_kind, DirectiveKind):
                key = (operation_kind, operation_id)
                if not self._execution_gate_open:
                    self._directives[key] = "suppressed"
                    return StartLease(granted=False, operation_id=operation_id)
                current = self._directives.get(key)
                if current is None:
                    self._directives[key] = "started"
                elif current == "not_started":
                    self._directives[key] = "started"
                elif current == "started":
                    return StartLease(granted=True, operation_id=operation_id)
                else:
                    return StartLease(granted=False, operation_id=operation_id)
                return StartLease(granted=True, operation_id=operation_id)

            send_key = TurnSendKey(kind=operation_kind.value, message_id=operation_id)
            if not self._execution_gate_open or self._transport_abandoned:
                self._send_slots[send_key] = SendSlot(
                    send_key=send_key,
                    authoritative=SendState.SUPPRESSED,
                    work_class=operation_kind.value,
                )
                return StartLease(granted=False, send_key=send_key)
            self._send_slots[send_key] = SendSlot(
                send_key=send_key,
                authoritative=SendState.QUEUED,
                work_class=operation_kind.value,
            )
            return StartLease(granted=True, send_key=send_key)

    def complete_directive(self, kind: DirectiveKind, operation_id: str, terminal: str) -> None:
        with self._lock:
            key = (kind, operation_id)
            if self._directives_frozen or self._frozen_snapshot is not None:
                self._directive_diagnostics[key] = terminal
                return
            self._directives[key] = terminal
            self._recompute_effect_and_cost_locked()

    def request_session_cancel(self) -> CancelResult:
        with self._lock:
            if self._terminal_lane is not TerminalLane.UNDECIDED:
                return CancelResult.IGNORED_AFTER_CUTOFF
            self._execution_gate_open = False
            self._suppress_not_started_directives_locked()
            self._suppress_queued_execution_gate_sends_locked()
            self._cancellation_accepted = True
            return CancelResult.ACCEPTED

    def seal_final_delivery(self) -> TerminalDecision:
        with self._lock:
            if self._terminal_decision is None:
                lane = (
                    TerminalLane.DECLINED
                    if self._transport_abandoned or self._terminal_lane is TerminalLane.DECLINED
                    else TerminalLane.GRANTED
                )
                self._terminal_lane = lane
                self._terminal_decision = TerminalDecision(
                    lane=lane,
                    cancellation_accepted=self._cancellation_accepted,
                )
            return self._terminal_decision

    def start_terminal_message(self, message_id: str, *, fallback: bool = False) -> StartLease:
        with self._lock:
            kind = "fallback" if fallback else "terminal_set"
            send_key = TurnSendKey(kind=kind, message_id=message_id)
            if self._terminal_lane is not TerminalLane.GRANTED:
                self._send_slots[send_key] = SendSlot(
                    send_key=send_key,
                    authoritative=SendState.SUPPRESSED,
                    work_class=kind,
                )
                return StartLease(granted=False, send_key=send_key)
            self._send_slots[send_key] = SendSlot(
                send_key=send_key,
                authoritative=SendState.QUEUED,
                work_class=kind,
            )
            return StartLease(granted=True, send_key=send_key)

    def start_response_send(self) -> StartLease:
        with self._lock:
            send_key = TurnSendKey(kind="protocol_response", message_id="response")
            if self._response_started and send_key in self._send_slots:
                slot = self._send_slots[send_key]
                granted = slot.authoritative is SendState.QUEUED
                return StartLease(granted=granted, send_key=send_key)
            self._response_started = True
            if self._transport_abandoned:
                self._send_slots[send_key] = SendSlot(
                    send_key=send_key,
                    authoritative=SendState.SUPPRESSED,
                    work_class="protocol_response",
                )
                self._rpc_response_delivery = RpcResponseDelivery.NOT_ATTEMPTED
                return StartLease(granted=False, send_key=send_key)
            self._send_slots[send_key] = SendSlot(
                send_key=send_key,
                authoritative=SendState.QUEUED,
                work_class="protocol_response",
            )
            return StartLease(granted=True, send_key=send_key)

    def mark_write_started(self, send_key: TurnSendKey) -> bool:
        with self._lock:
            slot = self._send_slots.get(send_key)
            if slot is None or slot.authoritative is not SendState.QUEUED:
                return False
            slot.authoritative = SendState.WRITE_STARTED
            return True

    def publish_authoritative(self, send_key: TurnSendKey, outcome: SendOutcome) -> None:
        with self._lock:
            slot = self._send_slots[send_key]
            if slot.authoritative in {
                SendState.FLUSHED,
                SendState.CONCLUSIVE_FAILURE,
                SendState.AMBIGUOUS,
                SendState.SUPPRESSED,
            }:
                return
            slot.authoritative = SendState(outcome.value)
            self._apply_send_consequence_locked(slot, outcome)

    def publish_diagnostic(self, send_key: TurnSendKey, outcome: SendOutcome) -> None:
        with self._lock:
            slot = self._send_slots[send_key]
            slot.diagnostic = outcome

    def request_transport_teardown(self) -> FinalDelivery:
        with self._lock:
            if self._teardown_classification is not None:
                return self._teardown_classification

            self._transport_abandoned = True
            self._execution_gate_open = False
            self._suppress_not_started_directives_locked()
            self._freeze_started_directives_locked()

            for slot in self._send_slots.values():
                if slot.authoritative is SendState.QUEUED:
                    slot.authoritative = SendState.SUPPRESSED
                    self._apply_send_consequence_locked(slot, SendOutcome.SUPPRESSED)
                elif slot.authoritative is SendState.WRITE_STARTED:
                    slot.authoritative = SendState.AMBIGUOUS
                    self._apply_send_consequence_locked(slot, SendOutcome.AMBIGUOUS)

            self._recompute_effect_and_cost_locked()
            self._directives_frozen = True
            self._frozen_snapshot = TurnSettlementSnapshot(
                settlement=Settlement.TRANSPORT_ABANDONED,
                final_delivery=self._final_delivery,
                rpc_response_delivery=self._rpc_response_delivery,
                conversation_commit=ConversationCommit.NOT_COMMITTED,
                effect_state=self._effect_state,
                cost_complete=self._cost_complete,
            )

            if self._terminal_lane is not TerminalLane.DECLINED:
                self._terminal_lane = TerminalLane.DECLINED
            if self._terminal_decision is None:
                self._terminal_decision = TerminalDecision(
                    lane=TerminalLane.DECLINED,
                    cancellation_accepted=self._cancellation_accepted,
                )
            else:
                self._terminal_decision = TerminalDecision(
                    lane=TerminalLane.DECLINED,
                    cancellation_accepted=self._terminal_decision.cancellation_accepted,
                )

            self._teardown_classification = self._classify_teardown_delivery_locked()
            handle = self._permission_handle

        if handle is not None:
            cancel = getattr(handle, "cancel", None)
            if callable(cancel):
                cancel()

        return self._teardown_classification

    def finalize_once(self, outcome: TurnSettlementSnapshot) -> TurnSettlementSnapshot:
        claimed = False
        with self._lock:
            if self._finalized:
                assert self._final_outcome is not None
                return self._final_outcome
            self._finalized = True
            self._final_outcome = outcome
            claimed = True
            remover = self._active_map_remover
            callback = self._settlement_callback

        if claimed and remover is not None:
            remover(self.session_id, self.turn_seq, self)
        if claimed and callback is not None:
            try:
                callback(outcome)
            except Exception:
                pass
        return outcome

    def _suppress_not_started_directives_locked(self) -> None:
        for key, state in list(self._directives.items()):
            if state == "not_started":
                self._directives[key] = "suppressed"

    def _suppress_queued_execution_gate_sends_locked(self) -> None:
        for slot in self._send_slots.values():
            if slot.work_class in {SendKind.PROGRESS.value, SendKind.PROVISIONAL_PLAN.value, SendKind.PERMISSION.value}:
                if slot.authoritative is SendState.QUEUED:
                    slot.authoritative = SendState.SUPPRESSED

    def _freeze_started_directives_locked(self) -> None:
        for (kind, operation_id), state in list(self._directives.items()):
            if state == "started":
                self._directives[(kind, operation_id)] = _FREEZE_TERMINAL[kind]

    def _apply_send_consequence_locked(self, slot: SendSlot, outcome: SendOutcome) -> None:
        kind = slot.work_class
        if kind in {"terminal_set", "fallback"}:
            if outcome is SendOutcome.SUPPRESSED:
                # Keep prior aggregate unless this is the sole classification path.
                if self._final_delivery is FinalDelivery.NOT_ATTEMPTED:
                    self._final_delivery = FinalDelivery.NOT_ATTEMPTED
            elif outcome is SendOutcome.AMBIGUOUS:
                self._final_delivery = FinalDelivery.AMBIGUOUS
            elif outcome is SendOutcome.FLUSHED:
                self._final_delivery = FinalDelivery.FLUSHED
            elif outcome is SendOutcome.CONCLUSIVE_FAILURE:
                self._final_delivery = FinalDelivery.CONCLUSIVE_FAILURE
        elif kind == "protocol_response":
            if outcome is SendOutcome.SUPPRESSED:
                self._rpc_response_delivery = RpcResponseDelivery.NOT_ATTEMPTED
            else:
                self._rpc_response_delivery = RpcResponseDelivery(outcome.value)
        elif kind == SendKind.PROVISIONAL_PLAN.value:
            if outcome is SendOutcome.AMBIGUOUS:
                self._delivery_indeterminate = True
            elif outcome is SendOutcome.FLUSHED:
                self._prior_history_flush = True
            elif outcome in {SendOutcome.CONCLUSIVE_FAILURE, SendOutcome.SUPPRESSED}:
                # Leave prior_history_flush unchanged on failure; false stays false.
                pass
        # progress / permission: best-effort or not-approved; permission handle cancel is separate.

    def _classify_teardown_delivery_locked(self) -> FinalDelivery:
        terminal_slots = [
            slot
            for slot in self._send_slots.values()
            if slot.work_class in {"terminal_set", "fallback"}
        ]
        if not terminal_slots:
            if self._final_delivery is FinalDelivery.AMBIGUOUS:
                return FinalDelivery.AMBIGUOUS
            return FinalDelivery.NOT_ATTEMPTED

        states = {slot.authoritative for slot in terminal_slots}
        if SendState.AMBIGUOUS in states or SendState.WRITE_STARTED in states:
            return FinalDelivery.AMBIGUOUS
        if states <= {SendState.SUPPRESSED} or states <= {SendState.QUEUED, SendState.SUPPRESSED}:
            return FinalDelivery.NOT_ATTEMPTED
        if SendState.FLUSHED in states and (
            SendState.SUPPRESSED in states or len(states) > 1
        ):
            # One flushed and another not fully flushed → partial.
            if states != {SendState.FLUSHED}:
                return FinalDelivery.PARTIAL
        if states == {SendState.FLUSHED}:
            return FinalDelivery.FLUSHED
        if SendState.FLUSHED in states:
            return FinalDelivery.PARTIAL
        return self._final_delivery

    def _recompute_effect_and_cost_locked(self) -> None:
        effectful: list[tuple[str, str]] = []
        for (kind, _), state in self._directives.items():
            if kind in {DirectiveKind.WRITE, DirectiveKind.TEST}:
                if state not in {"not_started", "started"}:
                    effectful.append((kind.value, state))
        self._effect_state = compute_effect_state(effectful)

        self._cost_complete = True
        for (kind, _), state in self._directives.items():
            if kind is DirectiveKind.GATEWAY and state == "cost_unknown":
                self._cost_complete = False
                break
