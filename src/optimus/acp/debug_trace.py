from __future__ import annotations

import functools
import json
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

from optimus.agent.models import AgentRunRequest
from optimus.agent.planning_loop import PlanningProgressEvent
from optimus.agent.workspace_context import WorkspaceContextResult
from optimus.gateway.attempts import gateway_failure_facts, host_failure_facts
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.redaction import redact_for_telemetry
from optimus_security.failure_facts import (
    UNRECOGNIZED,
    bounded,
    bounded_failure,
    bounded_guardrail_list,
    final_sanitize,
    gateway_request_id,
    host_route_id,
    host_run_of,
    host_session_id,
    provider_request_id,
    rpc_request_id,
)
from optimus_security.sanitization import session_correlation_tag

if TYPE_CHECKING:
    from optimus.acp.launch_gate import AuthorizedLaunch
    from optimus.gateway.attempts import ProviderAttempt
    from optimus.telemetry.jsonl import JsonlTelemetryWriter
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


def _status(value: Any) -> int | None:
    """An integer status as reported, else null: never inferred, never parsed from text."""
    return value if type(value) is int else None


# The router stage types the Gateway records (optimus_gateway.upstream_client.KNOWN_ROUTER_STAGES; a test keeps the
# two equal). The Gateway reports any other type as `unrecognized`, and so does the host.
ROUTER_STAGES = frozenset({"guardrail", "plugin", "server_tools", "response_healing", "context_compression"})


def _attempt_fields(attempt: ProviderAttempt) -> dict[str, Any]:
    """One attempt's content-free facts. A routed attempt's status is the upstream provider's; any other
    record's is the outer host-to-Gateway status, kept apart so a Gateway 502 never reads as an upstream one.
    ``router_pipeline`` is the allowlisted router stage types the Gateway reported; ``gateway_request_id`` and
    ``provider_request_id`` are the correlation ids, each kept only in its own generated shape (correction plan v4,
    C1); ``failure`` is the attempt's re-bounded cause. Each is None when not reported. ``router_guardrails``, each
    guardrail stage's re-bounded facts (#400), is added only when the Gateway reported them."""
    routed = attempt.routed is True
    status = _status(attempt.http_status)
    stages = attempt.router_pipeline
    fields = {
        "attempt": attempt.key,
        "outcome": attempt.outcome,
        "routed": routed,
        "upstream_http_status": status if routed else None,
        "gateway_http_status": None if routed else status,
        "router_pipeline": None if stages is None else [bounded(stage, ROUTER_STAGES) for stage in stages],
        "gateway_request_id": gateway_request_id(attempt.gateway_request_id),
        "provider_request_id": provider_request_id(attempt.provider_request_id),
        "failure": bounded_failure(attempt.failure),
    }
    if attempt.router_guardrails is not None:
        fields["router_guardrails"] = bounded_guardrail_list(attempt.router_guardrails)
    return fields


_CORRELATION_IDS: dict[str, Callable[[object], str | None]] = {"run_id": host_route_id, "session_id": host_session_id, "request_id": host_route_id}


def _correlation(values: dict[str, Any]) -> dict[str, Any]:
    """A call's correlation with each id in its generated shape (C1); any other field is a host counter or None."""
    return {
        key: _CORRELATION_IDS[key](value) if key in _CORRELATION_IDS else value if value is None or type(value) is int else UNRECOGNIZED
        for key, value in values.items()
    }


def _emit_failure(
    telemetry: JsonlTelemetryWriter, *, error_type: str, record: dict[str, Any], run_id: str | None, session_id: str | None, request_id: object
) -> None:
    """One always-on bounded ``error`` event (correction plan v4, C4), written with tracing on or off by the writer of
    the harness that started the work. The envelope: the record's run, else ``<session or no-session>:pre-run``; its
    request id as a string (an integer id as its decimal digits, 0 included), else the run, else ``pre-run``."""
    run = run_id or f"{session_id or 'no-session'}:pre-run"
    request = str(request_id) if request_id is not None else run_id or "pre-run"
    telemetry.append(
        TelemetryEvent.error(
            run_id=run,
            session_id=session_id,
            request_id=request,
            occurred_at=datetime.now(UTC),
            error_type=error_type,
            message=json.dumps(final_sanitize(record), separators=(",", ":"), sort_keys=True, default=_json_default_handler),
            disposition="recorded",
        )
    )


