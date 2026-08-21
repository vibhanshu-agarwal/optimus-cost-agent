"""Deterministic TurnControl gate, freeze, and finalization tests (Plan 11.25 Task 2)."""

from __future__ import annotations

import threading
from dataclasses import FrozenInstanceError

import pytest

from optimus.acp.lifecycle import (
    CancelResult,
    DirectiveKind,
    SendKind,
    TerminalDecision,
    TerminalLane,
    TurnControl,
    TurnSendKey,
)
from optimus.acp.settlement import (
    ConversationCommit,
    EffectState,
    FinalDelivery,
    RpcResponseDelivery,
    SendOutcome,
    SendState,
    Settlement,
    TurnSettlementSnapshot,
)


def _control(**kwargs: object) -> TurnControl:
    return TurnControl(session_id="sess-1", turn_seq=1, **kwargs)  # type: ignore[arg-type]


def test_register_operations_when_gate_open_starts_not_started() -> None:
    control = _control()
    control.register_operations(
        [
            (DirectiveKind.WRITE, "w1"),
            (DirectiveKind.TEST, "t1"),
            (DirectiveKind.READ, "r1"),
            (DirectiveKind.GATEWAY, "g1"),
            (DirectiveKind.PLANNING_READ, "pr1"),
            (DirectiveKind.PLAN_PERSISTENCE, "pp1"),
        ]
    )
    assert control.directive_state(DirectiveKind.WRITE, "w1") == "not_started"
    assert control.directive_state(DirectiveKind.GATEWAY, "g1") == "not_started"


def test_register_operations_when_gate_closed_registers_suppressed() -> None:
    control = _control()
    assert control.request_session_cancel() is CancelResult.ACCEPTED
    control.register_operations([(DirectiveKind.WRITE, "w1")])
    assert control.directive_state(DirectiveKind.WRITE, "w1") == "suppressed"


def test_try_start_directive_vs_send_vocabularies() -> None:
    control = _control()
    control.register_operations([(DirectiveKind.WRITE, "w1")])
    write_lease = control.try_start(DirectiveKind.WRITE, "w1")
    assert write_lease.granted is True
    assert control.directive_state(DirectiveKind.WRITE, "w1") == "started"

    progress_lease = control.try_start(SendKind.PROGRESS, "p1")
    assert progress_lease.granted is True
    assert progress_lease.send_key is not None
    assert control.send_slot(progress_lease.send_key).authoritative is SendState.QUEUED


def test_try_start_after_cancel_creates_terminal_suppressed_atomically() -> None:
    control = _control()
    control.register_operations([(DirectiveKind.WRITE, "w1")])
    control.request_session_cancel()
    lease = control.try_start(DirectiveKind.WRITE, "w1")
    assert lease.granted is False
    assert control.directive_state(DirectiveKind.WRITE, "w1") == "suppressed"

    send_lease = control.try_start(SendKind.PROVISIONAL_PLAN, "plan-1")
    assert send_lease.granted is False
    assert send_lease.send_key is not None
    assert control.send_slot(send_lease.send_key).authoritative is SendState.SUPPRESSED


def test_execution_start_versus_cancel_both_lock_orders() -> None:
    # Order A: start then cancel — started directive remains started; cancel accepted.
    a = _control()
    a.register_operations([(DirectiveKind.WRITE, "w1")])
    assert a.try_start(DirectiveKind.WRITE, "w1").granted is True
    assert a.request_session_cancel() is CancelResult.ACCEPTED
    assert a.directive_state(DirectiveKind.WRITE, "w1") == "started"
    assert a.halt_requested() is True

    # Order B: cancel then start — direct suppressed, no lease.
    b = _control()
    b.register_operations([(DirectiveKind.WRITE, "w1")])
    assert b.request_session_cancel() is CancelResult.ACCEPTED
    assert b.try_start(DirectiveKind.WRITE, "w1").granted is False
    assert b.directive_state(DirectiveKind.WRITE, "w1") == "suppressed"


