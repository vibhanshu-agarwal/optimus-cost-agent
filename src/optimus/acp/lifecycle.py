"""ACP turn and notice lifecycle controls (Plan 11.25 Tasks 2-3).

No asyncio I/O here. Permission correlation futures are channel-owned.
"""

from __future__ import annotations

import concurrent.futures
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
    SettlementInvariantError,
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

    def claim_write_started(self, send_key: TurnSendKey) -> SendState:
        with self._lock:
            slot = self._send_slots[send_key]
            if slot.authoritative is SendState.QUEUED:
                slot.authoritative = SendState.WRITE_STARTED
            return slot.authoritative

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


# ---------------------------------------------------------------------------
# Task 3: NoticeControl, typed send keys, response/warning/permission handles
# ---------------------------------------------------------------------------


class ResponsePart(StrEnum):
    RESPONSE = "response"
    TERMINAL_REFUSAL_NOTICE = "terminal_refusal_notice"


class ResponseKind(StrEnum):
    ORDINARY = "ordinary"
    TERMINAL_REFUSAL = "terminal_refusal"


@dataclass(frozen=True, slots=True)
class ResponseSendKey:
    response_id: int
    part: ResponsePart


@dataclass(frozen=True, slots=True)
class WarningAttemptSendKey:
    warning_id: int
    attempt_id: int


SendKey = TurnSendKey | ResponseSendKey | WarningAttemptSendKey


@dataclass(frozen=True, slots=True)
class SendCompletion:
    send_key: SendKey
    outcome: SendOutcome


class WriterToken:
    """One non-GC writer ownership token released exactly once."""

    def __init__(self, on_release: Callable[[], None]) -> None:
        self._on_release = on_release
        self._released = False
        self._lock = threading.Lock()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._on_release()


@dataclass(frozen=True, slots=True)
class SendTicket:
    send_key: SendKey
    source_future: concurrent.futures.Future[SendCompletion] | None
    immediate_completion: SendCompletion | None = None
    writer_token: WriterToken | None = None


@dataclass(slots=True)
class _NoticeSendSlot:
    send_key: SendKey
    authoritative: SendState
    diagnostic: SendOutcome | None = None
    writer_tokens: int = 0


