import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import (
    MutationForbidden,
    MutationGuard,
    MutationKind,
    assert_mutation_allowed,
)
from optimus.runtime.state import AgentState, RuntimeContext


def test_plan_mode_mutation_forbidden_with_required_message():
    context = RuntimeContext(execution_mode=ExecutionMode.PLAN, state=AgentState.CHAT_ONLY)

    with pytest.raises(MutationForbidden) as exc_info:
        assert_mutation_allowed(context, MutationKind.WRITE_FILE)

    assert exc_info.value.code == -32002
    assert str(exc_info.value) == "mutation forbidden in Plan/Chat mode"


def test_chat_mode_mutation_forbidden_with_required_message():
    context = RuntimeContext(execution_mode=ExecutionMode.CHAT, state=AgentState.CHAT_ONLY)

    with pytest.raises(MutationForbidden, match="mutation forbidden in Plan/Chat mode"):
        assert_mutation_allowed(context, MutationKind.SHELL_EXEC)


def test_agent_mode_before_approval_forbidden():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.AWAITING_APPROVAL,
        approval_granted=False,
    )

    with pytest.raises(MutationForbidden, match="approval required before mutation"):
        assert_mutation_allowed(context, MutationKind.WRITE_FILE)


def test_agent_mode_after_approval_allowed_in_executing_state():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-123",
    )

    assert assert_mutation_allowed(context, MutationKind.WRITE_FILE) is None


def test_agent_mode_mutation_rejected_from_terminal_state():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.TERMINATED,
        approval_granted=True,
        user_approval_id="approval-123",
    )

    with pytest.raises(MutationForbidden, match="mutation not allowed from state TERMINATED"):
        MutationGuard().assert_allowed(context, MutationKind.SHADOW_APPLY)