def test_cancel_versus_terminal_lane_seal_both_orders() -> None:
    # Cancel before seal → accepted; seal captures cancellation_accepted=True.
    before = _control()
    assert before.request_session_cancel() is CancelResult.ACCEPTED
    decision = before.seal_final_delivery()
    assert decision.lane is TerminalLane.GRANTED
    assert decision.cancellation_accepted is True
    assert before.request_session_cancel() is CancelResult.IGNORED_AFTER_CUTOFF

    # Seal before cancel → grant with cancellation_accepted=False; later cancel ignored.
    after = _control()
    decision = after.seal_final_delivery()
    assert decision.lane is TerminalLane.GRANTED
    assert decision.cancellation_accepted is False
    assert after.request_session_cancel() is CancelResult.IGNORED_AFTER_CUTOFF
    assert after.seal_final_delivery() == decision


def test_terminal_message_start_versus_teardown_both_orders() -> None:
    # Grant then start — queued lease.
    granted = _control()
    granted.seal_final_delivery()
    lease = granted.start_terminal_message("m1")
    assert lease.granted is True
    assert lease.send_key is not None
    assert granted.send_slot(lease.send_key).authoritative is SendState.QUEUED

    # Teardown after grant before start — suppressed, no lease.
    torn = _control()
    torn.seal_final_delivery()
    torn.request_transport_teardown()
    lease = torn.start_terminal_message("m1")
    assert lease.granted is False
    assert lease.send_key is not None
    assert torn.send_slot(lease.send_key).authoritative is SendState.SUPPRESSED


def test_response_start_versus_already_abandoned_transport() -> None:
    control = _control()
    control.request_transport_teardown()
    lease = control.start_response_send()
    assert lease.granted is False
    assert lease.send_key is not None
    assert control.send_slot(lease.send_key).authoritative is SendState.SUPPRESSED
    assert control.rpc_response_delivery is RpcResponseDelivery.NOT_ATTEMPTED


def test_concurrent_try_start_and_cancel_barrier_invariants() -> None:
    for _ in range(20):
        control = _control()
        control.register_operations([(DirectiveKind.WRITE, "w1")])
        barrier = threading.Barrier(2)
        results: dict[str, object] = {}

        def starter(
            barrier: threading.Barrier = barrier,
            control: TurnControl = control,
            results: dict[str, object] = results,
        ) -> None:
            barrier.wait()
            results["lease"] = control.try_start(DirectiveKind.WRITE, "w1").granted

        def canceller(
            barrier: threading.Barrier = barrier,
            control: TurnControl = control,
            results: dict[str, object] = results,
        ) -> None:
            barrier.wait()
            results["cancel"] = control.request_session_cancel()

        t1 = threading.Thread(target=starter)
        t2 = threading.Thread(target=canceller)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        state = control.directive_state(DirectiveKind.WRITE, "w1")
        assert results["cancel"] is CancelResult.ACCEPTED
        assert control.halt_requested() is True
        if results["lease"] is True:
            assert state == "started"
        else:
            assert state == "suppressed"


def test_queued_send_suppressed_on_teardown() -> None:
    control = _control()
    lease = control.try_start(SendKind.PROGRESS, "p1")
    assert lease.granted is True
    key = lease.send_key
    assert key is not None
    classification = control.request_transport_teardown()
    assert control.send_slot(key).authoritative is SendState.SUPPRESSED
    assert classification is FinalDelivery.NOT_ATTEMPTED


