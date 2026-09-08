from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

from optimus.agent.models import AgentRunRequest
from optimus.agent.planning_loop import PlanningProgressEvent
from optimus.agent.workspace_context import WorkspaceContextResult
from optimus.telemetry.redaction import redact_for_telemetry
from optimus_security.sanitization import session_correlation_tag

if TYPE_CHECKING:
    from optimus.acp.launch_gate import AuthorizedLaunch
_PROVENANCE_LOGGED = False
DEFAULT_DEBUG_LOG_RELATIVE_PATH = Path(".optimus/debug-acp.ndjson")


@dataclass(frozen=True)
class DebugTraceContext:
    """Process-local ACP debug trace configuration.

    Plan 9.96, Task 5 Step 2: debug trace state is an authorized in-memory
    context threaded explicitly through configure_debug_trace(), not through
    OPTIMUS_ACP_DEBUG_TRACE/OPTIMUS_ACP_DEBUG_LOG/OPTIMUS_ACP_PROVENANCE_ROOT
    environment variable mutation. Those three names are INTERNAL_ONLY in the
    launch_policy registry and must fail closed if inherited from the parent
    environment — a module that itself wrote to os.environ to enable tracing
    would be indistinguishable, from the gate's point of view, from a hostile
    inherited value.
    """

    enabled: bool
    session_id: str
    session_hmac_key: bytes
    log_path: Path | None = None
    provenance_root: Path | None = None


_ACTIVE_CONTEXT: DebugTraceContext | None = None


