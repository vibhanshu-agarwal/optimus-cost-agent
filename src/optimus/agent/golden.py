from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.golden.runner import GoldenTaskHarness
from optimus.golden.tasks import GoldenTask, GoldenTaskResult
from optimus.release.credentials import scan_local_credentials
from optimus.runtime.modes import ExecutionMode


class AgentGoldenTaskHarness(GoldenTaskHarness):
    def __init__(self, *, runner: AgentRunner, workspace_root: str | Path) -> None:
        self._runner = runner
        self._workspace_root = Path(workspace_root).resolve()

    def run(self, task: GoldenTask) -> GoldenTaskResult:
        mode = ExecutionMode.AGENT if task.expected_mode == "agent" else ExecutionMode.PLAN
        approval = AgentApproval()
        plan_cost = Decimal("0")
        run_id = f"golden:{task.task_id}"
        if mode is ExecutionMode.AGENT:
            plan_result = self._runner.run(
                AgentRunRequest(
                    run_id=run_id,
                    session_id=None,
                    task=task.description,
                    execution_mode=mode,
                    workspace_root=self._workspace_root,
                    max_cost_usd=task.max_cost_usd,
                )
            )
            plan_cost = plan_result.total_cost_usd
            if plan_result.status is AgentRunStatus.TERMINATED:
                return self._to_golden_result(task=task, result=plan_result, total_cost_usd=plan_cost)
            approval = AgentApproval(
                approved=True,
                approval_id=f"golden:{task.task_id}:approval",
                plan_hash=plan_result.plan_hash,
            )
        request = AgentRunRequest(
            run_id=run_id,
            session_id=None,
            task=task.description,
            execution_mode=mode,
            workspace_root=self._workspace_root,
            approval=approval,
            max_cost_usd=task.max_cost_usd,
        )
        result = self._runner.run(request)
        return self._to_golden_result(task=task, result=result, total_cost_usd=plan_cost + result.total_cost_usd)

    def _to_golden_result(
        self,
        *,
        task: GoldenTask,
        result: AgentRunResult,
        total_cost_usd: Decimal,
    ) -> GoldenTaskResult:
        actual_mode = "agent" if result.execution_mode is ExecutionMode.AGENT else "plan_chat"
        credential_scan = scan_local_credentials()
        return GoldenTaskResult(
            task_id=task.task_id,
            actual_mode=actual_mode,
            actual_tools=tuple(call.tool_name for call in result.tool_calls),
            actual_cost_usd=total_cost_usd,
            actual_final_state=result.final_state.lower(),
            mutation_count=result.mutation_count,
            provider_keys_resolvable=credential_scan.provider_keys_resolvable,
        )
