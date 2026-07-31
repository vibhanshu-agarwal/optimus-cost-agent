"""Real acpx / agent process collection with explicit argv and shell=False."""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

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


def _pump_stream(stream: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        if stream is None:
            return
        for line in stream:  # type: ignore[attr-defined]
            handle.write(line)
            handle.flush()


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
    process = subprocess.Popen(
        list(command),
        cwd=str(cwd.resolve()),
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    if stdout_path is None and stderr_path is None:
        try:
            process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.communicate()
            except Exception:
                pass
            raise HostError("acpx_timeout") from None
    else:
        out = stdout_path if stdout_path is not None else Path(os_devnull())
        err = stderr_path if stderr_path is not None else Path(os_devnull())
        threads = [
            threading.Thread(target=_pump_stream, args=(process.stdout, out), daemon=True),
            threading.Thread(target=_pump_stream, args=(process.stderr, err), daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            raise HostError("acpx_timeout") from None
        finally:
            for thread in threads:
                thread.join(timeout=5)
    if process.returncode is None:
        raise HostError("acpx_timeout")
    return int(process.returncode)


def os_devnull() -> str:
    import os

    return os.devnull