class ResponseHandle:
    def __init__(
        self,
        *,
        notice_control: NoticeControl,
        response_id: int,
        response_kind: ResponseKind,
    ) -> None:
        self.notice_control = notice_control
        self.response_id = response_id
        self.response_kind = response_kind
        self._lock = threading.Lock()
        self._roles: frozenset[ResponsePart] = (
            frozenset({ResponsePart.RESPONSE, ResponsePart.TERMINAL_REFUSAL_NOTICE})
            if response_kind is ResponseKind.TERMINAL_REFUSAL
            else frozenset({ResponsePart.RESPONSE})
        )
        self._started_roles: set[ResponsePart] = set()
        self._closed_roles: set[ResponsePart] = set()
        self._slots: dict[ResponseSendKey, _NoticeSendSlot] = {}
        self._rpc_response_delivery = RpcResponseDelivery.NOT_ATTEMPTED
        self._finalized = False
        self._final_outcome: Any = None
        self._retired = False

    @property
    def expected_roles(self) -> frozenset[ResponsePart]:
        return self._roles

    @property
    def rpc_response_delivery(self) -> RpcResponseDelivery:
        with self._lock:
            return self._rpc_response_delivery

    def close_role_as_not_attempted(self, part: ResponsePart) -> None:
        with self._lock:
            if part not in self._roles:
                raise SettlementInvariantError(f"role {part!r} not expected")
            key = ResponseSendKey(self.response_id, part)
            if key not in self._slots:
                self._slots[key] = _NoticeSendSlot(send_key=key, authoritative=SendState.SUPPRESSED)
            self._closed_roles.add(part)
            self._started_roles.add(part)
        self.notice_control._maybe_retire_response(self)

    def start_non_turn_response_send(self) -> SendTicket:
        return self._start_role(ResponsePart.RESPONSE)

    def start_notice_send(self, part: ResponsePart = ResponsePart.TERMINAL_REFUSAL_NOTICE) -> SendTicket:
        if part is not ResponsePart.TERMINAL_REFUSAL_NOTICE:
            raise SettlementInvariantError("start_notice_send only accepts terminal_refusal_notice")
        return self._start_role(part)

    def _start_role(self, part: ResponsePart) -> SendTicket:
        with self._lock:
            if part not in self._roles:
                raise SettlementInvariantError(f"role {part!r} not expected on handle")
            if part in self._started_roles:
                raise SettlementInvariantError(f"role {part!r} already started")
            key = ResponseSendKey(self.response_id, part)
            self._started_roles.add(part)
            if self.notice_control.transport_abandoned():
                slot = _NoticeSendSlot(send_key=key, authoritative=SendState.SUPPRESSED)
                self._slots[key] = slot
                self._closed_roles.add(part)
                if part is ResponsePart.RESPONSE:
                    self._rpc_response_delivery = RpcResponseDelivery.NOT_ATTEMPTED
                completion = SendCompletion(send_key=key, outcome=SendOutcome.SUPPRESSED)
                ticket = SendTicket(
                    send_key=key,
                    source_future=None,
                    immediate_completion=completion,
                    writer_token=None,
                )
            else:
                slot = _NoticeSendSlot(send_key=key, authoritative=SendState.QUEUED, writer_tokens=0)
                self._slots[key] = slot
                future: concurrent.futures.Future[SendCompletion] = concurrent.futures.Future()

                def _on_release(handle: ResponseHandle = self, send_key: ResponseSendKey = key) -> None:
                    with handle._lock:
                        s = handle._slots[send_key]
                        if s.writer_tokens > 0:
                            s.writer_tokens -= 1
                    handle.notice_control._maybe_retire_response(handle)

                token = WriterToken(_on_release)
                slot.writer_tokens = 1
                ticket = SendTicket(
                    send_key=key,
                    source_future=future,
                    immediate_completion=None,
                    writer_token=token,
                )
        if ticket.immediate_completion is not None:
            self.notice_control._maybe_retire_response(self)
        return ticket

    def mark_write_started(self, send_key: ResponseSendKey) -> bool:
        with self._lock:
            slot = self._slots.get(send_key)
            if slot is None or slot.authoritative is not SendState.QUEUED:
                return False
            slot.authoritative = SendState.WRITE_STARTED
            return True

    def claim_write_started(self, send_key: ResponseSendKey) -> SendState:
        with self._lock:
            slot = self._slots[send_key]
            if slot.authoritative is SendState.QUEUED:
                slot.authoritative = SendState.WRITE_STARTED
            return slot.authoritative

    def publish_authoritative(self, send_key: ResponseSendKey, outcome: SendOutcome) -> None:
        with self._lock:
            slot = self._slots[send_key]
            if slot.authoritative in {
                SendState.FLUSHED,
                SendState.CONCLUSIVE_FAILURE,
                SendState.AMBIGUOUS,
                SendState.SUPPRESSED,
            }:
                return
            slot.authoritative = SendState(outcome.value)
            self._closed_roles.add(send_key.part)
            if send_key.part is ResponsePart.RESPONSE:
                if outcome is SendOutcome.SUPPRESSED:
                    self._rpc_response_delivery = RpcResponseDelivery.NOT_ATTEMPTED
                else:
                    self._rpc_response_delivery = RpcResponseDelivery(outcome.value)

    def publish_diagnostic(self, send_key: ResponseSendKey, outcome: SendOutcome) -> None:
        with self._lock:
            self._slots[send_key].diagnostic = outcome

    def freeze_abandoned(self) -> None:
        with self._lock:
            for slot in self._slots.values():
                if slot.authoritative is SendState.QUEUED:
                    slot.authoritative = SendState.SUPPRESSED
                    self._closed_roles.add(slot.send_key.part)  # type: ignore[union-attr]
                    if isinstance(slot.send_key, ResponseSendKey) and slot.send_key.part is ResponsePart.RESPONSE:
                        self._rpc_response_delivery = RpcResponseDelivery.NOT_ATTEMPTED
                elif slot.authoritative is SendState.WRITE_STARTED:
                    slot.authoritative = SendState.AMBIGUOUS
                    self._closed_roles.add(slot.send_key.part)  # type: ignore[union-attr]
                    if isinstance(slot.send_key, ResponseSendKey) and slot.send_key.part is ResponsePart.RESPONSE:
                        self._rpc_response_delivery = RpcResponseDelivery.AMBIGUOUS

    def finalize_once(self, outcome: Any) -> Any:
        with self._lock:
            if self._finalized:
                return self._final_outcome
            self._finalized = True
            self._final_outcome = outcome
        self.notice_control._maybe_retire_response(self)
        return outcome

    def _join_ready_locked(self) -> bool:
        if not self._finalized:
            return False
        if not self._roles <= self._started_roles:
            return False
        if not self._roles <= self._closed_roles:
            return False
        for part in self._roles:
            key = ResponseSendKey(self.response_id, part)
            slot = self._slots.get(key)
            if slot is None:
                return False
            if slot.authoritative not in {
                SendState.FLUSHED,
                SendState.CONCLUSIVE_FAILURE,
                SendState.AMBIGUOUS,
                SendState.SUPPRESSED,
            }:
                return False
            if slot.writer_tokens != 0:
                return False
        return True


