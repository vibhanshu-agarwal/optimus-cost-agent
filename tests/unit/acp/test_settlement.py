"""Exact-set registry, consequence, and effect-algebra tests for Plan 11.25 Task 1."""

from __future__ import annotations

import dataclasses

import pytest

from optimus.acp.settlement import (
    COMMON_SEND_LIFECYCLE,
    COMMON_SEND_TERMINAL,
    EXECUTION_READ_LIFECYCLE,
    EXECUTION_READ_TERMINAL,
    EXECUTION_WRITE_TEST_LIFECYCLE,
    EXECUTION_WRITE_TEST_TERMINAL,
    GATEWAY_LIFECYCLE,
    GATEWAY_TERMINAL,
    PLAN_PERSISTENCE_LIFECYCLE,
    PLAN_PERSISTENCE_TERMINAL,
    PLANNING_READ_LIFECYCLE,
    PLANNING_READ_TERMINAL,
    WORK_CLASS_REGISTRY,
    Consequence,
    ConversationCommit,
    EffectState,
    FinalDelivery,
    GateLane,
    OwnerKind,
    PermissionEligibility,
    ProvisionalHistoryEffect,
    RpcResponseDelivery,
    SendOutcome,
    Settlement,
    StartOperation,
    TurnSettlementSnapshot,
    WorkClass,
    WorkClassSpec,
    WorkKind,
    compute_effect_state,
    final_delivery_for_outcome,
    notice_behavior_for_outcome,
    permission_eligibility_for_outcome,
    provisional_history_for_outcome,
    rpc_response_delivery_for_outcome,
    settlement_invariant_error,
)

SEND_CLASSES = frozenset(
    {
        WorkClass.PROGRESS,
        WorkClass.PROVISIONAL_PLAN,
        WorkClass.PERMISSION,
        WorkClass.TERMINAL_SET_MESSAGE,
        WorkClass.FALLBACK_SUB_SEND,
        WorkClass.PROTOCOL_RESPONSE,
        WorkClass.TERMINAL_REFUSAL,
        WorkClass.NON_TURN_PROTOCOL_RESPONSE,
        WorkClass.WARNING_NOTICE,
    }
)

DIRECTIVE_CLASSES = frozenset(
    {
        WorkClass.PLANNING_ITERATION,
        WorkClass.PLANNING_READ,
        WorkClass.GATEWAY,
        WorkClass.EXECUTION,
        WorkClass.PLAN_PERSISTENCE,
    }
)


def _by_class() -> dict[WorkClass, WorkClassSpec]:
    return {spec.work_class: spec for spec in WORK_CLASS_REGISTRY}


def test_registry_has_exactly_fifteen_rows_with_eight_fields() -> None:
    assert len(WORK_CLASS_REGISTRY) == 15
    assert len({spec.work_class for spec in WORK_CLASS_REGISTRY}) == 15
    for spec in WORK_CLASS_REGISTRY:
        assert isinstance(spec, WorkClassSpec)
        assert set(spec.__dataclass_fields__) == {
            "work_class",
            "kind",
            "owner",
            "gate_lane",
            "start_operation",
            "lifecycle_vocabulary",
            "terminal_vocabulary",
            "consequence",
        }


def test_exactly_nine_send_rows() -> None:
    sends = [spec for spec in WORK_CLASS_REGISTRY if spec.kind is WorkKind.SEND]
    assert len(sends) == 9
    assert {spec.work_class for spec in sends} == SEND_CLASSES


def test_directive_and_evidence_row_counts() -> None:
    directives = [spec for spec in WORK_CLASS_REGISTRY if spec.kind is WorkKind.DIRECTIVE]
    evidence = [spec for spec in WORK_CLASS_REGISTRY if spec.kind is WorkKind.EVIDENCE_APPEND]
    assert {spec.work_class for spec in directives} == DIRECTIVE_CLASSES
    assert len(evidence) == 1
    assert evidence[0].work_class is WorkClass.SETTLEMENT_TELEMETRY


