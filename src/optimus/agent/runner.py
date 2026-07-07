from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from optimus.agent.models import AgentRunRequest, AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.agent.tools import AgentToolbox
from optimus.gateway.client import GatewayClient
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.loops.completion import DeterministicCompletionEvaluator
from optimus.loops.controller import GoalLoopController, IterationRunner
from optimus.loops.ledger import InMemoryProgressLedger
from optimus.loops.models import CompletionEvaluatorProtocol, IterationOutcome, IterationState, LoopBudgetPolicy, LoopStopReason
from optimus.loops.tools import GuardedLoopToolExecutor
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, AwaitingApproval, RuntimeContext, StateTransition, TransitionValidator
from optimus.skills.registry import SkillRegistry
from optimus.telemetry.events import TelemetryEvent

_READ_DIRECTIVE = re.compile(r"^READ\s+(\S+)", re.MULTILINE)
_WRITE_DIRECTIVE = re.compile(r"^WRITE\s+(\S+)\n([\s\S]*)", re.MULTILINE)


class _AgentLoopIterationRunner:
    def __init__(self, agent_runner: AgentRunner, request: AgentRunRequest) -> None:
        self._agent_runner = agent_runner
        self._request = request
        self.last_result: AgentRunResult | None = None

    def run_iteration(self, state: IterationState, tools: GuardedLoopToolExecutor) -> IterationOutcome:
        result = self._agent_runner._run_once(self._request)
        self.last_result = result
        return IterationOutcome(
            summary=result.output_text,
            cost_credits=result.total_cost_usd,
            deterministic_completion=result.status is AgentRunStatus.COMPLETED,
        )