class WarningSequenceHandle:
    def __init__(self, *, notice_control: NoticeControl, warning_id: int) -> None:
        self.notice_control = notice_control
        self.warning_id = warning_id
        self._lock = threading.Lock()
        self._closed = False
        self._flushed = False
        self._in_flight: WarningAttemptSendKey | None = None
        self._attempts: dict[WarningAttemptSendKey, _NoticeSendSlot] = {}
        self._coordinator_token_held = True
        self._retired_attempts: set[WarningAttemptSendKey] = set()

    def begin_warning_attempt(self) -> SendTicket:
        with self._lock:
            if self._closed or self._flushed:
                raise SettlementInvariantError("warning sequence is closed")
            if self._in_flight is not None:
                raise SettlementInvariantError("warning attempt already in flight")
            attempt_id = self.notice_control._next_attempt_id()
            key = WarningAttemptSendKey(warning_id=self.warning_id, attempt_id=attempt_id)
            if self.notice_control.transport_abandoned():
                slot = _NoticeSendSlot(send_key=key, authoritative=SendState.SUPPRESSED)
                self._attempts[key] = slot
                self._closed = True
                self._in_flight = None
                completion = SendCompletion(send_key=key, outcome=SendOutcome.SUPPRESSED)
                ticket = SendTicket(
                    send_key=key,
                    source_future=None,
                    immediate_completion=completion,
                    writer_token=None,
                )
            else:
                slot = _NoticeSendSlot(send_key=key, authoritative=SendState.QUEUED)
                self._attempts[key] = slot
                self._in_flight = key
                future: concurrent.futures.Future[SendCompletion] = concurrent.futures.Future()

                def _on_release(
                    handle: WarningSequenceHandle = self,
                    send_key: WarningAttemptSendKey = key,
                ) -> None:
                    with handle._lock:
                        s = handle._attempts[send_key]
                        if s.writer_tokens > 0:
                            s.writer_tokens -= 1
                    handle._maybe_retire_attempt(send_key)

                token = WriterToken(_on_release)
                slot.writer_tokens = 1
                ticket = SendTicket(
                    send_key=key,
                    source_future=future,
                    writer_token=token,
                )
        return ticket

    def acknowledge_attempt(self, completion: SendCompletion) -> None:
        key = completion.send_key
        if not isinstance(key, WarningAttemptSendKey):
            raise SettlementInvariantError("warning acknowledge requires WarningAttemptSendKey")
        with self._lock:
            slot = self._attempts[key]
            if slot.authoritative not in {
                SendState.FLUSHED,
                SendState.CONCLUSIVE_FAILURE,
                SendState.AMBIGUOUS,
                SendState.SUPPRESSED,
            }:
                slot.authoritative = SendState(completion.outcome.value)
            if completion.outcome is SendOutcome.FLUSHED:
                self._flushed = True
                self._closed = True
            self._in_flight = None
        self._maybe_retire_attempt(key)

    def mark_write_started(self, send_key: WarningAttemptSendKey) -> bool:
        with self._lock:
            slot = self._attempts.get(send_key)
            if slot is None or slot.authoritative is not SendState.QUEUED:
                return False
            slot.authoritative = SendState.WRITE_STARTED
            return True

    def publish_authoritative(self, send_key: WarningAttemptSendKey, outcome: SendOutcome) -> None:
        with self._lock:
            slot = self._attempts[send_key]
            if slot.authoritative in {
                SendState.FLUSHED,
                SendState.CONCLUSIVE_FAILURE,
                SendState.AMBIGUOUS,
                SendState.SUPPRESSED,
            }:
                return
            slot.authoritative = SendState(outcome.value)
            if outcome is SendOutcome.FLUSHED:
                self._flushed = True
                self._closed = True

    def publish_diagnostic(self, send_key: WarningAttemptSendKey, outcome: SendOutcome) -> None:
        with self._lock:
            self._attempts[send_key].diagnostic = outcome

    def freeze_abandoned(self) -> None:
        with self._lock:
            self._closed = True
            for slot in self._attempts.values():
                if slot.authoritative is SendState.QUEUED:
                    slot.authoritative = SendState.SUPPRESSED
                elif slot.authoritative is SendState.WRITE_STARTED:
                    slot.authoritative = SendState.AMBIGUOUS
            self._in_flight = None

    def release_coordinator_token(self) -> None:
        with self._lock:
            self._coordinator_token_held = False
        self.notice_control._maybe_retire_warning(self)

    def abort(self) -> None:
        with self._lock:
            self._closed = True
            self._coordinator_token_held = False
        self.notice_control._maybe_retire_warning(self)

    def live_attempt_count(self) -> int:
        with self._lock:
            return sum(1 for key in self._attempts if key not in self._retired_attempts)

    def _maybe_retire_attempt(self, key: WarningAttemptSendKey) -> None:
        with self._lock:
            slot = self._attempts.get(key)
            if slot is None or slot.writer_tokens != 0:
                return
            if slot.authoritative not in {
                SendState.FLUSHED,
                SendState.CONCLUSIVE_FAILURE,
                SendState.AMBIGUOUS,
                SendState.SUPPRESSED,
            }:
                return
            self._retired_attempts.add(key)
        self.notice_control._maybe_retire_warning(self)


