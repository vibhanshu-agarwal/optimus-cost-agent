from __future__ import annotations

import json

import pytest

from optimus_gateway import __main__ as gateway_main
from optimus_security.launch_manifest import (
    LaunchManifestError,
    build_gateway_child_manifest,
    serialize_gateway_child_manifest,
    verify_gateway_child_manifest,
)

_HMAC_KEY = b"test-mcp-profile-manifest-key!"
_PROFILE = {
    "profile_id": "context7",
    "revision": "rev-1",
    "manifest_hash": "a" * 64,
    "transport": "http",
    "credential_ref": "gateway://mcp/context7",
    "upstream_allowlist": ["search", "fetch"],
    "limits": {"max_pages": 10, "max_tools": 50, "max_descriptor_bytes": 65536},
    "attribution_policy": {"allow_unattributed_spend": False},
    "transport_config": {"endpoint": "https://context7.example/mcp"},
}


def _build(**overrides: object):
    values: dict[str, object] = {
        "workspace_digest": "a" * 64,
        "security_snapshot_digest": "b" * 64,
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "bind_host": "127.0.0.1",
        "bind_port": 8765,
        "provider_api_key": "sk-or-test-key",
        "shared_secret": "shared-secret-value",
        "hmac_key": _HMAC_KEY,
        "policy_version": "P11.8-v1",
        "mcp_profiles": (_PROFILE,),
    }
    values.update(overrides)
    return build_gateway_child_manifest(**values)  # type: ignore[arg-type]


def test_signed_manifest_carries_non_secret_profile_bootstrap_metadata():
    manifest = _build()
    serialized = serialize_gateway_child_manifest(manifest)

    assert "sk-or-test-key" not in serialized
    assert "shared-secret-value" not in serialized
    assert "context7" in serialized
    assert "https://context7.example/mcp" in serialized

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
    assert len(verified.mcp_profiles) == 1
    assert verified.mcp_profiles[0]["profile_id"] == "context7"


def test_profile_bootstrap_metadata_is_signed_and_tamper_evident():
    serialized = serialize_gateway_child_manifest(_build())
    payload = json.loads(serialized)
    payload["mcp_profiles"][0]["transport_config"]["endpoint"] = "https://evil.example/mcp"

    with pytest.raises(LaunchManifestError, match="MANIFEST_INVALID_SIGNATURE"):
        verify_gateway_child_manifest(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            hmac_key=_HMAC_KEY,
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            provider_api_key="sk-or-test-key",
            shared_secret="shared-secret-value",
            bind_host="127.0.0.1",
            bind_port=8765,
        )


@pytest.mark.parametrize("field", ["oauth", "access_token", "refresh_token", "catalog_url", "autoload"])
def test_profile_bootstrap_rejects_oauth_catalog_and_autoload_fields(field: str):
    profile = dict(_PROFILE)
    profile[field] = "forbidden"

    with pytest.raises(LaunchManifestError, match="MANIFEST_MCP_PROFILE_INVALID"):
        _build(mcp_profiles=(profile,))


def test_profile_bootstrap_rejects_secret_material_and_secret_fingerprint_fields():
    profile = dict(_PROFILE)
    profile["access_token"] = "CANARY-UPSTREAM-TOKEN"
    profile["credential_fingerprint"] = "c" * 64

    with pytest.raises(LaunchManifestError, match="MANIFEST_MCP_PROFILE_INVALID"):
        _build(mcp_profiles=(profile,))


def test_profile_bootstrap_rejects_duplicate_or_malformed_profiles():
    with pytest.raises(LaunchManifestError, match="MANIFEST_MCP_PROFILE_INVALID"):
        _build(mcp_profiles=(_PROFILE, dict(_PROFILE)))

    malformed = dict(_PROFILE)
    del malformed["credential_ref"]
    with pytest.raises(LaunchManifestError, match="MANIFEST_MCP_PROFILE_INVALID"):
        _build(mcp_profiles=(malformed,))


def test_entrypoint_activates_signed_profiles_before_serving(monkeypatch: pytest.MonkeyPatch):
    import base64

    class Keyring:
        def get_password(self, service: str, key: str) -> str | None:
            return base64.urlsafe_b64encode(_HMAC_KEY).decode("ascii") if key == "hmac_integrity_key" else None

    class FakeServer:
        server_address = ("127.0.0.1", 8765)

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def shutdown(self) -> None:
            pass

    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "shared-secret-value")
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "sk-or-test-key")
    monkeypatch.setattr(gateway_main, "_keyring_module", Keyring())
    captured: dict[str, object] = {}

    def fake_serve_gateway(**kwargs: object) -> FakeServer:
        captured.update(kwargs)
        return FakeServer()

    monkeypatch.setattr(gateway_main, "serve_gateway", fake_serve_gateway)
    exit_code = gateway_main.main(
        ["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", serialize_gateway_child_manifest(_build())]
    )

    assert exit_code == 0
    registry = captured["mcp_registry"]
    assert registry.get("context7").state.value == "ACTIVE"
