from __future__ import annotations

from pathlib import Path

from optimus.agent.models import AgentToolCall
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.runtime.modes import GenerationScope
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import RuntimeContext
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
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._context = context
        self._run_id = run_id
        self._session_id = session_id
        self._guard = guard

    @classmethod
    def for_workspace(
        cls,
        *,
        workspace_root: str | Path,
        context: RuntimeContext,
        run_id: str,
        session_id: str | None = None,
        guard: PreToolGuard | None = None,
    ) -> "AgentToolbox":
        root = Path(workspace_root).resolve()
        return cls(
            workspace_root=root,
            context=context,
            run_id=run_id,
            session_id=session_id,
            guard=guard or PreToolGuard.for_workspace(workspace_root=root, allowed_network_hosts=()),
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