class NoticeControl:
    """Process-lifetime owner for non-turn responses and warning notices."""

    def __init__(self) -> None:
        self._registry_lock = threading.Lock()
        self._transport_abandoned = False
        self._next_response_id = 1
        self._next_warning_id = 1
        self._next_attempt_id_value = 1
        self._responses: dict[int, ResponseHandle] = {}
        self._warnings: dict[int, WarningSequenceHandle] = {}
        self._abandoned_once = False

    def transport_abandoned(self) -> bool:
        with self._registry_lock:
            return self._transport_abandoned

    def allocate_response_handle(self, response_kind: ResponseKind) -> ResponseHandle:
        with self._registry_lock:
            response_id = self._next_response_id
            self._next_response_id += 1
            handle = ResponseHandle(
                notice_control=self,
                response_id=response_id,
                response_kind=response_kind,
            )
            self._responses[response_id] = handle
            return handle

    def allocate_warning_sequence(self) -> WarningSequenceHandle:
        with self._registry_lock:
            warning_id = self._next_warning_id
            self._next_warning_id += 1
            handle = WarningSequenceHandle(notice_control=self, warning_id=warning_id)
            self._warnings[warning_id] = handle
            return handle

    def abort_warning_sequence(self, handle: WarningSequenceHandle) -> None:
        handle.abort()

    def _next_attempt_id(self) -> int:
        with self._registry_lock:
            value = self._next_attempt_id_value
            self._next_attempt_id_value += 1
            return value

    def mark_transport_abandoned(self) -> None:
        with self._registry_lock:
            if self._abandoned_once:
                return
            self._abandoned_once = True
            self._transport_abandoned = True
            responses = list(self._responses.values())
            warnings = list(self._warnings.values())
        for handle in responses:
            handle.freeze_abandoned()
            self._maybe_retire_response(handle)
        for handle in warnings:
            handle.freeze_abandoned()
            self._maybe_retire_warning(handle)

    def lookup_response(self, response_id: int) -> ResponseHandle | str:
        with self._registry_lock:
            handle = self._responses.get(response_id)
            if handle is None:
                return "unknown_or_retired"
            return handle

    def live_response_count(self) -> int:
        with self._registry_lock:
            return len(self._responses)

    def live_warning_count(self) -> int:
        with self._registry_lock:
            return len(self._warnings)

    def _maybe_retire_response(self, handle: ResponseHandle) -> None:
        with handle._lock:
            ready = handle._join_ready_locked()
            response_id = handle.response_id
        if not ready:
            return
        with self._registry_lock:
            current = self._responses.get(response_id)
            if current is handle:
                del self._responses[response_id]
                handle._retired = True

    def _maybe_retire_warning(self, handle: WarningSequenceHandle) -> None:
        with handle._lock:
            if handle._coordinator_token_held:
                return
            if not handle._closed:
                return
            for key, slot in handle._attempts.items():
                if key not in handle._retired_attempts:
                    return
                if slot.writer_tokens != 0:
                    return
            warning_id = handle.warning_id
        with self._registry_lock:
            current = self._warnings.get(warning_id)
            if current is handle:
                del self._warnings[warning_id]


