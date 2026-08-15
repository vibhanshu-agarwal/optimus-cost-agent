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
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from optimus.acp.trusted_paths import WorkspaceIdentity

# --- Constants ---

APPROVAL_SCHEMA_VERSION = 2
LEGACY_APPROVAL_SCHEMA_VERSION = 1
LAUNCH_POLICY_COMPATIBILITY = "P9.99-v1"
MAX_APPROVAL_RECORD_BYTES = 1800
ONE_SHOT_TTL_SECONDS = 300
DIAGNOSTIC_TTL_SECONDS = 900

_KEYRING_SERVICE = "optimus-cost-agent-approvals"
_HMAC_KEY_ENTRY = "hmac_integrity_key"
_HANDLE_DOMAIN = b"p996-one-shot-handle-v1"
_FINGERPRINT_DOMAIN = b"p996-secret-fingerprint-v1"
_RECORD_HMAC_DOMAIN = b"p996-record-hmac-v1"
_GRANT_HMAC_DOMAIN = b"p996-diagnostic-grant-hmac-v1"


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
class ApprovalMigrationProvenance:
    """Authenticated origin of a promoted durable record. Not fresh assurance."""

    disposition: Literal["legacy_v2_to_v3"]
    source_identity_format_version: Literal[2]
    source_workspace_digest: str
    inherited_trust: Literal["pre_migration_assurance_not_upgraded"]


@dataclass(frozen=True)
class ApprovalRecord:
    """An HMAC-protected approval record bound to a workspace digest."""

    schema_version: int
    policy_compatibility: str
    approval_id: str
    mode: Literal["one-shot", "durable"]
    identity_format_version: int
    workspace_digest: str
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
    migration_provenance: ApprovalMigrationProvenance | None = None


@dataclass(frozen=True)
class DurableApprovalLookup:
    """Result of ordered v3-then-legacy durable lookup."""

    record: ApprovalRecord | None
    state: Literal["current", "migrated", "legacy_reapproval_required"]


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
    workspace_digest: str,
    registry_version: str,
) -> str:
    """Compute a digest over all security-relevant content.

    This is the SINGLE shared implementation used by both approval-record
    construction (build_approval_record) and launch-candidate resolution
    (launch_gate.resolve_launch_candidate). Both sides MUST call this exact
    function with the same inputs, or the resulting digests can never match
    and authorization becomes permanently impossible.

    Plan 9.96, Task 5 Batch 3 (Step 5 monotonic pinning): monotonic_grants is
    deliberately NOT hashed into this digest. An earlier version folded
    monotonic values in, which made ANY change to them — including a pure
    tightening, which Global Constraint 12 explicitly allows without
    approval — trigger SNAPSHOT_MISMATCH and force re-approval. Digest
    equality can only express "changed or unchanged," never "looser or
    tighter," so it cannot correctly gate a monotonic comparison.
    authorize_launch() enforces the actual tighten-or-equal-is-free /
    loosen-requires-exact-approval comparison directly against
    ApprovalRecord.monotonic_grants, which remains protected by
    compute_record_hmac (unaffected by this change) — approved loosenings
    still cannot be tampered with, they are just no longer part of THIS
    digest.
    """
    hasher = hashlib.sha256()
    hasher.update(b"security-snapshot-v3\x00")
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
        record.workspace_digest.encode(),
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
    if record.schema_version >= 2:
        parts.append(b"\x00")
        parts.append(str(record.identity_format_version).encode())
        parts.append(b"\x00")
        provenance = record.migration_provenance
        if provenance is None:
            parts.append(b"")
        else:
            parts.append(provenance.disposition.encode())
            parts.append(b"\x00")
            parts.append(str(provenance.source_identity_format_version).encode())
            parts.append(b"\x00")
            parts.append(provenance.source_workspace_digest.encode())
            parts.append(b"\x00")
            parts.append(provenance.inherited_trust.encode())

    msg = b"".join(parts)
    return hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()


