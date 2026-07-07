from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path

from optimus.agent.models import AgentRunRequest, AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.agent.tools import AgentToolbox
from optimus.gateway.client import GatewayClient
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, AwaitingApproval, RuntimeContext, StateTransition, TransitionValidator

_READ_DIRECTIVE = re.compile(r"^READ\s+(\S+)", re.MULTILINE)
_WRITE_DIRECTIVE = re.compile(r"^WRITE\s+(\S+)\n([\s\S]*)", re.MULTILINE)


class AgentRunner:
    def __init__(
        self,
        *,
        gateway_client: GatewayClient,
        model: str,
        guard: PreToolGuard | None = None,
    ) -> None:
        self._gateway_client = gateway_client
        self._model = model
        self._guard = guard
        self._transition_validator = TransitionValidator()

    def run(self, request: AgentRunRequest) -> AgentRunResult:
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
            context = self._transition(context, AgentState.CHAT_ONLY)
            return self._build_result(
                request=request,
                status=AgentRunStatus.COMPLETED,
                final_state="CHAT_ONLY",
                output_text=output_text,
                tool_calls=tuple(tool_calls),
                total_cost_usd=total_cost_usd,
            )

        if not request.approval.approved or request.approval.plan_hash != plan_hash:
            context = self._transition(context, AgentState.AWAITING_APPROVAL)
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

        mutation_count = 0
        write_calls = self._execute_write_directives(output_text, workspace_root=request.workspace_root, toolbox=toolbox)
        tool_calls.extend(write_calls)
        mutation_count = sum(1 for call in write_calls if call.tool_name == "write_file")
        context = self._transition(context, AgentState.COMPLETED)

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