def test_settlement_telemetry_has_no_owner_start_lifecycle_or_terminal() -> None:
    spec = _by_class()[WorkClass.SETTLEMENT_TELEMETRY]
    assert spec.kind is WorkKind.EVIDENCE_APPEND
    assert spec.owner is None
    assert spec.gate_lane is None
    assert spec.start_operation is None
    assert spec.lifecycle_vocabulary == frozenset()
    assert spec.terminal_vocabulary == frozenset()
    assert spec.consequence is Consequence.SETTLEMENT_TELEMETRY_EVIDENCE


def test_planning_iteration_is_halt_only_without_registered_lifecycle() -> None:
    spec = _by_class()[WorkClass.PLANNING_ITERATION]
    assert spec.kind is WorkKind.DIRECTIVE
    assert spec.owner is OwnerKind.TURN_CONTROL
    assert spec.gate_lane is None
    assert spec.start_operation is None
    assert spec.lifecycle_vocabulary == frozenset()
    assert spec.terminal_vocabulary == frozenset()
    assert spec.consequence is Consequence.PLANNING_HALT_ONLY


def test_planning_read_full_vocabularies() -> None:
    spec = _by_class()[WorkClass.PLANNING_READ]
    assert spec.lifecycle_vocabulary == PLANNING_READ_LIFECYCLE
    assert spec.terminal_vocabulary == PLANNING_READ_TERMINAL
    assert PLANNING_READ_LIFECYCLE == frozenset(
        {
            "not_started",
            "started",
            "succeeded",
            "failed_no_effect",
            "abandoned_no_effect",
            "suppressed",
        }
    )
    assert PLANNING_READ_TERMINAL == frozenset(
        {"succeeded", "failed_no_effect", "abandoned_no_effect", "suppressed"}
    )
    assert spec.consequence is Consequence.READ_NEVER_IN_E


def test_gateway_full_vocabularies() -> None:
    spec = _by_class()[WorkClass.GATEWAY]
    assert spec.lifecycle_vocabulary == GATEWAY_LIFECYCLE
    assert spec.terminal_vocabulary == GATEWAY_TERMINAL
    assert GATEWAY_LIFECYCLE == frozenset(
        {
            "not_started",
            "started",
            "succeeded",
            "failed_known_cost",
            "cost_unknown",
            "suppressed",
        }
    )
    assert GATEWAY_TERMINAL == frozenset(
        {"succeeded", "failed_known_cost", "cost_unknown", "suppressed"}
    )
    assert spec.consequence is Consequence.GATEWAY_COST_NEVER_IN_E


def test_execution_expands_read_and_write_test_vocabularies() -> None:
    spec = _by_class()[WorkClass.EXECUTION]
    assert EXECUTION_READ_LIFECYCLE == PLANNING_READ_LIFECYCLE
    assert EXECUTION_READ_TERMINAL == PLANNING_READ_TERMINAL
    assert EXECUTION_WRITE_TEST_LIFECYCLE == frozenset(
        {
            "not_started",
            "started",
            "succeeded",
            "failed_no_effect",
            "failed_effect_unknown",
            "suppressed",
        }
    )
    assert EXECUTION_WRITE_TEST_TERMINAL == frozenset(
        {"succeeded", "failed_no_effect", "failed_effect_unknown", "suppressed"}
    )
    assert spec.lifecycle_vocabulary == EXECUTION_READ_LIFECYCLE | EXECUTION_WRITE_TEST_LIFECYCLE
    assert spec.terminal_vocabulary == EXECUTION_READ_TERMINAL | EXECUTION_WRITE_TEST_TERMINAL
    assert spec.consequence is Consequence.EXECUTION_EFFECT_ALGEBRA


def test_plan_persistence_full_vocabularies() -> None:
    spec = _by_class()[WorkClass.PLAN_PERSISTENCE]
    assert spec.lifecycle_vocabulary == PLAN_PERSISTENCE_LIFECYCLE
    assert spec.terminal_vocabulary == PLAN_PERSISTENCE_TERMINAL
    assert PLAN_PERSISTENCE_TERMINAL == frozenset(
        {"persisted", "persistence_failed", "persistence_partial", "suppressed"}
    )
    assert "persisted" in PLAN_PERSISTENCE_LIFECYCLE
    assert "persistence_failed" in PLAN_PERSISTENCE_LIFECYCLE
    assert "persistence_partial" in PLAN_PERSISTENCE_LIFECYCLE
    assert spec.consequence is Consequence.PLAN_PERSISTENCE_NEVER_IN_E


