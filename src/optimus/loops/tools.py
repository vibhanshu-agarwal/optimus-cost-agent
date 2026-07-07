from __future__ import annotations

from collections.abc import Mapping

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult
from optimus.runtime.modes import ExecutionMode, GenerationScope


class LoopToolBlocked(RuntimeError):
    def __init__(self, result: PreToolResult) -> None:
        self.result = result
        super().__init__(result.reason)


class GuardedLoopToolExecutor:
    def __init__(self, *, guard: PreToolGuard) -> None:
        self._guard = guard

    def preflight(
        self,
        *,
        run_id: str,
        session_id: str | None,
        execution_mode: ExecutionMode,
        tool_surface: ToolSurface,
        action: str,
        command: tuple[str, ...] = (),
        target_path: str | None = None,
        generation_scope: GenerationScope = GenerationScope.INLINE_SNIPPET,
        approval_granted: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> PreToolResult:
        result = self._guard.check(
            PreToolRequest(
                run_id=run_id,
                session_id=session_id,
                execution_mode=execution_mode,
                tool_surface=tool_surface,
                action=action,
                command=command,
                target_path=target_path,
                generation_scope=generation_scope,
                approval_granted=approval_granted,
                environment=environment or {},
            )
        )
        if not result.allowed:
            raise LoopToolBlocked(result)
        return result
