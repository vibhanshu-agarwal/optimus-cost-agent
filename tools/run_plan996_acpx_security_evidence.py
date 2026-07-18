#!/usr/bin/env python3
"""Controlled ACP capture entry point for Plan 9.96 evidence.

The capture path is deliberately independent of ``optimus.acp.__main__`` so
it can exercise the launch trust gates before starting the independently
provided ``acpx`` child.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO

import keyring

from optimus.acp.launch_approvals import (
    LAUNCH_POLICY_COMPATIBILITY,
    ApprovalError,
    KeyringApprovalStore,
)
from optimus.acp.launch_audit import LaunchAuditError, LaunchAuditEvent, append_launch_audit_event
from optimus.acp.launch_gate import (
    AuthorizedLaunch,
    LaunchGateError,
    authorize_launch,
    resolve_launch_candidate,
)
from optimus.acp.launch_policy import (
    LAUNCH_VARIABLE_POLICIES,
    LaunchEnvironmentSnapshot,
    LaunchVariableTier,
)
from optimus.acp.local_infra import _SYSTEM_ENV_KEYS, apply_local_defaults
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import (
    TrustedPathError,
    resolve_trusted_operator_roots,
    resolve_workspace_identity,
    revalidate_workspace_identity,
)
from optimus.agent.state_store import RedisAgentStateStore
from optimus_security.launch_manifest import LaunchManifestError, read_manifest_hmac_key
from optimus_security.sanitization import StreamingTextSanitizer


@dataclass(frozen=True)
class CaptureLaunch:
    """An authorized capture launch that has not yet started a child process."""

    authorized: AuthorizedLaunch
    agent_environ: Mapping[str, str]
    acpx_client_environ: Mapping[str, str]


@dataclass(frozen=True)
class AuditedLaunch:
    """A capture launch whose required audit event was recorded."""

    capture: CaptureLaunch


@dataclass(frozen=True)
class SessionResultEvidence:
    session_id: str
    prompt_request_id: int
    run_id: str
    stop_reason: str
    tool_names: tuple[str, ...]
    tool_call_count: int


@dataclass(frozen=True)
class ExternalSessionEvidence:
    run_id: str
    total_cost_usd: Decimal


@dataclass(frozen=True)
class RunScopedLogEvidence:
    child_key_names: tuple[str, ...]
    elevated_comparison_record_present: bool
    rule_counts: Mapping[str, int]


def _parse_session_result(transcript: str) -> SessionResultEvidence:
    """Reduce the observed ACP JSON-RPC session shape to content-free fields."""
    session_id: str | None = None
    prompt_request_id: int | None = None
    stop_reason: str | None = None
    tool_names: list[str] = []
    for line in transcript.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        result = record.get("result")
        if isinstance(result, dict) and isinstance(result.get("sessionId"), str):
            session_id = result["sessionId"]
        if record.get("method") == "session/prompt" and isinstance(record.get("id"), int):
            prompt_request_id = record["id"]
        if isinstance(result, dict) and isinstance(result.get("stopReason"), str):
            stop_reason = result["stopReason"]
        update = record.get("params", {}).get("update", {}) if isinstance(record.get("params"), dict) else {}
        if isinstance(update, dict) and update.get("sessionUpdate") == "tool_call" and isinstance(update.get("title"), str):
            tool_names.append(update["title"])
    if session_id is None or prompt_request_id is None or stop_reason is None:
        raise ValueError("incomplete ACP session result")
    return SessionResultEvidence(session_id, prompt_request_id, f"{session_id}:{prompt_request_id}", stop_reason, tuple(tool_names), len(tool_names))


def _collect_external_session_evidence(
    *, capture: CaptureLaunch, session_result: SessionResultEvidence, output_dir: Path, known_secrets: tuple[str, ...]
) -> ExternalSessionEvidence:
    """Read the run-bound Redis plan once and persist its content-free cost only."""
    redis_url = capture.agent_environ["OPTIMUS_REDIS_URL"]
    store = RedisAgentStateStore.from_url(redis_url)
    record = store.latest_plan_for_run(run_id=session_result.run_id)
    if record is None or record.run_id != session_result.run_id:
        raise ValueError("external session evidence is absent or run-ID mismatched")
    try:
        cost = Decimal(str(record.cost_usd))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("external session evidence has invalid cost") from exc
    if cost <= 0:
        raise ValueError("external session evidence cost must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = json.dumps({"run_id": session_result.run_id, "total_cost_usd": str(cost)}, sort_keys=True)
    _stream_sanitized(io.StringIO(snapshot), output_dir / "external-session-evidence.json", known_secrets=known_secrets)
    return ExternalSessionEvidence(run_id=session_result.run_id, total_cost_usd=cost)


_STREAM_READ_SIZE = 8192
_CAPTURE_WAIT_TIMEOUT_SECONDS = 30.0
_DRIVE_SESSION_WAIT_TIMEOUT_SECONDS = 600.0
_TERMINATION_CLEANUP_GRACE_SECONDS = 3.0
_SANITIZER_VERSION = "p996-streaming-sanitizer-v1"
_EVIDENCE_MANIFEST_HMAC_DOMAIN = b"p996-evidence-manifest-hmac-v1"
_EVIDENCE_MANIFEST_FILENAME = "sanitizer-manifest.json"
_TRANSCRIPT_ARTIFACTS = (
    "transcript.stdout",
    "transcript.stderr",
    "external-session-evidence.json",
    "audit-snapshot.ndjson",
    "debug-snapshot.ndjson",
)
_SESSION_FIXTURE_FILENAME = "plan998_fixture.py"
_SESSION_FIXTURE_PRISTINE_CONTENT = "def status():\n    return 'pending'\n"
SESSION_TASK = (
    "Add a module docstring to `plan998_fixture.py` describing its function. "
    "Modify only `plan998_fixture.py`; do not create any other files or tests."
)
_EVIDENCE_RUN_NONCE_RE = re.compile(r"^run_[0-9a-f]{24}$")
_CORRELATION_TAG_RE = re.compile(r"^[0-9a-f]{32}$")
_ALLOWED_CORRELATION_TAG_FIELDS = frozenset(
    name
    for name, policy in LAUNCH_VARIABLE_POLICIES.items()
    if policy.tier is LaunchVariableTier.SECRET
)


def _build_agent_invocation(
    *,
    optimus_agent: str,
    workspace: Path,
    launch_session_id: str,
    diagnostic_grant_id: str | None,
) -> str:
    """Build only the inner Optimus-agent invocation for an acpx session."""
    arguments = [
        # ACPX parses --agent as raw command text and treats backslashes as
        # escapes, so Windows paths embedded here must use forward slashes.
        optimus_agent.replace("\\", "/"),
        "--workspace-root",
        workspace.as_posix(),
        "--launch-session-id",
        launch_session_id,
        "--debug-trace",
    ]
    if diagnostic_grant_id is not None:
        arguments.extend(("--diagnostic-grant-id", diagnostic_grant_id))
    return " ".join(arguments)


def _build_capture_command(
    *,
    acpx: str,
    workspace: Path,
    agent_invocation: str | None,
    drive_session: bool,
) -> list[str]:
    """Build the unchanged smoke command or the independently driven session."""
    if not drive_session:
        return [acpx, "--version"]
    if agent_invocation is None:
        raise ValueError("agent invocation is required for --drive-session")
    return [
        acpx,
        "--format",
        "json",
        "--approve-all",
        "--cwd",
        str(workspace),
        "--agent",
        agent_invocation,
        "exec",
        SESSION_TASK,
    ]



def authorize_capture(
    *,
    workspace: Path,
    environment: Mapping[str, str],
    keyring_backend: Any | None = None,
    approval_runtime_root: Path | None = None,
    launch_approval_id: str | None = None,
    launch_session_id: str,
    diagnostic_grant_id: str | None = None,
    drive_session: bool = False,
) -> CaptureLaunch:
    """Capture once, resolve, and authorize a controlled ACP capture launch.

    For elevated mode (diagnostic_grant_id is not None), consume the
    diagnostic grant via the committed single-use path, bound to the launch
    session ID. Fail CLOSED on any grant error — unlike the serving process
    (which silently downgrades to ordinary), an evidence harness that claims
    elevated but captured ordinary produces wrong-mode evidence.
    """
    snapshot = LaunchEnvironmentSnapshot.capture(environment)
    workspace_identity = resolve_workspace_identity(workspace)
    operator_paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
    )
    if keyring_backend is None:
        import keyring as keyring_backend

    if approval_runtime_root is None:
        approval_runtime_root = resolve_trusted_operator_roots(platform_name=sys.platform).approval_runtime_root
    store = KeyringApprovalStore(keyring_backend=keyring_backend, runtime_root=approval_runtime_root)
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=workspace_identity,
        operator_paths=operator_paths,
        hmac_key=store.hmac_key,
        credential_keyring_backend=keyring_backend,
    )
    authorized = authorize_launch(
        candidate=candidate,
        store=store,
        approval_id=launch_approval_id,
        launch_session_id=launch_session_id,
    )
    if drive_session and candidate.display_rows:
        classified_names = ",".join(row.name for row in candidate.display_rows)
        raise LaunchGateError(
            code="ACPX_CLIENT_ENV_NOT_CLEAN",
            detail=f"classified inherited settings: {classified_names}",
        )
    if diagnostic_grant_id is not None:
        # Fail CLOSED: an invalid/expired/wrong-session grant must not silently
        # downgrade to ordinary. The serving process (__main__.py) downgrades
        # because ordinary is the safe serving mode; an evidence harness that
        # claims elevated but captured ordinary is wrong-mode evidence.
        try:
            grant = store.consume_diagnostic_grant(diagnostic_grant_id, launch_session_id)
        except ApprovalError as exc:
            raise LaunchGateError(
                code=exc.code,
                detail=exc.detail,
            ) from exc
        from dataclasses import replace
        authorized = replace(authorized, diagnostic_grant=grant)
    agent_environ = apply_local_defaults(
        authorized.candidate.agent_environ,
        config_root=authorized.candidate.operator_paths.config_root,
        resolved_shared_secret=authorized.candidate.shared_secret,
    )
    acpx_client_environ = {
        name: value
        for name in _SYSTEM_ENV_KEYS
        if (value := authorized.candidate.inherited.values.get(name, ""))
    }
    return CaptureLaunch(
        authorized=authorized,
        agent_environ=agent_environ,
        acpx_client_environ=acpx_client_environ,
    )


def append_authorized_audit(capture: CaptureLaunch) -> AuditedLaunch:
    """Append the value-safe launch audit event before child startup."""
    authorized = capture.authorized
    candidate = authorized.candidate
    setting_decisions = tuple(
        {
            "name": row.name,
            "tier": row.tier.value,
            "source_class": row.source_class,
            "decision": row.decision,
        }
        for row in candidate.display_rows
    )
    event = LaunchAuditEvent(
        timestamp=datetime.now(timezone.utc),
        workspace_digest=candidate.workspace_identity.digest,
        launch_session_id=authorized.launch_session_id,
        approval_id=authorized.approval_id,
        approval_mode=authorized.approval_mode,
        registry_version=LAUNCH_POLICY_COMPATIBILITY,
        policy_version=LAUNCH_POLICY_COMPATIBILITY,
        setting_decisions=setting_decisions,
        monotonic_dispositions=tuple(
            {"name": name, "disposition": "recorded"} for name in sorted(candidate.monotonic_grants)
        ),
        rejected_names=(),
        child_propagation_decisions={
            "agent_child": tuple(sorted(capture.agent_environ)),
            "gateway_child": tuple(sorted(candidate.gateway_environ)),
            "acpx_client": tuple(
                sorted(
                    name
                    for name in capture.acpx_client_environ
                    if name not in _SYSTEM_ENV_KEYS
                )
            ),
        },
        diagnostic_grant_state="none" if authorized.diagnostic_grant is None else "granted",
        sanitizer_rule_counts={},
        final_reason_code="AUTHORIZED",
    )
    append_launch_audit_event(event, runtime_root=candidate.operator_paths.runtime_root)
    return AuditedLaunch(capture=capture)


def spawn_authorized_capture(
    audited: AuditedLaunch, *, command: Sequence[str], drive_session: bool = False
) -> subprocess.Popen[str]:
    """Revalidate the workspace and start the authorized capture child."""
    if not command:
        raise ValueError("capture command must not be empty")
    capture = audited.capture
    candidate = capture.authorized.candidate
    revalidate_workspace_identity(candidate.workspace_identity)
    # ACPX is only a transport client. The effective agent mapping belongs to
    # the independently launched inner agent and must never be inherited here.
    spawn_kwargs: dict[str, Any] = {}
    if drive_session:
        if sys.platform == "win32":
            spawn_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            spawn_kwargs["start_new_session"] = True
    return subprocess.Popen(
        list(command),
        cwd=candidate.workspace_identity.canonical_path,
        env=capture.acpx_client_environ,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **spawn_kwargs,
    )


def capture_acpx(
    *,
    workspace: Path,
    environment: Mapping[str, str],
    keyring_backend: Any | None = None,
    approval_runtime_root: Path | None = None,
    launch_approval_id: str | None = None,
    launch_session_id: str,
    command: Sequence[str],
    diagnostic_grant_id: str | None = None,
    drive_session: bool = False,
) -> subprocess.Popen[str]:
    """Run the complete authorization, audit, revalidation, and spawn walk."""
    capture = authorize_capture(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring_backend,
        approval_runtime_root=approval_runtime_root,
        launch_approval_id=launch_approval_id,
        launch_session_id=launch_session_id,
        diagnostic_grant_id=diagnostic_grant_id,
        drive_session=drive_session,
    )
    audited = append_authorized_audit(capture)
    return spawn_authorized_capture(
        audited,
        command=command,
        drive_session=drive_session,
    )


def _known_secrets(capture: CaptureLaunch) -> tuple[str, ...]:
    candidate = capture.authorized.candidate
    secrets: list[str] = []
    # Env-sourced SECRET-tier values from the projected child environments —
    # the child sees these and could echo them. Uses the projected env (not
    # inherited.values) because the projection is what the child actually
    # receives, and it is the gate's sanctioned one-time snapshot.
    for name in candidate.secret_inventory:
        if name in candidate.agent_environ:
            secrets.append(candidate.agent_environ[name])
        if name in candidate.gateway_environ:
            secrets.append(candidate.gateway_environ[name])
    # Resolved provider API key and shared secret may come from .env.gateway or
    # keyring, NOT the inherited env scan, so they are absent from
    # secret_inventory when sourced from keyring (Task 9's real configuration:
    # credentials in Windows Credential Manager, no .env). apply_local_defaults
    # projects the shared secret into the child's OPTIMUS_API_KEY; the provider
    # key is projected into the gateway child env. Both must be folded in or an
    # acpx echo of OPTIMUS_API_KEY goes raw to disk — Task 8's purpose defeated
    # in precisely the configuration Task 9 runs.
    if (
        candidate.provider_credentials is not None
        and candidate.provider_credentials.secrets is not None
    ):
        secrets.append(candidate.provider_credentials.secrets.model_provider_api_key)
    if candidate.shared_secret:
        secrets.append(candidate.shared_secret)
    return tuple(secrets)


def _stream_sanitized(
    source: TextIO, destination: Path, *, known_secrets: tuple[str, ...]
) -> Mapping[str, int]:
    """Stream-sanitize source to destination. Returns the sanitizer's rule
    counts (content-free metadata for the evidence manifest)."""
    sanitizer = StreamingTextSanitizer(known_secrets=known_secrets)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        while chunk := source.read(_STREAM_READ_SIZE):
            stream.write(sanitizer.feed(chunk))
        stream.write(sanitizer.finalize())
    return dict(sanitizer.rule_counts)


def _current_log_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _read_log_suffix(path: Path, *, offset: int) -> str:
    """Read one append-only log suffix from an already-captured byte offset."""
    if offset < 0:
        raise ValueError("run-scoped log offset must be nonnegative")
    if not path.exists():
        if offset == 0:
            return ""
        raise ValueError("run-scoped log disappeared after offset capture")
    size = path.stat().st_size
    if size < offset:
        raise ValueError("run-scoped log shrank after offset capture")
    with path.open("rb") as stream:
        stream.seek(offset)
        encoded = stream.read()
    try:
        return encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("run-scoped log suffix is not UTF-8") from exc


def _parse_ndjson_suffix(suffix: str, *, source_name: str) -> tuple[dict[str, object], ...]:
    """Parse a complete append-only NDJSON suffix without exposing its values."""
    if not suffix:
        return ()
    if not suffix.endswith("\n"):
        raise ValueError(f"{source_name} suffix ended with a partial record")
    records: list[dict[str, object]] = []
    for line in suffix.splitlines():
        if not line:
            raise ValueError(f"{source_name} suffix contains an empty record")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source_name} suffix contains malformed JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{source_name} suffix record is not an object")
        records.append(record)
    return tuple(records)


def _validate_correlation_tags(tags: object) -> None:
    if not isinstance(tags, list):
        raise ValueError("comparison correlation_tags must be an array")
    for item in tags:
        if not isinstance(item, dict) or set(item) != {"field_name", "tag"}:
            raise ValueError("comparison correlation tag has malformed fields")
        field_name = item["field_name"]
        tag = item["tag"]
        if not isinstance(field_name, str) or field_name not in _ALLOWED_CORRELATION_TAG_FIELDS:
            raise ValueError("comparison correlation tag field is not allowlisted")
        if not isinstance(tag, str) or _CORRELATION_TAG_RE.fullmatch(tag) is None:
            raise ValueError("comparison correlation tag is not sanitized 128-bit hex")


def _snapshot_run_scoped_launch_logs(
    *,
    workspace: Path,
    output_dir: Path,
    audit_offset: int,
    debug_offset: int,
    launch_session_id: str,
    session_mode: str,
    known_secrets: tuple[str, ...],
) -> RunScopedLogEvidence:
    """Validate and sanitize only this capture's append-only audit/debug suffixes."""
    runtime_root = workspace / ".optimus"
    audit_suffix = _read_log_suffix(
        runtime_root / "launch-audit.ndjson",
        offset=audit_offset,
    )
    debug_suffix = _read_log_suffix(
        runtime_root / "debug-acp.ndjson",
        offset=debug_offset,
    )
    audit_records = _parse_ndjson_suffix(audit_suffix, source_name="launch audit")
    debug_records = _parse_ndjson_suffix(debug_suffix, source_name="debug trace")

    if len(audit_records) != 2:
        raise ValueError("run-scoped launch audit suffix must contain exactly two records")
    if any(record.get("launch_session_id") != launch_session_id for record in audit_records):
        raise ValueError("run-scoped launch audit suffix contains a foreign session")

    outer_decisions = audit_records[0].get("child_propagation_decisions")
    if not isinstance(outer_decisions, dict):
        raise ValueError("outer launch audit record lacks child propagation decisions")
    agent_child = outer_decisions.get("agent_child")
    if (
        not isinstance(agent_child, list)
        or any(not isinstance(name, str) for name in agent_child)
        or len(agent_child) != len(set(agent_child))
    ):
        raise ValueError("outer launch audit agent_child names are malformed")
    acpx_client = outer_decisions.get("acpx_client")
    if not isinstance(acpx_client, list) or acpx_client:
        raise ValueError("outer launch audit acpx_client role must exist and be empty")

    if debug_records:
        debug_session_ids = {record.get("sessionId") for record in debug_records}
        if (
            len(debug_session_ids) != 1
            or any(not isinstance(session_id, str) or not session_id for session_id in debug_session_ids)
        ):
            raise ValueError("run-scoped debug suffix contains multiple or malformed sessions")

    comparison_records = tuple(
        record
        for record in debug_records
        if record.get("location") == "launch_authorization_comparison"
    )
    expected_comparisons = 1 if session_mode == "elevated" else 0
    if session_mode not in {"ordinary", "elevated"}:
        raise ValueError("session mode must be ordinary or elevated")
    if len(comparison_records) != expected_comparisons:
        raise ValueError("run-scoped comparison-record count does not match session mode")
    for record in comparison_records:
        data = record.get("data")
        if not isinstance(data, dict):
            raise ValueError("comparison record data is malformed")
        _validate_correlation_tags(data.get("correlation_tags"))

    output_dir.mkdir(parents=True, exist_ok=True)
    audit_snapshot = output_dir / "audit-snapshot.ndjson"
    debug_snapshot = output_dir / "debug-snapshot.ndjson"
    try:
        audit_counts = _stream_sanitized(
            io.StringIO(audit_suffix),
            audit_snapshot,
            known_secrets=known_secrets,
        )
        debug_counts = _stream_sanitized(
            io.StringIO(debug_suffix),
            debug_snapshot,
            known_secrets=known_secrets,
        )
    except Exception:
        audit_snapshot.unlink(missing_ok=True)
        debug_snapshot.unlink(missing_ok=True)
        raise

    rule_counts: dict[str, int] = {}
    for counts in (audit_counts, debug_counts):
        for name, count in counts.items():
            rule_counts[name] = rule_counts.get(name, 0) + count
    return RunScopedLogEvidence(
        child_key_names=tuple(agent_child),
        elevated_comparison_record_present=bool(comparison_records),
        rule_counts=rule_counts,
    )


