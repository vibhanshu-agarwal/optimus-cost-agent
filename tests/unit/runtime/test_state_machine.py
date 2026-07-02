import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import (
    AgentState,
    RuntimeContext,
    StateTransition,
    TransitionValidator,
)


def test_idle_to_planning_valid_on_user_request():
    context = RuntimeContext(execution_mode=ExecutionMode.PLAN)

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.PLANNING, reason="user request"),
    )

    assert updated.state is AgentState.PLANNING


def test_plan_ready_to_chat_only_valid_for_plan_mode():
    context = RuntimeContext(
        execution_mode=ExecutionMode.PLAN,
        state=AgentState.PLAN_READY,
    )

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.CHAT_ONLY, reason="advisory response"),
    )

    assert updated.state is AgentState.CHAT_ONLY


def test_plan_ready_direct_to_executing_rejected_with_code_32002():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.PLAN_READY,
    )

    with pytest.raises(MutationForbidden) as exc_info:
        TransitionValidator().transition(
            context,
            StateTransition(target=AgentState.EXECUTING, reason="bypass approval"),
        )

    assert exc_info.value.code == -32002
    assert "must pass through AwaitingApproval" in str(exc_info.value)


def test_any_bypass_to_executing_rejected():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.IDLE,
    )

    with pytest.raises(MutationForbidden, match="No path bypasses AwaitingApproval"):
        TransitionValidator().transition(
            context,
            StateTransition(target=AgentState.EXECUTING, reason="bypass"),
        )


def test_failed_to_planning_increments_retry_count():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.FAILED,
        retry_count=1,
        failure_context="gate failed",
    )

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.PLANNING, reason="retry"),
    )

    assert updated.state is AgentState.PLANNING
    assert updated.retry_count == 2
    assert updated.failure_context == "gate failed"


def test_failed_to_terminated_after_max_retries():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.FAILED,
        retry_count=3,
        max_retries=3,
    )

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.TERMINATED, reason="retry budget exhausted"),
    )

    assert updated.state is AgentState.TERMINATED
    assert updated.user_escalation is True


def test_approved_execution_enters_tool_calling_then_validating():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-123",
    )
    validator = TransitionValidator()

    tool_calling = validator.transition(
        context,
        StateTransition(target=AgentState.TOOL_CALLING, reason="authorized tool call"),
    )
    validating = validator.transition(
        tool_calling,
        StateTransition(target=AgentState.VALIDATING, reason="tool response received"),
    )

    assert tool_calling.state is AgentState.TOOL_CALLING
    assert validating.state is AgentState.VALIDATING


def test_validation_pass_returns_to_executing_before_completion():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.VALIDATING,
        approval_granted=True,
        user_approval_id="approval-123",
    )
    validator = TransitionValidator()

    executing = validator.transition(
        context,
        StateTransition(target=AgentState.EXECUTING, reason="all gates passed"),
    )
    completed = validator.transition(
        executing,
        StateTransition(target=AgentState.COMPLETED, reason="planned work done"),
    )

    assert executing.state is AgentState.EXECUTING
    assert completed.state is AgentState.COMPLETED


def test_validation_failure_enters_failed_state():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.VALIDATING,
        approval_granted=True,
        user_approval_id="approval-123",
    )

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.FAILED, reason="fitness gate failed"),
    )

    assert updated.state is AgentState.FAILED


def test_validation_pass_requires_existing_approval():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.VALIDATING,
        approval_granted=False,
        user_approval_id=None,
    )

    with pytest.raises(MutationForbidden, match="approval required before Executing"):
        TransitionValidator().transition(
            context,
            StateTransition(target=AgentState.EXECUTING, reason="all gates passed"),
        )
