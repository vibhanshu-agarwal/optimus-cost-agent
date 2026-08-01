"""Redact-time durable reauthorization and public gate composition.

Host-only. Imports Optimus launch/trusted-path APIs and the public redaction
gate surface. Never persists AuthorizedLaunch, host context, or credential values.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from evidence_handoff.collector.bundles import (
    load_provisional_result,
    load_verified_raw_bundle,
    validate_custody_roots,
)
from evidence_handoff.collector.models import ClassificationResult, RunContext
from evidence_handoff.redaction.gate import run_redaction_gate
from evidence_handoff.redaction.models import (
    ArtifactKind,
    Disposition,
    RedactionGateResult,
    RedactionRequest,
    RedactionRuntimeInputs,
    ScreenshotApproval,
)
from optimus.acp.evidence_redaction_adapter import (
    EvidenceRedactionAdapterError,
    EvidenceRedactionHostContext,
    build_redaction_runtime_inputs,
)
from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.launch_gate import AuthorizedLaunch, LaunchGateError, authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_workspace_identity

from .common import HostError, require_absolute_path

_ROLE_TO_KIND: dict[str, ArtifactKind] = {
    "screenshot": ArtifactKind.SCREENSHOT,
    "acp_debug_suffix": ArtifactKind.ACP_DEBUG_TRACE,
    "zed_process_dump": ArtifactKind.PROCESS_DUMP,
    "zed_panic_json": ArtifactKind.JSON,
    "zed_log": ArtifactKind.TEXT,
}

_LAUNCH_ERROR_MAP = {
    "SNAPSHOT_MISMATCH": "REDACTION_AUTHORIZATION_SNAPSHOT_MISMATCH",
    "NO_APPROVAL": "REDACTION_AUTHORIZATION_NO_DURABLE_APPROVAL",
}

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


def map_artifact_role(role: str) -> ArtifactKind:
    kind = _ROLE_TO_KIND.get(role)
    if kind is None:
        raise HostError("unknown_artifact_role")
    return kind


def exhaustive_role_kind_pairs() -> tuple[tuple[str, ArtifactKind], ...]:
    return tuple(sorted(_ROLE_TO_KIND.items(), key=lambda item: item[0]))


def load_screenshot_approval(path: Path) -> ScreenshotApproval:
    absolute = require_absolute_path(path)
    if not absolute.is_file():
        raise HostError("screenshot_approval_missing")
    raw = json.loads(absolute.read_text(encoding="utf-8"))
    approved_at = datetime.fromisoformat(str(raw["approved_at"]))
    return ScreenshotApproval(
        staged_sha256=str(raw["staged_sha256"]),
        approver_id=str(raw["approver_id"]),
        collector_id=str(raw["collector_id"]),
        approved_at=approved_at,
        rationale=str(raw["rationale"]),
    )


def resolve_operator_profile_root() -> Path:
    if sys.platform == "win32":
        return _windows_profile_root()
    import pwd

    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    except Exception:
        raise HostError("operator_profile_unavailable") from None


def resolve_operator_identity_values() -> tuple[str, ...]:
    values: list[str] = []
    if sys.platform == "win32":
        user = _windows_account_name()
        host = _windows_host_name()
        upn = _windows_user_principal_name()
        if user:
            values.append(user)
        if upn and upn not in values:
            values.append(upn)
        if host:
            values.append(host)
    else:
        import pwd
        import socket

        try:
            values.append(pwd.getpwuid(os.getuid()).pw_name)
        except Exception:
            raise HostError("operator_identity_unavailable") from None
        values.append(socket.gethostname())
    cleaned = tuple(item for item in values if item)
    if not cleaned:
        raise HostError("operator_identity_unavailable")
    return cleaned


def path_has_cloud_sync_segment(path: Path) -> bool:
    parts = [part.casefold() for part in path.resolve().parts]
    for part in parts:
        if part in CLOUD_SYNC_SEGMENTS:
            return True
    for index in range(len(parts) - 1):
        joined = f"{parts[index]} {parts[index + 1]}"
        if joined in CLOUD_SYNC_SEGMENTS:
            return True
    return False


def reject_cloud_sync_roots(roots: Sequence[Path]) -> None:
    for root in roots:
        absolute = require_absolute_path(Path(root)).resolve()
        if path_has_cloud_sync_segment(absolute):
            raise HostError("cloud_sync_path_segment")


def validate_redaction_custody_roots(
    *,
    workspace_root: Path,
    capture_root: Path,
    staging_root: Path,
    quarantine_root: Path,
    sanitized_root: Path,
    user_data_roots: Sequence[Path],
    forbidden_roots: Sequence[Path],
) -> None:
    workspace = require_absolute_path(workspace_root).resolve()
    capture = require_absolute_path(capture_root).resolve()
    staging = require_absolute_path(staging_root).resolve()
    quarantine = require_absolute_path(quarantine_root).resolve()
    sanitized = require_absolute_path(sanitized_root).resolve()
    users = tuple(require_absolute_path(Path(path)).resolve() for path in user_data_roots)
    forbidden = (workspace, *(require_absolute_path(Path(path)).resolve() for path in forbidden_roots))
    reject_cloud_sync_roots((capture, staging, quarantine, sanitized, *users, *forbidden))
    try:
        validate_custody_roots(
            capture_root=capture,
            other_roots=(staging, quarantine, sanitized, *users),
            forbidden_roots=forbidden,
        )
    except ValueError as exc:
        code = exc.args[0] if exc.args and isinstance(exc.args[0], str) else "path_overlap"
        raise HostError(code) from None


def authorize_redaction_launch(
    *,
    workspace_root: Path,
    environ: Mapping[str, str] | None = None,
    keyring_backend: object | None = None,
    credential_keyring_backend: object | None = None,
) -> AuthorizedLaunch:
    """Capture env once, resolve current candidate, authorize durable approval."""
    workspace = require_absolute_path(workspace_root).resolve()
    if not workspace.is_dir():
        raise HostError("workspace_missing")
    env_map = dict(os.environ if environ is None else environ)
    snapshot = LaunchEnvironmentSnapshot.capture(env_map)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    import keyring as keyring_mod

    approval_backend = keyring_backend if keyring_backend is not None else keyring_mod
    credential_backend = (
        credential_keyring_backend if credential_keyring_backend is not None else approval_backend
    )
    store = KeyringApprovalStore(keyring_backend=approval_backend, runtime_root=paths.runtime_root)
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=resolve_workspace_identity(workspace),
        operator_paths=paths,
        hmac_key=store.hmac_key,
        credential_keyring_backend=credential_backend,
    )
    try:
        return authorize_launch(
            candidate=candidate,
            store=store,
            approval_id=None,
            launch_session_id=f"evidence-redact-{secrets.token_hex(12)}",
        )
    except LaunchGateError as exc:
        mapped = _LAUNCH_ERROR_MAP.get(exc.code)
        if mapped is None:
            raise HostError("redaction_authorization_failed") from None
        raise HostError(mapped) from None


def build_redaction_host_context(
    *,
    authorized_launch: AuthorizedLaunch,
    workspace_root: Path,
    user_data_roots: Sequence[Path],
    temporary_capture_root: Path,
    staging_root: Path,
    quarantine_root: Path,
    operator_forbidden_roots: Sequence[Path],
    operator_profile_root: Path | None = None,
    operator_identity_values: Sequence[str] | None = None,
) -> EvidenceRedactionHostContext:
    workspace = require_absolute_path(workspace_root).resolve()
    profile = (
        require_absolute_path(operator_profile_root).resolve()
        if operator_profile_root is not None
        else resolve_operator_profile_root()
    )
    identities = (
        tuple(operator_identity_values)
        if operator_identity_values is not None
        else resolve_operator_identity_values()
    )
    if not identities:
        raise HostError("operator_identity_unavailable")
    user_roots = tuple(require_absolute_path(Path(path)).resolve() for path in user_data_roots)
    if not user_roots:
        raise HostError("user_data_root_required")
    capture = require_absolute_path(temporary_capture_root).resolve()
    staging = require_absolute_path(staging_root).resolve()
    quarantine = require_absolute_path(quarantine_root).resolve()
    forbidden = [workspace]
    for path in operator_forbidden_roots:
        forbidden.append(require_absolute_path(Path(path)).resolve())
    seen: set[Path] = set()
    forbidden_tuple: list[Path] = []
    for path in forbidden:
        if path in seen:
            continue
        seen.add(path)
        forbidden_tuple.append(path)
    return EvidenceRedactionHostContext(
        authorized_launch=authorized_launch,
        operator_profile_root=profile,
        user_data_roots=user_roots,
        temporary_capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        operator_identity_values=tuple(identities),
        forbidden_persistence_roots=tuple(forbidden_tuple),
    )


def convert_host_context(context: EvidenceRedactionHostContext) -> RedactionRuntimeInputs:
    try:
        return build_redaction_runtime_inputs(context)
    except EvidenceRedactionAdapterError as exc:
        raise HostError(exc.code) from None


def redact_raw_bundle(
    *,
    context: RunContext,
    destination_root: Path,
    runtime: RedactionRuntimeInputs,
    screenshot_approval: ScreenshotApproval | None,
) -> tuple[tuple[RedactionGateResult, ...], ClassificationResult]:
    """Run the public gate over every captured artifact; preserve provisional outcome."""
    provisional_path = context.capture_root / context.run_id / "provisional-result.json"
    provisional = load_provisional_result(context=context, path=provisional_path)
    bundle_path = context.capture_root / context.run_id / "raw-bundle.json"
    batches = load_verified_raw_bundle(context=context, bundle_path=bundle_path)
    results: list[RedactionGateResult] = []
    dest = require_absolute_path(destination_root).resolve()
    for batch in batches:
        for artifact in batch.artifacts:
            kind = map_artifact_role(artifact.role)
            source = (context.capture_root / context.run_id / artifact.relative_locator).resolve()
            approval = screenshot_approval if kind is ArtifactKind.SCREENSHOT else None
            try:
                RedactionRequest(
                    source_path=source,
                    destination_root=dest,
                    artifact_kind=kind,
                    artifact_role=artifact.role,
                    runtime=runtime,
                    screenshot_approval=approval,
                )
            except ValueError as exc:
                code = (
                    exc.args[0]
                    if exc.args and isinstance(exc.args[0], str)
                    else "redaction_request_invalid"
                )
                raise HostError(code) from None
            result = run_redaction_gate(
                source_path=source,
                destination_root=dest,
                artifact_kind=kind,
                artifact_role=artifact.role,
                runtime=runtime,
                screenshot_approval=approval,
            )
            if kind is ArtifactKind.PROCESS_DUMP and result.disposition is Disposition.PROMOTED:
                raise HostError("dump_promotion_forbidden")
            results.append(result)
    again = load_provisional_result(context=context, path=provisional_path)
    if again.outcome != provisional.outcome or again.raw_bundle_sha256 != provisional.raw_bundle_sha256:
        raise HostError("provisional_outcome_mutated")
    return tuple(results), provisional


def report_eligible(results: Sequence[RedactionGateResult]) -> bool:
    if not results:
        return False
    for result in results:
        if result.disposition is not Disposition.PROMOTED:
            return False
        if result.artifact_locator is None:
            return False
    return True


def _windows_profile_root() -> Path:
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    # FOLDERID_Profile = {5E6C858F-0E22-4760-9AFE-EA3317B67173}
    folder = GUID(
        0x5E6C858F,
        0x0E22,
        0x4760,
        (ctypes.c_ubyte * 8)(0x9A, 0xFE, 0xEA, 0x33, 0x17, 0xB6, 0x71, 0x73),
    )
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    path_ptr = ctypes.c_wchar_p()
    hr = shell32.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(path_ptr))
    if hr != 0 or not path_ptr.value:
        raise HostError("operator_profile_unavailable")
    path = Path(path_ptr.value).resolve()
    ole32.CoTaskMemFree(path_ptr)
    return path


def _windows_account_name() -> str:
    import ctypes
    from ctypes import wintypes

    size = wintypes.DWORD(256)
    buf = ctypes.create_unicode_buffer(256)
    if ctypes.windll.advapi32.GetUserNameW(buf, ctypes.byref(size)):
        return buf.value.strip()
    return ""


def _windows_host_name() -> str:
    import ctypes
    from ctypes import wintypes

    size = wintypes.DWORD(256)
    buf = ctypes.create_unicode_buffer(256)
    if ctypes.windll.kernel32.GetComputerNameW(buf, ctypes.byref(size)):
        return buf.value.strip()
    return ""


def _windows_user_principal_name() -> str:
    import ctypes
    from ctypes import wintypes

    # EXTENDED_NAME_FORMAT.NameUserPrincipal = 8
    name_user_principal = 8
    size = wintypes.DWORD(0)
    secur32 = ctypes.windll.secur32
    secur32.GetUserNameExW(name_user_principal, None, ctypes.byref(size))
    if size.value <= 1:
        return ""
    buf = ctypes.create_unicode_buffer(size.value)
    if secur32.GetUserNameExW(name_user_principal, buf, ctypes.byref(size)):
        return buf.value.strip()
    return ""