def compute_grant_hmac(grant: DiagnosticGrant, *, hmac_key: bytes) -> str:
    """Compute HMAC-SHA-256 over every DiagnosticGrant field except
    record_hmac itself.

    Plan 9.96, Task 6 Batch 2: closes the "" / "placeholder" record_hmac
    stub left in Task 5's launch_approval_cli.py (_cmd_run's --elevated-debug
    branch, explicitly commented "Grant HMAC computed separately in
    Task 6"). Uses a domain-separation prefix (_GRANT_HMAC_DOMAIN) distinct
    from _RECORD_HMAC_DOMAIN so a DiagnosticGrant and an ApprovalRecord with
    coincidentally matching field content can never produce colliding
    HMACs — the two types must remain cryptographically unrelated even
    though both are signed with the same underlying store hmac_key.

    launch_session_id is the field consume_diagnostic_grant's session check
    depends on being tamper-evident: without this HMAC, a same-process
    attacker (or a serialization bug) could rewrite the raw keyring entry's
    launch_session_id to match an attacker-controlled session and the grant
    would still verify.
    """
    parts: list[bytes] = [
        _GRANT_HMAC_DOMAIN,
        b"\x00",
        grant.grant_id.encode(),
        b"\x00",
        grant.workspace_digest.encode(),
        b"\x00",
        grant.approval_id.encode(),
        b"\x00",
        grant.launch_session_id.encode(),
        b"\x00",
        grant.expires_at.isoformat().encode(),
    ]
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
        workspace_digest=workspace_identity.digest,
        registry_version=registry_version,
    )

    # Build record without HMAC first, then compute and attach.
    record = ApprovalRecord(
        schema_version=APPROVAL_SCHEMA_VERSION,
        policy_compatibility=LAUNCH_POLICY_COMPATIBILITY,
        approval_id=f"appr_{secrets.token_hex(12)}",
        mode=mode,
        identity_format_version=workspace_identity.format_version,
        workspace_digest=workspace_identity.digest,
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
        migration_provenance=None,
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
        "workspace_digest": record.workspace_digest,
    }
    if record.schema_version >= 2:
        data["identity_format_version"] = record.identity_format_version
        data["migration_provenance"] = None
        if record.migration_provenance is not None:
            data["migration_provenance"] = {
                "disposition": record.migration_provenance.disposition,
                "inherited_trust": record.migration_provenance.inherited_trust,
                "source_identity_format_version": record.migration_provenance.source_identity_format_version,
                "source_workspace_digest": record.migration_provenance.source_workspace_digest,
            }
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _parse_migration_provenance(raw: object) -> ApprovalMigrationProvenance | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TypeError("migration_provenance must be an object or null")
    return ApprovalMigrationProvenance(
        disposition=raw["disposition"],
        source_identity_format_version=raw["source_identity_format_version"],
        source_workspace_digest=raw["source_workspace_digest"],
        inherited_trust=raw["inherited_trust"],
    )


