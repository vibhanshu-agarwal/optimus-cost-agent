"""HMAC-signed Gateway child manifest.

Plan 9.96, Task 5 Step 4: The standalone Gateway entrypoint no longer trusts
inherited OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT. The authorized parent passes
code-derived bind host/port as explicit arguments plus a short-lived HMAC
child manifest bound to the approved snapshot; the Gateway process validates
the manifest against its exact provider/base/credential inputs before
constructing GatewayServiceConfig. Direct unmanifested startup fails closed.

optimus_gateway is a distinct process/deployable that does not import
optimus.acp (see docs/superpowers/plans/2026-07-07-local-optimus-gateway-service.md).
This module lives in the neutral optimus_security package so both the ACP
parent and the Gateway child can build/verify manifests without either side
importing the other's package.

The manifest contains no secret material — only HMAC fingerprints of the
provider API key and shared secret, signed under a domain distinct from the
approval-store's other HMAC uses (record HMAC, secret fingerprints, one-shot
handles) so a manifest signature can never be reused as one of those, or
vice versa.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_MAX_AGE_SECONDS = 60

# Plan 9.96, Task 5 Batch 3 (review finding): the SINGLE shared source for
# each provider's default base URL. Both the parent (ProviderSecrets /
# resolve_provider_credentials in optimus.acp.local_gateway_secrets) and the
# Gateway (GatewayServiceConfig.from_env in optimus_gateway.models) MUST
# resolve an omitted OPTIMUS_LOCAL_GATEWAY_BASE_URL to this SAME concrete
# value. A prior version had each side independently default it —
# ProviderSecrets.base_url stayed None while GatewayServiceConfig.from_env
# applied its own _DEFAULT_BASE_URLS — so a manifest signed with base_url=None
# was rejected by the real Gateway with MANIFEST_BASE_URL_MISMATCH even for a
# completely legitimate default-base_url launch. This lives in the neutral
# optimus_security package (not optimus.acp or optimus_gateway) so neither
# side imports the other's package to share it — the same reason
# launch_manifest.py itself lives here.
DEFAULT_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def resolve_effective_base_url(*, provider: str, base_url: str | None) -> str | None:
    """Resolve the EFFECTIVE base_url for a provider, applying the shared
    default when base_url is unset. Returns None for anthropic (which never
    uses a base_url) or any provider not in DEFAULT_PROVIDER_BASE_URLS.

    Both the parent and the Gateway call this exact function so an omitted
    OPTIMUS_LOCAL_GATEWAY_BASE_URL resolves identically on both sides.
    """
    if provider == "anthropic":
        return None
    if base_url:
        return base_url
    return DEFAULT_PROVIDER_BASE_URLS.get(provider)

# Same keyring namespace/entry as optimus.acp.launch_approvals.KeyringApprovalStore's
# integrity key — one root key, domain-separated per use. Duplicated here (rather than
# imported) because optimus_gateway must not import optimus.acp.
_KEYRING_SERVICE = "optimus-cost-agent-approvals"
_HMAC_KEY_ENTRY = "hmac_integrity_key"

_MANIFEST_SIGNATURE_DOMAIN = b"p996-gateway-child-manifest-v1"
_MANIFEST_FINGERPRINT_DOMAIN = b"p996-manifest-credential-fingerprint-v1"


class LaunchManifestError(ValueError):
    """Raised when manifest construction or verification fails."""

    def __init__(self, *, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class GatewayChildManifest:
    """A short-lived, HMAC-signed manifest binding an approved launch snapshot
    to explicit Gateway construction parameters. Contains no secret."""

    schema_version: int
    policy_version: str
    workspace_digest: str
    security_snapshot_digest: str
    provider: str
    base_url: str | None
    bind_host: str
    bind_port: int
    provider_api_key_fingerprint: str
    shared_secret_fingerprint: str
    issued_at: datetime
    expires_at: datetime
    nonce: str
    signature: str


def read_manifest_hmac_key(keyring_backend: Any) -> bytes:
    """Read the shared approval-store HMAC key from the dedicated keyring
    namespace through this neutral module. Raises LaunchManifestError if the
    key is missing or malformed — there is no fallback key."""
    try:
        raw = keyring_backend.get_password(_KEYRING_SERVICE, _HMAC_KEY_ENTRY)
    except Exception as exc:
        raise LaunchManifestError(code="MANIFEST_KEY_UNAVAILABLE", detail="keyring read failed") from exc
    if not raw:
        raise LaunchManifestError(code="MANIFEST_KEY_UNAVAILABLE", detail="approval-store HMAC key not found")
    try:
        return base64.urlsafe_b64decode(raw)
    except Exception as exc:
        raise LaunchManifestError(code="MANIFEST_KEY_INVALID", detail="cannot decode HMAC key") from exc


def _fingerprint_credential(value: str, *, field_name: str, hmac_key: bytes) -> str:
    msg = _MANIFEST_FINGERPRINT_DOMAIN + b"\x00" + field_name.encode("utf-8") + b"\x00" + value.encode("utf-8")
    return hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()


def _canonical_fields(
    *,
    schema_version: int,
    policy_version: str,
    workspace_digest: str,
    security_snapshot_digest: str,
    provider: str,
    base_url: str | None,
    bind_host: str,
    bind_port: int,
    provider_api_key_fingerprint: str,
    shared_secret_fingerprint: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    """Canonical field mapping used for BOTH signing and serialization.

    Field order/types must be identical between build and verify — any
    divergence produces a signature that can never match, which is exactly
    the class of bug that made Task 4's candidate/approval digest
    computation permanently incompatible before the shared-function fix.
    """
    return {
        "schema_version": schema_version,
        "policy_version": policy_version,
        "workspace_digest": workspace_digest,
        "security_snapshot_digest": security_snapshot_digest,
        "provider": provider,
        "base_url": base_url,
        "bind_host": bind_host,
        "bind_port": bind_port,
        "provider_api_key_fingerprint": provider_api_key_fingerprint,
        "shared_secret_fingerprint": shared_secret_fingerprint,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce,
    }


def _compute_signature(fields: dict[str, Any], *, hmac_key: bytes) -> str:
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    msg = _MANIFEST_SIGNATURE_DOMAIN + b"\x00" + canonical.encode("utf-8")
    return hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()


def build_gateway_child_manifest(
    *,
    workspace_digest: str,
    security_snapshot_digest: str,
    provider: str,
    base_url: str | None,
    bind_host: str,
    bind_port: int,
    provider_api_key: str,
    shared_secret: str,
    hmac_key: bytes,
    policy_version: str,
) -> GatewayChildManifest:
    """Build a signed manifest. issued_at/expires_at are exactly
    MANIFEST_MAX_AGE_SECONDS apart."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=MANIFEST_MAX_AGE_SECONDS)
    nonce = secrets.token_hex(16)

    provider_fp = _fingerprint_credential(provider_api_key, field_name="provider_api_key", hmac_key=hmac_key)
    shared_fp = _fingerprint_credential(shared_secret, field_name="shared_secret", hmac_key=hmac_key)

    fields = _canonical_fields(
        schema_version=MANIFEST_SCHEMA_VERSION,
        policy_version=policy_version,
        workspace_digest=workspace_digest,
        security_snapshot_digest=security_snapshot_digest,
        provider=provider,
        base_url=base_url,
        bind_host=bind_host,
        bind_port=bind_port,
        provider_api_key_fingerprint=provider_fp,
        shared_secret_fingerprint=shared_fp,
        issued_at=now.isoformat(),
        expires_at=expires_at.isoformat(),
        nonce=nonce,
    )
    signature = _compute_signature(fields, hmac_key=hmac_key)

    return GatewayChildManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        policy_version=policy_version,
        workspace_digest=workspace_digest,
        security_snapshot_digest=security_snapshot_digest,
        provider=provider,
        base_url=base_url,
        bind_host=bind_host,
        bind_port=bind_port,
        provider_api_key_fingerprint=provider_fp,
        shared_secret_fingerprint=shared_fp,
        issued_at=now,
        expires_at=expires_at,
        nonce=nonce,
        signature=signature,
    )


