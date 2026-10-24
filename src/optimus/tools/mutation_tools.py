from __future__ import annotations

import hashlib
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol, TypeVar

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult, PreToolVerdict
from optimus.runtime.modes import GenerationScope
from optimus.runtime.mutation import MutationForbidden, MutationKind, assert_mutation_allowed
from optimus.runtime.process_tree import run_bounded
from optimus.runtime.state import RuntimeContext
from optimus.tools.line_endings import WRITE_LINE_ENDINGS_MIXED, fit_body_to_file, line_ending_style

ShellResult = TypeVar("ShellResult")
# Plan 12.3, Design 8: one TEST directive's default deadline; the approved replay sets its own.
DEFAULT_TEST_DEADLINE_SECONDS = 15 * 60
PatchResult = TypeVar("PatchResult")


class PreToolGuardLike(Protocol):
    """
    Defines an interface for a pre-tool guard that processes and evaluates
    requests based on a custom protocol.

    This class serves as a blueprint for implementing functionality to check
    and return results for pre-tool operations. Classes implementing this protocol
    must define the method outlined, adhering to its specified behavior. Commonly
    used in scenarios requiring validation, condition checks, or permission grants
    before performing tool-specific tasks.

    :ivar request: Represents the input request to be processed by the `check`
        method. Expected to be of type ``PreToolRequest``.
    :type request: PreToolRequest
    :ivar result: Represents the output result produced by the `check` method.
        It encapsulates the evaluation or decision made for the input request.
        Expected to be of type ``PreToolResult``.
    :type result: PreToolResult
    """
    def check(self, request: PreToolRequest) -> PreToolResult:
        ...


def _assert_pre_tool_allowed(result: PreToolResult) -> None:
    if result.verdict is PreToolVerdict.BLOCK:
        raise MutationForbidden(result.reason)
    if result.verdict is PreToolVerdict.HOLD:
        raise MutationForbidden(f"human approval required: {result.reason}")


class WriteRefused(Exception):
    """A write refused before any effect (#410): `code` is closed, and `path` is the file it names."""

    def __init__(self, code: str, path: str | Path) -> None:
        super().__init__(f"{code}: {path}")
        self.code = code
        self.path = path


class WriteSourceChanged(MutationForbidden):
    """The target no longer has the content a write was computed from; nothing was written (#407)."""


def write_file(
    path: str | Path,
    content: str,
    *,
    context: RuntimeContext,
    guard: PreToolGuardLike | None = None,
    requested_relative_path: str | None = None,
    target_unresolved: bool = False,
    newline: str | None = "",
    expected_sha256: str | None = None,
) -> None:
    """Write exactly `content` after the mutation gate and the guard allow it. The two optional fields carry a model's
    requested path and an unresolvable target to the guard (Plan 12.2 W); without them the check is exactly as before.

    ``newline`` defaults to ``""``: no platform newline translation, for every caller (#410). ``expected_sha256`` is
    re-checked against the target's bytes after the guard allows the write and immediately before it: a mismatch
    raises ``WriteSourceChanged`` (#407). Neither excludes a concurrent external writer."""
    _authorize_file_mutation(path, context=context, guard=guard, requested_relative_path=requested_relative_path, target_unresolved=target_unresolved)
    if expected_sha256 is not None:
        try:
            current = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except FileNotFoundError:
            current = None
        if current != expected_sha256:
            raise WriteSourceChanged(f"source changed before write: {path}")
    Path(path).write_text(content, encoding="utf-8", newline=newline)