def test_send_rows_share_common_lifecycle_and_terminal_sets() -> None:
    assert COMMON_SEND_LIFECYCLE == frozenset(
        {
            "queued",
            "write_started",
            "flushed",
            "conclusive_failure",
            "ambiguous",
            "suppressed",
        }
    )
    assert COMMON_SEND_TERMINAL == frozenset(
        {"flushed", "conclusive_failure", "ambiguous", "suppressed"}
    )
    for work_class in SEND_CLASSES:
        spec = _by_class()[work_class]
        assert spec.lifecycle_vocabulary == COMMON_SEND_LIFECYCLE
        assert spec.terminal_vocabulary == COMMON_SEND_TERMINAL


def test_send_owners_gates_and_start_operations() -> None:
    by_class = _by_class()

    turn_owned = {
        WorkClass.PROGRESS,
        WorkClass.PROVISIONAL_PLAN,
        WorkClass.PERMISSION,
        WorkClass.TERMINAL_SET_MESSAGE,
        WorkClass.FALLBACK_SUB_SEND,
        WorkClass.PROTOCOL_RESPONSE,
    }
    notice_owned = {
        WorkClass.TERMINAL_REFUSAL,
        WorkClass.NON_TURN_PROTOCOL_RESPONSE,
        WorkClass.WARNING_NOTICE,
    }

    for work_class in turn_owned:
        assert by_class[work_class].owner is OwnerKind.TURN_CONTROL
    for work_class in notice_owned:
        assert by_class[work_class].owner is OwnerKind.NOTICE_CONTROL

    assert by_class[WorkClass.PROGRESS].gate_lane is GateLane.EXECUTION_START
    assert by_class[WorkClass.PROGRESS].start_operation is StartOperation.TRY_START
    assert by_class[WorkClass.PROVISIONAL_PLAN].start_operation is StartOperation.TRY_START
    assert by_class[WorkClass.PERMISSION].start_operation is StartOperation.TRY_START
    assert by_class[WorkClass.TERMINAL_SET_MESSAGE].gate_lane is GateLane.TERMINAL_DELIVERY
    assert by_class[WorkClass.TERMINAL_SET_MESSAGE].start_operation is StartOperation.START_TERMINAL_MESSAGE
    assert by_class[WorkClass.FALLBACK_SUB_SEND].start_operation is StartOperation.START_TERMINAL_MESSAGE
    assert by_class[WorkClass.PROTOCOL_RESPONSE].gate_lane is GateLane.TRANSPORT_ABANDONED_CHECK
    assert by_class[WorkClass.PROTOCOL_RESPONSE].start_operation is StartOperation.START_RESPONSE_SEND
    assert by_class[WorkClass.TERMINAL_REFUSAL].start_operation is StartOperation.START_NOTICE_SEND
    assert (
        by_class[WorkClass.NON_TURN_PROTOCOL_RESPONSE].start_operation
        is StartOperation.START_NON_TURN_RESPONSE_SEND
    )
    assert by_class[WorkClass.WARNING_NOTICE].start_operation is StartOperation.BEGIN_WARNING_ATTEMPT


