#!/usr/bin/env python3
"""Live evidence runner for the portable redaction gate (test tooling only).

Exercises authorized launch resolution, real OS credential reads (no writes),
independently authored ``acpx``, and fixed evidence fixtures through
``run_redaction_gate``. Does not collect scenarios, automate UI, or classify
crashes. Evidence roots are CLI-only: never read from ambient environment and
never projected into the agent child process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import keyring

from evidence_handoff.redaction.gate import run_redaction_gate
from evidence_handoff.redaction.manifest import manifest_canary_scan
from evidence_handoff.redaction.models import (
    ArtifactKind,
    Disposition,
    RedactionRuntimeInputs,
    ScreenshotApproval,
)
from optimus.acp.evidence_redaction_adapter import (
    EvidenceRedactionHostContext,
    assert_portable_runtime_inputs,
    build_redaction_runtime_inputs,
)
from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record
from optimus.acp.launch_gate import authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.local_infra import _SYSTEM_ENV_KEYS
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_trusted_operator_roots, resolve_workspace_identity
from optimus_security.sanitization import PathAliasRule, sanitize_for_persistence

REPO_ROOT = Path(__file__).resolve().parents[1]


class _ApprovalKeyring:
    """In-memory approval store backend. Never touches the OS credential store."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._store.pop((service, key), None)
FIXTURE_ZED_LINE = REPO_ROOT / "tests" / "fixtures" / "evidence" / "zed_rust_debug_line.txt"
FIXTURE_CANARIES = REPO_ROOT / "tests" / "fixtures" / "evidence" / "redaction_canaries.json"

# Known cloud-sync path segments (case-insensitive). Owned by this runner.
CLOUD_SYNC_SEGMENTS = frozenset(
    {
        "onedrive",
        "onedrivebusiness",
        "dropbox",
        "google drive",
        "googledrive",
        "icloud",
        "icloud drive",
        "box",
        "box sync",
        "mega",
        "pcloud",
        "synologydrive",
        "nextcloud",
        "owncloud",
        "seafile",
        "sugarsync",
        "amazon drive",
        "amazon photos",
        "skydrive",
    }
)

_EVIDENCE_ROOT_ENV_NAMES = frozenset(
    {
        "evidence_capture_root",
        "evidence_staging_root",
        "evidence_quarantine_root",
        "evidence_output_root",
        "EVIDENCE_CAPTURE_ROOT",
        "EVIDENCE_STAGING_ROOT",
        "EVIDENCE_QUARANTINE_ROOT",
        "EVIDENCE_OUTPUT_ROOT",
    }
)

_STREAM_READ_BYTES = 64 * 1024
_ACP_TIMEOUT_SECONDS = 600.0
_SMOKE_PROMPT = "Reply with exactly: ok"