def serialize_gateway_child_manifest(manifest: GatewayChildManifest) -> str:
    """Serialize to canonical compact JSON. Contains no secret."""
    data = {
        "schema_version": manifest.schema_version,
        "policy_version": manifest.policy_version,
        "workspace_digest": manifest.workspace_digest,
        "security_snapshot_digest": manifest.security_snapshot_digest,
        "provider": manifest.provider,
        "base_url": manifest.base_url,
        "bind_host": manifest.bind_host,
        "bind_port": manifest.bind_port,
        "provider_api_key_fingerprint": manifest.provider_api_key_fingerprint,
        "shared_secret_fingerprint": manifest.shared_secret_fingerprint,
        "issued_at": manifest.issued_at.isoformat(),
        "expires_at": manifest.expires_at.isoformat(),
        "nonce": manifest.nonce,
        "signature": manifest.signature,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def verify_gateway_child_manifest(
    serialized: str,
    *,
    hmac_key: bytes,
    provider: str,
    base_url: str | None,
    provider_api_key: str,
    shared_secret: str,
    bind_host: str,
    bind_port: int,
) -> GatewayChildManifest:
    """Verify a serialized manifest against the Gateway's actual construction
    inputs. Rejects missing, expired, mismatched, or invalid manifests.

    provider/base_url/provider_api_key/shared_secret/bind_host/bind_port are
    the EXACT values the Gateway process is ABOUT to construct
    GatewayServiceConfig with. All six must match the manifest's signed
    values, or the manifest was issued for a different launch and startup
    must fail closed. provider/base_url are signed but non-secret fields —
    without comparing them here, a manifest valid for one endpoint could be
    replayed against a different (attacker-controlled) base_url while still
    presenting the same credentials, exfiltrating the provider API key to an
    unapproved endpoint. This is caught the same way bind_host/bind_port
    mismatches are.
    """
    try:
        data = json.loads(serialized)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LaunchManifestError(code="MANIFEST_CORRUPT", detail="invalid JSON") from exc

    try:
        fields = _canonical_fields(
            schema_version=data["schema_version"],
            policy_version=data["policy_version"],
            workspace_digest=data["workspace_digest"],
            security_snapshot_digest=data["security_snapshot_digest"],
            provider=data["provider"],
            base_url=data.get("base_url"),
            bind_host=data["bind_host"],
            bind_port=data["bind_port"],
            provider_api_key_fingerprint=data["provider_api_key_fingerprint"],
            shared_secret_fingerprint=data["shared_secret_fingerprint"],
            issued_at=data["issued_at"],
            expires_at=data["expires_at"],
            nonce=data["nonce"],
        )
        signature = data["signature"]
    except (KeyError, TypeError) as exc:
        raise LaunchManifestError(code="MANIFEST_CORRUPT", detail="missing required field") from exc

    expected_signature = _compute_signature(fields, hmac_key=hmac_key)
    if not hmac.compare_digest(signature, expected_signature):
        raise LaunchManifestError(code="MANIFEST_INVALID_SIGNATURE")

    try:
        issued_at = datetime.fromisoformat(data["issued_at"])
        expires_at = datetime.fromisoformat(data["expires_at"])
    except ValueError as exc:
        raise LaunchManifestError(code="MANIFEST_CORRUPT", detail="invalid timestamp") from exc

    # Reject a signed-but-abnormally-long-lived manifest even though the
    # signature is valid — defends against a manifest-construction bug, not
    # just tampering.
    if (expires_at - issued_at) > timedelta(seconds=MANIFEST_MAX_AGE_SECONDS):
        raise LaunchManifestError(code="MANIFEST_INVALID_LIFETIME")

    if datetime.now(timezone.utc) > expires_at:
        raise LaunchManifestError(code="MANIFEST_EXPIRED")

    actual_provider_fp = _fingerprint_credential(provider_api_key, field_name="provider_api_key", hmac_key=hmac_key)
    if not hmac.compare_digest(actual_provider_fp, data["provider_api_key_fingerprint"]):
        raise LaunchManifestError(code="MANIFEST_CREDENTIAL_MISMATCH", detail="provider_api_key")

    actual_shared_fp = _fingerprint_credential(shared_secret, field_name="shared_secret", hmac_key=hmac_key)
    if not hmac.compare_digest(actual_shared_fp, data["shared_secret_fingerprint"]):
        raise LaunchManifestError(code="MANIFEST_CREDENTIAL_MISMATCH", detail="shared_secret")

    # provider/base_url are signed but non-secret; without this comparison a
    # validly-signed manifest for one endpoint could be presented alongside a
    # different (attacker-controlled) base_url while reusing the same
    # credentials, exfiltrating the provider API key to an unapproved host.
    if data["provider"] != provider:
        raise LaunchManifestError(code="MANIFEST_PROVIDER_MISMATCH")

    if data.get("base_url") != base_url:
        raise LaunchManifestError(code="MANIFEST_BASE_URL_MISMATCH")

    if data["bind_host"] != bind_host or data["bind_port"] != bind_port:
        raise LaunchManifestError(code="MANIFEST_BIND_MISMATCH")

    return GatewayChildManifest(
        schema_version=data["schema_version"],
        policy_version=data["policy_version"],
        workspace_digest=data["workspace_digest"],
        security_snapshot_digest=data["security_snapshot_digest"],
        provider=data["provider"],
        base_url=data.get("base_url"),
        bind_host=data["bind_host"],
        bind_port=data["bind_port"],
        provider_api_key_fingerprint=data["provider_api_key_fingerprint"],
        shared_secret_fingerprint=data["shared_secret_fingerprint"],
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=data["nonce"],
        signature=signature,
    )