@dataclass(frozen=True)
class CaptureResult:
    """Result of a capture: child exit code and aggregated sanitizer rule counts."""

    exit_code: int
    rule_counts: Mapping[str, int]


def _capture_to_disk(
    audited: AuditedLaunch, *, command: Sequence[str], output_dir: Path, drive_session: bool = False,
    wait_timeout_seconds: float | None = None,
) -> CaptureResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    process = spawn_authorized_capture(audited, command=command, drive_session=drive_session)
    assert process.stdout is not None
    assert process.stderr is not None
    secrets = _known_secrets(audited.capture)
    rule_counts: dict[str, int] = {}
    counts_lock = threading.Lock()

    def _merge_counts(counts: Mapping[str, int]) -> None:
        with counts_lock:
            for name, count in counts.items():
                rule_counts[name] = rule_counts.get(name, 0) + count

    workers = [
        threading.Thread(
            target=lambda: _merge_counts(
                _stream_sanitized(process.stdout, output_dir / "transcript.stdout", known_secrets=secrets)
            ),
        ),
        threading.Thread(
            target=lambda: _merge_counts(
                _stream_sanitized(process.stderr, output_dir / "transcript.stderr", known_secrets=secrets)
            ),
        ),
    ]
    for worker in workers:
        worker.start()
    timeout = wait_timeout_seconds or (
        _DRIVE_SESSION_WAIT_TIMEOUT_SECONDS if drive_session else _CAPTURE_WAIT_TIMEOUT_SECONDS
    )
    deadline = time.monotonic() + timeout
    timed_out = False
    for worker in workers:
        worker.join(timeout=max(0.0, deadline - time.monotonic()))
        timed_out = timed_out or worker.is_alive()
    try:
        if timed_out:
            raise subprocess.TimeoutExpired(command, timeout)
        exit_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if drive_session and sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    check=False,
                    capture_output=True,
                    timeout=_TERMINATION_CLEANUP_GRACE_SECONDS,
                )
            except subprocess.TimeoutExpired:
                pass
        else:
            process.kill()
        try:
            process.wait(timeout=_TERMINATION_CLEANUP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        cleanup_deadline = time.monotonic() + _TERMINATION_CLEANUP_GRACE_SECONDS
        for worker in workers:
            worker.join(timeout=max(0.0, cleanup_deadline - time.monotonic()))
        exit_code = process.returncode or 1
    return CaptureResult(exit_code=exit_code, rule_counts=dict(rule_counts))


def _compute_artifact_sha256(path: Path) -> str:
    """SHA-256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_decoded_strings(content: str) -> list[str]:
    """Extract every string value from JSON lines in the transcript.

    Plan 9.96 Task 8 Step 3 requires scanning **decoded** transcript records,
    not just raw text. A secret inside a JSON string can be unicode-escaped
    (e.g. ``\u0068unter2``) and evade a raw-text scan entirely. This function
    parses each line as JSON and recursively extracts every string value,
    so the joined scan can catch what the raw-text layer misses.
    """
    decoded: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        _collect_strings(obj, decoded)
    return decoded


def _extract_decoded_strings_by_path(content: str) -> dict[str, list[str]]:
    """Extract decoded string values grouped by their JSON key path.

    Plan 9.96 Task 8 Step 3 requires "**join** decoded transcript records."
    The join is per-path: streamed deltas always recur at the same key path
    (e.g. ``update.content.text``), so concatenating values at each path in
    document order reconstructs the stream exactly. Structural fields like
    ``method`` or ``sessionUpdate`` join only with themselves (harmless).
    This is fully general — no protocol-specific path assumptions, no
    fallback branch.

    Returns a dict mapping dotted key paths to lists of string values at
    that path, in document order.
    """
    by_path: dict[str, list[str]] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        _collect_strings_by_path(obj, (), by_path)
    return by_path


def _collect_strings_by_path(
    obj: object, path: tuple[str, ...], out: dict[str, list[str]]
) -> None:
    """Recursively collect string values with their key path (dict keys only,
    array indices ignored)."""
    if isinstance(obj, str):
        key = ".".join(path) if path else "<root>"
        out.setdefault(key, []).append(obj)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            _collect_strings_by_path(value, path + (key,), out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_strings_by_path(item, path, out)


def _collect_strings(obj: object, out: list[str]) -> None:
    """Recursively collect every string value from a parsed JSON object."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            _collect_strings(value, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_strings(item, out)


def _scan_content_for_secrets(
    content: str,
    known_secrets: tuple[str, ...],
    *,
    artifact_name: str,
    secret_start_index: int = 0,
) -> list[str]:
    """Scan raw text AND decoded JSON strings for known secrets and patterns.

    Two layers:
    1. Raw-text scan: exact secret match + bearer/assignment patterns.
    2. Decoded-JSON scan: parse each JSON line, extract string values, and
       scan the decoded values. Catches unicode-escaped secrets that evade
       the raw-text layer.
    """
    rules_fired: list[str] = []

    # Layer 1: raw-text scan.
    for i, secret in enumerate(known_secrets):
        if secret and secret in content:
            rules_fired.append(f"exact_secret_leak:artifact={artifact_name}:index={secret_start_index + i}")
    if _BEARER_PATTERN.search(content):
        rules_fired.append(f"bearer_token_pattern:artifact={artifact_name}")
    if _SECRET_ASSIGNMENT_PATTERN.search(content):
        rules_fired.append(f"secret_assignment_pattern:artifact={artifact_name}")

    # Layer 2: decoded-JSON scan (per-string).
    decoded_strings = _extract_decoded_strings(content)
    for i, secret in enumerate(known_secrets):
        if secret:
            for decoded in decoded_strings:
                if secret in decoded:
                    rules_fired.append(f"decoded_secret_leak:artifact={artifact_name}:index={secret_start_index + i}")
                    break
    for decoded in decoded_strings:
        if _BEARER_PATTERN.search(decoded):
            rules_fired.append(f"decoded_bearer_token_pattern:artifact={artifact_name}")
            break
    for decoded in decoded_strings:
        if _SECRET_ASSIGNMENT_PATTERN.search(decoded):
            rules_fired.append(f"decoded_secret_assignment_pattern:artifact={artifact_name}")
            break

    # Layer 3: joined-decoded-strings scan (per JSON path). For each key path,
    # concatenate all string values at that path in document order with NO
    # separator (delta-faithful — ACP sessions stream agent text as chunked
    # deltas across records at the same path, e.g. ``update.content.text``;
    # deltas concatenate directly; a newline join would re-split the secret at
    # the boundary). This catches secrets split across record boundaries that
    # neither the raw-text scan (layer 1) nor the per-string decoded scan
    # (layer 2) can catch. The frozen plan says "**join** decoded transcript
    # records" — the join is the entire point.
    #
    # Per-path grouping (not all-strings join) so structural fields like
    # ``method`` don't interleave between content halves. Fully general — no
    # protocol-specific path assumptions.
    #
    # False-positive risk of coincidental concatenations is accepted — this is
    # a fail-closed evidence gate, and quarantine-and-investigate is the
    # correct outcome.
    strings_by_path = _extract_decoded_strings_by_path(content)
    for _path, values in strings_by_path.items():
        joined_decoded = "".join(values)
        for i, secret in enumerate(known_secrets):
            if secret and secret in joined_decoded:
                rules_fired.append(f"joined_decoded_secret_leak:artifact={artifact_name}:index={secret_start_index + i}")
        if _BEARER_PATTERN.search(joined_decoded):
            rules_fired.append(f"joined_decoded_bearer_token_pattern:artifact={artifact_name}")
        if _SECRET_ASSIGNMENT_PATTERN.search(joined_decoded):
            rules_fired.append(f"joined_decoded_secret_assignment_pattern:artifact={artifact_name}")

    return rules_fired


def _joined_scan(artifact_dir: Path, known_secrets: tuple[str, ...]) -> dict[str, object]:
    """Join decoded transcript records and scan for exact known secret values
    plus canaries/patterns. Runs while current secrets are still in memory.

    Scans both raw text and decoded JSON string values (a secret inside a JSON
    string can be unicode-escaped and evade a raw-text scan).

    Returns a result dict with:
    - hit: bool (True if any secret/canary found in sanitized output)
    - rules_fired: list of rule identifiers that triggered (content-free)
    - scanned_artifacts: list of artifact filenames scanned
    """
    rules_fired: list[str] = []
    scanned: list[str] = []

    for name in _TRANSCRIPT_ARTIFACTS:
        path = artifact_dir / name
        if not path.is_file():
            continue
        scanned.append(name)
        content = path.read_text(encoding="utf-8")
        rules_fired.extend(
            _scan_content_for_secrets(content, known_secrets, artifact_name=name)
        )

    return {
        "hit": len(rules_fired) > 0,
        "rules_fired": rules_fired,
        "scanned_artifacts": scanned,
    }


_BEARER_PATTERN = re.compile(r"(?i)(authorization:\s*bearer\s+|bearer\s+)\S+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(r"(?i)\b(token|password|secret|credential|api[_-]?key)((?:=|:)\s*)\S+")


def _compute_evidence_manifest_hmac(fields: dict[str, object], hmac_key: bytes) -> str:
    """Domain-separated HMAC-SHA-256 over the manifest fields (excluding the
    hmac field itself). Uses a distinct domain prefix from approval-record,
    grant, and gateway-child-manifest HMACs so cross-type collisions are
    impossible."""
    signed_fields = {k: v for k, v in fields.items() if k != "hmac"}
    canonical = json.dumps(signed_fields, sort_keys=True, separators=(",", ":"))
    msg = _EVIDENCE_MANIFEST_HMAC_DOMAIN + b"\x00" + canonical.encode("utf-8")
    return hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()


def _write_evidence_manifest(
    output_dir: Path,
    *,
    rule_counts: Mapping[str, int],
    joined_scan_result: dict[str, object],
    hmac_key: bytes,
    session_mode: str | None = None,
    session_result: SessionResultEvidence | None = None,
    external_evidence: ExternalSessionEvidence | None = None,
    log_evidence: RunScopedLogEvidence | None = None,
    evidence_run_nonce: str | None = None,
) -> Path:
    """Write the compact evidence manifest with HMAC. Never includes secret
    material — only SHA-256 digests, rule counts, scan result, and HMAC."""
    artifact_sha256s: dict[str, str] = {}
    for name in _TRANSCRIPT_ARTIFACTS:
        path = output_dir / name
        if path.is_file():
            artifact_sha256s[name] = _compute_artifact_sha256(path)

    manifest_fields: dict[str, object] = {
        "sanitizer_version": _SANITIZER_VERSION,
        "rule_counts": dict(rule_counts),
        "artifact_sha256": artifact_sha256s,
        "joined_scan": joined_scan_result,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    session_inputs = (
        session_mode,
        session_result,
        external_evidence,
        log_evidence,
        evidence_run_nonce,
    )
    if any(value is not None for value in session_inputs):
        if any(value is None for value in session_inputs):
            raise ValueError("driven-session manifest evidence inputs must be complete")
        assert session_mode is not None
        assert session_result is not None
        assert external_evidence is not None
        assert log_evidence is not None
        assert evidence_run_nonce is not None
        if session_mode not in {"ordinary", "elevated"}:
            raise ValueError("session mode must be ordinary or elevated")
        if _EVIDENCE_RUN_NONCE_RE.fullmatch(evidence_run_nonce) is None:
            raise ValueError("evidence run nonce is malformed")
        if session_result.run_id != external_evidence.run_id:
            raise ValueError("session and external evidence run IDs differ")
        if (
            not isinstance(session_result.tool_names, tuple)
            or any(not isinstance(name, str) or not name for name in session_result.tool_names)
            or session_result.tool_call_count != len(session_result.tool_names)
        ):
            raise ValueError("session tool evidence is malformed")
        if not isinstance(log_evidence.elevated_comparison_record_present, bool):
            raise ValueError("comparison-record evidence must be boolean")
        if log_evidence.elevated_comparison_record_present != (session_mode == "elevated"):
            raise ValueError("comparison-record evidence does not match session mode")
        if (
            not isinstance(log_evidence.child_key_names, tuple)
            or any(not isinstance(name, str) or not name for name in log_evidence.child_key_names)
            or len(log_evidence.child_key_names) != len(set(log_evidence.child_key_names))
        ):
            raise ValueError("child-key evidence is malformed")
        try:
            total_cost_usd = Decimal(str(external_evidence.total_cost_usd))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("external session evidence cost is invalid") from exc
        if not total_cost_usd.is_finite() or total_cost_usd <= 0:
            raise ValueError("external session evidence cost must be positive")
        required_artifacts = {
            "external-session-evidence.json",
            "audit-snapshot.ndjson",
            "debug-snapshot.ndjson",
        }
        if not required_artifacts.issubset(artifact_sha256s):
            raise ValueError("driven-session evidence snapshots are incomplete")

        manifest_fields.update(
            {
                "session_mode": session_mode,
                "tool_names": list(session_result.tool_names),
                "tool_call_count": session_result.tool_call_count,
                "total_cost_usd": str(total_cost_usd),
                "stop_reason": session_result.stop_reason,
                "child_key_names": list(log_evidence.child_key_names),
                "elevated_comparison_record_present": (
                    log_evidence.elevated_comparison_record_present
                ),
                "evidence_run_nonce": evidence_run_nonce,
            }
        )
        if (
            session_result.stop_reason == "end_turn"
            and session_result.tool_call_count > 0
            and "write_file" in session_result.tool_names
        ):
            manifest_fields["final_agent_state"] = "COMPLETED"
    manifest_fields["hmac"] = _compute_evidence_manifest_hmac(manifest_fields, hmac_key)

    manifest_path = output_dir / _EVIDENCE_MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest_fields, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path


def _verify_evidence_manifest(
    manifest_path: Path,
    *,
    artifact_dir: Path,
    keyring_backend: Any | None = None,
) -> int:
    """Verify an evidence manifest: load HMAC key via read_manifest_hmac_key,
    verify the manifest HMAC, then re-check artifact/manifest digests, JSON
    strings, canaries, patterns, and the recorded promotion decision.

    A hit quarantines the artifact and exits nonzero.
    """
    if keyring_backend is None:
        import keyring as keyring_backend

    try:
        hmac_key = read_manifest_hmac_key(keyring_backend)
    except LaunchManifestError as exc:
        print(f"optimus-agent: {exc.code}: cannot read manifest HMAC key", file=sys.stderr)
        return 2

    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    # 1. Verify HMAC before trusting anything in the manifest.
    expected_hmac = _compute_evidence_manifest_hmac(manifest, hmac_key)
    actual_hmac = manifest.get("hmac", "")
    if not hmac.compare_digest(expected_hmac, actual_hmac):
        print("optimus-agent: EVIDENCE_HMAC_MISMATCH: manifest HMAC verification failed", file=sys.stderr)
        _quarantine_artifacts(artifact_dir)
        return 1

    # 2. Re-check artifact SHA-256 digests.
    artifact_sha256s = manifest.get("artifact_sha256", {})
    for name, expected_digest in artifact_sha256s.items():
        path = artifact_dir / name
        if not path.is_file():
            print(f"optimus-agent: EVIDENCE_ARTIFACT_MISSING: {name}", file=sys.stderr)
            _quarantine_artifacts(artifact_dir)
            return 1
        actual_digest = _compute_artifact_sha256(path)
        if actual_digest != expected_digest:
            print(f"optimus-agent: EVIDENCE_DIGEST_MISMATCH: {name}", file=sys.stderr)
            _quarantine_artifacts(artifact_dir)
            return 1

    # 3. Re-run joined scan for patterns (without known secrets — verify mode
    # does not have them; it checks that no bearer/secret-assignment patterns
    # survived sanitization). Scans both raw text AND decoded JSON strings.
    for name in _TRANSCRIPT_ARTIFACTS:
        path = artifact_dir / name
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        pattern_hits = _scan_content_for_secrets(content, (), artifact_name=name)
        if pattern_hits:
            print(f"optimus-agent: EVIDENCE_PATTERN_HIT: {name}", file=sys.stderr)
            _quarantine_artifacts(artifact_dir)
            return 1

    # 4. Check the recorded joined-scan result.
    recorded_scan = manifest.get("joined_scan", {})
    if recorded_scan.get("hit"):
        print("optimus-agent: EVIDENCE_SCAN_HIT: recorded joined-scan reported a hit", file=sys.stderr)
        _quarantine_artifacts(artifact_dir)
        return 1

    print("optimus-agent: evidence manifest verified", file=sys.stderr)
    return 0


def _quarantine_artifacts(artifact_dir: Path) -> None:
    """Move artifacts outside the promotable set on a verification hit."""
    quarantine = artifact_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    for name in _TRANSCRIPT_ARTIFACTS + (_EVIDENCE_MANIFEST_FILENAME,):
        path = artifact_dir / name
        if path.is_file():
            path.rename(quarantine / name)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    capture_parser = subcommands.add_parser("capture")
    capture_parser.add_argument("--workspace", type=Path, required=True)
    capture_parser.add_argument("--output-dir", type=Path, required=True)
    capture_parser.add_argument("--mode", choices=("ordinary", "elevated"), required=True)
    capture_parser.add_argument("--agent-approval-id")
    capture_parser.add_argument("--launch-session-id")
    capture_parser.add_argument("--diagnostic-grant-id")
    capture_parser.add_argument("--drive-session", action="store_true")
    capture_parser.add_argument("--evidence-run-nonce")
    verify_parser = subcommands.add_parser("verify")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


_LEGACY_LOCATOR_PATTERNS = (
    "run_plan987",
    "run_plan988",
    "plan-9-87",
    "plan-9-88",
)

# The frozen helpers (run_plan987:1231, run_plan988:971) write their raw
# transcript to ``<workspace>/attempt-{N}-transcript.jsonl``. This filename
# contains none of the substring patterns above, so it needs its own regex.
# Precise enough to never match the 9.96 tool's own artifacts
# (transcript.stdout, transcript.stderr, sanitizer-manifest.json).
_LEGACY_RAW_TRANSCRIPT_RE = re.compile(r"attempt-\d+-transcript\.jsonl")


def _is_legacy_locator(path: Path) -> str | None:
    """Check if a path contains a Plan 9.87/9.88 legacy locator pattern.
    Returns the matched pattern if found, None otherwise."""
    path_str = str(path).lower().replace("\\", "/")
    for pattern in _LEGACY_LOCATOR_PATTERNS:
        if pattern in path_str:
            return pattern
    if _LEGACY_RAW_TRANSCRIPT_RE.search(path_str):
        return "attempt-transcript-jsonl"
    return None


def _reject_legacy_locator(path: Path, *, kind: str) -> int:
    """Reject a Plan 9.87/9.88 legacy locator as Plan 9.96 evidence."""
    matched = _is_legacy_locator(path)
    if matched is not None:
        print(
            f"optimus-agent: rejecting Plan 9.87/9.88 legacy locator ({matched}) "
            f"as Plan 9.96 evidence ({kind}). Use the controlled capture command: "
            "tools/run_plan996_acpx_security_evidence.py capture",
            file=sys.stderr,
        )
        return 2
    return -1


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "verify":
        # Step 4: reject Plan 9.87/9.88 legacy locators before verification.
        for path in (args.manifest, args.artifact_dir):
            result = _reject_legacy_locator(path, kind="verify")
            if result != -1:
                return result
        return _verify_evidence_manifest(args.manifest, artifact_dir=args.artifact_dir)

    # Step 4: reject Plan 9.87/9.88 legacy locators in capture output-dir.
    result = _reject_legacy_locator(args.output_dir, kind="capture")
    if result != -1:
        return result

    acpx = shutil.which("acpx")
    if acpx is None:
        print("acpx is required for controlled Plan 9.96 capture", file=sys.stderr)
        return 2
    # Enforce mode⇔grant coupling BEFORE authorization: an evidence artifact
    # that claims elevated but captured ordinary (or vice versa) is wrong-mode
    # evidence. --mode elevated requires --diagnostic-grant-id; --mode ordinary
    # rejects it (must not burn a single-use grant on an ordinary capture).
    if args.mode == "elevated" and args.diagnostic_grant_id is None:
        print(
            "optimus-agent: --mode elevated requires --diagnostic-grant-id "
            "(author one with optimus-trust run --elevated-debug)",
            file=sys.stderr,
        )
        return 2
    if args.mode == "ordinary" and args.diagnostic_grant_id is not None:
        print(
            "optimus-agent: --mode ordinary must not be combined with --diagnostic-grant-id",
            file=sys.stderr,
        )
        return 2
    if args.evidence_run_nonce is not None and _EVIDENCE_RUN_NONCE_RE.fullmatch(args.evidence_run_nonce) is None:
        print("optimus-agent: --evidence-run-nonce must match run_ followed by 24 lowercase hex characters", file=sys.stderr)
        return 2
    launch_session_id = args.launch_session_id or f"sess_{secrets.token_hex(12)}"
    agent_invocation: str | None = None
    if args.drive_session:
        optimus_agent = shutil.which("optimus-agent")
        if optimus_agent is None:
            print("optimus-agent is required for --drive-session", file=sys.stderr)
            return 2
        if args.evidence_run_nonce is None:
            print("optimus-agent: --drive-session requires --evidence-run-nonce", file=sys.stderr)
            return 2
        agent_invocation = _build_agent_invocation(
            optimus_agent=optimus_agent,
            workspace=args.workspace,
            launch_session_id=launch_session_id,
            diagnostic_grant_id=args.diagnostic_grant_id,
        )
    try:
        capture = authorize_capture(
            workspace=args.workspace,
            environment=os.environ,
            launch_approval_id=args.agent_approval_id,
            launch_session_id=launch_session_id,
            diagnostic_grant_id=None if args.drive_session else args.diagnostic_grant_id,
            drive_session=args.drive_session,
        )
        audit_offset = 0
        debug_offset = 0
        if args.drive_session:
            runtime_root = args.workspace / ".optimus"
            audit_offset = _current_log_size(runtime_root / "launch-audit.ndjson")
            debug_offset = _current_log_size(runtime_root / "debug-acp.ndjson")
        audited = append_authorized_audit(capture)
        # The gated smoke command is ``acpx --version``: it exits cleanly, ignores
        # stdin, and produces capturable output. Bare ``acpx`` reads a prompt from
        # stdin and would hang (reviewer-proven empirically). The provenance
        # version string is recorded from the gated child's sanitized transcript.
        # _capture_to_disk is INSIDE the try because spawn_authorized_capture
        # calls revalidate_workspace_identity at spawn time — the one TOCTOU
        # vector (workspace relocated between authorize and spawn). Without this,
        # a workspace relocation would propagate as an uncaught traceback with
        # exit 1, same defect class as the NO_APPROVAL gap fixed in FIX 5.
        command = _build_capture_command(
            acpx=acpx,
            workspace=args.workspace,
            agent_invocation=agent_invocation,
            drive_session=args.drive_session,
        )
        result = _capture_to_disk(
            audited, command=command, output_dir=args.output_dir, drive_session=args.drive_session
        )
        if result.exit_code != 0:
            _quarantine_artifacts(args.output_dir)
            return result.exit_code
        # Joined promotion scan: while current secrets are still in memory,
        # join decoded transcript records and scan for exact known values plus
        # canaries/patterns. A hit quarantines the artifact.
        known = _known_secrets(capture)
        session_result: SessionResultEvidence | None = None
        external_evidence: ExternalSessionEvidence | None = None
        log_evidence: RunScopedLogEvidence | None = None
        if args.drive_session:
            try:
                transcript = (args.output_dir / "transcript.stdout").read_text(encoding="utf-8")
                session_result = _parse_session_result(transcript)
                external_evidence = _collect_external_session_evidence(
                    capture=capture,
                    session_result=session_result,
                    output_dir=args.output_dir,
                    known_secrets=known,
                )
                log_evidence = _snapshot_run_scoped_launch_logs(
                    workspace=args.workspace,
                    output_dir=args.output_dir,
                    audit_offset=audit_offset,
                    debug_offset=debug_offset,
                    launch_session_id=capture.authorized.launch_session_id,
                    session_mode=args.mode,
                    known_secrets=known,
                )
            except Exception:
                print(
                    "optimus-agent: SESSION_EVIDENCE_UNAVAILABLE: driven-session evidence could not be collected",
                    file=sys.stderr,
                )
                _quarantine_artifacts(args.output_dir)
                return 1
        scan_result = _joined_scan(args.output_dir, known)
        if scan_result["hit"]:
            print(
                "optimus-agent: EVIDENCE_SCAN_HIT: joined scan found secret material in sanitized output",
                file=sys.stderr,
            )
            _quarantine_artifacts(args.output_dir)
            return 1
        # Write the HMAC-signed evidence manifest. The HMAC key comes from the
        # same approval-store keyring namespace (read_manifest_hmac_key), domain-
        # separated so it can never be reused as an approval-record or grant HMAC.
        approval_runtime_root = resolve_trusted_operator_roots(platform_name=sys.platform).approval_runtime_root
        manifest_store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=approval_runtime_root,
        )
        manifest_rule_counts = dict(result.rule_counts)
        if log_evidence is not None:
            for name, count in getattr(log_evidence, "rule_counts", {}).items():
                manifest_rule_counts[name] = manifest_rule_counts.get(name, 0) + count
        if args.drive_session:
            assert session_result is not None
            assert external_evidence is not None
            assert log_evidence is not None
            assert args.evidence_run_nonce is not None
            _write_evidence_manifest(
                args.output_dir,
                rule_counts=manifest_rule_counts,
                joined_scan_result=scan_result,
                hmac_key=manifest_store.hmac_key,
                session_mode=args.mode,
                session_result=session_result,
                external_evidence=external_evidence,
                log_evidence=log_evidence,
                evidence_run_nonce=args.evidence_run_nonce,
            )
        else:
            _write_evidence_manifest(
                args.output_dir,
                rule_counts=manifest_rule_counts,
                joined_scan_result=scan_result,
                hmac_key=manifest_store.hmac_key,
            )
    except LaunchGateError as exc:
        if exc.code == "NO_APPROVAL":
            print(
                "optimus-agent: no launch approval found for this workspace. Review the effective "
                "configuration and author one with:\n"
                f"  optimus-trust --workspace-root {args.workspace} approve --mode durable",
                file=sys.stderr,
            )
        elif exc.code == "SNAPSHOT_MISMATCH":
            print(
                "optimus-agent: effective configuration changed since the last approval. Review the new "
                "configuration and re-approve with:\n"
                f"  optimus-trust --workspace-root {args.workspace} approve --mode durable",
                file=sys.stderr,
            )
        else:
            print(f"optimus-agent: {exc.code}" + (f": {exc.detail}" if exc.detail else ""), file=sys.stderr)
        return 2
    except LaunchAuditError as exc:
        print(f"optimus-agent: {exc.code}: audit could not be recorded; capture stopped.", file=sys.stderr)
        return 2
    except TrustedPathError as exc:
        print(f"optimus-agent: {exc}", file=sys.stderr)
        return 2
    transcript = args.output_dir / "transcript.stdout"
    if transcript.is_file():
        version = transcript.read_text(encoding="utf-8").strip()
        if version:
            print(f"acpx provenance: {version}", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
