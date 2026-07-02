from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden


class AgentState(StrEnum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    CHAT_ONLY = "CHAT_ONLY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    TOOL_CALLING = "TOOL_CALLING"
    VALIDATING = "VALIDATING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


@dataclass(frozen=True)
class RuntimeContext:
    execution_mode: ExecutionMode
    state: AgentState = AgentState.IDLE
    approval_granted: bool = False
    user_approval_id: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    failure_context: str | None = None
    user_escalation: bool = False


@dataclass(frozen=True)
class StateTransition:
    target: AgentState
    reason: str


class TransitionValidator:
    def transition(
        self,
        context: RuntimeContext,
        transition: StateTransition,
    ) -> RuntimeContext:
        source = context.state
        target = transition.target

        if target is AgentState.EXECUTING and source not in {
            AgentState.AWAITING_APPROVAL,
            AgentState.VALIDATING,
        }:
            if source is AgentState.PLAN_READY:
                raise MutationForbidden("PlanReady -> Executing rejected: must pass through AwaitingApproval")
            raise MutationForbidden("No path bypasses AwaitingApproval")

        if source is AgentState.IDLE and target is AgentState.PLANNING:
            return replace(context, state=target)
        if source is AgentState.PLANNING and target is AgentState.PLAN_READY:
            return replace(context, state=target)
        if source is AgentState.PLAN_READY and target is AgentState.CHAT_ONLY:
            if context.execution_mode is ExecutionMode.AGENT:
                raise MutationForbidden("Agent mode cannot fall through to ChatOnly without denial or timeout")
            return replace(context, state=target)
        if source is AgentState.PLAN_READY and target is AgentState.AWAITING_APPROVAL:
            if context.execution_mode is not ExecutionMode.AGENT:
                raise MutationForbidden("AwaitingApproval is valid only in Agent mode")
            return replace(context, state=target)
        if source is AgentState.AWAITING_APPROVAL and target is AgentState.EXECUTING:
            if not context.approval_granted:
                raise MutationForbidden("approval required before Executing")
            return replace(context, state=target)
        if source is AgentState.AWAITING_APPROVAL and target is AgentState.CHAT_ONLY:
            return replace(context, state=target, approval_granted=False)
        if source is AgentState.EXECUTING and target in {AgentState.TOOL_CALLING, AgentState.COMPLETED}:
            return replace(context, state=target)
        if source is AgentState.TOOL_CALLING and target is AgentState.VALIDATING:
            return replace(context, state=target)
        if source is AgentState.VALIDATING and target in {AgentState.EXECUTING, AgentState.FAILED}:
            if target is AgentState.EXECUTING and not context.approval_granted:
                raise MutationForbidden("approval required before Executing")
            return replace(context, state=target)
        if source is AgentState.FAILED and target is AgentState.PLANNING:
            if context.retry_count >= context.max_retries:
                raise MutationForbidden("retry budget exhausted")
            return replace(context, state=target, retry_count=context.retry_count + 1)
        if source is AgentState.FAILED and target is AgentState.TERMINATED:
            return replace(context, state=target, user_escalation=True)

        raise MutationForbidden(f"invalid transition: {source.value} -> {target.value}")
