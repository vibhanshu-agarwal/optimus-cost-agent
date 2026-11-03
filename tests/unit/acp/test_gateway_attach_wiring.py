"""#465 through the real entrypoints: what a refused launch runs, and that both sides compose one identity."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import __main__ as acp_main
from optimus.acp import local_infra
from optimus.acp.gateway_refusal import GatewayRefusalServer
from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES
from optimus.acp.local_gateway_secrets import CredentialLayer, CredentialProvenance, ProviderCredentialResolution, ProviderSecrets
from optimus.acp.local_infra import LocalInfrastructureError
from optimus.config.gateway import GATEWAY_IDENTITY_ENVIRON, OptimusGatewaySettings
from optimus_gateway import __main__ as gateway_main
from optimus_model_policy.binding import auto_approval_literal, trusted_approval_literal
from optimus_security import gateway_identity as gi
from optimus_security.launch_manifest import build_gateway_child_manifest, serialize_gateway_child_manifest
from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test

_REFUSAL = LocalInfrastructureError(code="GATEWAY_CONFIGURATION_MISMATCH", user_message="the stated reason")
_ENV = {
    "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
    "OPTIMUS_API_KEY": "test-key",  # pragma: allowlist secret - synthetic test fixture
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
}


@pytest.fixture
def launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, list[Any]]:
    """An authorized launch whose services are recorded. The Gateway step is the test's to set."""
    keyring = FakeKeyring()
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring)
    monkeypatch.setattr(acp_main, "keyring", keyring)
    for name, value in _ENV.items():
        monkeypatch.setenv(name, value)
    seen: dict[str, list[Any]] = {"served": [], "built": [], "preflight": [], "delivery": []}

    async def serving(server: Any, **_kwargs: Any) -> int:
        seen["served"].append(server)
        return 0

    class Delivery:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def start(self) -> None:
            seen["delivery"].append("start")

        def negotiate(self) -> None:
            pass

        def stop(self) -> None:
            pass

    monkeypatch.setattr(acp_main, "_run_serving_process", serving)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *_a, **_k: None)
    monkeypatch.setattr(acp_main, "build_configured_server", lambda **kwargs: seen["built"].append(kwargs) or object())
    monkeypatch.setattr(acp_main, "run_preflight", lambda *_a, **_k: seen["preflight"].append(True))
    monkeypatch.setattr("optimus.usage.capture_delivery.CaptureDelivery", Delivery)
    return seen


def _refuse(**_kwargs: object) -> None:
    raise _REFUSAL


def _refuse_running(*_a: object, **_k: object) -> None:
    raise _REFUSAL


