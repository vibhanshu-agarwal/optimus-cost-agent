"""Real acpx / agent process collection with explicit argv and shell=False."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from optimus.runtime import process_tree

from .common import HostError


def resolve_acpx() -> tuple[str, str]:
    path = shutil.which("acpx")
    if path is None:
        raise HostError("acpx_not_on_path")
    completed = subprocess.run(
        [path, "--version"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise HostError("acpx_version_failed")
    version = (completed.stdout or completed.stderr or "").strip()
    if not version:
        raise HostError("acpx_version_empty")
    return path, version


def host_process_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Pass only host process essentials — never OPTIMUS_* or provider secrets."""
    import os

    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOME",
        "SYSTEMDRIVE",
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "TERM",
    }
    env_source = os.environ if source is None else source
    return {key: value for key, value in env_source.items() if key in allowed}


def build_acpx_command(
    *,
    acpx_path: str,
    workspace_root: Path,
    agent_executable: Path,
    prompt: str,
    launch_session_id: str,
    no_auto_start: bool = False,
    launch_approval_id: str | None = None,
) -> list[str]:
    if not prompt or any(ch in prompt for ch in ("\n", "\r", "\x00")):
        raise HostError("invalid_prompt")
    workspace = workspace_root.resolve()
    agent = agent_executable.resolve()
    if not workspace.is_absolute() or not agent.is_absolute():
        raise HostError("relative_path_rejected")
    agent_args = [
        agent.as_posix(),
        "--workspace-root",
        workspace.as_posix(),
        "--launch-session-id",
        launch_session_id,
        "--debug-trace",
    ]
    if no_auto_start:
        agent_args.append("--no-auto-start")
    if launch_approval_id:
        agent_args.extend(("--launch-approval-id", launch_approval_id))
    agent_invocation = " ".join(agent_args)
    return [
        acpx_path,
        "--format",
        "json",
        "--approve-all",
        "--cwd",
        str(workspace),
        "--agent",
        agent_invocation,
        "exec",
        prompt,
    ]


def _pump_stream(stream: TextIO, path: Path | None, failures: list[OSError]) -> None:
    try:
        with stream:
            if path is None:
                while stream.read(8192):
                    pass
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                for line in stream:
                    handle.write(line)
                    handle.flush()
    except OSError as exc:
        failures.append(exc)


def spawn_acpx(
    *,
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> int:
    """Launch with ``shell=False`` and drain pipes while waiting.

    Completion evidence comes from the NDJSON debug log, not child stdio. Pipes
    are still drained so a chatty child cannot fill the OS pipe buffer and
    deadlock the parent. Optional paths persist drained bytes under the private
    capture root for content-free diagnosis (never logged as transcripts).
    """
    if timeout_seconds <= 0:
        raise HostError("invalid_timeout")
    try:
        process = process_tree.popen(
            command,
            cwd=str(cwd.resolve()),
            env=dict(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except process_tree.ContainmentError as exc:
        code = "acpx_containment_failed" if exc.stopped else "acpx_cleanup_incomplete"
        raise HostError(code) from None

    deadline = time.monotonic() + timeout_seconds
    readers: list[threading.Thread] = []
    capture_failures: list[OSError] = []
    try:
        for stream, path in ((process.stdout, stdout_path), (process.stderr, stderr_path)):
            if stream is not None:
                reader = threading.Thread(target=_pump_stream, args=(stream, path, capture_failures), daemon=True)
                reader.start()
                readers.append(reader)
        returncode = process.wait(timeout=max(0.0, deadline - time.monotonic()))
        if not process_tree.join_pipe_readers(readers, deadline=deadline):
            raise subprocess.TimeoutExpired("acpx", timeout_seconds)
        if capture_failures:
            raise HostError("acpx_capture_failed")
    except BaseException as exc:
        try:
            process_tree.stop_piped_process(process, readers, deadline=time.monotonic() + 5)
        except process_tree.PipeCleanupError as cleanup:
            if isinstance(exc, subprocess.TimeoutExpired):
                raise HostError("acpx_timeout_cleanup_incomplete") from None
            if isinstance(exc, HostError):
                raise HostError("acpx_cleanup_incomplete") from None
            exc.add_note(f"acpx cleanup incomplete: {cleanup}")
        if isinstance(exc, subprocess.TimeoutExpired):
            raise HostError("acpx_timeout") from None
        raise
    return returncode
