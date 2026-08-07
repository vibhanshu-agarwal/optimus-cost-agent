"""Identity-only durable client-MCP trust, session leases, and derived HMAC domains."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Literal

from optimus.mcp.client_config import ClientMcpSafeIdentity

MCP_POLICY_COMPATIBILITY = "P11-FU-9-v1"
CLIENT_MCP_SCHEMA_VERSION = 1
_KEYRING_SERVICE = "optimus-cost-agent-client-mcp"

_RECORD_HMAC_DOMAIN = b"p11-fu-9-client-mcp-record-hmac-v1"
_CREDENTIAL_FP_DOMAIN = b"p11-fu-9-client-mcp-credential-fingerprint-v1"
_IPC_AUTH_DOMAIN = b"p11-fu-9-client-mcp-ipc-auth-v1"
_IDENTITY_FP_DOMAIN = b"p11-fu-9-client-mcp-identity-fingerprint-v1"

EffectCeiling = Literal["non_mutating", "side_effect_eligible"]


class ClientMcpTrustError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"ClientMcpTrustError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


def derive_record_hmac_key(hmac_root: bytes) -> bytes:
    return hmac.new(hmac_root, _RECORD_HMAC_DOMAIN, hashlib.sha256).digest()


def derive_credential_fingerprint_key(hmac_root: bytes) -> bytes:
    return hmac.new(hmac_root, _CREDENTIAL_FP_DOMAIN, hashlib.sha256).digest()


def derive_ipc_auth_key(hmac_root: bytes) -> bytes:
    return hmac.new(hmac_root, _IPC_AUTH_DOMAIN, hashlib.sha256).digest()


def compute_identity_fingerprint(identity: ClientMcpSafeIdentity, *, hmac_key: bytes) -> str:
    payload = "\0".join(
        [
            identity.transport,
            identity.server_name,
            identity.canonical_target,
            json.dumps(list(identity.arguments), separators=(",", ":")),
            json.dumps(list(identity.credential_name_fingerprints), separators=(",", ":")),
        ]
    ).encode("utf-8")
    return hmac.new(
        hmac.new(hmac_key, _IDENTITY_FP_DOMAIN, hashlib.sha256).digest(),
        payload,
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True)
class ClientMcpDurableRecord:
    schema_version: int
    workspace_digest: str
    server_name: str
    identity_fingerprint: str
    transport: str
    canonical_target: str
    arguments: tuple[str, ...]
    credential_name_fingerprints: tuple[str, ...]
    policy_compatibility: str
    effect_ceiling: EffectCeiling
    record_hmac: str

    @classmethod
    def build(
        cls,
        *,
        workspace_digest: str,
        identity: ClientMcpSafeIdentity,
        identity_fingerprint: str,
        hmac_key: bytes,
        effect_ceiling: EffectCeiling = "non_mutating",
    ) -> ClientMcpDurableRecord:
        unsigned = cls(
            schema_version=CLIENT_MCP_SCHEMA_VERSION,
            workspace_digest=workspace_digest,
            server_name=identity.server_name,
            identity_fingerprint=identity_fingerprint,
            transport=identity.transport,
            canonical_target=identity.canonical_target,
            arguments=identity.arguments,
            credential_name_fingerprints=identity.credential_name_fingerprints,
            policy_compatibility=MCP_POLICY_COMPATIBILITY,
            effect_ceiling=effect_ceiling,
            record_hmac="",
        )
        return cls(
            **{
                **unsigned.__dict__,
                "record_hmac": compute_record_hmac(unsigned, hmac_key=hmac_key),
            }
        )

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workspace_digest": self.workspace_digest,
            "server_name": self.server_name,
            "identity_fingerprint": self.identity_fingerprint,
            "transport": self.transport,
            "canonical_target": self.canonical_target,
            "arguments": list(self.arguments),
            "credential_name_fingerprints": list(self.credential_name_fingerprints),
            "policy_compatibility": self.policy_compatibility,
            "effect_ceiling": self.effect_ceiling,
            "record_hmac": self.record_hmac,
        }


def compute_record_hmac(record: ClientMcpDurableRecord, *, hmac_key: bytes) -> str:
    payload = json.dumps(
        {
            "schema_version": record.schema_version,
            "workspace_digest": record.workspace_digest,
            "server_name": record.server_name,
            "identity_fingerprint": record.identity_fingerprint,
            "transport": record.transport,
            "canonical_target": record.canonical_target,
            "arguments": list(record.arguments),
            "credential_name_fingerprints": list(record.credential_name_fingerprints),
            "policy_compatibility": record.policy_compatibility,
            "effect_ceiling": record.effect_ceiling,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hmac.new(derive_record_hmac_key(hmac_key), payload, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ClientMcpSessionLease:
    session_id: str
    workspace_digest: str
    server_name: str
    identity_fingerprint: str
    effect_ceiling: EffectCeiling


class ClientMcpDurableStore:
    service_name = _KEYRING_SERVICE

    def __init__(self, *, keyring_backend: Any, hmac_key: bytes) -> None:
        self._keyring = keyring_backend
        self._hmac_key = hmac_key

    def entry_key(self, workspace_digest: str, server_name: str, identity_fingerprint: str) -> str:
        return f"client-mcp:{workspace_digest}:{server_name}:{identity_fingerprint}"

    def read(
        self, workspace_digest: str, server_name: str, identity_fingerprint: str
    ) -> ClientMcpDurableRecord | None:
        raw = self._keyring.get_password(
            self.service_name, self.entry_key(workspace_digest, server_name, identity_fingerprint)
        )
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            record = ClientMcpDurableRecord(
                schema_version=int(data["schema_version"]),
                workspace_digest=str(data["workspace_digest"]),
                server_name=str(data["server_name"]),
                identity_fingerprint=str(data["identity_fingerprint"]),
                transport=str(data["transport"]),
                canonical_target=str(data["canonical_target"]),
                arguments=tuple(data["arguments"]),
                credential_name_fingerprints=tuple(data["credential_name_fingerprints"]),
                policy_compatibility=str(data["policy_compatibility"]),
                effect_ceiling=data["effect_ceiling"],
                record_hmac=str(data["record_hmac"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ClientMcpTrustError("RECORD_CORRUPT") from exc
        if record.policy_compatibility != MCP_POLICY_COMPATIBILITY:
            raise ClientMcpTrustError("POLICY_MISMATCH")
        expected = compute_record_hmac(record, hmac_key=self._hmac_key)
        if not hmac.compare_digest(expected, record.record_hmac):
            raise ClientMcpTrustError("INTEGRITY_FAILURE")
        return record

    def write(self, record: ClientMcpDurableRecord) -> None:
        if record.policy_compatibility != MCP_POLICY_COMPATIBILITY:
            raise ClientMcpTrustError("POLICY_MISMATCH")
        expected = compute_record_hmac(record, hmac_key=self._hmac_key)
        if not hmac.compare_digest(expected, record.record_hmac):
            raise ClientMcpTrustError("INTEGRITY_FAILURE")
        payload = json.dumps(record.to_safe_dict(), separators=(",", ":"), sort_keys=True)
        self._keyring.set_password(
            self.service_name,
            self.entry_key(record.workspace_digest, record.server_name, record.identity_fingerprint),
            payload,
        )


class ClientMcpLeaseAuthority:
    def __init__(self, *, store: ClientMcpDurableStore) -> None:
        self._store = store

    def acquire_allow_once(
        self,
        *,
        session_id: str,
        workspace_digest: str,
        identity: ClientMcpSafeIdentity,
        identity_fingerprint: str,
    ) -> ClientMcpSessionLease:
        return ClientMcpSessionLease(
            session_id=session_id,
            workspace_digest=workspace_digest,
            server_name=identity.server_name,
            identity_fingerprint=identity_fingerprint,
            effect_ceiling="non_mutating",
        )

    def lookup_durable(
        self, workspace_digest: str, server_name: str, identity_fingerprint: str
    ) -> ClientMcpDurableRecord | None:
        return self._store.read(workspace_digest, server_name, identity_fingerprint)


def write_client_mcp_durable_from_fingerprint(
    *,
    store: ClientMcpDurableStore,
    workspace_digest: str,
    identity: ClientMcpSafeIdentity,
    rendered_fingerprint: str,
    effect_ceiling: EffectCeiling = "non_mutating",
) -> ClientMcpDurableRecord:
    """CLI-only writer: bind exactly the derived fingerprint for the reviewed identity."""
    expected = compute_identity_fingerprint(identity, hmac_key=store._hmac_key)
    if len(expected) != len(rendered_fingerprint) or not hmac.compare_digest(
        expected, rendered_fingerprint
    ):
        raise ClientMcpTrustError("IDENTITY_MISMATCH")
    record = ClientMcpDurableRecord.build(
        workspace_digest=workspace_digest,
        identity=identity,
        identity_fingerprint=rendered_fingerprint,
        effect_ceiling=effect_ceiling,
        hmac_key=store._hmac_key,
    )
    store.write(record)
    return record