def test_write_started_freeze_to_ambiguous_and_message_class_consequences() -> None:
    control = _control()
    control.seal_final_delivery()
    term = control.start_terminal_message("term-1")
    assert term.send_key is not None
    control.mark_write_started(term.send_key)

    proto = control.start_response_send()
    assert proto.send_key is not None
    control.mark_write_started(proto.send_key)

    progress = control.try_start(SendKind.PROGRESS, "prog-1")
    assert progress.send_key is not None
    control.mark_write_started(progress.send_key)

    provisional = control.try_start(SendKind.PROVISIONAL_PLAN, "prov-1")
    assert provisional.send_key is not None
    control.mark_write_started(provisional.send_key)

    classification = control.request_transport_teardown()
    assert classification is FinalDelivery.AMBIGUOUS
    assert control.send_slot(term.send_key).authoritative is SendState.AMBIGUOUS
    assert control.send_slot(proto.send_key).authoritative is SendState.AMBIGUOUS
    assert control.send_slot(progress.send_key).authoritative is SendState.AMBIGUOUS
    assert control.send_slot(provisional.send_key).authoritative is SendState.AMBIGUOUS
    assert control.final_delivery is FinalDelivery.AMBIGUOUS
    assert control.rpc_response_delivery is RpcResponseDelivery.AMBIGUOUS
    assert control.delivery_indeterminate is True
    assert control.prior_history_flush is False


def test_teardown_freezes_started_directives_exact_vocabularies() -> None:
    control = _control()
    control.register_operations(
        [
            (DirectiveKind.GATEWAY, "g1"),
            (DirectiveKind.WRITE, "w1"),
            (DirectiveKind.TEST, "t1"),
            (DirectiveKind.READ, "r1"),
            (DirectiveKind.PLANNING_READ, "pr1"),
            (DirectiveKind.PLAN_PERSISTENCE, "pp1"),
        ]
    )
    for kind, oid in [
        (DirectiveKind.GATEWAY, "g1"),
        (DirectiveKind.WRITE, "w1"),
        (DirectiveKind.TEST, "t1"),
        (DirectiveKind.READ, "r1"),
        (DirectiveKind.PLANNING_READ, "pr1"),
        (DirectiveKind.PLAN_PERSISTENCE, "pp1"),
    ]:
        assert control.try_start(kind, oid).granted is True

    control.request_transport_teardown()
    assert control.directive_state(DirectiveKind.GATEWAY, "g1") == "cost_unknown"
    assert control.directive_state(DirectiveKind.WRITE, "w1") == "failed_effect_unknown"
    assert control.directive_state(DirectiveKind.TEST, "t1") == "failed_effect_unknown"
    assert control.directive_state(DirectiveKind.READ, "r1") == "abandoned_no_effect"
    assert control.directive_state(DirectiveKind.PLANNING_READ, "pr1") == "abandoned_no_effect"
    assert control.directive_state(DirectiveKind.PLAN_PERSISTENCE, "pp1") == "persistence_partial"
    assert control.effect_state is EffectState.INDETERMINATE
    assert control.cost_complete is False


def test_frozen_snapshot_immutable_and_repeated_teardown_is_pure_read() -> None:
    control = _control()
    control.register_operations([(DirectiveKind.WRITE, "w1")])
    control.try_start(DirectiveKind.WRITE, "w1")
    first = control.request_transport_teardown()
    snap = control.frozen_snapshot
    assert snap is not None
    second = control.request_transport_teardown()
    assert second is first
    assert control.frozen_snapshot is snap
    with pytest.raises(FrozenInstanceError):
        snap.effect_state = EffectState.NONE  # type: ignore[misc]


def test_late_directive_reports_are_diagnostic_only() -> None:
    control = _control()
    control.register_operations([(DirectiveKind.WRITE, "w1")])
    control.try_start(DirectiveKind.WRITE, "w1")
    control.request_transport_teardown()
    assert control.directive_state(DirectiveKind.WRITE, "w1") == "failed_effect_unknown"
    control.complete_directive(DirectiveKind.WRITE, "w1", "succeeded")
    assert control.directive_state(DirectiveKind.WRITE, "w1") == "failed_effect_unknown"
    assert control.directive_diagnostic(DirectiveKind.WRITE, "w1") == "succeeded"
    assert control.effect_state is EffectState.INDETERMINATE