def test_protocol_response_mutates_only_rpc_response_delivery() -> None:
    protocol = _by_class()[WorkClass.PROTOCOL_RESPONSE]
    non_turn = _by_class()[WorkClass.NON_TURN_PROTOCOL_RESPONSE]
    assert protocol.consequence is Consequence.PROTOCOL_RESPONSE_RPC_ONLY
    assert non_turn.consequence is Consequence.NON_TURN_PROTOCOL_RESPONSE_RPC_ONLY
    for outcome in COMMON_SEND_TERMINAL:
        send_outcome = SendOutcome(outcome)
        assert rpc_response_delivery_for_outcome(WorkClass.PROTOCOL_RESPONSE, send_outcome) is not None
        assert final_delivery_for_outcome(WorkClass.PROTOCOL_RESPONSE, send_outcome) is None
        assert rpc_response_delivery_for_outcome(WorkClass.NON_TURN_PROTOCOL_RESPONSE, send_outcome) is not None
        assert final_delivery_for_outcome(WorkClass.NON_TURN_PROTOCOL_RESPONSE, send_outcome) is None


def test_terminal_set_and_fallback_mutate_only_final_delivery() -> None:
    for work_class in (WorkClass.TERMINAL_SET_MESSAGE, WorkClass.FALLBACK_SUB_SEND):
        assert _by_class()[work_class].consequence is Consequence.TERMINAL_SET_FINAL_DELIVERY
        for outcome in COMMON_SEND_TERMINAL:
            send_outcome = SendOutcome(outcome)
            assert final_delivery_for_outcome(work_class, send_outcome) is not None
            assert rpc_response_delivery_for_outcome(work_class, send_outcome) is None


def test_effect_algebra_empty_is_none() -> None:
    assert compute_effect_state(()) == EffectState.NONE
    assert compute_effect_state([]) == EffectState.NONE


def test_effect_algebra_all_succeeded_is_complete() -> None:
    assert (
        compute_effect_state(
            (
                ("write", "succeeded"),
                ("test", "succeeded"),
            )
        )
        == EffectState.COMPLETE
    )


def test_effect_algebra_any_failed_effect_unknown_is_indeterminate() -> None:
    assert (
        compute_effect_state(
            (
                ("write", "succeeded"),
                ("test", "failed_effect_unknown"),
            )
        )
        == EffectState.INDETERMINATE
    )
    assert compute_effect_state((("write", "failed_effect_unknown"),)) == EffectState.INDETERMINATE


def test_effect_algebra_named_write_succeeded_test_suppressed_is_partial() -> None:
    assert (
        compute_effect_state(
            (
                ("write", "succeeded"),
                ("test", "suppressed"),
            )
        )
        == EffectState.PARTIAL
    )


def test_effect_algebra_failed_no_effect_and_suppressed_only_is_none() -> None:
    assert (
        compute_effect_state(
            (
                ("write", "failed_no_effect"),
                ("test", "suppressed"),
            )
        )
        == EffectState.NONE
    )


def test_read_gateway_and_plan_persistence_never_enter_e() -> None:
    # Non-effectful terminals must be ignored even if passed accidentally.
    assert (
        compute_effect_state(
            (
                ("read", "succeeded"),
                ("gateway", "succeeded"),
                ("plan_persistence", "persisted"),
            )
        )
        == EffectState.NONE
    )
    assert (
        compute_effect_state(
            (
                ("read", "abandoned_no_effect"),
                ("write", "succeeded"),
            )
        )
        == EffectState.COMPLETE
    )


def test_send_outcome_to_final_delivery_mapping() -> None:
    assert (
        final_delivery_for_outcome(WorkClass.TERMINAL_SET_MESSAGE, SendOutcome.FLUSHED)
        is FinalDelivery.FLUSHED
    )
    assert (
        final_delivery_for_outcome(WorkClass.FALLBACK_SUB_SEND, SendOutcome.AMBIGUOUS)
        is FinalDelivery.AMBIGUOUS
    )
    assert (
        final_delivery_for_outcome(WorkClass.TERMINAL_SET_MESSAGE, SendOutcome.SUPPRESSED)
        is FinalDelivery.NOT_ATTEMPTED
    )
    assert (
        final_delivery_for_outcome(WorkClass.TERMINAL_SET_MESSAGE, SendOutcome.CONCLUSIVE_FAILURE)
        is FinalDelivery.CONCLUSIVE_FAILURE
    )


