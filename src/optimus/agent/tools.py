from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from optimus.agent.directives import validate_mcp_name
from optimus.agent.models import AgentMcpToolOutput, AgentToolCall
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.runtime.modes import GenerationScope
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import RuntimeContext
from optimus.tools.mutation_tools import shell_exec
from optimus.tools.mutation_tools import write_file as guarded_write_file


class AgentToolbox:
    def __init__(
        self,
        *,
        workspace_root: Path,
        context: RuntimeContext,
        run_id: str,
        session_id: str | None,
        guard: PreToolGuard,
        shell_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
        client_mcp_service: Any | None = None,
        mcp_permission_broker: Any | None = None,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._context = context
        self._run_id = run_id
        self._session_id = session_id
        self._guard = guard
        self._shell_runner = shell_runner
        self._client_mcp_service = client_mcp_service
        self._mcp_permission_broker = mcp_permission_broker

    @classmethod
    def for_workspace(
        cls,
        *,
        workspace_root: str | Path,
        context: RuntimeContext,
        run_id: str,
        session_id: str | None = None,
        guard: PreToolGuard | None = None,
        shell_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
        client_mcp_service: Any | None = None,
        mcp_permission_broker: Any | None = None,
    ) -> "AgentToolbox":
        root = Path(workspace_root).resolve()
        return cls(
            workspace_root=root,
            context=context,
            run_id=run_id,
            session_id=session_id,
            guard=guard or PreToolGuard.for_workspace(workspace_root=root, allowed_network_hosts=()),
            shell_runner=shell_runner,
            client_mcp_service=client_mcp_service,
            mcp_permission_broker=mcp_permission_broker,
        )

    def read_file(self, path: str | Path) -> tuple[str, AgentToolCall]:
        target = Path(path).resolve()
        result = self._guard.check(
            PreToolRequest(
                run_id=self._run_id,
                session_id=self._session_id,
                execution_mode=self._context.execution_mode,
                tool_surface=ToolSurface.FILE_READ,
                action="read_file",
                target_path=str(target),
                generation_scope=GenerationScope.INLINE_SNIPPET,
                approval_granted=self._context.approval_granted,
                approver=self._context.user_approval_id,
            )
        )
        if result.verdict is not PreToolVerdict.ALLOW:
            raise PermissionError(result.reason)
        return target.read_text(encoding="utf-8"), AgentToolCall(
            tool_name="file_reader",
            summary=f"read {target.relative_to(self._workspace_root).as_posix()}",
            authorization_outcome=result.verdict.value,
        )

    def write_file(self, path: str | Path, content: str) -> AgentToolCall:
        target = Path(path).resolve()
        try:
            guarded_write_file(target, content, context=self._context, guard=self._guard)
        except MutationForbidden as exc:
            raise PermissionError(str(exc)) from exc
        return AgentToolCall(
            tool_name="write_file",
            summary=f"wrote {target.relative_to(self._workspace_root).as_posix()}",
            authorization_outcome="ALLOW",
        )

    def run_tests(self, command: tuple[str, ...]) -> AgentToolCall:
        result = shell_exec(
            command,
            context=self._context,
            runner=self._shell_runner,
            guard=self._guard,
        )
        command_text = " ".join(command)
        return AgentToolCall(
            tool_name="test_runner",
            summary=f"ran {command_text} exit={result.returncode}",
            authorization_outcome="ALLOW",
        )

    def mcp_list_tools(self, server: str) -> tuple[AgentMcpToolOutput, AgentToolCall]:
        try:
            safe_server = validate_mcp_name(server, label="server")
        except ValueError:
            return self._unavailable_mcp(
                server=server,
                tool_name="mcp_list_tools",
                audit_name="mcp_list_tools",
                summary="unsafe MCP server name",
                outcome="BLOCK",
            )
        service = self._client_mcp_service
        if service is None:
            return self._unavailable_mcp(
                server=safe_server,
                tool_name="mcp_list_tools",
                audit_name="mcp_list_tools",
                summary="client MCP service unavailable",
                outcome="BLOCK",
            )
        return service.list_tools(safe_server)

    def mcp_call(
        self,
        server: str,
        tool: str,
        arguments: Mapping[str, Any] | Any,
    ) -> tuple[AgentMcpToolOutput, AgentToolCall]:
        try:
            safe_server = validate_mcp_name(server, label="server")
            safe_tool = validate_mcp_name(tool, label="tool")
        except ValueError:
            return self._unavailable_mcp(
                server=server,
                tool_name=tool,
                audit_name="mcp_call",
                summary="unsafe MCP server or tool name",
                outcome="BLOCK",
            )
        if not isinstance(arguments, Mapping) or isinstance(arguments, (str, bytes)):
            return self._unavailable_mcp(
                server=safe_server,
                tool_name=safe_tool,
                audit_name="mcp_call",
                summary="MCP arguments must be a JSON object",
                outcome="BLOCK",
            )
        args = dict(arguments)
        service = self._client_mcp_service
        if service is None:
            return self._unavailable_mcp(
                server=safe_server,
                tool_name=safe_tool,
                audit_name="mcp_call",
                summary="client MCP service unavailable",
                outcome="BLOCK",
            )

        one_call_approval: str | None = None
        requires_write = getattr(service, "requires_write_approval", None)
        if callable(requires_write) and requires_write(safe_server, safe_tool):
            broker = self._mcp_permission_broker
            if broker is None:
                return self._unavailable_mcp(
                    server=safe_server,
                    tool_name=safe_tool,
                    audit_name="mcp_call",
                    summary="write-classified MCP call requires permission broker",
                    outcome="HOLD",
                )
            request = PreToolRequest(
                run_id=self._run_id,
                session_id=self._session_id,
                execution_mode=self._context.execution_mode,
                tool_surface=ToolSurface.MCP,
                action=f"{safe_server}.{safe_tool}",
                generation_scope=GenerationScope.INLINE_SNIPPET,
                approval_granted=False,
                mcp_authority="client_session",
                mcp_server_id=safe_server,
                mcp_tool_name=safe_tool,
                mcp_arguments=args,
            )
            approval = broker.request_write(request)
            if approval is None:
                return self._unavailable_mcp(
                    server=safe_server,
                    tool_name=safe_tool,
                    audit_name="mcp_call",
                    summary="write approval denied or timed out",
                    outcome="HOLD",
                )
            one_call_approval = approval.token

        return service.call_tool(
            safe_server,
            safe_tool,
            args,
            one_call_approval=one_call_approval,
        )

    @staticmethod
    def _unavailable_mcp(
        *,
        server: str,
        tool_name: str,
        audit_name: str,
        summary: str,
        outcome: str,
    ) -> tuple[AgentMcpToolOutput, AgentToolCall]:
        return (
            AgentMcpToolOutput(
                server_name=server,
                tool_name=tool_name,
                text="unavailable:rejected",
            ),
            AgentToolCall(
                tool_name=audit_name,
                summary=summary,
                authorization_outcome=outcome,
            ),
        )
