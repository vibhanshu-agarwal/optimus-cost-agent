from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

_DEBUG_SESSION_ID = "c66f94"
_PROVENANCE_LOGGED = False
DEFAULT_DEBUG_LOG_RELATIVE_PATH = Path(".optimus/debug-acp.ndjson")


def resolve_debug_log_path(*, workspace_root: str | Path, log_path: str | Path | None = None) -> Path:
    """Resolve debug log path relative to workspace root unless absolute."""
    root = Path(workspace_root).resolve()
    if log_path is None:
        return (root / DEFAULT_DEBUG_LOG_RELATIVE_PATH).resolve()
    candidate = Path(log_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def configure_debug_trace(*, enabled: bool, log_path: str | Path | None = None) -> None:
    """Enable ACP debug tracing via CLI (sets process env before serve_ndjson starts)."""
    if enabled:
        os.environ["OPTIMUS_ACP_DEBUG_TRACE"] = "1"
    if log_path is not None:
        os.environ["OPTIMUS_ACP_DEBUG_LOG"] = str(Path(log_path).resolve())


def debug_trace_enabled() -> bool:
    return os.environ.get("OPTIMUS_ACP_DEBUG_TRACE", "").strip().lower() in {"1", "true", "yes"}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _log_path() -> Path:
    configured = os.environ.get("OPTIMUS_ACP_DEBUG_LOG", "").strip()
    if configured:
        return Path(configured).resolve()
    return (_project_root() / "debug-c66f94.log").resolve()


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_project_root(),
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _package_version() -> str:
    try:
        return version("optimus-cost-agent")
    except PackageNotFoundError:
        return "unknown"


def log_provenance_once() -> None:
    global _PROVENANCE_LOGGED
    if not debug_trace_enabled() or _PROVENANCE_LOGGED:
        return
    _PROVENANCE_LOGGED = True
    acp_debug_log(
        location="debug_trace.py:log_provenance_once",
        message="debug trace session provenance",
        data={
            "git_sha": _git_sha(),
            "package_version": _package_version(),
            "optimus_acp_file": str(Path(__file__).resolve()),
            "sys_executable": sys.executable,
            "log_path": str(_log_path()),
            "cwd": str(Path.cwd().resolve()),
        },
        hypothesis_id="PROVENANCE",
        run_id="pre-fix",
    )


def acp_debug_log(
    *,
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    """Append one NDJSON debug line. Never writes to stdout (ACP protocol channel)."""
    if not debug_trace_enabled():
        return
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "timestamp": int(time.time() * 1000),
        "location": location,
        "message": message,
        "data": data or {},
        "hypothesisId": hypothesis_id,
        "runId": run_id,
    }
    try:
        log_path = _log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), default=str) + "\n")
    except Exception:
        return