# Causes a diagnostic can record without an exception (Codex round 13 finding 2).
TRACE_REASONS = frozenset({"summary_disclosure_undelivered"})


def log_provider_attempts(
    *,
    stage: str,
    correlation: Callable[[], dict[str, Any]],
    attempts: Iterable[ProviderAttempt],
    failure: BaseException | None = None,
    reason: str | None = None,
    telemetry: JsonlTelemetryWriter | None = None,
) -> None:
    """Record the content-free status and cause of every provider attempt behind one host model request (Plan 12.2
    r4 stop diagnosis; Codex disposition 2026-10-13, revised 2026-10-21 under the operator's diagnosability
    directive, Codex round 13 and correction plan v4): the attempts the host already classified, in order, including
    failures before a safe recovery. Written: the call correlation with each id in its generated shape, the stage,
    and each attempt's key, outcome, routing, integer-or-null status, allowlisted router stage types, Gateway and
    provider request ids in their own shapes, and re-bounded cause. A request that failed with a Gateway HTTP error
    adds `gateway_failure`: the Gateway's allowlisted refusal code, its outer status (apart from any routed attempt's
    upstream status, r8 offline correction), the host's own cause, the error envelope's facts and a dropped-attempts
    flag. Any other failure adds `host_failure`: a response-contract audit code, or the exception's class, first
    cause and errno. A `reason` without an exception is recorded only when allowlisted. Never a body, header, error
    text, key, provider error type, prompt or reply.

    The trace line is written only with tracing enabled. With ``telemetry`` (the harness's workspace writer, bound
    at composition), a request that failed, has a reason or any attempt short of completed also leaves one always-on
    ``provider_attempt_failure`` event. Nothing is read when neither applies; any ordinary failure building or
    writing either record is contained, and cancellation propagates."""
    if not debug_trace_enabled() and telemetry is None:
        return

    @functools.cache
    def data() -> dict[str, Any]:
        record: dict[str, Any] = {"stage": stage, **_correlation(correlation()), "attempts": [_attempt_fields(attempt) for attempt in attempts]}
        if failure is not None:
            facts = gateway_failure_facts(failure)
            if facts is not None:
                record["gateway_failure"] = facts
            host = host_failure_facts(failure)
            if host is not None:
                record["host_failure"] = host
        if reason is not None:
            record["reason"] = bounded(reason, TRACE_REASONS)
        return record

    acp_debug_log(location="debug_trace.py:log_provider_attempts", message="provider attempts classified", data=data, hypothesis_id="P12.2-ATTEMPT-STATUS")
    if telemetry is None:
        return
    try:
        record = data()
        if failure is None and reason is None and all(attempt["outcome"] == "completed" for attempt in record["attempts"]):
            return
        request = record.get("request_id")
        _emit_failure(
            telemetry,
            error_type="provider_attempt_failure",
            record=record,
            run_id=record.get("run_id") or host_run_of(request),
            session_id=record.get("session_id"),
            request_id=request,
        )
    except Exception:  # noqa: BLE001 - a diagnostic never fails the request it describes
        return


# Fixed admission refusal reasons (optimus.acp.conversation and spec's fallback).
PROMPT_REFUSAL_REASONS = frozenset({"cap", "cap_closed", "reservation", "delivery_indeterminate", "refused"})
# Fixed refusals of a prompt request before any turn starts (spec `_handle_session_prompt`, correction plan v4 C5).
PRE_RUN_REFUSAL_REASONS = frozenset({"invalid_params", "invalid_prompt_shape", "unknown_session", "empty_prompt", "turn_in_progress"})


def _refusal_record(session_id: object, request_id: object, reason: str, allowed: frozenset[str]) -> dict[str, Any]:
    return {"session_id": host_session_id(session_id), "request_id": rpc_request_id(request_id), "reason": bounded(reason, allowed)}


def _emit_refusal(telemetry: JsonlTelemetryWriter | None, error_type: str, data: Callable[[], dict[str, Any]]) -> None:
    if telemetry is None:
        return
    try:
        record = data()
        _emit_failure(telemetry, error_type=error_type, record=record, run_id=None, session_id=record["session_id"], request_id=record["request_id"])
    except Exception:  # noqa: BLE001 - a diagnostic never fails the refusal it describes
        return