class PermissionRequestHandle:
    """Owns permission request_id, correlation future, and send settlement."""

    _CANCELLED = {"outcome": {"outcome": "cancelled"}}
    _NOT_APPROVED = {"outcome": {"outcome": "rejected"}}

    def __init__(
        self,
        *,
        channel: Any,
        request_id: int,
        response_future: Any,
        method: str,
        params: dict[str, Any],
    ) -> None:
        self._channel = channel
        self.request_id = request_id
        self.response_future = response_future
        self.method = method
        self.params = params
        self._send_key: TurnSendKey | None = None

    def begin_send(self, turn: TurnControl) -> StartLease:
        lease = turn.try_start(SendKind.PERMISSION, str(self.request_id))
        self._send_key = lease.send_key
        if not lease.granted:
            self.apply_send_completion(
                SendCompletion(
                    send_key=lease.send_key or TurnSendKey(kind="permission", message_id=str(self.request_id)),
                    outcome=SendOutcome.SUPPRESSED,
                )
            )
        return lease

    def apply_send_completion(self, completion: SendCompletion) -> None:
        outcome = completion.outcome
        if outcome is SendOutcome.FLUSHED:
            return
        if outcome is SendOutcome.SUPPRESSED:
            self._resolve_and_remove(self._CANCELLED)
            return
        self._resolve_and_remove(self._NOT_APPROVED)

    def cancel(self) -> None:
        self._resolve_and_remove(self._CANCELLED)

    def _resolve_and_remove(self, result: dict[str, Any]) -> None:
        future = self._channel._futures.pop(self.request_id, None)
        if future is not None and not future.done():
            future.set_result(result)