def test_a_refused_launch_serves_only_the_diagnostic_host(launch, monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(acp_main, "ensure_local_gateway", _refuse)
    assert acp_main.main(["--workspace-root", str(tmp_path)]) == 0
    [server] = launch["served"]
    assert isinstance(server, GatewayRefusalServer)
    assert launch["built"] == [] and launch["preflight"] == [] and launch["delivery"] == []
    assert "GATEWAY_CONFIGURATION_MISMATCH: the stated reason" in capsys.readouterr().err


def test_a_launch_that_starts_nothing_is_refused_the_same_way(launch, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(acp_main, "confirm_running_gateway", _refuse_running)
    assert acp_main.main(["--no-auto-start", "--workspace-root", str(tmp_path)]) == 0
    assert isinstance(launch["served"][0], GatewayRefusalServer)
    assert launch["built"] == [] and launch["delivery"] == []


@pytest.mark.parametrize("flags", [["--check-config", "--strict"], ["--check-config", "--strict", "--no-auto-start"]])
def test_strict_check_config_refuses_with_the_reason_before_its_model_probe(launch, monkeypatch, tmp_path, capsys, flags) -> None:
    monkeypatch.setattr(acp_main, "ensure_local_gateway", _refuse)
    monkeypatch.setattr(acp_main, "confirm_running_gateway", _refuse_running)
    assert acp_main.main([*flags, "--workspace-root", str(tmp_path)]) == 2
    assert launch["preflight"] == [] and launch["served"] == []
    assert "the stated reason" in capsys.readouterr().err


def test_plain_check_config_makes_no_request_so_it_needs_no_confirmation(launch, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(acp_main, "ensure_local_gateway", _refuse)
    monkeypatch.setattr(acp_main, "confirm_running_gateway", _refuse_running)
    assert acp_main.main(["--check-config", "--workspace-root", str(tmp_path)]) == 0


def test_a_confirmed_launch_binds_every_request_to_what_it_compared(launch, monkeypatch, tmp_path) -> None:
    compared: list[object] = []
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **kwargs: compared.append(kwargs["expected_identity"]))
    acp_main.main(["--workspace-root", str(tmp_path)])
    environ = launch["built"][0]["environ"]
    identity = compared[0]
    assert isinstance(identity, gi.GatewayIdentity)
    assert environ[GATEWAY_IDENTITY_ENVIRON] == identity.digest
    assert OptimusGatewaySettings.from_env(environ).auth_headers()[gi.HEADER] == identity.digest
    assert launch["delivery"] == ["start"]


def test_settings_with_no_expectation_send_no_binding() -> None:
    settings = OptimusGatewaySettings.from_env({"OPTIMUS_API_KEY": "k"})  # pragma: allowlist secret - synthetic test fixture
    assert gi.HEADER not in settings.auth_headers()


def test_the_binding_is_never_taken_from_the_environment() -> None:
    policy = LAUNCH_VARIABLE_POLICIES[GATEWAY_IDENTITY_ENVIRON]
    assert policy.approval == "reject_inherited"


# --- One identity, composed on each side from its own inputs ----------------------------------------------------------


_KEY = b"test-gateway-attach-wiring-key!!"
_SECRET = "shared-secret-value"  # pragma: allowlist secret - synthetic test fixture
_API_KEY = "sk-or-test-key"  # pragma: allowlist secret - synthetic test fixture
_BASE_URL = "http://127.0.0.1:9/stub/v1"


class _Keyring:
    def get_password(self, _service: str, key: str) -> str | None:
        return base64.urlsafe_b64encode(_KEY).decode("ascii") if key == "hmac_integrity_key" else None


class _Server:
    server_address = ("127.0.0.1", 8765)

    def serve_forever(self) -> None:
        raise KeyboardInterrupt

    def shutdown(self) -> None:
        return None


@pytest.mark.parametrize("auto", [False, True])
def test_what_a_launch_expects_is_what_the_gateway_it_starts_serves(monkeypatch, tmp_path, auto: bool) -> None:
    """The real Gateway entrypoint composes from its verified values, in another package. A drift here would refuse every
    launch's own Gateway, and would be invisible to any test that fakes one side."""
    (tmp_path / ".env.gateway").write_text("OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS=example.com\nTAVILY_API_KEY=tvly\n", encoding="utf-8")
    registry = auto_approval_literal() if auto else trusted_approval_literal()
    accounting_dir, accounting = local_infra.gateway_accounting(tmp_path, None)
    assert accounting_dir is not None
    provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, "test")
    expected = local_infra.expected_gateway_identity(
        gateway_url="http://127.0.0.1:8765",
        provider_credentials=ProviderCredentialResolution(
            secrets=ProviderSecrets(provider="openrouter", model_provider_api_key=_API_KEY, base_url=_BASE_URL),
            provider_provenance=provenance, api_key_provenance=provenance, base_url_provenance=provenance,
        ),
        shared_secret=_SECRET,
        manifest_hmac_key=_KEY,
        config_root=tmp_path,
        model_registry=registry,
        auto_composition=auto,
        usage_accounting=True,
        approved_accounting_config=None,
    )
    assert expected is not None

    for name in ("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "OPTIMUS_LOCAL_GATEWAY_PORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", _SECRET)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", _API_KEY)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_BASE_URL", _BASE_URL)
    # What `ensure_local_gateway` projects into the child.
    monkeypatch.setenv("OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS", "example.com")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly")
    monkeypatch.setattr(gateway_main, "_keyring_module", _Keyring())
    configs: list[Any] = []

    def serving(*, config: Any) -> _Server:
        configs.append(config)
        return _Server()

    monkeypatch.setattr(gateway_main, "serve_gateway", serving)
    manifest = build_gateway_child_manifest(
        workspace_digest="a" * 64, security_snapshot_digest="b" * 64, provider="openrouter", base_url=_BASE_URL,
        bind_host="127.0.0.1", bind_port=8765, provider_api_key=_API_KEY, shared_secret=_SECRET, hmac_key=_KEY,
        policy_version="P9.99-v1", model_registry=registry, accounting=accounting,
    )
    argv = ["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", serialize_gateway_child_manifest(manifest),
            "--accounting-root", str(accounting_dir), *(["--auto-composition"] if auto else [])]
    assert gateway_main.main(argv) == 0
    served = configs[0].local_identity
    assert served.identity == expected
    nonce = gi.new_nonce()
    assert gi.read_reply(json.loads(json.dumps(served.reply(nonce))), nonce=nonce, hmac_key=_KEY) == expected