class LiveEvidenceError(Exception):
    """Value-free runner failure. Message is the stable reason code only."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class EvidenceRoots:
    capture_root: Path
    staging_root: Path
    quarantine_root: Path
    output_root: Path


@dataclass(frozen=True)
class ArtifactRecord:
    role: str
    kind: str
    disposition: str
    artifact_sha256: str | None
    artifact_locator: str | None
    manifest_locator: str | None
    reason_code: str | None
    dropped_tail_bytes: int | None = None


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _path_has_cloud_sync_segment(path: Path) -> bool:
    parts = [part.casefold() for part in path.resolve().parts]
    for part in parts:
        if part in CLOUD_SYNC_SEGMENTS:
            return True
    for index in range(len(parts) - 1):
        joined = f"{parts[index]} {parts[index + 1]}"
        if joined in CLOUD_SYNC_SEGMENTS:
            return True
    return False


def validate_evidence_roots(
    *,
    capture_root: Path,
    staging_root: Path,
    quarantine_root: Path,
    output_root: Path,
    forbidden_persistence_roots: Sequence[Path],
) -> EvidenceRoots:
    roots = (capture_root, staging_root, quarantine_root, output_root)
    for root in roots:
        if not root.is_absolute():
            raise LiveEvidenceError("relative_root_rejected")
        resolved = root.resolve()
        if _path_has_cloud_sync_segment(resolved):
            raise LiveEvidenceError("cloud_sync_path_segment")
        for forbidden in forbidden_persistence_roots:
            if _is_under(resolved, Path(forbidden).resolve()):
                raise LiveEvidenceError("path_under_forbidden_root")
    resolved_roots = [root.resolve() for root in roots]
    for index, left in enumerate(resolved_roots):
        for right in resolved_roots[index + 1 :]:
            if left == right or _is_under(left, right) or _is_under(right, left):
                raise LiveEvidenceError("root_overlap")
    return EvidenceRoots(
        capture_root=resolved_roots[0],
        staging_root=resolved_roots[1],
        quarantine_root=resolved_roots[2],
        output_root=resolved_roots[3],
    )


def resolve_acpx() -> tuple[str, str]:
    path = shutil.which("acpx")
    if path is None:
        raise LiveEvidenceError("acpx_not_on_path")
    completed = subprocess.run(
        [path, "--version"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise LiveEvidenceError("acpx_version_failed")
    version = (completed.stdout or completed.stderr or "").strip()
    if not version:
        raise LiveEvidenceError("acpx_version_empty")
    return path, version


def spawn_agent_process(
    *,
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
) -> subprocess.Popen[str]:
    cleaned = {
        key: value
        for key, value in env.items()
        if key not in _EVIDENCE_ROOT_ENV_NAMES
    }
    return subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=dict(cleaned),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )


def load_screenshot_approval(path: Path) -> ScreenshotApproval:
    if not path.is_file():
        raise LiveEvidenceError("screenshot_approval_required")
    raw = json.loads(path.read_text(encoding="utf-8"))
    approved_at = datetime.fromisoformat(str(raw["approved_at"]))
    return ScreenshotApproval(
        staged_sha256=str(raw["staged_sha256"]),
        approver_id=str(raw["approver_id"]),
        collector_id=str(raw["collector_id"]),
        approved_at=approved_at,
        rationale=str(raw["rationale"]),
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Redaction-gate live evidence runner (test tooling only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="Run live redaction-gate evidence.")
    verify.add_argument("--capture-root", type=Path, required=True)
    verify.add_argument("--staging-root", type=Path, required=True)
    verify.add_argument("--quarantine-root", type=Path, required=True)
    verify.add_argument("--output-root", type=Path, required=True)
    verify.add_argument("--workspace-root", type=Path, default=REPO_ROOT)
    verify.add_argument("--screenshot-approval", type=Path, default=None)
    verify.add_argument(
        "--drive-acp",
        action="store_true",
        help="Drive a real acpx to agent session (requires gateway credentials).",
    )
    verify.add_argument(
        "--launch-approval-id",
        default=None,
        help="Existing durable approval id for the spawned optimus-agent.",
    )

    drive = sub.add_parser(
        "drive-acp",
        help="Re-run only the acpx session capture into the redaction gate.",
    )
    drive.add_argument("--capture-root", type=Path, required=True)
    drive.add_argument("--staging-root", type=Path, required=True)
    drive.add_argument("--quarantine-root", type=Path, required=True)
    drive.add_argument("--output-root", type=Path, required=True)
    drive.add_argument("--workspace-root", type=Path, default=REPO_ROOT)
    drive.add_argument(
        "--launch-approval-id",
        default=None,
        help="Existing durable approval id for the spawned optimus-agent.",
    )

    inspect_cmd = sub.add_parser("inspect", help="Canary/provenance scan of output root.")
    inspect_cmd.add_argument("--output-root", type=Path, required=True)

    return parser


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_STREAM_READ_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _write_private_capture(capture_root: Path, name: str, body: bytes | str) -> Path:
    capture_root.mkdir(parents=True, exist_ok=True)
    path = capture_root / name
    if isinstance(body, str):
        path.write_text(body, encoding="utf-8")
    else:
        path.write_bytes(body)
    return path.resolve()


def _promote_and_record(
    *,
    source_path: Path,
    destination_root: Path,
    artifact_kind: ArtifactKind,
    artifact_role: str,
    runtime: RedactionRuntimeInputs,
    screenshot_approval: ScreenshotApproval | None = None,
) -> ArtifactRecord:
    result = run_redaction_gate(
        source_path=source_path,
        destination_root=destination_root,
        artifact_kind=artifact_kind,
        artifact_role=artifact_role,
        runtime=runtime,
        screenshot_approval=screenshot_approval,
    )
    digest: str | None = None
    dropped: int | None = None
    if result.disposition is Disposition.PROMOTED:
        matches = sorted(
            destination_root.glob(f"bundle-{artifact_role}-*"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for bundle in matches:
            manifest_path = bundle / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            raw_digest = payload.get("artifact_sha256")
            digest = raw_digest if isinstance(raw_digest, str) else None
            raw_dropped = payload.get("dropped_tail_bytes")
            dropped = raw_dropped if isinstance(raw_dropped, int) else None
            break
    return ArtifactRecord(
        role=artifact_role,
        kind=artifact_kind.value,
        disposition=result.disposition.value,
        artifact_sha256=digest,
        artifact_locator=result.artifact_locator,
        manifest_locator=result.manifest_locator,
        reason_code=result.reason_code,
        dropped_tail_bytes=dropped,
    )


def _build_runtime(
    *,
    workspace: Path,
    roots: EvidenceRoots,
    forbidden: Sequence[Path],
) -> tuple[RedactionRuntimeInputs, dict[str, Any]]:
    env = {key: value for key, value in os.environ.items() if value}
    snapshot = LaunchEnvironmentSnapshot.capture(env)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    paths.runtime_root.mkdir(parents=True, exist_ok=True)

    assert keyring.get_keyring() is not None
    backend = keyring.get_keyring()
    backend_identity = f"{type(backend).__module__}.{type(backend).__name__}"

    # Durable approval uses an in-memory store so the OS credential store is not written.
    approval_store = KeyringApprovalStore(
        keyring_backend=_ApprovalKeyring(),
        runtime_root=paths.runtime_root,
    )
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=resolve_workspace_identity(workspace),
        operator_paths=paths,
        hmac_key=approval_store.hmac_key,
        credential_keyring_backend=keyring,
    )
    record = build_approval_record(
        mode="durable",
        workspace_identity=candidate.workspace_identity,
        security_literals=candidate.security_literals,
        secret_fingerprints=candidate.secret_fingerprints,
        monotonic_grants=candidate.monotonic_grants,
        model_observation=candidate.model_observation,
        hmac_key=approval_store.hmac_key,
    )
    approval_store.write_durable(record)
    launch = authorize_launch(
        candidate=candidate,
        store=approval_store,
        approval_id=None,
        launch_session_id=f"redaction-live-{uuid.uuid4().hex}",
    )

    profile = (roots.capture_root / ".operator-profile").resolve()
    user_data = (roots.capture_root / ".user-data").resolve()
    profile.mkdir(parents=True, exist_ok=True)
    user_data.mkdir(parents=True, exist_ok=True)

    context = EvidenceRedactionHostContext(
        authorized_launch=launch,
        operator_profile_root=profile,
        user_data_roots=(user_data,),
        temporary_capture_root=roots.capture_root,
        staging_root=roots.staging_root,
        quarantine_root=roots.quarantine_root,
        operator_identity_values=("redaction-gate-operator", "redaction-gate-host"),
        forbidden_persistence_roots=tuple(Path(item).resolve() for item in forbidden),
    )
    runtime = build_redaction_runtime_inputs(context)
    assert_portable_runtime_inputs(runtime)
    identities = {
        "keyring_backend": backend_identity,
        "approval_mode": launch.approval_mode,
        "workspace_digest": candidate.workspace_identity.digest,
        "secret_source_classes": dict(runtime.sensitive_values.source_class_counts),
        "secret_count": runtime.sensitive_values.secret_count,
        "path_alias_count": len(runtime.path_aliases),
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
    return runtime, identities


def _stream_process_to_capture(
    process: subprocess.Popen[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
) -> None:
    """Stream child stdout/stderr into private capture files only (no output transcript).

    Stdout is written as raw NDJSON lines (acpx ``--format json``). Stderr is a
    separate text capture so NDJSON parsing is not poisoned by labels.
    """
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    def _pump(stream: TextIO | None, path: Path) -> None:
        if stream is None:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for line in stream:
                handle.write(line)
                handle.flush()

    threads = [
        threading.Thread(target=_pump, args=(process.stdout, stdout_path), daemon=True),
        threading.Thread(target=_pump, args=(process.stderr, stderr_path), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_ACP_TIMEOUT_SECONDS)


def _drive_acpx_into_gate(
    *,
    acpx_path: str,
    workspace: Path,
    roots: EvidenceRoots,
    runtime: RedactionRuntimeInputs,
    launch_approval_id: str | None = None,
) -> ArtifactRecord:
    optimus_agent = shutil.which("optimus-agent")
    if optimus_agent is None:
        raise LiveEvidenceError("optimus_agent_not_on_path")

    # Match Plan 9.96 drive-session: authorize and spawn from a clean client
    # environment (system keys only). Durable approvals authored by
    # optimus-trust for keyring/.env.gateway-resolved credentials do NOT
    # include inherited OPTIMUS_* fingerprints. Loading .env into the parent
    # shell and projecting agent_environ into acpx adds
    # OPTIMUS_API_KEY / OPTIMUS_GATEWAY_URL / OPTIMUS_REDIS_URL to the child's
    # snapshot and forces SNAPSHOT_MISMATCH (diagnosis:
    # reports/task8-redaction-gate/launch-snapshot-diagnosis.json).
    clean_env = {
        name: value
        for name in _SYSTEM_ENV_KEYS
        if (value := os.environ.get(name, ""))
    }
    snapshot = LaunchEnvironmentSnapshot.capture(clean_env)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    # Same approval-runtime root the agent process uses (trusted operator roots).
    trusted = resolve_trusted_operator_roots(platform_name=sys.platform)
    approval_store = KeyringApprovalStore(
        keyring_backend=keyring,
        runtime_root=trusted.approval_runtime_root,
    )
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=resolve_workspace_identity(workspace),
        operator_paths=paths,
        hmac_key=approval_store.hmac_key,
        credential_keyring_backend=keyring,
    )
    # Fail closed only on *inherited* classified settings (OPTIMUS_* leaked into
    # the acpx client env). Keyring/default display rows for local-gateway
    # credentials are expected when the durable approval was authored against
    # keyring/.env.gateway resolution — they appear even with a clean system-key
    # snapshot and do not imply env pollution.
    inherited_rows = tuple(
        row.name for row in candidate.display_rows if row.source_class == "inherited"
    )
    if inherited_rows:
        raise LiveEvidenceError("acpx_client_env_not_clean")
    launch_session_id = f"redaction-acpx-{uuid.uuid4().hex}"
    # Fail closed in the parent before spawn; the child still re-authorizes alone.
    authorize_launch(
        candidate=candidate,
        store=approval_store,
        approval_id=launch_approval_id,
        launch_session_id=launch_session_id,
    )
    agent_args = [
        optimus_agent.replace("\\", "/"),
        "--workspace-root",
        workspace.as_posix(),
        "--launch-session-id",
        launch_session_id,
        "--debug-trace",
    ]
    if launch_approval_id:
        agent_args.extend(("--launch-approval-id", launch_approval_id))
    agent_invocation = " ".join(agent_args)
    command = [
        acpx_path,
        "--format",
        "json",
        "--approve-all",
        "--cwd",
        str(workspace),
        "--agent",
        agent_invocation,
        "exec",
        _SMOKE_PROMPT,
    ]
    stdout_path = (roots.capture_root / f"acpx-stream-{uuid.uuid4().hex}.ndjson").resolve()
    stderr_path = (roots.capture_root / f"acpx-stderr-{uuid.uuid4().hex}.txt").resolve()
    process = spawn_agent_process(
        command=command,
        cwd=workspace,
        env=dict(clean_env),
    )
    try:
        _stream_process_to_capture(
            process,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        process.wait(timeout=_ACP_TIMEOUT_SECONDS)
    finally:
        if process.poll() is None:
            process.kill()
    try:
        if stdout_path.is_file() and stdout_path.stat().st_size > 0:
            return _promote_and_record(
                source_path=stdout_path,
                destination_root=roots.output_root,
                artifact_kind=ArtifactKind.ACP_DEBUG_TRACE,
                artifact_role="acpx_session_stream",
                runtime=runtime,
            )
        return _promote_and_record(
            source_path=stderr_path,
            destination_root=roots.output_root,
            artifact_kind=ArtifactKind.TEXT,
            artifact_role="acpx_session_stream",
            runtime=runtime,
        )
    finally:
        stdout_path.unlink(missing_ok=True)
        stderr_path.unlink(missing_ok=True)


def run_verify(
    *,
    capture_root: Path,
    staging_root: Path,
    quarantine_root: Path,
    output_root: Path,
    workspace_root: Path = REPO_ROOT,
    screenshot_approval_path: Path | None = None,
    drive_acp: bool = False,
    launch_approval_id: str | None = None,
) -> dict[str, Any]:
    workspace = workspace_root.resolve()
    forbidden = (workspace, REPO_ROOT.resolve())
    roots = validate_evidence_roots(
        capture_root=capture_root,
        staging_root=staging_root,
        quarantine_root=quarantine_root,
        output_root=output_root,
        forbidden_persistence_roots=forbidden,
    )
    for root in (
        roots.capture_root,
        roots.staging_root,
        roots.quarantine_root,
        roots.output_root,
    ):
        root.mkdir(parents=True, exist_ok=True)

    acpx_path, acpx_version = resolve_acpx()
    runtime, identities = _build_runtime(
        workspace=workspace,
        roots=roots,
        forbidden=forbidden,
    )
    runtime = replace(
        runtime,
        path_aliases=runtime.path_aliases
        + (PathAliasRule(source_root=str(roots.output_root), alias="<destination>"),),
    )
    identities = {
        **identities,
        "path_alias_count": len(runtime.path_aliases),
    }

    approval: ScreenshotApproval | None = None
    if screenshot_approval_path is not None:
        approval = load_screenshot_approval(screenshot_approval_path)

    records: list[ArtifactRecord] = []

    zed_src = _write_private_capture(
        roots.capture_root,
        f"zed-line-{uuid.uuid4().hex}.txt",
        FIXTURE_ZED_LINE.read_text(encoding="utf-8"),
    )
    records.append(
        _promote_and_record(
            source_path=zed_src,
            destination_root=roots.output_root,
            artifact_kind=ArtifactKind.TEXT,
            artifact_role="zed_debug_line",
            runtime=runtime,
        )
    )
    zed_src.unlink(missing_ok=True)

    canary_src = _write_private_capture(
        roots.capture_root,
        f"canaries-{uuid.uuid4().hex}.json",
        FIXTURE_CANARIES.read_bytes(),
    )
    records.append(
        _promote_and_record(
            source_path=canary_src,
            destination_root=roots.output_root,
            artifact_kind=ArtifactKind.JSON,
            artifact_role="redaction_canaries",
            runtime=runtime,
        )
    )
    canary_src.unlink(missing_ok=True)

    secret = "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa"
    complete_lines = [
        json.dumps({"sessionId": "session-zed-canary-0123456789abcdef", "event": "start"}),
        json.dumps({"sessionId": "session-zed-canary-0123456789abcdef", "token": secret}),
    ]
    # Incomplete final line MUST NOT end with a newline (ACP truncated-tail contract).
    crash_body = "\n".join(complete_lines) + "\n" + '{"incomplete":'
    crash_src = _write_private_capture(
        roots.capture_root,
        f"acp-tail-{uuid.uuid4().hex}.ndjson",
        crash_body,
    )
    records.append(
        _promote_and_record(
            source_path=crash_src,
            destination_root=roots.output_root,
            artifact_kind=ArtifactKind.ACP_DEBUG_TRACE,
            artifact_role="acp_truncated_tail",
            runtime=runtime,
        )
    )
    crash_src.unlink(missing_ok=True)

    png_path = (roots.capture_root / f"screenshot-{uuid.uuid4().hex}.png").resolve()
    from PIL import Image

    Image.new("RGB", (16, 12), color=(10, 20, 30)).save(png_path)
    records.append(
        _promote_and_record(
            source_path=png_path,
            destination_root=roots.output_root,
            artifact_kind=ArtifactKind.SCREENSHOT,
            artifact_role="zed_render",
            runtime=runtime,
            screenshot_approval=approval,
        )
    )
    png_path.unlink(missing_ok=True)

    if drive_acp:
        records.append(
            _drive_acpx_into_gate(
                acpx_path=acpx_path,
                workspace=workspace,
                roots=roots,
                runtime=runtime,
                launch_approval_id=launch_approval_id,
            )
        )
    else:
        stdout_path = (roots.capture_root / f"acpx-version-{uuid.uuid4().hex}.txt").resolve()
        stderr_path = (roots.capture_root / f"acpx-version-err-{uuid.uuid4().hex}.txt").resolve()
        process = spawn_agent_process(
            command=[acpx_path, "--version"],
            cwd=workspace,
            env={
                key: value
                for key, value in os.environ.items()
                if key not in _EVIDENCE_ROOT_ENV_NAMES
            },
        )
        try:
            _stream_process_to_capture(
                process,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
            process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
        try:
            records.append(
                _promote_and_record(
                    source_path=stdout_path,
                    destination_root=roots.output_root,
                    artifact_kind=ArtifactKind.TEXT,
                    artifact_role="acpx_version_banner",
                    runtime=runtime,
                )
            )
        finally:
            stdout_path.unlink(missing_ok=True)
            stderr_path.unlink(missing_ok=True)

    for name in ("transcript.stdout", "transcript.stderr", "raw-transcript"):
        if any(path.name == name for path in roots.output_root.rglob("*")):
            raise LiveEvidenceError("raw_transcript_materialized")

    summary = {
        "schema_version": "redaction-gate-live-summary-v1",
        "created_at": datetime.now(tz=UTC).isoformat(),
        "acpx_path_digest": hashlib.sha256(acpx_path.encode("utf-8")).hexdigest(),
        "acpx_version": acpx_version,
        "identities": identities,
        "artifacts": [record.__dict__ for record in records],
        "raw_transcript_present": False,
        "drive_acp": drive_acp,
    }
    summary_path = roots.output_root / "run-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def run_drive_acp_only(
    *,
    capture_root: Path,
    staging_root: Path,
    quarantine_root: Path,
    output_root: Path,
    workspace_root: Path = REPO_ROOT,
    launch_approval_id: str | None = None,
) -> dict[str, Any]:
    """Capture only the acpx→agent session through the gate (no fixture suite)."""
    workspace = workspace_root.resolve()
    forbidden = (workspace, REPO_ROOT.resolve())
    roots = validate_evidence_roots(
        capture_root=capture_root,
        staging_root=staging_root,
        quarantine_root=quarantine_root,
        output_root=output_root,
        forbidden_persistence_roots=forbidden,
    )
    for root in (
        roots.capture_root,
        roots.staging_root,
        roots.quarantine_root,
        roots.output_root,
    ):
        root.mkdir(parents=True, exist_ok=True)

    acpx_path, acpx_version = resolve_acpx()
    runtime, identities = _build_runtime(
        workspace=workspace,
        roots=roots,
        forbidden=forbidden,
    )
    runtime = replace(
        runtime,
        path_aliases=runtime.path_aliases
        + (PathAliasRule(source_root=str(roots.output_root), alias="<destination>"),),
    )
    identities = {
        **identities,
        "path_alias_count": len(runtime.path_aliases),
        "launch_approval_id_present": bool(launch_approval_id),
    }

    record = _drive_acpx_into_gate(
        acpx_path=acpx_path,
        workspace=workspace,
        roots=roots,
        runtime=runtime,
        launch_approval_id=launch_approval_id,
    )

    for name in ("transcript.stdout", "transcript.stderr", "raw-transcript"):
        if any(path.name == name for path in roots.output_root.rglob("*")):
            raise LiveEvidenceError("raw_transcript_materialized")

    # Merge into existing summary when present so inspect still sees prior fixtures.
    summary_path = roots.output_root / "run-summary.json"
    prior: dict[str, Any] = {}
    if summary_path.is_file():
        try:
            prior = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}
    prior_artifacts = [
        item
        for item in prior.get("artifacts", [])
        if isinstance(item, dict) and item.get("role") != "acpx_session_stream"
    ]
    summary = {
        "schema_version": "redaction-gate-live-summary-v1",
        "created_at": datetime.now(tz=UTC).isoformat(),
        "acpx_path_digest": hashlib.sha256(acpx_path.encode("utf-8")).hexdigest(),
        "acpx_version": acpx_version,
        "identities": identities,
        "artifacts": [*prior_artifacts, record.__dict__],
        "raw_transcript_present": False,
        "drive_acp": True,
        "drive_acp_only": True,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def run_inspect(*, output_root: Path) -> dict[str, Any]:
    if not output_root.is_absolute():
        raise LiveEvidenceError("relative_root_rejected")
    root = output_root.resolve()
    if not root.is_dir():
        raise LiveEvidenceError("output_root_missing")

    artifacts: list[dict[str, Any]] = []
    canary_hits = 0
    canary_obj = json.loads(FIXTURE_CANARIES.read_text(encoding="utf-8"))
    probe_secrets = tuple(
        str(canary_obj[key]) for key in ("unlabeled_api_key",) if key in canary_obj
    )
    for manifest_path in sorted(root.rglob("manifest.json")):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_path = manifest_path.parent / "artifact"
        digest = payload.get("artifact_sha256")
        actual = _sha256_file(artifact_path) if artifact_path.is_file() else None
        rendered = json.dumps(payload, sort_keys=True)
        if canary_obj.get("unlabeled_api_key") in rendered:
            canary_hits += 1
        try:
            sanitize_for_persistence(
                rendered,
                known_secrets=probe_secrets,
                known_pii=(),
            )
            if not manifest_canary_scan(
                rendered,
                known_secrets=probe_secrets,
                known_pii=(),
            ):
                canary_hits += 1
        except Exception:
            canary_hits += 1
        if artifact_path.is_file():
            body = artifact_path.read_bytes()
            token = str(canary_obj.get("unlabeled_api_key", "")).encode("utf-8")
            if token and token in body:
                canary_hits += 1
        artifacts.append(
            {
                "role_dir": manifest_path.parent.name,
                "artifact_sha256": digest,
                "digest_match": actual == digest if digest and actual else False,
                "disposition": payload.get("disposition"),
                "artifact_locator": payload.get("artifact_locator"),
                "dropped_tail_bytes": payload.get("dropped_tail_bytes"),
                "absolute_source_emitted": False,
            }
        )

    summary_path = root / "run-summary.json"
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    )
    report = {
        "artifact_count": len(artifacts),
        "canary_hits": canary_hits,
        "artifacts": artifacts,
        "acpx_version": summary.get("acpx_version"),
        "screenshot_states": [
            item
            for item in summary.get("artifacts", [])
            if item.get("kind") == "screenshot"
        ],
        "raw_transcript_present": any(
            path.name in {"transcript.stdout", "transcript.stderr", "raw-transcript"}
            for path in root.rglob("*")
        ),
    }
    if report["canary_hits"] != 0:
        raise LiveEvidenceError("inspect_canary_hit")
    if report["raw_transcript_present"]:
        raise LiveEvidenceError("raw_transcript_materialized")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "verify":
            summary = run_verify(
                capture_root=args.capture_root,
                staging_root=args.staging_root,
                quarantine_root=args.quarantine_root,
                output_root=args.output_root,
                workspace_root=args.workspace_root,
                screenshot_approval_path=args.screenshot_approval,
                drive_acp=bool(args.drive_acp),
                launch_approval_id=args.launch_approval_id,
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "acpx_version": summary["acpx_version"],
                        "artifact_count": len(summary["artifacts"]),
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "drive-acp":
            summary = run_drive_acp_only(
                capture_root=args.capture_root,
                staging_root=args.staging_root,
                quarantine_root=args.quarantine_root,
                output_root=args.output_root,
                workspace_root=args.workspace_root,
                launch_approval_id=args.launch_approval_id,
            )
            stream = next(
                (
                    item
                    for item in summary["artifacts"]
                    if item.get("role") == "acpx_session_stream"
                ),
                None,
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "acpx_version": summary["acpx_version"],
                        "acpx_session_stream": stream,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "inspect":
            report = run_inspect(output_root=args.output_root)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "artifact_count": report["artifact_count"],
                        "canary_hits": report["canary_hits"],
                        "acpx_version": report["acpx_version"],
                        "raw_transcript_present": report["raw_transcript_present"],
                    },
                    sort_keys=True,
                )
            )
            for item in report["artifacts"]:
                print(
                    json.dumps(
                        {
                            "role_dir": item["role_dir"],
                            "artifact_sha256": item["artifact_sha256"],
                            "digest_match": item["digest_match"],
                            "disposition": item["disposition"],
                        },
                        sort_keys=True,
                    )
                )
            for shot in report["screenshot_states"]:
                print(json.dumps({"screenshot": shot}, sort_keys=True))
            return 0
    except LiveEvidenceError as exc:
        print(json.dumps({"ok": False, "error": exc.code}), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — surface type + gate code when present
        payload: dict[str, object] = {"ok": False, "error": type(exc).__name__}
        code = getattr(exc, "code", None)
        detail = getattr(exc, "detail", None)
        if isinstance(code, str):
            payload["code"] = code
        if isinstance(detail, str):
            # Detail is policy text only for LaunchGateError; still avoid dumping values.
            payload["detail"] = detail
        print(json.dumps(payload), file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
