import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import (
    AgentState,
    AwaitingApproval,
    RuntimeContext,
    StateTransition,
    TransitionValidator,
)
from optimus.tools.mutation_tools import write_file


def test_full_plan_chat_boundary_returns_plan_text_and_does_not_mutate(tmp_path):
    context = RuntimeContext(execution_mode=ExecutionMode.PLAN)
    validator = TransitionValidator()
    context = validator.transition(context, StateTransition(AgentState.PLANNING, "user request"))
    context = validator.transition(context, StateTransition(AgentState.PLAN_READY, "plan ready"))
    context = validator.transition(context, StateTransition(AgentState.CHAT_ONLY, "advisory response"))

    plan_text = "Plan text returned for review."
    target = tmp_path / "blocked.txt"
    with pytest.raises(MutationForbidden):
        write_file(target, "blocked", context=context)

    assert plan_text == "Plan text returned for review."
    assert target.exists() is False


def test_agent_mode_approval_denied_falls_back_to_chat_only_and_no_mutation(tmp_path):
    context = RuntimeContext(execution_mode=ExecutionMode.AGENT)
    validator = TransitionValidator()
    context = validator.transition(context, StateTransition(AgentState.PLANNING, "user request"))
    context = validator.transition(context, StateTransition(AgentState.PLAN_READY, "plan ready"))
    context = validator.transition(context, StateTransition(AgentState.AWAITING_APPROVAL, "needs approval"))
    context = AwaitingApproval("approval-1", requested_at_ms=1000, timeout_ms=5000).deny(context)

    target = tmp_path / "denied.txt"
    with pytest.raises(MutationForbidden):
        write_file(target, "blocked", context=context)

    assert context.state is AgentState.CHAT_ONLY
    assert target.exists() is False


def test_agent_mode_after_approval_can_write_file(tmp_path):
    context = RuntimeContext(execution_mode=ExecutionMode.AGENT)
    validator = TransitionValidator()
    context = validator.transition(context, StateTransition(AgentState.PLANNING, "user request"))
    context = validator.transition(context, StateTransition(AgentState.PLAN_READY, "plan ready"))
    context = validator.transition(context, StateTransition(AgentState.AWAITING_APPROVAL, "needs approval"))
    context = AwaitingApproval("approval-1", requested_at_ms=1000, timeout_ms=5000).grant(context)
    context = validator.transition(context, StateTransition(AgentState.EXECUTING, "approval granted"))

    target = tmp_path / "allowed.txt"
    write_file(target, "allowed", context=context)

    assert target.read_text(encoding="utf-8") == "allowed"
