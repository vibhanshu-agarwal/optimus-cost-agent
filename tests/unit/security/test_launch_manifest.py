"""Tests for the HMAC-signed Gateway child manifest.

Plan 9.96, Task 5 Step 4: GatewayChildManifest contains schema/policy
versions, workspace and security-snapshot digests, exact non-secret
provider/base/bind values, HMAC fingerprints of provider/shared credentials,
issued/expiry times no more than 60 seconds apart, and a random nonce. It
contains no secret. optimus_gateway rejects missing, expired, mismatched, or
invalid manifests.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from optimus_security.launch_manifest import (
    MANIFEST_MAX_AGE_SECONDS,
    GatewayChildManifest,
    LaunchManifestError,
    build_gateway_child_manifest,
    read_manifest_hmac_key,
    serialize_gateway_child_manifest,
    verify_gateway_child_manifest,
)

_HMAC_KEY = b"test-manifest-hmac-key-32-bytes!"


def _build_sample_manifest(**overrides: object) -> GatewayChildManifest:
    defaults: dict[str, object] = {
        "workspace_digest": "a" * 64,
        "security_snapshot_digest": "b" * 64,
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "bind_host": "127.0.0.1",
        "bind_port": 8765,
        "provider_api_key": "sk-or-test-key",
        "shared_secret": "shared-secret-value",
        "hmac_key": _HMAC_KEY,
        "policy_version": "P9.96-v1",
    }
    defaults.update(overrides)
    return build_gateway_child_manifest(**defaults)  # type: ignore[arg-type]


class TestManifestConstruction:
    """Manifest schema and field constraints."""

    def test_manifest_has_required_fields(self) -> None:
        manifest = _build_sample_manifest()
        assert manifest.schema_version == 1
        assert manifest.policy_version == "P9.96-v1"
        assert manifest.workspace_digest == "a" * 64
        assert manifest.provider == "openrouter"
        assert manifest.bind_host == "127.0.0.1"
        assert manifest.bind_port == 8765
        assert manifest.nonce
        assert manifest.signature

    def test_manifest_lifetime_is_at_most_60_seconds(self) -> None:
        manifest = _build_sample_manifest()
        delta = manifest.expires_at - manifest.issued_at
        assert delta <= timedelta(seconds=MANIFEST_MAX_AGE_SECONDS)
        assert delta == timedelta(seconds=MANIFEST_MAX_AGE_SECONDS)

    def test_manifest_contains_no_raw_secret(self) -> None:
        manifest = _build_sample_manifest(
            provider_api_key="sk-CANARY-SECRET-VALUE",
            shared_secret="CANARY-SHARED-SECRET",
        )
        serialized = serialize_gateway_child_manifest(manifest)
        assert "sk-CANARY-SECRET-VALUE" not in serialized
        assert "CANARY-SHARED-SECRET" not in serialized

    def test_manifest_nonces_are_random(self) -> None:
        m1 = _build_sample_manifest()
        m2 = _build_sample_manifest()
        assert m1.nonce != m2.nonce

    def test_manifest_serialization_is_canonical_json(self) -> None:
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)
        parsed = json.loads(serialized)
        re_serialized = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        assert serialized == re_serialized


class TestManifestVerification:
    """Manifest verification against actual Gateway construction inputs."""

    def test_valid_manifest_verifies(self) -> None:
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)
        verified = verify_gateway_child_manifest(
            serialized,
            hmac_key=_HMAC_KEY,
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            provider_api_key="sk-or-test-key",
            shared_secret="shared-secret-value",
            bind_host="127.0.0.1",
            bind_port=8765,
        )
        assert verified.workspace_digest == manifest.workspace_digest

    def test_mismatched_provider_rejected(self) -> None:
        """A manifest signed for one provider must not verify against another,
        even with matching credentials/bind — this is the base_url-redirect
        attack's sibling: swapping provider is the same class of hole."""
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                serialized,
                hmac_key=_HMAC_KEY,
                provider="anthropic",  # Manifest was signed for openrouter.
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="sk-or-test-key",
                shared_secret="shared-secret-value",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_PROVIDER_MISMATCH"

    def test_mismatched_base_url_rejected(self) -> None:
        """The base_url-redirect attack: a validly-signed manifest for one
        endpoint must not verify against a different base_url, even with
        matching provider/credentials/bind — otherwise the provider API key
        gets sent to an attacker-controlled endpoint."""
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                serialized,
                hmac_key=_HMAC_KEY,
                provider="openrouter",
                base_url="https://evil.attacker.example/v1",  # Redirected.
                provider_api_key="sk-or-test-key",
                shared_secret="shared-secret-value",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_BASE_URL_MISMATCH"

    def test_none_base_url_matches_none(self) -> None:
        """Anthropic-style manifests have base_url=None; verification must
        accept that exact match rather than treating None as a wildcard."""
        manifest = _build_sample_manifest(provider="anthropic", base_url=None)
        serialized = serialize_gateway_child_manifest(manifest)

        verified = verify_gateway_child_manifest(
            serialized,
            hmac_key=_HMAC_KEY,
            provider="anthropic",
            base_url=None,
            provider_api_key="sk-or-test-key",
            shared_secret="shared-secret-value",
            bind_host="127.0.0.1",
            bind_port=8765,
        )
        assert verified.base_url is None

    def test_none_base_url_does_not_match_real_url(self) -> None:
        """A manifest signed with base_url=None must not verify against a
        real base_url — the None/non-None boundary itself is a mismatch."""
        manifest = _build_sample_manifest(provider="anthropic", base_url=None)
        serialized = serialize_gateway_child_manifest(manifest)

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                serialized,
                hmac_key=_HMAC_KEY,
                provider="anthropic",
                base_url="https://evil.attacker.example/v1",
                provider_api_key="sk-or-test-key",
                shared_secret="shared-secret-value",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_BASE_URL_MISMATCH"

    def test_tampered_signature_rejected(self) -> None:
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)
        data = json.loads(serialized)
        data["bind_port"] = 9999  # Tamper without re-signing.
        tampered = json.dumps(data, sort_keys=True, separators=(",", ":"))

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                tampered,
                hmac_key=_HMAC_KEY,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="sk-or-test-key",
                shared_secret="shared-secret-value",
                bind_host="127.0.0.1",
                bind_port=9999,
            )
        assert exc_info.value.code == "MANIFEST_INVALID_SIGNATURE"

    def test_wrong_key_rejected(self) -> None:
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)
        wrong_key = b"wrong-manifest-hmac-key-32bytes!"

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                serialized,
                hmac_key=wrong_key,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="sk-or-test-key",
                shared_secret="shared-secret-value",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_INVALID_SIGNATURE"

    def test_expired_manifest_rejected(self) -> None:
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)
        data = json.loads(serialized)
        # Force expiry into the past without touching the signature domain content —
        # re-sign is not possible without the key, so we directly test the
        # expiry check by constructing a manifest with a past issued_at via the
        # public builder using monkeypatched time is unavailable; instead
        # verify the check triggers on a manually backdated but re-signed manifest.
        from optimus_security.launch_manifest import _canonical_fields, _compute_signature

        past_issued = datetime.now(timezone.utc) - timedelta(seconds=120)
        past_expires = past_issued + timedelta(seconds=MANIFEST_MAX_AGE_SECONDS)
        fields = _canonical_fields(
            schema_version=data["schema_version"],
            policy_version=data["policy_version"],
            workspace_digest=data["workspace_digest"],
            security_snapshot_digest=data["security_snapshot_digest"],
            provider=data["provider"],
            base_url=data["base_url"],
            bind_host=data["bind_host"],
            bind_port=data["bind_port"],
            provider_api_key_fingerprint=data["provider_api_key_fingerprint"],
            shared_secret_fingerprint=data["shared_secret_fingerprint"],
            issued_at=past_issued.isoformat(),
            expires_at=past_expires.isoformat(),
            nonce=data["nonce"],
        )
        signature = _compute_signature(fields, hmac_key=_HMAC_KEY)
        data["issued_at"] = past_issued.isoformat()
        data["expires_at"] = past_expires.isoformat()
        data["signature"] = signature
        backdated = json.dumps(data, sort_keys=True, separators=(",", ":"))

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                backdated,
                hmac_key=_HMAC_KEY,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="sk-or-test-key",
                shared_secret="shared-secret-value",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_EXPIRED"

    def test_mismatched_provider_credential_rejected(self) -> None:
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                serialized,
                hmac_key=_HMAC_KEY,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="sk-WRONG-KEY",
                shared_secret="shared-secret-value",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_CREDENTIAL_MISMATCH"

    def test_mismatched_shared_secret_rejected(self) -> None:
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                serialized,
                hmac_key=_HMAC_KEY,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="sk-or-test-key",
                shared_secret="WRONG-SHARED-SECRET",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_CREDENTIAL_MISMATCH"

    def test_mismatched_bind_rejected(self) -> None:
        manifest = _build_sample_manifest()
        serialized = serialize_gateway_child_manifest(manifest)

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                serialized,
                hmac_key=_HMAC_KEY,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="sk-or-test-key",
                shared_secret="shared-secret-value",
                bind_host="127.0.0.1",
                bind_port=9999,  # Wrong port.
            )
        assert exc_info.value.code == "MANIFEST_BIND_MISMATCH"

    def test_corrupt_json_rejected(self) -> None:
        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                "not valid json {{{",
                hmac_key=_HMAC_KEY,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="x",
                shared_secret="y",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_CORRUPT"

    def test_missing_field_rejected(self) -> None:
        incomplete = json.dumps({"schema_version": 1})
        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                incomplete,
                hmac_key=_HMAC_KEY,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="x",
                shared_secret="y",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_CORRUPT"

    def test_abnormally_long_lifetime_rejected_even_with_valid_signature(self) -> None:
        """A manifest signed with a lifetime > 60s must fail even if the
        signature is otherwise valid — defends against a builder bug."""
        from optimus_security.launch_manifest import _canonical_fields, _compute_signature

        now = datetime.now(timezone.utc)
        long_expiry = now + timedelta(seconds=3600)
        fields = _canonical_fields(
            schema_version=1,
            policy_version="P9.96-v1",
            workspace_digest="a" * 64,
            security_snapshot_digest="b" * 64,
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            bind_host="127.0.0.1",
            bind_port=8765,
            provider_api_key_fingerprint="fp1",
            shared_secret_fingerprint="fp2",
            issued_at=now.isoformat(),
            expires_at=long_expiry.isoformat(),
            nonce="deadbeef",
        )
        signature = _compute_signature(fields, hmac_key=_HMAC_KEY)
        data = dict(fields)
        data["signature"] = signature
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                serialized,
                hmac_key=_HMAC_KEY,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                provider_api_key="whatever",
                shared_secret="whatever",
                bind_host="127.0.0.1",
                bind_port=8765,
            )
        assert exc_info.value.code == "MANIFEST_INVALID_LIFETIME"


class TestManifestKeyReading:
    """Reading the shared HMAC key through the neutral module."""

    def test_read_key_from_keyring(self) -> None:
        import base64

        class FakeKeyring:
            def get_password(self, service: str, key: str) -> str | None:
                return base64.urlsafe_b64encode(_HMAC_KEY).decode("ascii")

        key = read_manifest_hmac_key(FakeKeyring())
        assert key == _HMAC_KEY

    def test_missing_key_fails(self) -> None:
        class EmptyKeyring:
            def get_password(self, service: str, key: str) -> str | None:
                return None

        with pytest.raises(LaunchManifestError) as exc_info:
            read_manifest_hmac_key(EmptyKeyring())
        assert exc_info.value.code == "MANIFEST_KEY_UNAVAILABLE"

    def test_keyring_exception_fails_closed(self) -> None:
        class BrokenKeyring:
            def get_password(self, service: str, key: str) -> str | None:
                raise RuntimeError("keyring backend unavailable")

        with pytest.raises(LaunchManifestError) as exc_info:
            read_manifest_hmac_key(BrokenKeyring())
        assert exc_info.value.code == "MANIFEST_KEY_UNAVAILABLE"
