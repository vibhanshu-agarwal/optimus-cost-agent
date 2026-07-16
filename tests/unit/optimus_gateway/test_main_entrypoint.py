"""Tests for the standalone optimus_gateway entrypoint's manifest gate.

Plan 9.96, Task 5 Step 4: The standalone Gateway entrypoint rejects
inherited OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT. The authorized parent passes
code-derived bind host/port as explicit arguments plus a short-lived HMAC
child manifest bound to the approved snapshot; Gateway validates the
manifest against its exact provider/base/credential inputs before
constructing GatewayServiceConfig. Direct unmanifested startup fails closed.
"""

from __future__ import annotations

import base64

import pytest

from optimus_gateway import __main__ as gateway_main
from optimus_security.launch_manifest import build_gateway_child_manifest, serialize_gateway_child_manifest

_HMAC_KEY = b"test-gateway-main-hmac-key-32by!"


class FakeKeyring:
    """In-memory keyring pre-loaded with the manifest HMAC key."""

    def __init__(self, hmac_key: bytes = _HMAC_KEY) -> None:
        self._encoded_key = base64.urlsafe_b64encode(hmac_key).decode("ascii")

    def get_password(self, service: str, key: str) -> str | None:
        if key == "hmac_integrity_key":
            return self._encoded_key
        return None


def _valid_manifest(**overrides: object) -> str:
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
    manifest = build_gateway_child_manifest(**defaults)  # type: ignore[arg-type]
    return serialize_gateway_child_manifest(manifest)


class TestInheritedBindRejection:
    """Inherited bind env vars are rejected before any other startup work."""

    def test_inherited_bind_host_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "0.0.0.0")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "s")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "k")
        exit_code = gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", "irrelevant"])
        assert exit_code == 2

    def test_inherited_port_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PORT", "9999")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "s")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "k")
        exit_code = gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", "irrelevant"])
        assert exit_code == 2

    def test_rejection_happens_before_manifest_validation(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """The inherited-bind rejection message appears, not a manifest error —
        proving the check runs first and stops before any manifest/keyring work."""
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "0.0.0.0")
        exit_code = gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", "garbage-manifest"])
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "inherited bind settings" in captured.err

    def test_missing_manifest_argument_fails_parsing(self) -> None:
        with pytest.raises(SystemExit):
            gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765"])

    def test_missing_bind_host_argument_fails_parsing(self) -> None:
        with pytest.raises(SystemExit):
            gateway_main.main(["--port", "8765", "--manifest", "x"])


class TestManifestValidation:
    """Direct unmanifested startup fails closed."""

    def test_missing_manifest_content_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "shared-secret-value")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "sk-or-test-key")
        monkeypatch.setattr(gateway_main, "_keyring_module", FakeKeyring())
        exit_code = gateway_main.main(
            ["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", "not valid json {{{"]
        )
        assert exit_code == 2

    def test_manifest_credential_mismatch_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "WRONG-SECRET")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "sk-or-test-key")
        monkeypatch.setattr(gateway_main, "_keyring_module", FakeKeyring())
        manifest = _valid_manifest()
        exit_code = gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", manifest])
        assert exit_code == 2

    def test_manifest_bind_mismatch_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "shared-secret-value")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "sk-or-test-key")
        monkeypatch.setattr(gateway_main, "_keyring_module", FakeKeyring())
        manifest = _valid_manifest()
        # Different port than the manifest was signed for.
        exit_code = gateway_main.main(["--bind-host", "127.0.0.1", "--port", "9999", "--manifest", manifest])
        assert exit_code == 2

    def test_manifest_base_url_redirect_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """The base_url-redirect attack at the entrypoint level: a manifest
        signed for one base_url, paired with an env pointing the actually
        constructed GatewayServiceConfig at a different (attacker-controlled)
        base_url, must be rejected — otherwise the provider API key would be
        sent to the redirected endpoint."""
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "shared-secret-value")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "sk-or-test-key")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "openrouter")
        # Redirect the actual config's base_url away from what the manifest signed.
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "https://evil.attacker.example/v1")
        monkeypatch.setattr(gateway_main, "_keyring_module", FakeKeyring())
        manifest = _valid_manifest()  # Signed for https://openrouter.ai/api/v1.

        exit_code = gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", manifest])

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "MANIFEST_BASE_URL_MISMATCH" in captured.err

    def test_manifest_provider_mismatch_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A manifest signed for one provider must not verify against a
        different provider's constructed config, even with matching
        credentials/bind."""
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "shared-secret-value")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-or-test-key")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "anthropic")
        monkeypatch.setattr(gateway_main, "_keyring_module", FakeKeyring())
        manifest = _valid_manifest()  # Signed for provider="openrouter".

        exit_code = gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", manifest])
        assert exit_code == 2

    def test_manifest_missing_keyring_key_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "shared-secret-value")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "sk-or-test-key")

        class EmptyKeyring:
            def get_password(self, service: str, key: str) -> str | None:
                return None

        monkeypatch.setattr(gateway_main, "_keyring_module", EmptyKeyring())
        manifest = _valid_manifest()
        exit_code = gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", manifest])
        assert exit_code == 2

    def test_valid_manifest_with_matching_inputs_passes_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A correct manifest + matching env passes the gate and proceeds to
        server construction (mocked to avoid actually binding a socket)."""
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "shared-secret-value")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "sk-or-test-key")
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "openrouter")
        monkeypatch.setattr(gateway_main, "_keyring_module", FakeKeyring())
        manifest = _valid_manifest()

        class FakeServer:
            server_address = ("127.0.0.1", 8765)

            def serve_forever(self) -> None:
                raise KeyboardInterrupt()

            def shutdown(self) -> None:
                pass

        monkeypatch.setattr(gateway_main, "serve_gateway", lambda *, config: FakeServer())

        exit_code = gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", manifest])
        assert exit_code == 0