def resolve_debug_log_path(*, workspace_root: str | Path, log_path: str | Path | None = None) -> Path:
    """Resolve debug log path relative to workspace root unless absolute."""
    root = Path(workspace_root).resolve()
    if log_path is None:
        return (root / DEFAULT_DEBUG_LOG_RELATIVE_PATH).resolve()
    candidate = Path(log_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def configure_debug_trace(
    *,
    enabled: bool,
    log_path: str | Path | None = None,
    provenance_root: str | Path | None = None,
) -> None:
    """Set the process-local debug trace context.

    Replaces the prior os.environ mutation with an explicit in-memory
    DebugTraceContext. Callers (the authorized __main__ entrypoint) invoke
    this exactly once, after authorization, with typed/validated inputs —
    never in response to an inherited environment variable.
    """
    global _ACTIVE_CONTEXT
    _ACTIVE_CONTEXT = DebugTraceContext(
        enabled=enabled,
        session_id=f"debug_{secrets.token_hex(12)}",
        session_hmac_key=secrets.token_bytes(32),
        log_path=Path(log_path).resolve() if log_path is not None else None,
        provenance_root=Path(provenance_root).resolve() if provenance_root is not None else None,
    )


def reset_debug_trace_context() -> None:
    """Clear the process-local debug trace context.

    Test isolation helper: without this, DebugTraceContext set by one test
    would leak into the next since the context is process-local module state
    rather than per-call-site.
    """
    global _ACTIVE_CONTEXT
    _ACTIVE_CONTEXT = None


def debug_trace_enabled() -> bool:
    return _ACTIVE_CONTEXT is not None and _ACTIVE_CONTEXT.enabled


def _log_path() -> Path:
    if _ACTIVE_CONTEXT is not None and _ACTIVE_CONTEXT.log_path is not None:
        return _ACTIVE_CONTEXT.log_path
    return (Path.cwd() / DEFAULT_DEBUG_LOG_RELATIVE_PATH).resolve()


def _git_sha() -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        return "unknown"
    provenance_root = _ACTIVE_CONTEXT.provenance_root if _ACTIVE_CONTEXT is not None else None
    try:
        completed = subprocess.run(
            [git_executable, "rev-parse", "HEAD"],
            cwd=provenance_root or Path.cwd(),
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
    # The once-only attempt is consumed above, before the payload exists: a failing
    # provenance field is contained by the sink and never retried.
    acp_debug_log(
        location="debug_trace.py:log_provenance_once",
        message="debug trace session provenance",
        data=lambda: {
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



def _json_default_handler(value: Any) -> str:
    """Serialize only safe numeric values or non-invoking type metadata."""
    if isinstance(value, Decimal):
        return str(value)
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def log_authorized_launch_comparison(authorized_launch: "AuthorizedLaunch") -> None:
    """Emit tags only for the completed, predeclared launch comparison."""
    context = _ACTIVE_CONTEXT
    if context is None or not context.enabled or authorized_launch.diagnostic_grant is None:
        return

    candidate = authorized_launch.candidate

    def _tags() -> dict[str, Any]:
        # HMAC tag generation is diagnostic-only work: it runs inside the sink's failure
        # boundary, after the enabled check, and only under a predeclared grant.
        return {
            "correlation_tags": [
                {
                    "field_name": field_name,
                    "tag": session_correlation_tag(
                        candidate.inherited.values[field_name],
                        field_name=field_name,
                        session_key=context.session_hmac_key,
                    ),
                }
                for field_name in candidate.secret_inventory
                if candidate.inherited.values.get(field_name)
            ]
        }

    acp_debug_log(
        location="launch_authorization_comparison",
        message="authorized launch secret comparison",
        data=_tags,
    )


def acp_debug_log(
    *,
    location: str,
    message: str,
    data: dict[str, Any] | Callable[[], dict[str, Any] | None] | None = None,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    """Append one NDJSON debug line. Never writes to stdout (ACP protocol channel).

    ``data`` may be a dict, ``None``, or a zero-argument synchronous supplier returning
    one. The supplier is evaluated once, only after the enabled check, and inside this
    function's failure boundary: a diagnostic that raises can never break the request it
    was describing, and with tracing disabled no payload work happens at all. Only the
    top-level supplier is invoked; callables nested inside a payload are data and are
    serialized as type metadata, never called. Supplier evaluation, payload assembly,
    redaction, serialization, path resolution and the write share one boundary
    deliberately: this is one best-effort attempt that returns without error when any of
    them fails. Nothing is retried, nothing is written before redaction, and an I/O
    failure does not guarantee that no partial line was written. Only ordinary
    ``Exception`` is contained -- cancellation, ``KeyboardInterrupt``, ``SystemExit`` and
    other control flow propagate.

    ``message`` and ``data`` are passed through ``redact_for_telemetry`` unconditionally
    before being written to disk. This is a deliberate last line of defense: call sites
    are expected to log content-free fields already, but this sink cannot assume every
    current and future caller (including generic exception handlers that log
    ``str(exc)``) gets that right on its own.
    """
    if not debug_trace_enabled():
        return
    try:
        # Only the explicit `data` supplier is invoked, once, after the enabled check.
        # Callables nested inside a payload are never called.
        resolved = data() if callable(data) else data
        payload = {
            "sessionId": _ACTIVE_CONTEXT.session_id if _ACTIVE_CONTEXT is not None else "",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": redact_for_telemetry(message),
            "data": redact_for_telemetry(resolved if resolved is not None else {}),
            "hypothesisId": hypothesis_id,
            "runId": run_id,
        }
        log_path = _log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), default=_json_default_handler) + "\n")
    except Exception:
        return


def log_workspace_context_result(request: AgentRunRequest, result: WorkspaceContextResult) -> None:
    """Record content-free workspace context diagnostics for the active run.

    Nothing is read with tracing disabled. The envelope ``run_id`` is the one field read
    outside the sink's supplier; it shares the same best-effort rule (an ordinary failure
    means no log line, never an error for the caller).
    """
    if not debug_trace_enabled():
        return
    try:
        run_id = request.run_id
    except Exception:
        return
    acp_debug_log(
        location="debug_trace.py:log_workspace_context_result",
        message="workspace context assembled",
        data=lambda: {
            "run_id": request.run_id,
            "session_id": request.session_id,
            "max_total_bytes": result.max_total_bytes,
            "used_bytes": result.used_bytes,
            "prioritized_paths": list(result.prioritized_paths),
            "omitted_count": len(result.omitted_paths),
            "references": [
                {
                    "reference": item.reference,
                    "status": item.status.value,
                    "candidate_count": len(item.candidates),
                    "candidates": list(item.candidates),
                }
                for item in result.diagnostics
            ],
            "blocking_stop_reason": result.blocking_stop_reason,
        },
        hypothesis_id="P9.8-CONTEXT",
        run_id=run_id,
    )


def log_planning_replan_event(event: PlanningProgressEvent, *, stop_reason: str | None = None) -> None:
    """Record content-free multi-turn planning progress for ACP/debug evidence.

    ``stop_reason`` is an explicit override for callers that don't build it into
    the event; PlanningLoopRunner's own final-settlement event already carries
    ``event.stop_reason`` (None for intermediate READ_MORE turns, set once on
    the settling call), which is used when no override is given.

    Nothing is read with tracing disabled; the envelope ``run_id`` read follows the same
    best-effort rule as the payload.
    """
    if not debug_trace_enabled():
        return
    try:
        run_id = event.run_id
    except Exception:
        return
    acp_debug_log(
        location="debug_trace.py:log_planning_replan_event",
        message="planning turn settled",
        data=lambda: {
            "run_id": event.run_id,
            "session_id": event.session_id,
            "settled_turn": event.settled_turn,
            "max_planning_turns": event.max_planning_turns,
            "reported_aggregate_cost_usd": str(event.total_cost_usd),
            "cost_complete": event.cost_complete,
            "unknown_cost_attempt_count": event.unknown_cost_attempt_count,
            "remaining_budget_usd": str(event.remaining_budget_usd),
            "read_identities": list(event.read_identities),
            "read_byte_counts": list(event.read_byte_counts),
            "source_sha256s": list(event.source_sha256s),
            "gateway_request_ids": list(event.gateway_request_ids),
            "wire_retry_count": event.wire_retry_count,
            "loop_stop": stop_reason if stop_reason is not None else event.stop_reason,
        },
        hypothesis_id="P9.85-REPLAN",
        run_id=run_id,
    )