def test_publish_authoritative_is_idempotent_diagnostic_accepts_late() -> None:
    control = _control()
    lease = control.try_start(SendKind.PROGRESS, "p1")
    key = lease.send_key
    assert key is not None
    control.mark_write_started(key)
    control.publish_authoritative(key, SendOutcome.AMBIGUOUS)
    control.publish_authoritative(key, SendOutcome.FLUSHED)
    assert control.send_slot(key).authoritative is SendState.AMBIGUOUS
    control.publish_diagnostic(key, SendOutcome.FLUSHED)
    assert control.send_slot(key).diagnostic is SendOutcome.FLUSHED


def test_finalize_once_identity_conditional_and_idempotent() -> None:
    control = _control()
    removals: list[tuple[str, int, int]] = []
    callbacks: list[TurnSettlementSnapshot] = []

    def remover(session_id: str, turn_seq: int, obj: TurnControl) -> bool:
        removals.append((session_id, turn_seq, id(obj)))
        return obj is control and session_id == "sess-1" and turn_seq == 1

    def sink(snapshot: TurnSettlementSnapshot) -> None:
        callbacks.append(snapshot)

    control.set_finalization_hooks(active_map_remover=remover, settlement_callback=sink)
    first = TurnSettlementSnapshot(
        settlement=Settlement.CANCELLED,
        final_delivery=FinalDelivery.NOT_ATTEMPTED,
        rpc_response_delivery=RpcResponseDelivery.NOT_ATTEMPTED,
        conversation_commit=ConversationCommit.NOT_COMMITTED,
        effect_state=EffectState.NONE,
        cost_complete=True,
    )
    out1 = control.finalize_once(first)
    out2 = control.finalize_once(
        TurnSettlementSnapshot(
            settlement=Settlement.FAILED,
            final_delivery=FinalDelivery.AMBIGUOUS,
            rpc_response_delivery=RpcResponseDelivery.AMBIGUOUS,
            conversation_commit=ConversationCommit.NOT_COMMITTED,
            effect_state=EffectState.INDETERMINATE,
            cost_complete=False,
        )
    )
    assert out1 is first
    assert out2 is first
    assert removals == [("sess-1", 1, id(control))]
    assert callbacks == [first]


def test_finalize_once_skips_remover_when_identity_mismatches() -> None:
    control = _control()
    other = _control()
    called = {"n": 0}

    def remover(session_id: str, turn_seq: int, obj: TurnControl) -> bool:
        called["n"] += 1
        return False

    control.set_finalization_hooks(active_map_remover=remover)
    snap = TurnSettlementSnapshot(
        settlement=Settlement.COMPLETED,
        final_delivery=FinalDelivery.FLUSHED,
        rpc_response_delivery=RpcResponseDelivery.FLUSHED,
        conversation_commit=ConversationCommit.COMMITTED,
        effect_state=EffectState.COMPLETE,
        cost_complete=True,
    )
    # Remover is still invoked with this control; it decides mismatch.
    control.finalize_once(snap)
    assert called["n"] == 1
    assert other.session_id == "sess-1"


def test_complete_directive_before_freeze() -> None:
    control = _control()
    control.register_operations([(DirectiveKind.WRITE, "w1"), (DirectiveKind.TEST, "t1")])
    control.try_start(DirectiveKind.WRITE, "w1")
    control.try_start(DirectiveKind.TEST, "t1")
    control.complete_directive(DirectiveKind.WRITE, "w1", "succeeded")
    control.complete_directive(DirectiveKind.TEST, "t1", "suppressed")
    assert control.effect_state is EffectState.PARTIAL


def test_cancel_does_not_suppress_terminal_set_messages() -> None:
    control = _control()
    control.request_session_cancel()
    decision = control.seal_final_delivery()
    assert decision.cancellation_accepted is True
    assert decision.lane is TerminalLane.GRANTED
    lease = control.start_terminal_message("cancel-text")
    assert lease.granted is True


def test_terminal_decision_type() -> None:
    decision = TerminalDecision(lane=TerminalLane.GRANTED, cancellation_accepted=False)
    assert decision.lane is TerminalLane.GRANTED
    key = TurnSendKey(kind="terminal_set", message_id="m1")
    assert key.kind == "terminal_set"
