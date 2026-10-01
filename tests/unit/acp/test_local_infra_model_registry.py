"""Plan 12.2 Task 5: the local Gateway launch signs the approved registry literal into its manifest."""

from __future__ import annotations

import json

import pytest

from optimus.acp import local_infra
from optimus.acp.local_gateway_secrets import (
    CredentialLayer,
    CredentialProvenance,
    ProviderCredentialResolution,
    ProviderSecrets,
)

_KEY = b"test-local-infra-registry-key-32!"
_LITERAL = "optimus-model-registry-v1:" + "c" * 64


def _spawned_manifest(tmp_path, monkeypatch: pytest.MonkeyPatch, **extra: object) -> dict:
    calls = {"n": 0}

    def reachable(host, port, *, timeout=1.0):
        calls["n"] += 1
        return calls["n"] > 1

    class _Process:
        pid = 1
        returncode = None

        def poll(self):
            return None

    captured: dict = {}

    def fake_popen(args, *, env, stdin, stdout, stderr):
        captured["args"] = args
        return _Process()

    monkeypatch.setattr(local_infra, "_tcp_reachable", reachable)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(local_infra.subprocess, "Popen", fake_popen)
    provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, "test")
    local_infra.ensure_local_gateway(
        gateway_url="http://127.0.0.1:8765",
        provider_credentials=ProviderCredentialResolution(
            secrets=ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test"),  # pragma: allowlist secret - synthetic test fixture
            provider_provenance=provenance,
            api_key_provenance=provenance,
            base_url_provenance=provenance,
        ),
        shared_secret="shared-secret-value",  # pragma: allowlist secret - synthetic test fixture
        workspace_digest="a" * 64,
        security_snapshot_digest="b" * 64,
        manifest_hmac_key=_KEY,
        policy_version="P9.99-v1",
        runtime_root=tmp_path / ".optimus",
        **extra,
    )
    args = captured["args"]
    return json.loads(args[args.index("--manifest") + 1])


def test_inactive_launch_signs_a_version_one_manifest(tmp_path, monkeypatch) -> None:
    manifest = _spawned_manifest(tmp_path, monkeypatch)
    assert manifest["schema_version"] == 1
    assert "model_registry" not in manifest


def test_active_launch_signs_the_approved_registry(tmp_path, monkeypatch) -> None:
    manifest = _spawned_manifest(tmp_path, monkeypatch, model_registry=_LITERAL)
    assert (manifest["schema_version"], manifest["model_registry"]) == (2, _LITERAL)
