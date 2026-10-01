"""Plan 12.2 Task 5: Gateway startup composes the trusted registry and checks it against the manifest.

While enforcement is inactive the Gateway composes nothing and starts with today's routing from a
version-1 manifest. Once a trusted snapshot exists, the signed manifest must bind exactly that
snapshot's approval literal or the Gateway refuses to start; a registry that cannot be trusted also
stops startup.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from optimus_gateway import __main__ as gateway_main
from optimus_model_policy.binding import BindingError, approval_literal
from optimus_security.launch_manifest import build_gateway_child_manifest, serialize_gateway_child_manifest
from tests.unit.optimus_gateway.model_policy_support import verified_snapshot

_KEY = b"test-gateway-main-registry-key!!"
_SECRET = "shared-secret-value"  # pragma: allowlist secret - synthetic test fixture
_API_KEY = "sk-or-test-key"  # pragma: allowlist secret - synthetic test fixture


class _Keyring:
    def get_password(self, service: str, key: str) -> str | None:
        return base64.urlsafe_b64encode(_KEY).decode("ascii") if key == "hmac_integrity_key" else None


class _Server:
    server_address = ("127.0.0.1", 8765)

    def serve_forever(self) -> None:
        raise KeyboardInterrupt

    def shutdown(self) -> None:
        return None


def _manifest(model_registry: str | None) -> str:
    manifest = build_gateway_child_manifest(
        workspace_digest="a" * 64,
        security_snapshot_digest="b" * 64,
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        bind_host="127.0.0.1",
        bind_port=8765,
        provider_api_key=_API_KEY,
        shared_secret=_SECRET,
        hmac_key=_KEY,
        policy_version="P9.99-v1",
        model_registry=model_registry,
    )
    return serialize_gateway_child_manifest(manifest)


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list:
    for name in ("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "OPTIMUS_LOCAL_GATEWAY_PORT", "OPTIMUS_LOCAL_GATEWAY_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", _SECRET)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", _API_KEY)
    monkeypatch.setattr(gateway_main, "_keyring_module", _Keyring())
    configs: list = []

    def fake_serve(*, config):
        configs.append(config)
        return _Server()

    monkeypatch.setattr(gateway_main, "serve_gateway", fake_serve)
    return configs


def _run(manifest: str) -> int:
    return gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", manifest])


def test_inactive_gateway_starts_with_todays_routing(started: list) -> None:
    assert _run(_manifest(None)) == 0
    assert started[0].model_policy is None


def test_inactive_gateway_refuses_a_manifest_that_binds_a_registry(started: list, capsys) -> None:
    assert _run(_manifest("optimus-model-registry-v1:" + "c" * 64)) == 2
    assert "MANIFEST_MODEL_REGISTRY_MISMATCH" in capsys.readouterr().err
    assert started == []


def test_active_gateway_enforces_the_registry_the_manifest_binds(started: list, monkeypatch, tmp_path: Path) -> None:
    snapshot = verified_snapshot(tmp_path)
    monkeypatch.setattr(gateway_main, "trusted_snapshot", lambda: snapshot)
    assert _run(_manifest(approval_literal(snapshot))) == 0
    policy = started[0].model_policy
    assert policy is not None
    assert policy.snapshot.effective_hash == policy.approved_hash == snapshot.effective_hash


@pytest.mark.parametrize("signed", [None, "optimus-model-registry-v1:" + "d" * 64])
def test_active_gateway_refuses_a_manifest_for_no_or_another_registry(started: list, monkeypatch, tmp_path: Path, capsys, signed) -> None:
    snapshot = verified_snapshot(tmp_path)
    monkeypatch.setattr(gateway_main, "trusted_snapshot", lambda: snapshot)
    assert _run(_manifest(signed)) == 2
    assert "MANIFEST_MODEL_REGISTRY_MISMATCH" in capsys.readouterr().err
    assert started == []


def test_an_untrustworthy_registry_stops_startup(started: list, monkeypatch, capsys) -> None:
    def refuse():
        raise BindingError("FIXTURE_POLICY")

    monkeypatch.setattr(gateway_main, "trusted_snapshot", refuse)
    assert _run(_manifest(None)) == 2
    assert "FIXTURE_POLICY" in capsys.readouterr().err
    assert started == []
