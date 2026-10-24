from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult
from optimus.guardrails.runtime_tree import resolve_target
from optimus.runtime.modes import ExecutionMode, GenerationScope
from optimus.tools.line_endings import line_ending_style

if TYPE_CHECKING:
    from optimus.agent.planning_loop import PlanningReadEvidence, PlanningReadRequest


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
        requested_relative_path: str | None = None,
        target_unresolved: bool = False,
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
                requested_relative_path=requested_relative_path,
                target_unresolved=target_unresolved,
            )
        )
        if not result.allowed:
            raise LoopToolBlocked(result)
        return result

    def read_file_range(
        self,
        *,
        workspace_root: Path,
        run_id: str,
        session_id: str | None,
        execution_mode: ExecutionMode,
        request: PlanningReadRequest,
        approval_granted: bool = False,
    ) -> PlanningReadEvidence:
        # Imported here: the planning loop imports this package, so a module-level import is a cycle.
        from optimus.agent.planning_loop import PlanningReadError, PlanningReadEvidence

        if request.end_byte <= request.start_byte:
            raise PlanningReadError("PLANNING_READ_INVALID_RANGE", "READ range end must be greater than start")

        root = workspace_root.resolve()
        relative = Path(request.path)
        if relative.is_absolute():
            raise PlanningReadError("PLANNING_READ_INVALID_PATH", "READ path must be workspace-relative")

        # The guard judges the requested path beside its resolved target; an unresolvable target is denied through the
        # guard (Plan 12.2 READ), so only an allowed, resolved target is ever read below.
        resolved = resolve_target(root / relative)
        target = root / relative if resolved is None else resolved
        outside_workspace = False
        try:
            target.relative_to(root)
        except ValueError:
            outside_workspace = True

        self.preflight(
            run_id=run_id,
            session_id=session_id,
            execution_mode=execution_mode,
            tool_surface=ToolSurface.FILE_READ,
            action="read_file_range",
            target_path=str(target),
            approval_granted=approval_granted,
            requested_relative_path=request.path,
            target_unresolved=resolved is None,
        )
        if outside_workspace:
            raise PlanningReadError("PLANNING_READ_INVALID_PATH", "READ path must stay inside workspace")

        if not target.is_file():
            raise PlanningReadError("PLANNING_READ_FILE_NOT_FOUND", f"file not found: {request.path}")

        file_bytes = target.read_bytes()
        source_sha256 = hashlib.sha256(file_bytes).hexdigest()
        range_bytes = file_bytes[request.start_byte : request.end_byte]
        try:
            range_text = range_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PlanningReadError(
                "PLANNING_READ_NOT_UTF8_ALIGNED",
                "READ range bytes are not valid UTF-8",
            ) from exc

        return PlanningReadEvidence(
            path=relative.as_posix(),
            start_byte=request.start_byte,
            end_byte=request.end_byte,
            source_sha256=source_sha256,
            range_text=range_text,
            line_endings=line_ending_style(file_bytes),
        )
