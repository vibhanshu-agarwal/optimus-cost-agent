"""HMAC-protected keyring approvals and single-use consumption.

Plan 9.96, Task 3: Durable and one-shot records have fixed schema, size,
integrity, workspace binding, expiry/revocation, and concurrency semantics.

Approval records contain no literal secret/URI userinfo. Secret fields use
domain-separated HMAC-SHA-256 fingerprints. The record_hmac binds all fields
to the approval-store HMAC key.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from optimus.acp.trusted_paths import WorkspaceIdentity

# --- Constants ---

APPROVAL_SCHEMA_VERSION = 1
LAUNCH_POLICY_COMPATIBILITY = "P9.96-v1"
MAX_APPROVAL_RECORD_BYTES = 1800
ONE_SHOT_TTL_SECONDS = 300
DIAGNOSTIC_TTL_SECONDS = 900

_KEYRING_SERVICE = "optimus-cost-agent-approvals"
_HMAC_KEY_ENTRY = "hmac_integrity_key"
_HANDLE_DOMAIN = b"p996-one-shot-handle-v1"
_FINGERPRINT_DOMAIN = b"p996-secret-fingerprint-v1"
_RECORD_HMAC_DOMAIN = b"p996-record-hmac-v1"


# --- Error type ---


class ApprovalError(ValueError):
    """Raised when an approval operation fails.

    Not a frozen dataclass because Python's exception machinery needs to set
    __traceback__ during propagation, which frozen dataclasses prevent.
    """

    def __init__(self, *, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)

    def __str__(self) -> str:
        if self.detail:
            return f"{self.code}: {self.detail}"
        return self.code


# --- Data classes ---


@dataclass(frozen=True)
class ApprovalRecord:
    """An HMAC-protected approval record bound to a workspace identity."""

    schema_version: int
    policy_compatibility: str
    approval_id: str
    mode: Literal["one-shot", "durable"]
    workspace_identity: WorkspaceIdentity
    created_at: datetime
    expires_at: datetime | None
    creator_identity: str
    ceremony_cli_version: str
    security_literals: Mapping[str, str]
    secret_fingerprints: Mapping[str, str]
    monotonic_grants: Mapping[str, str]
    model_observation: str | None
    registry_version: str
    security_snapshot_digest: str
    consumed: bool
    record_hmac: str


@dataclass(frozen=True)
class DiagnosticGrant:
    """A short-lived grant for elevated diagnostic output."""

    grant_id: str
    workspace_digest: str
    approval_id: str
    launch_session_id: str
    expires_at: datetime
    record_hmac: str


# --- Helper functions ---


def _package_version() -> str:
    try:
        return version("optimus-cost-agent")
    except PackageNotFoundError:
        return "dev"


def _creator_identity() -> str:
    """Identify who created this approval (username@hostname, no secrets)."""
    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown"
    return user


def compute_security_snapshot_digest(
    *,
    security_literals: Mapping[str, str],
    secret_fingerprints: Mapping[str, str],
    monotonic_grants: Mapping[str, str],
    workspace_digest: str,
    registry_version: str,
) -> str:
    """Compute a digest over all security-relevant content.

    This is the SINGLE shared implementation used by both approval-record
    construction (build_approval_record) and launch-candidate resolution
    (launch_gate.resolve_launch_candidate). Both sides MUST call this exact
    function with the same inputs, or the resulting digests can never match
    and authorization becomes permanently impossible.
    """
    hasher = hashlib.sha256()
    hasher.update(b"security-snapshot-v1\x00")
    hasher.update(workspace_digest.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(registry_version.encode("utf-8"))
    hasher.update(b"\x00")
    for key in sorted(security_literals):
        hasher.update(key.encode("utf-8"))
        hasher.update(b"=")
        hasher.update(security_literals[key].encode("utf-8"))
        hasher.update(b"\x00")
    for key in sorted(secret_fingerprints):
        hasher.update(key.encode("utf-8"))
        hasher.update(b"=")
        hasher.update(secret_fingerprints[key].encode("utf-8"))
        hasher.update(b"\x00")
    for key in sorted(monotonic_grants):
        hasher.update(key.encode("utf-8"))
        hasher.update(b"=")
        hasher.update(monotonic_grants[key].encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


# --- Public API ---


def compute_secret_fingerprint(
    value: str,
    *,
    field_name: str,
    hmac_key: bytes,
) -> str:
    """Compute a domain-separated HMAC-SHA-256 fingerprint for a secret value.

    The fingerprint is bound to the field name (domain separation) so the same
    raw value under different fields produces different fingerprints.
    """
    msg = _FINGERPRINT_DOMAIN + b"\x00" + field_name.encode("utf-8") + b"\x00" + value.encode("utf-8")
    return hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()


def derive_one_shot_handle(nonce: bytes) -> str:
    """Derive a one-shot handle from a 32-byte nonce.

    Returns 'p996_' + unpadded base64url of SHA-256(domain || nonce).
    The writer never prints this handle.
    """
    digest = hashlib.sha256(_HANDLE_DOMAIN + b"\x00" + nonce).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"p996_{encoded}"


def compute_record_hmac(record: ApprovalRecord, *, hmac_key: bytes) -> str:
    """Compute HMAC-SHA-256 over all approval record fields (except record_hmac itself)."""
    # Canonical field serialization for HMAC input.
    parts: list[bytes] = [
        _RECORD_HMAC_DOMAIN,
        b"\x00",
        str(record.schema_version).encode(),
        b"\x00",
        record.policy_compatibility.encode(),
        b"\x00",
        record.approval_id.encode(),
        b"\x00",
        record.mode.encode(),
        b"\x00",
        record.workspace_identity.digest.encode(),
        b"\x00",
        record.created_at.isoformat().encode(),
        b"\x00",
        (record.expires_at.isoformat() if record.expires_at else "").encode(),
        b"\x00",
        record.creator_identity.encode(),
        b"\x00",
        record.ceremony_cli_version.encode(),
        b"\x00",
        record.registry_version.encode(),
        b"\x00",
        record.security_snapshot_digest.encode(),
        b"\x00",
    ]
    # Include security literals in sorted order.
    for key in sorted(record.security_literals):
        parts.append(key.encode())
        parts.append(b"=")
        parts.append(record.security_literals[key].encode())
        parts.append(b"\x00")
    # Include secret fingerprints in sorted order.
    for key in sorted(record.secret_fingerprints):
        parts.append(key.encode())
        parts.append(b"=")
        parts.append(record.secret_fingerprints[key].encode())
        parts.append(b"\x00")
    # Include monotonic grants in sorted order.
    for key in sorted(record.monotonic_grants):
        parts.append(key.encode())
        parts.append(b"=")
        parts.append(record.monotonic_grants[key].encode())
        parts.append(b"\x00")
    # Model observation.
    parts.append((record.model_observation or "").encode())

    msg = b"".join(parts)
    return hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()


def build_approval_record(
    *,
    mode: str,
    workspace_identity: WorkspaceIdentity,
    security_literals: Mapping[str, str],
    secret_fingerprints: Mapping[str, str],
    monotonic_grants: Mapping[str, str],
    model_observation: str | None,
    hmac_key: bytes,
    override_created_at: datetime | None = None,
) -> ApprovalRecord:
    """Build a complete approval record with HMAC integrity."""
    now = override_created_at or datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=ONE_SHOT_TTL_SECONDS)) if mode == "one-shot" else None

    registry_version = LAUNCH_POLICY_COMPATIBILITY
    snapshot_digest = compute_security_snapshot_digest(
        security_literals=security_literals,
        secret_fingerprints=secret_fingerprints,
        monotonic_grants=monotonic_grants,
        workspace_digest=workspace_identity.digest,
        registry_version=registry_version,
    )

    # Build record without HMAC first, then compute and attach.
    record = ApprovalRecord(
        schema_version=APPROVAL_SCHEMA_VERSION,
        policy_compatibility=LAUNCH_POLICY_COMPATIBILITY,
        approval_id=f"appr_{secrets.token_hex(12)}",
        mode=mode,
        workspace_identity=workspace_identity,
        created_at=now,
        expires_at=expires_at,
        creator_identity=_creator_identity(),
        ceremony_cli_version=_package_version(),
        security_literals=dict(security_literals),
        secret_fingerprints=dict(secret_fingerprints),
        monotonic_grants=dict(monotonic_grants),
        model_observation=model_observation,
        registry_version=registry_version,
        security_snapshot_digest=snapshot_digest,
        consumed=False,
        record_hmac="",  # Placeholder.
    )
    record_hmac = compute_record_hmac(record, hmac_key=hmac_key)
    return replace(record, record_hmac=record_hmac)


def serialize_approval_record(record: ApprovalRecord) -> str:
    """Serialize an approval record to canonical compact JSON.

    Sorted keys, no extra whitespace. The result must fit within
    MAX_APPROVAL_RECORD_BYTES UTF-8 bytes.
    """
    data = {
        "approval_id": record.approval_id,
        "ceremony_cli_version": record.ceremony_cli_version,
        "consumed": record.consumed,
        "created_at": record.created_at.isoformat(),
        "creator_identity": record.creator_identity,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "mode": record.mode,
        "model_observation": record.model_observation,
        "monotonic_grants": dict(record.monotonic_grants),
        "policy_compatibility": record.policy_compatibility,
        "record_hmac": record.record_hmac,
        "registry_version": record.registry_version,
        "schema_version": record.schema_version,
        "secret_fingerprints": dict(record.secret_fingerprints),
        "security_literals": dict(record.security_literals),
        "security_snapshot_digest": record.security_snapshot_digest,
        "workspace_digest": record.workspace_identity.digest,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _deserialize_approval_record(raw: str, *, hmac_key: bytes) -> ApprovalRecord:
    """Deserialize and verify an approval record from JSON."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ApprovalError(code="RECORD_CORRUPT", detail="invalid JSON") from exc

    try:
        workspace_identity = WorkspaceIdentity(
            canonical_path="",  # Not stored in serialized form for size.
            device=0,
            inode=0,
            repository_root=None,
            git_common_dir=None,
            digest=data["workspace_digest"],
        )
        created_at = datetime.fromisoformat(data["created_at"])
        expires_at = datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None

        record = ApprovalRecord(
            schema_version=data["schema_version"],
            policy_compatibility=data["policy_compatibility"],
            approval_id=data["approval_id"],
            mode=data["mode"],
            workspace_identity=workspace_identity,
            created_at=created_at,
            expires_at=expires_at,
            creator_identity=data["creator_identity"],
            ceremony_cli_version=data["ceremony_cli_version"],
            security_literals=data.get("security_literals", {}),
            secret_fingerprints=data.get("secret_fingerprints", {}),
            monotonic_grants=data.get("monotonic_grants", {}),
            model_observation=data.get("model_observation"),
            registry_version=data["registry_version"],
            security_snapshot_digest=data["security_snapshot_digest"],
            consumed=data.get("consumed", False),
            record_hmac=data["record_hmac"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ApprovalError(code="RECORD_CORRUPT", detail="missing or invalid fields") from exc

    # Verify HMAC integrity.
    expected_hmac = compute_record_hmac(record, hmac_key=hmac_key)
    if not hmac.compare_digest(record.record_hmac, expected_hmac):
        raise ApprovalError(code="INTEGRITY_FAILURE", detail="record HMAC mismatch")

    return record


# --- Keyring Approval Store ---


class KeyringApprovalStore:
    """Manages approval records in the OS keyring with HMAC integrity.

    Uses a dedicated service namespace distinct from provider credentials.
    """

    _service_name: str = _KEYRING_SERVICE

    def __init__(
        self,
        *,
        keyring_backend: Any,
        runtime_root: Path,
        hmac_key: bytes | None = None,
    ) -> None:
        self._keyring = keyring_backend
        self._runtime_root = runtime_root
        self._hmac_key = hmac_key or self._ensure_hmac_key()

    def _ensure_hmac_key(self) -> bytes:
        """Load or create the HMAC integrity key."""
        raw = self._keyring.get_password(self._service_name, _HMAC_KEY_ENTRY)
        if raw:
            return base64.urlsafe_b64decode(raw)
        # Generate a new 32-byte key.
        key = secrets.token_bytes(32)
        encoded = base64.urlsafe_b64encode(key).decode("ascii")
        self._keyring.set_password(self._service_name, _HMAC_KEY_ENTRY, encoded)
        return key

    def read_durable(self, workspace_digest: str) -> ApprovalRecord | None:
        """Read a durable approval record for the given workspace digest."""
        entry_key = f"durable:{workspace_digest}"
        raw = self._keyring.get_password(self._service_name, entry_key)
        if raw is None:
            return None
        record = _deserialize_approval_record(raw, hmac_key=self._hmac_key)
        if record.policy_compatibility != LAUNCH_POLICY_COMPATIBILITY:
            raise ApprovalError(code="POLICY_MISMATCH")
        return record

    def write_durable(self, record: ApprovalRecord) -> None:
        """Write a durable approval record."""
        serialized = serialize_approval_record(record)
        byte_len = len(serialized.encode("utf-8"))
        if byte_len > MAX_APPROVAL_RECORD_BYTES:
            raise ApprovalError(
                code="RECORD_TOO_LARGE",
                detail=f"{byte_len} bytes exceeds {MAX_APPROVAL_RECORD_BYTES} limit",
            )
        entry_key = f"durable:{record.workspace_identity.digest}"
        self._keyring.set_password(self._service_name, entry_key, serialized)

    def write_one_shot(self, record: ApprovalRecord, nonce: bytes) -> str:
        """Write a one-shot approval record and return the handle."""
        handle = derive_one_shot_handle(nonce)
        serialized = serialize_approval_record(record)
        byte_len = len(serialized.encode("utf-8"))
        if byte_len > MAX_APPROVAL_RECORD_BYTES:
            raise ApprovalError(
                code="RECORD_TOO_LARGE",
                detail=f"{byte_len} bytes exceeds {MAX_APPROVAL_RECORD_BYTES} limit",
            )
        entry_key = f"oneshot:{handle}"
        self._keyring.set_password(self._service_name, entry_key, serialized)
        return handle

    def _workspace_lock_path(self, workspace_digest: str) -> Path:
        """Return the lock file path for a workspace-digest under runtime_root."""
        lock_dir = self._runtime_root / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        return lock_dir / f"{workspace_digest}.lock"

    def consume_one_shot(self, handle: str, expected_snapshot_digest: str) -> ApprovalRecord:
        """Consume a one-shot record: lock, verify, delete, return.

        The entire read-verify-delete-confirm sequence is wrapped in a
        cross-platform file lock (msvcrt.locking on Windows, fcntl.flock on
        POSIX) per Plan 9.96 Step 3. Under the lock: verify handle/HMAC/
        snapshot/expiry, delete the record, confirm deletion, then return it.
        Crash or deletion failure leaves startup unauthorized.
        """
        import sys

        entry_key = f"oneshot:{handle}"

        # Derive workspace digest from the stored record for locking.
        # We need to read first to know which workspace to lock, but the
        # critical section re-reads after acquiring the lock.
        raw_peek = self._keyring.get_password(self._service_name, entry_key)
        if raw_peek is None:
            raise ApprovalError(code="ONE_SHOT_NOT_FOUND")

        # Parse minimally to get workspace_digest for the lock path.
        try:
            peek_data = json.loads(raw_peek)
            ws_digest = peek_data["workspace_digest"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise ApprovalError(code="RECORD_CORRUPT", detail="cannot determine workspace") from exc

        lock_path = self._workspace_lock_path(ws_digest)

        # Acquire cross-platform exclusive lock.
        lock_fd = open(lock_path, "w")  # noqa: SIM115
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise ApprovalError(code="LOCK_CONTENTION", detail="another consumer holds the lock") from exc
            else:
                import fcntl

                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise ApprovalError(code="LOCK_CONTENTION", detail="another consumer holds the lock") from exc

            # Under lock: re-read the record (TOCTOU protection).
            raw = self._keyring.get_password(self._service_name, entry_key)
            if raw is None:
                raise ApprovalError(code="ONE_SHOT_NOT_FOUND")

            record = _deserialize_approval_record(raw, hmac_key=self._hmac_key)

            # Check policy compatibility.
            if record.policy_compatibility != LAUNCH_POLICY_COMPATIBILITY:
                raise ApprovalError(code="POLICY_MISMATCH")

            # Check expiry.
            if record.expires_at and datetime.now(timezone.utc) > record.expires_at:
                self._keyring.delete_password(self._service_name, entry_key)
                raise ApprovalError(code="APPROVAL_EXPIRED")

            # Check snapshot digest.
            if record.security_snapshot_digest != expected_snapshot_digest:
                raise ApprovalError(code="SNAPSHOT_MISMATCH")

            # Delete before returning (delete-before-use semantics).
            self._keyring.delete_password(self._service_name, entry_key)

            # Confirm deletion — if the record still exists, fail.
            if self._keyring.get_password(self._service_name, entry_key) is not None:
                raise ApprovalError(code="DELETION_FAILED")

            return record
        finally:
            # Release lock and close.
            if sys.platform == "win32":
                import msvcrt

                try:
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            lock_fd.close()

    def write_diagnostic_grant(self, grant: DiagnosticGrant) -> None:
        """Write a diagnostic grant."""
        data = {
            "grant_id": grant.grant_id,
            "workspace_digest": grant.workspace_digest,
            "approval_id": grant.approval_id,
            "launch_session_id": grant.launch_session_id,
            "expires_at": grant.expires_at.isoformat(),
            "record_hmac": grant.record_hmac,
        }
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        entry_key = f"grant:{grant.grant_id}"
        self._keyring.set_password(self._service_name, entry_key, serialized)

    def consume_diagnostic_grant(self, grant_id: str, launch_session_id: str) -> DiagnosticGrant:
        """Consume a diagnostic grant: verify session, delete, return."""
        entry_key = f"grant:{grant_id}"
        raw = self._keyring.get_password(self._service_name, entry_key)
        if raw is None:
            raise ApprovalError(code="GRANT_NOT_FOUND")

        try:
            data = json.loads(raw)
            grant = DiagnosticGrant(
                grant_id=data["grant_id"],
                workspace_digest=data["workspace_digest"],
                approval_id=data["approval_id"],
                launch_session_id=data["launch_session_id"],
                expires_at=datetime.fromisoformat(data["expires_at"]),
                record_hmac=data["record_hmac"],
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise ApprovalError(code="GRANT_CORRUPT") from exc

        if grant.launch_session_id != launch_session_id:
            raise ApprovalError(code="GRANT_SESSION_MISMATCH")

        if datetime.now(timezone.utc) > grant.expires_at:
            self._keyring.delete_password(self._service_name, entry_key)
            raise ApprovalError(code="GRANT_EXPIRED")

        # Delete before returning.
        self._keyring.delete_password(self._service_name, entry_key)
        return grant

    def revoke_workspace(self, workspace_digest: str) -> None:
        """Revoke a durable approval for a workspace."""
        entry_key = f"durable:{workspace_digest}"
        self._keyring.delete_password(self._service_name, entry_key)

    def rotate_hmac_key(self) -> None:
        """Rotate the HMAC integrity key.

        WARNING: This invalidates all existing approval records.
        """
        key = secrets.token_bytes(32)
        encoded = base64.urlsafe_b64encode(key).decode("ascii")
        self._keyring.set_password(self._service_name, _HMAC_KEY_ENTRY, encoded)
        self._hmac_key = key