def test_send_outcome_to_rpc_response_delivery_mapping() -> None:
    assert (
        rpc_response_delivery_for_outcome(WorkClass.PROTOCOL_RESPONSE, SendOutcome.FLUSHED)
        is RpcResponseDelivery.FLUSHED
    )
    assert (
        rpc_response_delivery_for_outcome(WorkClass.NON_TURN_PROTOCOL_RESPONSE, SendOutcome.SUPPRESSED)
        is RpcResponseDelivery.NOT_ATTEMPTED
    )
    assert (
        rpc_response_delivery_for_outcome(WorkClass.PROTOCOL_RESPONSE, SendOutcome.AMBIGUOUS)
        is RpcResponseDelivery.AMBIGUOUS
    )


def test_provisional_history_consequences() -> None:
    assert (
        provisional_history_for_outcome(SendOutcome.FLUSHED)
        is ProvisionalHistoryEffect.PRIOR_HISTORY_FLUSH_TRUE
    )
    assert (
        provisional_history_for_outcome(SendOutcome.CONCLUSIVE_FAILURE)
        is ProvisionalHistoryEffect.PRIOR_HISTORY_FLUSH_FALSE
    )
    assert (
        provisional_history_for_outcome(SendOutcome.AMBIGUOUS)
        is ProvisionalHistoryEffect.LATCH_DELIVERY_INDETERMINATE
    )
    assert (
        provisional_history_for_outcome(SendOutcome.SUPPRESSED)
        is ProvisionalHistoryEffect.PRIOR_HISTORY_FLUSH_FALSE
    )


def test_permission_eligibility() -> None:
    assert permission_eligibility_for_outcome(SendOutcome.FLUSHED) is PermissionEligibility.AWAITABLE
    assert (
        permission_eligibility_for_outcome(SendOutcome.AMBIGUOUS) is PermissionEligibility.NOT_APPROVED
    )
    assert (
        permission_eligibility_for_outcome(SendOutcome.CONCLUSIVE_FAILURE)
        is PermissionEligibility.NOT_APPROVED
    )
    assert (
        permission_eligibility_for_outcome(SendOutcome.SUPPRESSED) is PermissionEligibility.NOT_APPROVED
    )


def test_notice_behavior_is_best_effort() -> None:
    for work_class in (WorkClass.PROGRESS, WorkClass.TERMINAL_REFUSAL, WorkClass.WARNING_NOTICE):
        for outcome in (
            SendOutcome.FLUSHED,
            SendOutcome.CONCLUSIVE_FAILURE,
            SendOutcome.AMBIGUOUS,
            SendOutcome.SUPPRESSED,
        ):
            assert notice_behavior_for_outcome(work_class, outcome) == "best_effort"


def test_unknown_class_outcome_raises_invariant() -> None:
    assert final_delivery_for_outcome(WorkClass.PROGRESS, SendOutcome.FLUSHED) is None
    assert rpc_response_delivery_for_outcome(WorkClass.PROGRESS, SendOutcome.FLUSHED) is None

    with pytest.raises(settlement_invariant_error()) as exc_info:
        final_delivery_for_outcome(WorkClass.PLANNING_READ, SendOutcome.FLUSHED)
    assert "PLANNING_READ" in str(exc_info.value) or "Planning READ" in str(exc_info.value)

    with pytest.raises(settlement_invariant_error()):
        rpc_response_delivery_for_outcome(WorkClass.GATEWAY, SendOutcome.FLUSHED)

    with pytest.raises(settlement_invariant_error()):
        notice_behavior_for_outcome(WorkClass.PROTOCOL_RESPONSE, SendOutcome.FLUSHED)


def test_turn_settlement_snapshot_is_frozen() -> None:
    snapshot = TurnSettlementSnapshot(
        settlement=Settlement.COMPLETED,
        final_delivery=FinalDelivery.FLUSHED,
        rpc_response_delivery=RpcResponseDelivery.FLUSHED,
        conversation_commit=ConversationCommit.COMMITTED,
        effect_state=EffectState.COMPLETE,
        cost_complete=True,
    )
    assert snapshot.settlement is Settlement.COMPLETED
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.settlement = Settlement.FAILED  # type: ignore[misc]