class AgentRunner:
    def __init__(
        self,
        *,
        gateway_client: GatewayClient,
        model: str,
        guard: PreToolGuard | None = None,
        event_sink: Callable[[TelemetryEvent], None] | None = None,
        loop_iteration_runner: IterationRunner | None = None,
        loop_evaluator: CompletionEvaluatorProtocol | None = None,
    ) -> None:
        self._gateway_client = gateway_client
        self._model = model
        self._guard = guard
        self._event_sink = event_sink
        self._loop_iteration_runner = loop_iteration_runner
        self._loop_evaluator = loop_evaluator
        self._transition_validator = TransitionValidator()

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        matched_skills = self._match_skills(request)
        if request.completion_condition:
            result = self._run_bounded_loop(request, matched_skills=matched_skills)
        else:
            result = self._run_once(request)
        self._emit_agent_run(request, result, matched_skills=matched_skills)
        return result

    def _match_skills(self, request: AgentRunRequest) -> tuple[str, ...]:
        if not request.skill_paths:
            return ()
        registry = SkillRegistry.from_paths(tuple(request.skill_paths), event_sink=self._event_sink)
        matches = registry.match(
            run_id=request.run_id,
            session_id=request.session_id,
            task_text=request.task,
            changed_paths=(),
            execution_mode=request.execution_mode,
        )
        return tuple(match.manifest.name for match in matches)

    def _run_bounded_loop(self, request: AgentRunRequest, *, matched_skills: tuple[str, ...]) -> AgentRunResult:
        del matched_skills
        workspace_root = request.workspace_root
        guard = self._guard or PreToolGuard.for_workspace(workspace_root=workspace_root, allowed_network_hosts=())
        iteration_runner = self._loop_iteration_runner or _AgentLoopIterationRunner(self, request)
        evaluator = self._loop_evaluator or DeterministicCompletionEvaluator(completed=False, reason="goal not complete")
        controller = GoalLoopController(
            policy=LoopBudgetPolicy(
                max_iterations=5,
                max_budget_credits=max(request.max_cost_usd, Decimal("0.01")),
                max_wall_clock_minutes=30,
            ),
            runner=iteration_runner,
            tools=GuardedLoopToolExecutor(guard=guard),
            evaluator=evaluator,
            ledger=InMemoryProgressLedger(),
            event_sink=self._event_sink,
        )
        loop_result = controller.run(
            IterationState(
                run_id=request.run_id,
                session_id=request.session_id,
                goal=request.task,
                completion_condition=request.completion_condition or request.task,
                started_at=datetime.now(tz=UTC),
            )
        )
        if isinstance(iteration_runner, _AgentLoopIterationRunner) and iteration_runner.last_result is not None:
            return iteration_runner.last_result.model_copy(update={"stop_reason": loop_result.stop_reason.value})
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED
            if loop_result.stop_reason is LoopStopReason.COMPLETED
            else AgentRunStatus.TERMINATED,
            final_state=loop_result.stop_reason.value,
            output_text=loop_result.summary,
            tool_calls=(),
            total_cost_usd=Decimal("0"),
            mutation_count=0,
            provider_keys_resolvable=(),
            stop_reason=loop_result.stop_reason.value,
        )

    def _run_once(self, request: AgentRunRequest) -> AgentRunResult:
        context = RuntimeContext(execution_mode=request.execution_mode)
        toolbox = AgentToolbox.for_workspace(
            workspace_root=request.workspace_root,
            context=context,
            run_id=request.run_id,
            session_id=request.session_id,
            guard=self._guard,
        )
        tool_calls: list[AgentToolCall] = []
        total_cost_usd = Decimal("0")

        context = self._transition(context, AgentState.PLANNING)
        response = self._gateway_client.create_response(
            model=self._model,
            input_text=request.task,
            metadata={
                "run_id": request.run_id,
                "session_id": request.session_id,
                "purpose": "agent_plan",
            },
        )
        total_cost_usd += response.gateway_usage.cost_usd
        output_text = response.output_text
        plan_hash = hashlib.sha256(output_text.encode("utf-8")).hexdigest()

        context = self._transition(context, AgentState.PLAN_READY)
        tool_calls.extend(self._execute_read_directives(output_text, workspace_root=request.workspace_root, toolbox=toolbox))

        if total_cost_usd > request.max_cost_usd:
            return self._build_result(
                request=request,
                status=AgentRunStatus.TERMINATED,
                final_state="TERMINATED",
                output_text=output_text,
                tool_calls=tuple(tool_calls),
                total_cost_usd=total_cost_usd,
                stop_reason="BUDGET_EXHAUSTED",
                plan_hash=plan_hash,
            )

        if request.execution_mode in {ExecutionMode.PLAN, ExecutionMode.CHAT}:
            self._transition(context, AgentState.CHAT_ONLY)
            return self._build_result(
                request=request,
                status=AgentRunStatus.COMPLETED,
                final_state="CHAT_ONLY",
                output_text=output_text,
                tool_calls=tuple(tool_calls),
                total_cost_usd=total_cost_usd,
            )

        if not request.approval.approved or request.approval.plan_hash != plan_hash:
            self._transition(context, AgentState.AWAITING_APPROVAL)
            return self._build_result(
                request=request,
                status=AgentRunStatus.AWAITING_APPROVAL,
                final_state="AWAITING_APPROVAL",
                output_text=output_text,
                tool_calls=tuple(tool_calls),
                total_cost_usd=total_cost_usd,
                plan_hash=plan_hash,
            )

        context = self._transition(context, AgentState.AWAITING_APPROVAL)
        awaiting = AwaitingApproval(
            approval_id=request.approval.approval_id or "unknown-approval",
            requested_at_ms=0,
            timeout_ms=3_600_000,
        )
        context = awaiting.grant(context)
        context = self._transition(context, AgentState.EXECUTING)
        toolbox = AgentToolbox.for_workspace(
            workspace_root=request.workspace_root,
            context=context,
            run_id=request.run_id,
            session_id=request.session_id,
            guard=self._guard,
        )

        write_calls = self._execute_write_directives(output_text, workspace_root=request.workspace_root, toolbox=toolbox)
        tool_calls.extend(write_calls)
        mutation_count = sum(1 for call in write_calls if call.tool_name == "write_file")
        self._transition(context, AgentState.COMPLETED)

        return self._build_result(
            request=request,
            status=AgentRunStatus.COMPLETED,
            final_state="COMPLETED",
            output_text=output_text,
            tool_calls=tuple(tool_calls),
            total_cost_usd=total_cost_usd,
            mutation_count=mutation_count,
            plan_hash=plan_hash,
        )

    def _emit_agent_run(
        self,
        request: AgentRunRequest,
        result: AgentRunResult,
        *,
        matched_skills: tuple[str, ...],
    ) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.agent_run(
                run_id=request.run_id,
                session_id=request.session_id,
                request_id=f"{request.run_id}:agent-run",
                occurred_at=datetime.now(tz=UTC),
                status=result.status.value,
                final_state=result.final_state,
                tool_names=tuple(call.tool_name for call in result.tool_calls),
                total_cost_usd=result.total_cost_usd,
                mutation_count=result.mutation_count,
                stop_reason=result.stop_reason,
                matched_skills=matched_skills,
            )
        )

    def _transition(self, context: RuntimeContext, target: AgentState, *, reason: str = "") -> RuntimeContext:
        return self._transition_validator.transition(
            context,
            StateTransition(target=target, reason=reason),
        )

    def _execute_read_directives(
        self,
        output_text: str,
        *,
        workspace_root: Path,
        toolbox: AgentToolbox,
    ) -> list[AgentToolCall]:
        calls: list[AgentToolCall] = []
        for match in _READ_DIRECTIVE.finditer(output_text):
            relative_path = match.group(1)
            if not self._is_safe_relative_path(relative_path):
                continue
            _, call = toolbox.read_file(workspace_root / relative_path)
            calls.append(call)
        return calls

    def _execute_write_directives(
        self,
        output_text: str,
        *,
        workspace_root: Path,
        toolbox: AgentToolbox,
    ) -> list[AgentToolCall]:
        match = _WRITE_DIRECTIVE.match(output_text)
        if match is None:
            return []
        relative_path = match.group(1)
        content = match.group(2)
        if not self._is_safe_relative_path(relative_path):
            return []
        target = workspace_root / relative_path
        calls: list[AgentToolCall] = []
        if target.exists():
            _, read_call = toolbox.read_file(target)
            calls.append(read_call)
        calls.append(toolbox.write_file(target, content))
        return calls

    @staticmethod
    def _is_safe_relative_path(path_text: str) -> bool:
        path = Path(path_text)
        if path.is_absolute():
            return False
        return ".." not in path.parts

    @staticmethod
    def _build_result(
        *,
        request: AgentRunRequest,
        status: AgentRunStatus,
        final_state: str,
        output_text: str,
        tool_calls: tuple[AgentToolCall, ...],
        total_cost_usd: Decimal,
        mutation_count: int = 0,
        plan_hash: str | None = None,
        stop_reason: str | None = None,
    ) -> AgentRunResult:
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=status,
            final_state=final_state,
            output_text=output_text,
            tool_calls=tool_calls,
            total_cost_usd=total_cost_usd,
            mutation_count=mutation_count,
            provider_keys_resolvable=(),
            plan_hash=plan_hash,
            stop_reason=stop_reason,
        )
