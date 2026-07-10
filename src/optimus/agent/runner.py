from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from optimus.agent.directives import AgentDirectiveParseError, parse_agent_plan
from optimus.agent.models import AgentRunRequest, AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.agent.prompts import build_agent_planner_input
from optimus.agent.state_store import AgentPlanRecord, AgentStateStore, InMemoryAgentStateStore
from optimus.agent.tools import AgentToolbox
from optimus.agent.workspace_context import gather_workspace_context_for_prompt
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
        state_store: AgentStateStore | None = None,
        clock_ms: Callable[[], int] | None = None,
        shell_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self._gateway_client = gateway_client
        self._model = model
        self._guard = guard
        self._event_sink = event_sink
        self._loop_iteration_runner = loop_iteration_runner
        self._loop_evaluator = loop_evaluator
        self._state_store = state_store or InMemoryAgentStateStore(clock_ms=clock_ms)
        self._clock_ms = clock_ms or _epoch_ms
        self._shell_runner = shell_runner
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
            shell_runner=self._shell_runner,
        )
        tool_calls: list[AgentToolCall] = []
        total_cost_usd = Decimal("0")

        if request.execution_mode is ExecutionMode.AGENT and request.approval.approved:
            return self._run_approved_from_store(request=request, context=context, toolbox=toolbox)

        context = self._transition(context, AgentState.PLANNING)
        workspace_context = gather_workspace_context_for_prompt(request.workspace_root)
        planner_input = build_agent_planner_input(request.task, workspace_context=workspace_context)
        response = self._gateway_client.create_response(
            model=self._model,
            input_text=planner_input,
            metadata={
                "run_id": request.run_id,
                "session_id": request.session_id,
                "purpose": "agent_plan",
                "task": request.task,
            },
        )
        total_cost_usd += response.gateway_usage.cost_usd
        output_text = response.output_text
        if request.execution_mode is ExecutionMode.AGENT:
            try:
                parse_agent_plan(output_text)
            except AgentDirectiveParseError:
                return self._build_result(
                    request=request,
                    status=AgentRunStatus.FAILED,
                    final_state="FAILED",
                    output_text=output_text,
                    tool_calls=(),
                    total_cost_usd=total_cost_usd,
                    stop_reason="UNPARSEABLE_PLAN",
                )
        plan_hash = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
        created_at_ms = self._clock_ms()

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
            if request.execution_mode is ExecutionMode.AGENT:
                self._state_store.save_plan(
                    AgentPlanRecord(
                        run_id=request.run_id,
                        session_id=request.session_id,
                        task=request.task,
                        execution_mode=request.execution_mode,
                        workspace_root=str(request.workspace_root),
                        plan_hash=plan_hash,
                        plan_text=output_text,
                        gateway_request_id=response.gateway_usage.gateway_request_id,
                        model=self._model,
                        provider=response.gateway_usage.provider,
                        cost_usd=response.gateway_usage.cost_usd,
                        created_at_ms=created_at_ms,
                        expires_at_ms=created_at_ms + 3_600_000,
                    )
                )
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
            shell_runner=self._shell_runner,
        )

        write_calls = self._execute_write_directives(output_text, workspace_root=request.workspace_root, toolbox=toolbox)
        tool_calls.extend(write_calls)
        mutation_count = sum(1 for call in write_calls if call.tool_name == "write_file")
        try:
            tool_calls.extend(self._execute_test_directives(output_text, toolbox=toolbox))
        except AgentDirectiveParseError as exc:
            if "unsafe TEST directive" in str(exc):
                return self._unsafe_test_directive_result(request)
            raise
        write_failure = self._write_execution_failure_if_needed(
            request=request,
            plan_text=output_text,
            tool_calls=tool_calls,
            total_cost_usd=total_cost_usd,
            plan_hash=plan_hash,
        )
        if write_failure is not None:
            return write_failure
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

    def _run_approved_from_store(
        self,
        *,
        request: AgentRunRequest,
        context: RuntimeContext,
        toolbox: AgentToolbox,
    ) -> AgentRunResult:
        try:
            record = self._state_store.load_plan(run_id=request.run_id, plan_hash=request.approval.plan_hash or "")
        except KeyError:
            latest = self._state_store.latest_plan_for_run(run_id=request.run_id)
            if latest is not None and _record_matches_request(latest, request):
                return self._build_result(
                    request=request,
                    status=AgentRunStatus.AWAITING_APPROVAL,
                    final_state="AWAITING_APPROVAL",
                    output_text=latest.plan_text,
                    tool_calls=(),
                    total_cost_usd=latest.cost_usd,
                    plan_hash=latest.plan_hash,
                )
            return self._missing_plan_result(request)

        if not _record_matches_request(record, request):
            return self._missing_plan_result(request)

        context = self._transition(context, AgentState.PLANNING)
        context = self._transition(context, AgentState.PLAN_READY)
        tool_calls = self._execute_read_directives(record.plan_text, workspace_root=request.workspace_root, toolbox=toolbox)
        context = self._transition(context, AgentState.AWAITING_APPROVAL)
        awaiting = AwaitingApproval(
            approval_id=request.approval.approval_id or "unknown-approval",
            requested_at_ms=0,
            timeout_ms=3_600_000,
        )
        context = awaiting.grant(context)
        context = self._transition(context, AgentState.EXECUTING)
        approved_toolbox = AgentToolbox.for_workspace(
            workspace_root=request.workspace_root,
            context=context,
            run_id=request.run_id,
            session_id=request.session_id,
            guard=self._guard,
            shell_runner=self._shell_runner,
        )
        write_calls = self._execute_write_directives(record.plan_text, workspace_root=request.workspace_root, toolbox=approved_toolbox)
        tool_calls.extend(write_calls)
        mutation_count = sum(1 for call in write_calls if call.tool_name == "write_file")
        try:
            tool_calls.extend(self._execute_test_directives(record.plan_text, toolbox=approved_toolbox))
        except AgentDirectiveParseError as exc:
            if "unsafe TEST directive" in str(exc):
                return self._unsafe_test_directive_result(request)
            raise
        write_failure = self._write_execution_failure_if_needed(
            request=request,
            plan_text=record.plan_text,
            tool_calls=tool_calls,
            total_cost_usd=record.cost_usd,
            plan_hash=record.plan_hash,
        )
        if write_failure is not None:
            return write_failure
        self._transition(context, AgentState.COMPLETED)
        return self._build_result(
            request=request,
            status=AgentRunStatus.COMPLETED,
            final_state="COMPLETED",
            output_text=record.plan_text,
            tool_calls=tuple(tool_calls),
            total_cost_usd=record.cost_usd,
            mutation_count=mutation_count,
            plan_hash=record.plan_hash,
        )

    def _missing_plan_result(self, request: AgentRunRequest) -> AgentRunResult:
        return self._build_result(
            request=request,
            status=AgentRunStatus.FAILED,
            final_state="FAILED",
            output_text="Plan approval expired or was not found. Re-run planning and approve the new plan.",
            tool_calls=(),
            total_cost_usd=Decimal("0"),
            stop_reason="PLAN_NOT_FOUND_OR_EXPIRED",
        )

    def _unsafe_test_directive_result(self, request: AgentRunRequest) -> AgentRunResult:
        return self._build_result(
            request=request,
            status=AgentRunStatus.FAILED,
            final_state="FAILED",
            output_text="Unsafe TEST directive rejected.",
            tool_calls=(),
            total_cost_usd=Decimal("0"),
            stop_reason="UNSAFE_TEST_DIRECTIVE",
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
                execution_mode=request.execution_mode.value,
                user_approval_id=request.approval.approval_id or "unauthorized_direct_run",
            )
        )

    def _transition(self, context: RuntimeContext, target: AgentState, *, reason: str = "") -> RuntimeContext:
        return self._transition_validator.transition(
            context,
            StateTransition(target=target, reason=reason),
        )

    def _execute_read_directives(
        self,
        plan_text: str,
        *,
        workspace_root: Path,
        toolbox: AgentToolbox,
    ) -> list[AgentToolCall]:
        try:
            directives = parse_agent_plan(plan_text)
        except AgentDirectiveParseError:
            return []
        calls: list[AgentToolCall] = []
        for relative_path in directives.read_paths:
            if not self._is_safe_relative_path(relative_path):
                continue
            target = workspace_root / relative_path
            if not target.is_file():
                continue
            try:
                _, call = toolbox.read_file(target)
            except OSError:
                continue
            calls.append(call)
        return calls

    def _execute_write_directives(
        self,
        plan_text: str,
        *,
        workspace_root: Path,
        toolbox: AgentToolbox,
    ) -> list[AgentToolCall]:
        try:
            directives = parse_agent_plan(plan_text)
        except AgentDirectiveParseError:
            return []
        if directives.write is None:
            return []
        relative_path = directives.write.path
        content = directives.write.content
        if not self._is_safe_relative_path(relative_path):
            return []
        target = workspace_root / relative_path
        calls: list[AgentToolCall] = []
        if target.exists():
            _, read_call = toolbox.read_file(target)
            calls.append(read_call)
        calls.append(toolbox.write_file(target, content))
        return calls

    def _execute_test_directives(self, plan_text: str, *, toolbox: AgentToolbox) -> list[AgentToolCall]:
        directives = parse_agent_plan(plan_text)
        return [toolbox.run_tests(command) for command in directives.tests]

    def _write_execution_failure_if_needed(
        self,
        *,
        request: AgentRunRequest,
        plan_text: str,
        tool_calls: list[AgentToolCall],
        total_cost_usd: Decimal,
        plan_hash: str | None,
    ) -> AgentRunResult | None:
        try:
            directives = parse_agent_plan(plan_text)
        except AgentDirectiveParseError:
            return None
        if directives.write is None:
            return None
        if any(call.tool_name == "write_file" for call in tool_calls):
            return None
        return self._build_result(
            request=request,
            status=AgentRunStatus.FAILED,
            final_state="FAILED",
            output_text=plan_text,
            tool_calls=tuple(tool_calls),
            total_cost_usd=total_cost_usd,
            stop_reason="WRITE_DIRECTIVE_NOT_EXECUTED",
            plan_hash=plan_hash,
        )

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


def _epoch_ms() -> int:
    return int(datetime.now(tz=UTC).timestamp() * 1000)


def _record_matches_request(record: AgentPlanRecord, request: AgentRunRequest) -> bool:
    return (
        record.task == request.task
        and record.execution_mode is request.execution_mode
        and Path(record.workspace_root).resolve() == request.workspace_root
    )
