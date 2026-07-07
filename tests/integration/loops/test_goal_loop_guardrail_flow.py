from datetime import UTC, datetime
from decimal import Decimal

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.loops.controller import GoalLoopController
from optimus.loops.ledger import InMemoryProgressLedger
from optimus.loops.models import CompletionEvaluation, IterationOutcome, IterationState, LoopBudgetPolicy, LoopStopReason
from optimus.loops.tools import GuardedLoopToolExecutor, LoopToolBlocked
from optimus.runtime.modes import ExecutionMode


class UnsafeRunner:
    def run_iteration(self, state: IterationState, tools: GuardedLoopToolExecutor) -> IterationOutcome:
        try:
            tools.preflight(
                run_id=state.run_id,
                session_id=state.session_id,
                execution_mode=ExecutionMode.AGENT,
                tool_surface=ToolSurface.SHELL,
                action="rm -rf src",
                command=("rm", "-rf", "src"),
                approval_granted=True,
            )
        except LoopToolBlocked as exc:
            return IterationOutcome(summary=exc.result.reason, failure_signature=exc.result.rule_id)
        return IterationOutcome(summary="unexpected allow")


class NeverComplete:
    def evaluate(self, state, ledger):
        return CompletionEvaluation(completed=False, reason="not done")


def test_goal_loop_never_bypasses_pre_tool_guard(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    tools = GuardedLoopToolExecutor(guard=guard)
    ledger = InMemoryProgressLedger()
    controller = GoalLoopController(
        policy=LoopBudgetPolicy(max_iterations=5, max_budget_credits=Decimal("1"), max_wall_clock_minutes=5, repeated_failure_limit=2),
        runner=UnsafeRunner(),
        tools=tools,
        evaluator=NeverComplete(),
        ledger=ledger,
        now=lambda: datetime(2026, 7, 6, tzinfo=UTC),
    )

    result = controller.run(
        IterationState(
            run_id="run-1",
            session_id="session-1",
            goal="Try unsafe loop action",
            completion_condition="must not run unsafe command",
            started_at=datetime(2026, 7, 6, tzinfo=UTC),
        )
    )

    assert result.stop_reason is LoopStopReason.REPEATED_FAILURE
    assert guard.audit_events()
    assert guard.audit_events()[0].rule_id == "shell.destructive.rm_rf"