def log_prompt_refusal(*, session_id: object, request_id: object, reason: str, telemetry: JsonlTelemetryWriter | None = None) -> None:
    """A prompt refused at admission, before any run (Codex round 13 finding 2): the session id and the client's
    request id, each in its own shape (C1), and the allowlisted fixed reason, in the trace and (C4) the always-on
    ``prompt_refused`` event. Never the prompt."""

    def data() -> dict[str, Any]:
        return _refusal_record(session_id, request_id, reason, PROMPT_REFUSAL_REASONS)

    acp_debug_log(location="debug_trace.py:log_prompt_refusal", message="prompt refused before any run", data=data, hypothesis_id="P12.2-DIAGNOSABILITY")
    _emit_refusal(telemetry, "prompt_refused", data)


def log_pre_run_refusal(*, session_id: object, request_id: object, reason: str, telemetry: JsonlTelemetryWriter | None = None) -> None:
    """A prompt request refused before any turn (correction plan v4, C5): the same facts as `log_prompt_refusal`
    with a fixed pre-run reason, as the ``pre_run_refused`` event. Never the prompt or the invalid values."""

    def data() -> dict[str, Any]:
        return _refusal_record(session_id, request_id, reason, PRE_RUN_REFUSAL_REASONS)

    acp_debug_log(location="debug_trace.py:log_pre_run_refusal", message="prompt request refused before any turn", data=data, hypothesis_id="P12.2-DIAGNOSABILITY")
    _emit_refusal(telemetry, "pre_run_refused", data)


def log_context_fault(*, run_id: str, phase: str, category: str, detail: str | None, outcome: str, telemetry: JsonlTelemetryWriter | None = None) -> None:
    """One attached-view fault with its bounded subtype (Codex round 13 finding 2): the same content-free facts as
    the operator line, kept in the trace and (C4) the always-on ``context_fault`` event."""

    def data() -> dict[str, Any]:
        return {"run_id": host_route_id(run_id), "phase": phase, "category": category, "detail": detail, "outcome": outcome}

    acp_debug_log(location="debug_trace.py:log_context_fault", message="context fault", data=data, hypothesis_id="P12.2-DIAGNOSABILITY")
    if telemetry is None:
        return
    try:
        record = data()
        run = record["run_id"]
        session = host_session_id(run.split(":")[0]) if run not in (None, UNRECOGNIZED) else None
        _emit_failure(telemetry, error_type="context_fault", record=record, run_id=run, session_id=session, request_id=None)
    except Exception:  # noqa: BLE001 - a diagnostic never fails the turn
        return


# An Auto turn refused before any answer call, or routed by the classifier-failure rule (Plan 12.4 Task 4).
AUTO_ROUTE_REASONS = frozenset(
    {
        "CLASSIFIER_NOT_INSTALLED",
        "AUTO_NO_ROUTABLE_MODEL",
        "ACCOUNTING_INTEGRITY",
        "timeout",
        "invalid_answer",
        "abstention",
        "stopped_classifier",
        "error",
    }
)


def log_auto_route(*, run_id: str, outcome: str, reason: str, telemetry: JsonlTelemetryWriter | None = None) -> None:
    """An Auto turn's refusal (``outcome`` refused) or classifier failure (``outcome`` failure_rule) with its bounded
    reason, in the trace and the always-on ``auto_route`` event. Never the prompt or the classifier's input."""

    def data() -> dict[str, Any]:
        return {"run_id": host_route_id(run_id), "outcome": outcome, "reason": bounded(reason, AUTO_ROUTE_REASONS)}

    acp_debug_log(location="debug_trace.py:log_auto_route", message="auto route", data=data, hypothesis_id="P12.4-AUTO")
    if telemetry is None:
        return
    try:
        record = data()
        run = record["run_id"]
        session = host_session_id(run.split(":")[0]) if run not in (None, UNRECOGNIZED) else None
        _emit_failure(telemetry, error_type="auto_route", record=record, run_id=run, session_id=session, request_id=None)
    except Exception:  # noqa: BLE001 - a diagnostic never fails the turn
        return


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
            # An evaluation caller's remaining explicit cap only; absent on product runs (Plan 12.2 Task 11).
            **({} if event.remaining_budget_usd is None else {"remaining_budget_usd": str(event.remaining_budget_usd)}),
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
