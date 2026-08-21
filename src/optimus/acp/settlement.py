"""Pure multi-turn settlement vocabulary and work-class registry (Plan 11.25 Task 1).

No asyncio or I/O. Production and tests import the same immutable WORK_CLASS_REGISTRY.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class SettlementInvariantError(ValueError):
    """Unknown work-class / outcome combination — never best-effort."""


def settlement_invariant_error() -> type[SettlementInvariantError]:
    return SettlementInvariantError


class WorkClass(StrEnum):
    PLANNING_ITERATION = "Planning iteration"
    PLANNING_READ = "Planning READ"
    GATEWAY = "Gateway"
    EXECUTION = "Execution (READ/WRITE/TEST)"
    PLAN_PERSISTENCE = "Plan persistence"
    PROGRESS = "Progress"
    PROVISIONAL_PLAN = "Provisional plan"
    PERMISSION = "Permission"
    TERMINAL_SET_MESSAGE = "Terminal-set message"
    FALLBACK_SUB_SEND = "Fallback sub-send"
    PROTOCOL_RESPONSE = "Protocol response"
    TERMINAL_REFUSAL = "Terminal refusal"
    NON_TURN_PROTOCOL_RESPONSE = "Non-turn protocol response"
    WARNING_NOTICE = "80%-warning notice"
    SETTLEMENT_TELEMETRY = "Settlement telemetry"


class WorkKind(StrEnum):
    DIRECTIVE = "directive"
    SEND = "send"
    EVIDENCE_APPEND = "evidence append"


class OwnerKind(StrEnum):
    TURN_CONTROL = "TurnControl"
    NOTICE_CONTROL = "NoticeControl"


class GateLane(StrEnum):
    EXECUTION_START = "execution-start gate"
    TERMINAL_DELIVERY = "terminal-delivery lane"
    TRANSPORT_ABANDONED_CHECK = "transport-abandoned check only"


class StartOperation(StrEnum):
    TRY_START = "try_start"
    START_TERMINAL_MESSAGE = "start_terminal_message"
    START_RESPONSE_SEND = "start_response_send"
    START_NOTICE_SEND = "start_notice_send"
    START_NON_TURN_RESPONSE_SEND = "start_non_turn_response_send"
    BEGIN_WARNING_ATTEMPT = "begin_warning_attempt"


class Consequence(StrEnum):
    PLANNING_HALT_ONLY = "planning_halt_only"
    READ_NEVER_IN_E = "read_never_in_e"
    GATEWAY_COST_NEVER_IN_E = "gateway_cost_never_in_e"
    EXECUTION_EFFECT_ALGEBRA = "execution_effect_algebra"
    PLAN_PERSISTENCE_NEVER_IN_E = "plan_persistence_never_in_e"
    PROGRESS_BEST_EFFORT = "progress_best_effort"
    PROVISIONAL_PLAN_HISTORY = "provisional_plan_history"
    PERMISSION_APPROVAL = "permission_approval"
    TERMINAL_SET_FINAL_DELIVERY = "terminal_set_final_delivery"
    PROTOCOL_RESPONSE_RPC_ONLY = "protocol_response_rpc_only"
    TERMINAL_REFUSAL_BEST_EFFORT = "terminal_refusal_best_effort"
    NON_TURN_PROTOCOL_RESPONSE_RPC_ONLY = "non_turn_protocol_response_rpc_only"
    WARNING_NOTICE_BEST_EFFORT = "warning_notice_best_effort"
    SETTLEMENT_TELEMETRY_EVIDENCE = "settlement_telemetry_evidence"


class SendState(StrEnum):
    QUEUED = "queued"
    WRITE_STARTED = "write_started"
    FLUSHED = "flushed"
    CONCLUSIVE_FAILURE = "conclusive_failure"
    AMBIGUOUS = "ambiguous"
    SUPPRESSED = "suppressed"


class SendOutcome(StrEnum):
    FLUSHED = "flushed"
    CONCLUSIVE_FAILURE = "conclusive_failure"
    AMBIGUOUS = "ambiguous"
    SUPPRESSED = "suppressed"


class Settlement(StrEnum):
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TRANSPORT_ABANDONED = "transport_abandoned"


class FinalDelivery(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    PARTIAL = "partial"
    FLUSHED = "flushed"
    CONCLUSIVE_FAILURE = "conclusive_failure"
    AMBIGUOUS = "ambiguous"


class RpcResponseDelivery(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    FLUSHED = "flushed"
    CONCLUSIVE_FAILURE = "conclusive_failure"
    AMBIGUOUS = "ambiguous"


class ConversationCommit(StrEnum):
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"


class EffectState(StrEnum):
    NONE = "none"
    COMPLETE = "complete"
    PARTIAL = "partial"
    INDETERMINATE = "indeterminate"


class ProvisionalHistoryEffect(StrEnum):
    PRIOR_HISTORY_FLUSH_TRUE = "prior_history_flush_true"
    PRIOR_HISTORY_FLUSH_FALSE = "prior_history_flush_false"
    LATCH_DELIVERY_INDETERMINATE = "latch_delivery_indeterminate"


class PermissionEligibility(StrEnum):
    AWAITABLE = "awaitable"
    NOT_APPROVED = "not_approved"


PLANNING_READ_LIFECYCLE: frozenset[str] = frozenset(
    {
        "not_started",
        "started",
        "succeeded",
        "failed_no_effect",
        "abandoned_no_effect",
        "suppressed",
    }
)
PLANNING_READ_TERMINAL: frozenset[str] = frozenset(
    {"succeeded", "failed_no_effect", "abandoned_no_effect", "suppressed"}
)

GATEWAY_LIFECYCLE: frozenset[str] = frozenset(
    {
        "not_started",
        "started",
        "succeeded",
        "failed_known_cost",
        "cost_unknown",
        "suppressed",
    }
)
GATEWAY_TERMINAL: frozenset[str] = frozenset(
    {"succeeded", "failed_known_cost", "cost_unknown", "suppressed"}
)

EXECUTION_READ_LIFECYCLE: frozenset[str] = PLANNING_READ_LIFECYCLE
EXECUTION_READ_TERMINAL: frozenset[str] = PLANNING_READ_TERMINAL
EXECUTION_WRITE_TEST_LIFECYCLE: frozenset[str] = frozenset(
    {
        "not_started",
        "started",
        "succeeded",
        "failed_no_effect",
        "failed_effect_unknown",
        "suppressed",
    }
)
EXECUTION_WRITE_TEST_TERMINAL: frozenset[str] = frozenset(
    {"succeeded", "failed_no_effect", "failed_effect_unknown", "suppressed"}
)

PLAN_PERSISTENCE_LIFECYCLE: frozenset[str] = frozenset(
    {
        "not_started",
        "started",
        "persisted",
        "persistence_failed",
        "persistence_partial",
        "suppressed",
    }
)
PLAN_PERSISTENCE_TERMINAL: frozenset[str] = frozenset(
    {"persisted", "persistence_failed", "persistence_partial", "suppressed"}
)

COMMON_SEND_LIFECYCLE: frozenset[str] = frozenset(
    {
        "queued",
        "write_started",
        "flushed",
        "conclusive_failure",
        "ambiguous",
        "suppressed",
    }
)
COMMON_SEND_TERMINAL: frozenset[str] = frozenset(
    {"flushed", "conclusive_failure", "ambiguous", "suppressed"}
)

_EFFECTFUL_KINDS = frozenset({"write", "test"})


@dataclass(frozen=True, slots=True)
class WorkClassSpec:
    work_class: WorkClass
    kind: WorkKind
    owner: OwnerKind | None
    gate_lane: GateLane | None
    start_operation: StartOperation | None
    lifecycle_vocabulary: frozenset[str]
    terminal_vocabulary: frozenset[str]
    consequence: Consequence


WORK_CLASS_REGISTRY: tuple[WorkClassSpec, ...] = (
    WorkClassSpec(
        work_class=WorkClass.PLANNING_ITERATION,
        kind=WorkKind.DIRECTIVE,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=None,
        start_operation=None,
        lifecycle_vocabulary=frozenset(),
        terminal_vocabulary=frozenset(),
        consequence=Consequence.PLANNING_HALT_ONLY,
    ),
    WorkClassSpec(
        work_class=WorkClass.PLANNING_READ,
        kind=WorkKind.DIRECTIVE,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.EXECUTION_START,
        start_operation=StartOperation.TRY_START,
        lifecycle_vocabulary=PLANNING_READ_LIFECYCLE,
        terminal_vocabulary=PLANNING_READ_TERMINAL,
        consequence=Consequence.READ_NEVER_IN_E,
    ),
    WorkClassSpec(
        work_class=WorkClass.GATEWAY,
        kind=WorkKind.DIRECTIVE,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.EXECUTION_START,
        start_operation=StartOperation.TRY_START,
        lifecycle_vocabulary=GATEWAY_LIFECYCLE,
        terminal_vocabulary=GATEWAY_TERMINAL,
        consequence=Consequence.GATEWAY_COST_NEVER_IN_E,
    ),
    WorkClassSpec(
        work_class=WorkClass.EXECUTION,
        kind=WorkKind.DIRECTIVE,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.EXECUTION_START,
        start_operation=StartOperation.TRY_START,
        lifecycle_vocabulary=EXECUTION_READ_LIFECYCLE | EXECUTION_WRITE_TEST_LIFECYCLE,
        terminal_vocabulary=EXECUTION_READ_TERMINAL | EXECUTION_WRITE_TEST_TERMINAL,
        consequence=Consequence.EXECUTION_EFFECT_ALGEBRA,
    ),
    WorkClassSpec(
        work_class=WorkClass.PLAN_PERSISTENCE,
        kind=WorkKind.DIRECTIVE,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.EXECUTION_START,
        start_operation=StartOperation.TRY_START,
        lifecycle_vocabulary=PLAN_PERSISTENCE_LIFECYCLE,
        terminal_vocabulary=PLAN_PERSISTENCE_TERMINAL,
        consequence=Consequence.PLAN_PERSISTENCE_NEVER_IN_E,
    ),
    WorkClassSpec(
        work_class=WorkClass.PROGRESS,
        kind=WorkKind.SEND,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.EXECUTION_START,
        start_operation=StartOperation.TRY_START,
        lifecycle_vocabulary=COMMON_SEND_LIFECYCLE,
        terminal_vocabulary=COMMON_SEND_TERMINAL,
        consequence=Consequence.PROGRESS_BEST_EFFORT,
    ),
    WorkClassSpec(
        work_class=WorkClass.PROVISIONAL_PLAN,
        kind=WorkKind.SEND,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.EXECUTION_START,
        start_operation=StartOperation.TRY_START,
        lifecycle_vocabulary=COMMON_SEND_LIFECYCLE,
        terminal_vocabulary=COMMON_SEND_TERMINAL,
        consequence=Consequence.PROVISIONAL_PLAN_HISTORY,
    ),
    WorkClassSpec(
        work_class=WorkClass.PERMISSION,
        kind=WorkKind.SEND,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.EXECUTION_START,
        start_operation=StartOperation.TRY_START,
        lifecycle_vocabulary=COMMON_SEND_LIFECYCLE,
        terminal_vocabulary=COMMON_SEND_TERMINAL,
        consequence=Consequence.PERMISSION_APPROVAL,
    ),
    WorkClassSpec(
        work_class=WorkClass.TERMINAL_SET_MESSAGE,
        kind=WorkKind.SEND,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.TERMINAL_DELIVERY,
        start_operation=StartOperation.START_TERMINAL_MESSAGE,
        lifecycle_vocabulary=COMMON_SEND_LIFECYCLE,
        terminal_vocabulary=COMMON_SEND_TERMINAL,
        consequence=Consequence.TERMINAL_SET_FINAL_DELIVERY,
    ),
    WorkClassSpec(
        work_class=WorkClass.FALLBACK_SUB_SEND,
        kind=WorkKind.SEND,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.TERMINAL_DELIVERY,
        start_operation=StartOperation.START_TERMINAL_MESSAGE,
        lifecycle_vocabulary=COMMON_SEND_LIFECYCLE,
        terminal_vocabulary=COMMON_SEND_TERMINAL,
        consequence=Consequence.TERMINAL_SET_FINAL_DELIVERY,
    ),
    WorkClassSpec(
        work_class=WorkClass.PROTOCOL_RESPONSE,
        kind=WorkKind.SEND,
        owner=OwnerKind.TURN_CONTROL,
        gate_lane=GateLane.TRANSPORT_ABANDONED_CHECK,
        start_operation=StartOperation.START_RESPONSE_SEND,
        lifecycle_vocabulary=COMMON_SEND_LIFECYCLE,
        terminal_vocabulary=COMMON_SEND_TERMINAL,
        consequence=Consequence.PROTOCOL_RESPONSE_RPC_ONLY,
    ),
    WorkClassSpec(
        work_class=WorkClass.TERMINAL_REFUSAL,
        kind=WorkKind.SEND,
        owner=OwnerKind.NOTICE_CONTROL,
        gate_lane=GateLane.TRANSPORT_ABANDONED_CHECK,
        start_operation=StartOperation.START_NOTICE_SEND,
        lifecycle_vocabulary=COMMON_SEND_LIFECYCLE,
        terminal_vocabulary=COMMON_SEND_TERMINAL,
        consequence=Consequence.TERMINAL_REFUSAL_BEST_EFFORT,
    ),
    WorkClassSpec(
        work_class=WorkClass.NON_TURN_PROTOCOL_RESPONSE,
        kind=WorkKind.SEND,
        owner=OwnerKind.NOTICE_CONTROL,
        gate_lane=GateLane.TRANSPORT_ABANDONED_CHECK,
        start_operation=StartOperation.START_NON_TURN_RESPONSE_SEND,
        lifecycle_vocabulary=COMMON_SEND_LIFECYCLE,
        terminal_vocabulary=COMMON_SEND_TERMINAL,
        consequence=Consequence.NON_TURN_PROTOCOL_RESPONSE_RPC_ONLY,
    ),
    WorkClassSpec(
        work_class=WorkClass.WARNING_NOTICE,
        kind=WorkKind.SEND,
        owner=OwnerKind.NOTICE_CONTROL,
        gate_lane=GateLane.TRANSPORT_ABANDONED_CHECK,
        start_operation=StartOperation.BEGIN_WARNING_ATTEMPT,
        lifecycle_vocabulary=COMMON_SEND_LIFECYCLE,
        terminal_vocabulary=COMMON_SEND_TERMINAL,
        consequence=Consequence.WARNING_NOTICE_BEST_EFFORT,
    ),
    WorkClassSpec(
        work_class=WorkClass.SETTLEMENT_TELEMETRY,
        kind=WorkKind.EVIDENCE_APPEND,
        owner=None,
        gate_lane=None,
        start_operation=None,
        lifecycle_vocabulary=frozenset(),
        terminal_vocabulary=frozenset(),
        consequence=Consequence.SETTLEMENT_TELEMETRY_EVIDENCE,
    ),
)


@dataclass(frozen=True, slots=True)
class TurnSettlementSnapshot:
    settlement: Settlement
    final_delivery: FinalDelivery
    rpc_response_delivery: RpcResponseDelivery
    conversation_commit: ConversationCommit
    effect_state: EffectState
    cost_complete: bool


def _send_outcome_to_delivery_value(
    outcome: SendOutcome,
) -> Literal["flushed", "conclusive_failure", "ambiguous", "not_attempted"]:
    if outcome is SendOutcome.FLUSHED:
        return "flushed"
    if outcome is SendOutcome.CONCLUSIVE_FAILURE:
        return "conclusive_failure"
    if outcome is SendOutcome.AMBIGUOUS:
        return "ambiguous"
    if outcome is SendOutcome.SUPPRESSED:
        return "not_attempted"
    raise SettlementInvariantError(f"unknown send outcome: {outcome!r}")


_FINAL_DELIVERY_CLASSES = frozenset(
    {WorkClass.TERMINAL_SET_MESSAGE, WorkClass.FALLBACK_SUB_SEND}
)
_RPC_RESPONSE_DELIVERY_CLASSES = frozenset(
    {WorkClass.PROTOCOL_RESPONSE, WorkClass.NON_TURN_PROTOCOL_RESPONSE}
)
_SEND_WORK_CLASSES = frozenset(
    spec.work_class for spec in WORK_CLASS_REGISTRY if spec.kind is WorkKind.SEND
)


def final_delivery_for_outcome(work_class: WorkClass, outcome: SendOutcome) -> FinalDelivery | None:
    if work_class in _FINAL_DELIVERY_CLASSES:
        return FinalDelivery(_send_outcome_to_delivery_value(outcome))
    if work_class in _SEND_WORK_CLASSES:
        return None
    raise SettlementInvariantError(
        f"final_delivery is not defined for work class {work_class!r} / outcome {outcome!r}"
    )


def rpc_response_delivery_for_outcome(
    work_class: WorkClass, outcome: SendOutcome
) -> RpcResponseDelivery | None:
    if work_class in _RPC_RESPONSE_DELIVERY_CLASSES:
        return RpcResponseDelivery(_send_outcome_to_delivery_value(outcome))
    if work_class in _SEND_WORK_CLASSES:
        return None
    raise SettlementInvariantError(
        f"rpc_response_delivery is not defined for work class {work_class!r} / outcome {outcome!r}"
    )


def provisional_history_for_outcome(outcome: SendOutcome) -> ProvisionalHistoryEffect:
    if outcome is SendOutcome.FLUSHED:
        return ProvisionalHistoryEffect.PRIOR_HISTORY_FLUSH_TRUE
    if outcome is SendOutcome.AMBIGUOUS:
        return ProvisionalHistoryEffect.LATCH_DELIVERY_INDETERMINATE
    if outcome in {SendOutcome.CONCLUSIVE_FAILURE, SendOutcome.SUPPRESSED}:
        return ProvisionalHistoryEffect.PRIOR_HISTORY_FLUSH_FALSE
    raise SettlementInvariantError(f"unknown provisional-plan outcome: {outcome!r}")


def permission_eligibility_for_outcome(outcome: SendOutcome) -> PermissionEligibility:
    if outcome is SendOutcome.FLUSHED:
        return PermissionEligibility.AWAITABLE
    if outcome in {
        SendOutcome.AMBIGUOUS,
        SendOutcome.CONCLUSIVE_FAILURE,
        SendOutcome.SUPPRESSED,
    }:
        return PermissionEligibility.NOT_APPROVED
    raise SettlementInvariantError(f"unknown permission outcome: {outcome!r}")


def notice_behavior_for_outcome(work_class: WorkClass, outcome: SendOutcome) -> str:
    if work_class not in {
        WorkClass.PROGRESS,
        WorkClass.TERMINAL_REFUSAL,
        WorkClass.WARNING_NOTICE,
    }:
        raise SettlementInvariantError(
            f"notice behavior is not defined for work class {work_class!r} / outcome {outcome!r}"
        )
    if outcome not in {
        SendOutcome.FLUSHED,
        SendOutcome.CONCLUSIVE_FAILURE,
        SendOutcome.AMBIGUOUS,
        SendOutcome.SUPPRESSED,
    }:
        raise SettlementInvariantError(f"unknown notice outcome: {outcome!r}")
    return "best_effort"


def compute_effect_state(
    directive_terminals: Sequence[tuple[str, str]] | Iterable[tuple[str, str]],
) -> EffectState:
    """Map effectful WRITE/TEST terminals to effect_state (§2.4.2).

    First matching row wins:
    any failed_effect_unknown -> indeterminate
    E == 0 -> none
    every effectful succeeded (E > 0) -> complete
    no effectful succeeded -> none
    otherwise -> partial

    READ, Gateway, and plan persistence never enter E.
    """
    effectful: list[str] = []
    for kind, terminal in directive_terminals:
        if kind not in _EFFECTFUL_KINDS:
            continue
        effectful.append(terminal)

    if any(terminal == "failed_effect_unknown" for terminal in effectful):
        return EffectState.INDETERMINATE
    if not effectful:
        return EffectState.NONE
    if all(terminal == "succeeded" for terminal in effectful):
        return EffectState.COMPLETE
    if not any(terminal == "succeeded" for terminal in effectful):
        return EffectState.NONE
    return EffectState.PARTIAL
