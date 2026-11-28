from __future__ import annotations

import contextlib
import errno
import hashlib
import os
import stat
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol, TypeVar

from optimus.guardrails.file_policy import FilePolicy, staging_name
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult, PreToolVerdict
from optimus.guardrails.runtime_tree import resolve_target
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
    if newline not in ("", "\n"):  # as `write_text` translates: None is the platform's line break
        content = content.replace("\n", os.linesep if newline is None else newline)
    _publish(Path(path), content.encode("utf-8"))


def write_file_keeping_line_endings(
    path: str | Path,
    body: str,
    *,
    context: RuntimeContext,
    guard: PreToolGuardLike | None = None,
    requested_relative_path: str | None = None,
    target_unresolved: bool = False,
    workspace_root: Path | None = None,
) -> None:
    """An Agent WRITE (#410): only after the gate and the guard allow it is the target read, as bytes; the body then
    takes the file's line endings, final newline and BOM. A mixed-ending file is refused, unchanged.

    With ``workspace_root`` (#689), the target's missing folders are created first, inside that root. If a folder or the
    write fails, the folders this call created are removed again (only while empty and still resolving to itself) and the
    failure is re-raised. The file itself is published atomically (#691): a failed write leaves its original bytes."""
    _authorize_file_mutation(path, context=context, guard=guard, requested_relative_path=requested_relative_path, target_unresolved=target_unresolved)
    target = Path(path)
    existing = target.read_bytes() if target.is_file() else None
    if existing is not None and line_ending_style(existing) == "mixed":
        raise WriteRefused(WRITE_LINE_ENDINGS_MIXED, requested_relative_path or path)
    created: list[Path] = []
    try:
        if workspace_root is not None:
            _create_missing_folders(target.parent, workspace_root, created)
        _publish(target, fit_body_to_file(body, existing).encode("utf-8"))
    except (OSError, MutationForbidden) as failed:
        for folder in reversed(created):
            if resolve_target(folder) == folder:  # a link swapped in is not this write's to remove
                with contextlib.suppress(OSError):  # a folder no longer empty is not this write's to remove
                    folder.rmdir()
        if isinstance(failed, WriteFailed):  # nothing remains only if every folder this write made is gone too
            failed.no_effect = failed.no_effect and not any(os.path.lexists(folder) for folder in created)
        raise


class WriteFailed(OSError):
    """#691: a staged write did not reach its target, which keeps its bytes. ``step`` names where it failed (resolve, refused,
    stage, fsync, chmod, replace, or a cleanup after one); ``no_effect`` is true only when nothing of the write is left."""

    def __init__(self, step: str, cause: OSError, *, no_effect: bool) -> None:
        super().__init__(cause.errno, f"the write failed at {step}")
        self.step = step
        self.no_effect = no_effect


# Windows' own write refuses a hidden or system file (CREATE_ALWAYS); a replace would not, so it is refused here as before.
_HIDDEN_OR_SYSTEM = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 0x4)
_SHARING_ERRORS = (5, 32)  # Windows access denied and sharing violation: another process holds the target briefly
_REPLACE_RETRY_WAITS = (0.05, 0.05, 0.05)


def _publish(path: Path, data: bytes) -> None:
    """#691: write ``data`` to a staging file beside the resolved target, flush it to disk, give it the target's mode and
    replace the target with it, so a failure at any step leaves the target's original bytes. The target is resolved, so a
    link stays a link and the file the guard judged is the one changed. A target this process could not open for writing
    today (read-only, or hidden or system on Windows) is refused before anything is staged. Every failure raises
    ``WriteFailed``; the staging file is removed first, and if that fails too, ``no_effect`` is false."""
    real = resolve_target(path)
    if real is None:
        raise WriteFailed("resolve", OSError(errno.ENOENT, "the target cannot be resolved"), no_effect=True)
    try:
        facts: os.stat_result | None = os.stat(real)
    except FileNotFoundError:
        facts = None
    except OSError as error:
        raise WriteFailed("resolve", error, no_effect=True) from error
    if facts is not None and (not os.access(real, os.W_OK) or getattr(facts, "st_file_attributes", 0) & _HIDDEN_OR_SYSTEM):
        raise WriteFailed("refused", PermissionError(errno.EACCES, "the target is not writable"), no_effect=True)
    mode = 0o666 if facts is None else stat.S_IMODE(facts.st_mode)  # created no wider than the target; the umask applies
    staging = real.with_name(staging_name())
    step, made = "stage", False
    try:
        descriptor = os.open(staging, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), mode)
        made = True
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            step = "fsync"
            os.fsync(handle.fileno())
        if facts is not None:
            step = "chmod"
            os.chmod(staging, mode)  # the umask may have narrowed it
        step = "replace"
        _replace(staging, real)
    except OSError as error:
        if made:
            try:
                staging.unlink(missing_ok=True)
            except OSError:
                raise WriteFailed(f"{step}, then cleanup", error, no_effect=False) from error
        raise WriteFailed(step, error, no_effect=True) from error


def _replace(staging: Path, target: Path) -> None:
    for wait in (*_REPLACE_RETRY_WAITS, None):
        try:
            os.replace(staging, target)
            return
        except PermissionError as error:
            if wait is None or getattr(error, "winerror", None) not in _SHARING_ERRORS:
                raise
            time.sleep(wait)


def _create_missing_folders(parent: Path, workspace_root: Path, created: list[Path]) -> None:
    """#689: create a WRITE's missing folders, outermost first, after the guard accepted the resolved target. Every folder
    is judged before any is made: inside the root, and nothing the file policy refuses by its spelling (a skipped,
    runtime or secret folder, a Windows device name); a refusal there has had no effect. Each one made must resolve to
    itself, so no link raced in; that failure comes after an effect, so it is an OSError, not a guard refusal."""
    root = workspace_root.resolve()
    missing: list[Path] = []
    folder = parent
    while not folder.exists() and folder != folder.parent:
        missing.append(folder)
        folder = folder.parent
    policy = FilePolicy(root)
    for folder in missing:
        if not folder.is_relative_to(root) or policy.path_denial(folder.relative_to(root).as_posix()) is not None:
            raise MutationForbidden("a folder this write needs is not allowed")
    for folder in reversed(missing):
        folder.mkdir()
        created.append(folder)
        if resolve_target(folder) != folder:
            raise OSError("a folder this write created does not resolve to itself")


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
