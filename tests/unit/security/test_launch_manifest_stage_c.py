"""Plan 12.2 Task 13 (Stage C): the Gateway child manifest binds the shared test envelope.

A Stage C launch signs the envelope literal beside the test profile's registry literal in a version-3
manifest. The Gateway composes the envelope itself from its actual ledger argument and source, and refuses
to start unless the signed literal is exactly that one. Version-1 and version-2 manifests keep their exact
signed field sets, so ordinary and profile-only launches are unchanged.
"""

from __future__ import annotations

import json

import pytest

from optimus_security.launch_manifest import (
    MANIFEST_REGISTRY_SCHEMA_VERSION,
    MANIFEST_STAGE_C_SCHEMA_VERSION,
    LaunchManifestError,
    build_gateway_child_manifest,
    serialize_gateway_child_manifest,
    verify_gateway_child_manifest,
)

_KEY = b"test-manifest-stage-c-hmac-key32"
_REGISTRY = "optimus-model-registry-v1:" + "c" * 64
_ENVELOPE = "optimus-stage-c-envelope-v1:" + "f" * 64
_INPUTS = {
    "provider": "openrouter",
    "base_url": "https://openrouter.ai/api/v1",
    "provider_api_key": "sk-or-test-key",  # pragma: allowlist secret - synthetic test fixture
    "shared_secret": "shared-secret-value",  # pragma: allowlist secret - synthetic test fixture
    "bind_host": "127.0.0.1",
    "bind_port": 8765,
}


def _serialized(model_registry: str | None, stage_c_envelope: str | None) -> str:
    manifest = build_gateway_child_manifest(
        workspace_digest="a" * 64,
        security_snapshot_digest="b" * 64,
        hmac_key=_KEY,
        policy_version="P9.99-v1",
        model_registry=model_registry,
        stage_c_envelope=stage_c_envelope,
        **_INPUTS,
    )
    return serialize_gateway_child_manifest(manifest)


def _verify(serialized: str, model_registry: str | None, stage_c_envelope: str | None):
    return verify_gateway_child_manifest(serialized, hmac_key=_KEY, model_registry=model_registry, stage_c_envelope=stage_c_envelope, **_INPUTS)


def test_a_stage_c_manifest_is_version_three_and_signs_both_literals() -> None:
    serialized = _serialized(_REGISTRY, _ENVELOPE)
    data = json.loads(serialized)
    assert (data["schema_version"], data["model_registry"], data["stage_c_envelope"]) == (MANIFEST_STAGE_C_SCHEMA_VERSION, _REGISTRY, _ENVELOPE)
    assert MANIFEST_STAGE_C_SCHEMA_VERSION == 3
    verified = _verify(serialized, _REGISTRY, _ENVELOPE)
    assert (verified.model_registry, verified.stage_c_envelope) == (_REGISTRY, _ENVELOPE)


def test_a_profile_manifest_without_an_envelope_is_unchanged_version_two() -> None:
    data = json.loads(_serialized(_REGISTRY, None))
    assert data["schema_version"] == MANIFEST_REGISTRY_SCHEMA_VERSION and "stage_c_envelope" not in data
    assert _verify(_serialized(_REGISTRY, None), _REGISTRY, None).stage_c_envelope is None


def test_an_envelope_needs_a_registry() -> None:
    with pytest.raises(LaunchManifestError) as caught:
        _serialized(None, _ENVELOPE)
    assert caught.value.code == "MANIFEST_STAGE_C_REQUIRES_REGISTRY"


@pytest.mark.parametrize(
    ("signed", "gateway"),
    [
        (_ENVELOPE, None),  # the Gateway was started without the ledger the parent bound
        (None, _ENVELOPE),  # the Gateway guards an envelope the parent did not bind
        (_ENVELOPE, "optimus-stage-c-envelope-v1:" + "e" * 64),  # another envelope (ledger, limits or scenarios)
    ],
)
def test_the_gateway_refuses_a_manifest_for_another_envelope(signed, gateway) -> None:
    with pytest.raises(LaunchManifestError) as caught:
        _verify(_serialized(_REGISTRY, signed), _REGISTRY, gateway)
    assert caught.value.code == "MANIFEST_STAGE_C_ENVELOPE_MISMATCH"


@pytest.mark.parametrize(
    ("tamper", "code"),
    [
        (lambda d: d.pop("stage_c_envelope"), "MANIFEST_CORRUPT"),  # stripped, still claiming version 3
        (lambda d: d.update(schema_version=2), "MANIFEST_CORRUPT"),  # downgraded, still carrying it
        (lambda d: d.update(stage_c_envelope=7), "MANIFEST_CORRUPT"),
        (lambda d: d.pop("model_registry"), "MANIFEST_CORRUPT"),  # an envelope without its registry
        (lambda d: d.update(stage_c_envelope="optimus-stage-c-envelope-v1:" + "e" * 64), "MANIFEST_INVALID_SIGNATURE"),
    ],
)
def test_tampering_with_the_envelope_binding_fails_closed(tamper, code: str) -> None:
    data = json.loads(_serialized(_REGISTRY, _ENVELOPE))
    tamper(data)
    with pytest.raises(LaunchManifestError) as caught:
        _verify(json.dumps(data), _REGISTRY, _ENVELOPE)
    assert caught.value.code == code


def test_adding_an_envelope_to_a_version_two_manifest_breaks_its_signature() -> None:
    data = json.loads(_serialized(_REGISTRY, None))
    data.update(schema_version=3, stage_c_envelope=_ENVELOPE)
    with pytest.raises(LaunchManifestError) as caught:
        _verify(json.dumps(data), _REGISTRY, _ENVELOPE)
    assert caught.value.code == "MANIFEST_INVALID_SIGNATURE"
