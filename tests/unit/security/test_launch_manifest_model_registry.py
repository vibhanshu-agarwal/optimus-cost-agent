"""Plan 12.2 Task 5: the Gateway child manifest binds the trusted model registry.

A manifest without a registry is exactly the version-1 manifest (same signed field set, same bytes
shape), so launches stay unchanged while registry enforcement is inactive. A version-2 manifest signs
the registry's approval literal, and the Gateway refuses to start unless that literal equals the
registry it composed itself.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from optimus_security.launch_manifest import (
    MANIFEST_REGISTRY_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    LaunchManifestError,
    build_gateway_child_manifest,
    serialize_gateway_child_manifest,
    verify_gateway_child_manifest,
)

_KEY = b"test-manifest-registry-hmac-32b!"
_LITERAL = "optimus-model-registry-v1:" + "c" * 64
_V1_FIELDS = {
    "schema_version",
    "policy_version",
    "workspace_digest",
    "security_snapshot_digest",
    "provider",
    "base_url",
    "bind_host",
    "bind_port",
    "provider_api_key_fingerprint",
    "shared_secret_fingerprint",
    "issued_at",
    "expires_at",
    "nonce",
}
_INPUTS = {
    "provider": "openrouter",
    "base_url": "https://openrouter.ai/api/v1",
    "provider_api_key": "sk-or-test-key",  # pragma: allowlist secret - synthetic test fixture
    "shared_secret": "shared-secret-value",  # pragma: allowlist secret - synthetic test fixture
    "bind_host": "127.0.0.1",
    "bind_port": 8765,
}


def _serialized(model_registry: str | None) -> str:
    manifest = build_gateway_child_manifest(
        workspace_digest="a" * 64,
        security_snapshot_digest="b" * 64,
        hmac_key=_KEY,
        policy_version="P9.99-v1",
        model_registry=model_registry,
        **_INPUTS,
    )
    return serialize_gateway_child_manifest(manifest)


def _verify(serialized: str, model_registry: str | None):
    return verify_gateway_child_manifest(serialized, hmac_key=_KEY, model_registry=model_registry, **_INPUTS)


def test_a_manifest_without_a_registry_is_exactly_version_one() -> None:
    data = json.loads(_serialized(None))
    assert data["schema_version"] == MANIFEST_SCHEMA_VERSION == 1
    assert set(data) == _V1_FIELDS | {"signature"}
    # Independent recomputation of the version-1 signature over the version-1 field set.
    signed = {name: data[name] for name in _V1_FIELDS}
    canonical = json.dumps(signed, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(_KEY, b"p996-gateway-child-manifest-v1\x00" + canonical.encode(), hashlib.sha256).hexdigest()
    assert data["signature"] == expected
    assert _verify(_serialized(None), None).model_registry is None


def test_a_registry_manifest_is_version_two_and_signs_the_literal() -> None:
    serialized = _serialized(_LITERAL)
    data = json.loads(serialized)
    assert data["schema_version"] == MANIFEST_REGISTRY_SCHEMA_VERSION == 2
    assert data["model_registry"] == _LITERAL
    assert _verify(serialized, _LITERAL).model_registry == _LITERAL


@pytest.mark.parametrize(
    ("signed", "gateway"),
    [
        (_LITERAL, None),  # the Gateway enforces no registry: unsupported combination
        (None, _LITERAL),  # the Gateway enforces one the parent did not bind
        (_LITERAL, "optimus-model-registry-v1:" + "d" * 64),  # a different registry
    ],
)
def test_the_gateway_refuses_a_manifest_for_another_registry(signed, gateway) -> None:
    with pytest.raises(LaunchManifestError) as caught:
        _verify(_serialized(signed), gateway)
    assert caught.value.code == "MANIFEST_MODEL_REGISTRY_MISMATCH"


@pytest.mark.parametrize(
    ("tamper", "code"),
    [
        (lambda d: d.pop("model_registry"), "MANIFEST_CORRUPT"),  # stripped, still claiming version 2
        (lambda d: d.update(schema_version=1), "MANIFEST_CORRUPT"),  # downgraded, still carrying it
        (lambda d: d.update(model_registry=7), "MANIFEST_CORRUPT"),
        (lambda d: d.update(model_registry="optimus-model-registry-v1:" + "e" * 64), "MANIFEST_INVALID_SIGNATURE"),
    ],
)
def test_tampering_with_the_registry_binding_fails_closed(tamper, code: str) -> None:
    data = json.loads(_serialized(_LITERAL))
    tamper(data)
    with pytest.raises(LaunchManifestError) as caught:
        _verify(json.dumps(data), _LITERAL)
    assert caught.value.code == code


def test_adding_a_registry_to_a_version_one_manifest_breaks_its_signature() -> None:
    data = json.loads(_serialized(None))
    data.update(schema_version=2, model_registry=_LITERAL)
    with pytest.raises(LaunchManifestError) as caught:
        _verify(json.dumps(data), _LITERAL)
    assert caught.value.code == "MANIFEST_INVALID_SIGNATURE"