def write_file_keeping_line_endings(
    path: str | Path,
    body: str,
    *,
    context: RuntimeContext,
    guard: PreToolGuardLike | None = None,
    requested_relative_path: str | None = None,
    target_unresolved: bool = False,
) -> None:
    """An Agent WRITE (#410): only after the gate and the guard allow it is the target read, as bytes; the body then
    takes the file's line endings, final newline and BOM. A mixed-ending file is refused, unchanged."""
    _authorize_file_mutation(path, context=context, guard=guard, requested_relative_path=requested_relative_path, target_unresolved=target_unresolved)
    target = Path(path)
    existing = target.read_bytes() if target.is_file() else None
    if existing is not None and line_ending_style(existing) == "mixed":
        raise WriteRefused(WRITE_LINE_ENDINGS_MIXED, requested_relative_path or path)
    target.write_text(fit_body_to_file(body, existing), encoding="utf-8", newline="")


def _authorize_file_mutation(
    path: str | Path,
    *,
    context: RuntimeContext,
    guard: PreToolGuardLike | None,
    requested_relative_path: str | None,
    target_unresolved: bool,
) -> None:
    assert_mutation_allowed(context, MutationKind.WRITE_FILE)
    active_guard = guard or PreToolGuard.for_workspace(workspace_root=Path.cwd(), allowed_network_hosts=())
    _assert_pre_tool_allowed(
        active_guard.check(
            PreToolRequest(
                run_id=context.user_approval_id or "unknown-run",
                session_id=None,
                execution_mode=context.execution_mode,
                tool_surface=ToolSurface.FILE_WRITE,
                action="write_file",
                target_path=str(path),
                generation_scope=GenerationScope.FILE_MUTATION,
                approval_granted=context.approval_granted,
                approver=context.user_approval_id,
                requested_relative_path=requested_relative_path,
                target_unresolved=target_unresolved,
            )
        )
    )


def shell_exec(
    command: Sequence[str],
    *,
    context: RuntimeContext,
    runner: Callable[[list[str]], ShellResult] | None = None,
    guard: PreToolGuardLike | None = None,
    deadline: float | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ShellResult | subprocess.CompletedProcess[str]:
    """Run `command` after the mutation gate and the guard allow it: contained, until it exits, `deadline`
    (a `time.monotonic()` value; default 15 minutes from now) or `cancelled()`. A stop raises `CommandStopped`."""
    assert_mutation_allowed(context, MutationKind.SHELL_EXEC)
    command_tuple = tuple(command)
    active_guard = guard or PreToolGuard.for_workspace(workspace_root=Path.cwd(), allowed_network_hosts=())
    _assert_pre_tool_allowed(
        active_guard.check(
            PreToolRequest(
                run_id=context.user_approval_id or "unknown-run",
                session_id=None,
                execution_mode=context.execution_mode,
                tool_surface=ToolSurface.SHELL,
                action=" ".join(command_tuple),
                command=command_tuple,
                generation_scope=GenerationScope.INLINE_SNIPPET,
                approval_granted=context.approval_granted,
                approver=context.user_approval_id,
            )
        )
    )
    if runner is not None:
        return runner(list(command))
    return run_bounded(
        list(command),
        deadline=time.monotonic() + DEFAULT_TEST_DEADLINE_SECONDS if deadline is None else deadline,
        cancelled=cancelled or (lambda: False),
    )


def shadow_apply(
    patch_text: str,
    *,
    context: RuntimeContext,
    applier: Callable[[str], PatchResult],
    guard: PreToolGuardLike | None = None,
) -> PatchResult:
    assert_mutation_allowed(context, MutationKind.SHADOW_APPLY)
    active_guard = guard or PreToolGuard.for_workspace(workspace_root=Path.cwd(), allowed_network_hosts=())
    _assert_pre_tool_allowed(
        active_guard.check(
            PreToolRequest(
                run_id=context.user_approval_id or "unknown-run",
                session_id=None,
                execution_mode=context.execution_mode,
                tool_surface=ToolSurface.SHADOW_APPLY,
                action="shadow_apply",
                generation_scope=GenerationScope.PATCH_PROPOSAL,
                approval_granted=context.approval_granted,
                approver=context.user_approval_id,
            )
        )
    )
    return applier(patch_text)