def _deserialize_approval_record(raw: str, *, hmac_key: bytes) -> ApprovalRecord:
    """Deserialize and verify an approval record from JSON."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ApprovalError(code="RECORD_CORRUPT", detail="invalid JSON") from exc

    try:
        schema_version = int(data["schema_version"])
        created_at = datetime.fromisoformat(data["created_at"])
        expires_at = datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
        if schema_version == LEGACY_APPROVAL_SCHEMA_VERSION:
            identity_format_version = 2
            provenance = None
        elif schema_version == APPROVAL_SCHEMA_VERSION:
            identity_format_version = int(data["identity_format_version"])
            provenance = _parse_migration_provenance(data.get("migration_provenance"))
        else:
            raise ValueError("unsupported schema_version")

        record = ApprovalRecord(
            schema_version=schema_version,
            policy_compatibility=data["policy_compatibility"],
            approval_id=data["approval_id"],
            mode=data["mode"],
            identity_format_version=identity_format_version,
            workspace_digest=data["workspace_digest"],
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
            migration_provenance=provenance,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ApprovalError(code="RECORD_CORRUPT", detail="missing or invalid fields") from exc

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

    @property
    def hmac_key(self) -> bytes:
        """Public accessor for the approval-store HMAC integrity key.

        Callers outside this module (the optimus-trust CLI, __main__.py's
        authorized launch path, and anything that needs to sign a
        GatewayChildManifest with the same root key) should use this
        property rather than reaching into the private _hmac_key attribute
        across a module boundary — that pattern reads fine today but quietly
        becomes load-bearing and brittle as more call sites accumulate.
        """
        return self._hmac_key

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
        entry_key = f"durable:{record.workspace_digest}"
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

    @contextmanager
    def _exclusive_workspace_lock(self, workspace_digest: str):
        import sys

        lock_path = self._workspace_lock_path(workspace_digest)
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
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                try:
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            lock_fd.close()

    def lookup_durable(
        self,
        *,
        current_identity: WorkspaceIdentity,
        legacy_workspace_digest: str,
        expected_legacy_snapshot_digest: str,
        current_security_snapshot_digest: str,
    ) -> DurableApprovalLookup:
        """Look up v3 first; promote exact legacy only when v3 is absent."""
        current_key = f"durable:{current_identity.digest}"
        raw_v3 = self._keyring.get_password(self._service_name, current_key)
        if raw_v3 is not None:
            record = _deserialize_approval_record(raw_v3, hmac_key=self._hmac_key)
            if record.policy_compatibility != LAUNCH_POLICY_COMPATIBILITY:
                raise ApprovalError(code="POLICY_MISMATCH")
            state: Literal["current", "migrated"] = (
                "migrated" if record.migration_provenance is not None else "current"
            )
            return DurableApprovalLookup(record=record, state=state)
        return self.promote_legacy_durable(
            current_identity=current_identity,
            legacy_workspace_digest=legacy_workspace_digest,
            expected_legacy_snapshot_digest=expected_legacy_snapshot_digest,
            current_security_snapshot_digest=current_security_snapshot_digest,
        )

    def promote_legacy_durable(
        self,
        *,
        current_identity: WorkspaceIdentity,
        legacy_workspace_digest: str,
        expected_legacy_snapshot_digest: str,
        current_security_snapshot_digest: str,
    ) -> DurableApprovalLookup:
        """Promote an exact matching durable v1 record to schema v2 / identity v3."""
        if legacy_workspace_digest.startswith("oneshot:") or current_identity.digest.startswith("oneshot:"):
            raise ApprovalError(code="ONE_SHOT_VERSION_MISMATCH", detail="durable migration must not touch oneshot keys")

        with self._exclusive_workspace_lock(current_identity.digest):
            current_key = f"durable:{current_identity.digest}"
            raw_v3 = self._keyring.get_password(self._service_name, current_key)
            if raw_v3 is not None:
                record = _deserialize_approval_record(raw_v3, hmac_key=self._hmac_key)
                if record.policy_compatibility != LAUNCH_POLICY_COMPATIBILITY:
                    raise ApprovalError(code="POLICY_MISMATCH")
                state: Literal["current", "migrated"] = (
                    "migrated" if record.migration_provenance is not None else "current"
                )
                return DurableApprovalLookup(record=record, state=state)

            if not legacy_workspace_digest:
                return DurableApprovalLookup(record=None, state="legacy_reapproval_required")

            legacy_key = f"durable:{legacy_workspace_digest}"
            raw_legacy = self._keyring.get_password(self._service_name, legacy_key)
            if raw_legacy is None:
                return DurableApprovalLookup(record=None, state="legacy_reapproval_required")

            legacy = _deserialize_approval_record(raw_legacy, hmac_key=self._hmac_key)
            if legacy.policy_compatibility != LAUNCH_POLICY_COMPATIBILITY:
                raise ApprovalError(code="POLICY_MISMATCH")
            if legacy.mode != "durable":
                raise ApprovalError(code="POLICY_MISMATCH", detail="non-durable records are not promoted")
            if legacy.workspace_digest != legacy_workspace_digest:
                raise ApprovalError(code="INTEGRITY_FAILURE", detail="legacy workspace digest mismatch")
            if legacy.security_snapshot_digest != expected_legacy_snapshot_digest:
                raise ApprovalError(code="SNAPSHOT_MISMATCH")

            promoted = ApprovalRecord(
                schema_version=APPROVAL_SCHEMA_VERSION,
                policy_compatibility=legacy.policy_compatibility,
                approval_id=legacy.approval_id,
                mode="durable",
                identity_format_version=3,
                workspace_digest=current_identity.digest,
                created_at=legacy.created_at,
                expires_at=None,
                creator_identity=legacy.creator_identity,
                ceremony_cli_version=legacy.ceremony_cli_version,
                security_literals=dict(legacy.security_literals),
                secret_fingerprints=dict(legacy.secret_fingerprints),
                monotonic_grants=dict(legacy.monotonic_grants),
                model_observation=legacy.model_observation,
                registry_version=legacy.registry_version,
                security_snapshot_digest=current_security_snapshot_digest,
                consumed=False,
                record_hmac="",
                migration_provenance=ApprovalMigrationProvenance(
                    disposition="legacy_v2_to_v3",
                    source_identity_format_version=2,
                    source_workspace_digest=legacy.workspace_digest,
                    inherited_trust="pre_migration_assurance_not_upgraded",
                ),
            )
            promoted = replace(promoted, record_hmac=compute_record_hmac(promoted, hmac_key=self._hmac_key))
            serialized = serialize_approval_record(promoted)
            if len(serialized.encode("utf-8")) > MAX_APPROVAL_RECORD_BYTES:
                raise ApprovalError(code="RECORD_TOO_LARGE")
            self._keyring.set_password(self._service_name, current_key, serialized)
            read_back = self._keyring.get_password(self._service_name, current_key)
            if read_back != serialized:
                raise ApprovalError(code="RECORD_CORRUPT", detail="v3 read-back verification failed")
            verified = _deserialize_approval_record(read_back, hmac_key=self._hmac_key)
            return DurableApprovalLookup(record=verified, state="migrated")

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

            if record.schema_version != APPROVAL_SCHEMA_VERSION:
                raise ApprovalError(
                    code="ONE_SHOT_VERSION_MISMATCH",
                    detail="outstanding one-shot records must be reissued",
                )

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

        expected_hmac = compute_grant_hmac(grant, hmac_key=self._hmac_key)
        if not hmac.compare_digest(grant.record_hmac, expected_hmac):
            raise ApprovalError(code="GRANT_INTEGRITY_FAILURE", detail="grant HMAC mismatch")

        if grant.launch_session_id != launch_session_id:
            raise ApprovalError(code="GRANT_SESSION_MISMATCH")

        if datetime.now(timezone.utc) > grant.expires_at:
            self._keyring.delete_password(self._service_name, entry_key)
            raise ApprovalError(code="GRANT_EXPIRED")

        # Delete before returning.
        self._keyring.delete_password(self._service_name, entry_key)
        return grant

    def revoke_workspace(self, workspace_digest: str) -> None:
        """Revoke a durable approval for a workspace.

        A migrated record also deletes the authenticated legacy source key
        recorded in provenance. Fresh v3 records do not search for legacy keys.
        """
        entry_key = f"durable:{workspace_digest}"
        raw = self._keyring.get_password(self._service_name, entry_key)
        provenance_legacy_key: str | None = None
        if raw is not None:
            try:
                record = _deserialize_approval_record(raw, hmac_key=self._hmac_key)
            except ApprovalError:
                record = None
            if record is not None and record.migration_provenance is not None:
                provenance_legacy_key = f"durable:{record.migration_provenance.source_workspace_digest}"
        self._keyring.delete_password(self._service_name, entry_key)
        if provenance_legacy_key is not None:
            self._keyring.delete_password(self._service_name, provenance_legacy_key)

    def rotate_hmac_key(self) -> None:
        """Rotate the HMAC integrity key.

        WARNING: This invalidates all existing approval records.
        """
        key = secrets.token_bytes(32)
        encoded = base64.urlsafe_b64encode(key).decode("ascii")
        self._keyring.set_password(self._service_name, _HMAC_KEY_ENTRY, encoded)
        self._hmac_key = key


# --- P11-FU-9 client-MCP ceremony helpers (CLI display + keyed fingerprints) ---

# Must match optimus.mcp.client_config credential fingerprint domain so manual
# ceremony fingerprints bind to the same identity surface as normalization.
_CLIENT_MCP_CREDENTIAL_FP_DOMAIN = b"p11-fu-9-client-mcp-credential-fingerprint-v1"


@dataclass(frozen=True)
class ClientMcpReviewDisplay:
    """Safe ceremony display inputs — names and fingerprints only, never raw values."""

    workspace_digest: str
    session_id: str
    received_at: str
    server_name: str
    transport: str
    canonical_target: str
    credential_field_names: tuple[str, ...]
    credential_name_fingerprints: tuple[str, ...]
    rendered_fingerprint: str
    provenance: str = "client_supplied_acp"
    scanner_rule_ids: tuple[str, ...] = ()


def compute_client_mcp_credential_fingerprint(
    value: str,
    *,
    kind: str,
    name: str,
    index: int,
    hmac_key: bytes,
) -> str:
    """Domain-separated HMAC fingerprint keyed by kind, canonical name, and index."""
    msg = (
        _CLIENT_MCP_CREDENTIAL_FP_DOMAIN
        + b"\0"
        + f"{kind}\0{name}\0{index}\0{value}".encode("utf-8")
    )
    return hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()


def format_client_mcp_review_lines(display: ClientMcpReviewDisplay) -> tuple[str, ...]:
    """Render operator-facing review lines with names/fingerprints only."""
    names = ", ".join(display.credential_field_names) if display.credential_field_names else "(none)"
    fingerprints = (
        ", ".join(display.credential_name_fingerprints)
        if display.credential_name_fingerprints
        else "(none)"
    )
    rules = ", ".join(display.scanner_rule_ids) if display.scanner_rule_ids else "(none)"
    return (
        "optimus-trust: client MCP candidate for review:",
        f"  Provenance: {display.provenance}",
        f"  Session: {display.session_id or '(manual)'}",
        f"  Workspace digest: {display.workspace_digest[:16]}...",
        f"  Received-at: {display.received_at or '(not provided)'}",
        f"  Server: {display.server_name}",
        f"  Transport: {display.transport}",
        f"  Canonical target: {display.canonical_target}",
        f"  Credential field names: {names}",
        f"  Credential fingerprints: {fingerprints}",
        f"  Identity fingerprint: {display.rendered_fingerprint}",
        f"  Scanner rules: {rules}",
    )
