"""#465 through the real entrypoints: what a refused launch runs, and that both sides compose one identity."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optimus.acp import __main__ as acp_main
from optimus.acp import launch_approval_cli, local_infra
from optimus.acp.gateway_refusal import GatewayRefusalServer
from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES
from optimus.acp.local_gateway_secrets import CredentialLayer, CredentialProvenance, ProviderCredentialResolution, ProviderSecrets
from optimus.acp.local_infra import LocalInfrastructureError
from optimus.acp.trusted_paths import TrustedOperatorRoots
from optimus.config.gateway import GATEWAY_IDENTITY_ENVIRON, OptimusGatewaySettings
from optimus_gateway import __main__ as gateway_main
from optimus_model_policy.binding import (
    APPROVAL_LITERAL_NAME,
    AUTO_COMPOSITION,
    COMPOSITION_LITERAL_NAME,
    auto_approval_literal,
    trusted_approval_literal,
)
from optimus_security import gateway_identity as gi
from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test

_REFUSAL = LocalInfrastructureError(code="GATEWAY_CONFIGURATION_MISMATCH", user_message="the stated reason")
_ENV = {
    "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
    "OPTIMUS_API_KEY": "test-key",  # pragma: allowlist secret - synthetic test fixture
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
    # Named here because the environment outranks the keyring: without them, a developer machine's real credentials decide.
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter",
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-test-key",  # pragma: allowlist secret - synthetic test fixture
    "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret-value",  # pragma: allowlist secret - synthetic test fixture
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


def _credentials() -> ProviderCredentialResolution:
    provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, "test")
    return ProviderCredentialResolution(
        secrets=ProviderSecrets(provider="openrouter", model_provider_api_key=_API_KEY, base_url=_BASE_URL),
        provider_provenance=provenance, api_key_provenance=provenance, base_url_provenance=provenance,
    )


def _served_by_real_gateway(monkeypatch: pytest.MonkeyPatch, argv: list[str], env: dict[str, str], keyring: Any) -> gi.ServedIdentity:
    """Run the real Gateway entrypoint on the exact arguments and environment a parent gave its child."""
    assert argv[:2] == ["-m", "optimus_gateway"]
    for name in ("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "OPTIMUS_LOCAL_GATEWAY_PORT", "OPTIMUS_LOCAL_GATEWAY_BASE_URL",
                 *gi.TOOL_POLICY_NAMES):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(gateway_main, "_keyring_module", keyring)
    configs: list[Any] = []

    def serving(*, config: Any) -> _Server:
        configs.append(config)
        return _Server()

    monkeypatch.setattr(gateway_main, "serve_gateway", serving)
    assert gateway_main.main(argv[2:]) == 0
    return configs[0].local_identity


@pytest.mark.parametrize("auto", [False, True])
def test_what_a_launch_expects_is_what_the_gateway_it_starts_serves(monkeypatch, tmp_path, auto: bool) -> None:
    """The child's real arguments and environment, into the real Gateway entrypoint. A drift here would refuse every launch's
    own Gateway, and is invisible to a test that builds either side by hand."""
    (tmp_path / ".env.gateway").write_text("OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS=example.com\nTAVILY_API_KEY=tvly\n", encoding="utf-8")
    inherited = {"OPTIMUS_GATEWAY_TOOL_MAX_CALLS_PER_TOOL": "2"}
    launch_inputs: dict[str, Any] = {
        "gateway_url": "http://127.0.0.1:8765", "provider_credentials": _credentials(), "shared_secret": _SECRET,
        "manifest_hmac_key": _KEY, "system_env": inherited, "config_root": tmp_path,
        "model_registry": auto_approval_literal() if auto else trusted_approval_literal(),
        "auto_composition": auto, "usage_accounting": True, "approved_accounting_config": None,
    }
    expected = local_infra.expected_gateway_identity(**launch_inputs)
    assert expected is not None

    spawned: dict[str, Any] = {}

    class Child:
        pid = 1
        returncode = None

        def poll(self) -> None:
            return None

    def popen(args: list[str], **kwargs: Any) -> Child:
        spawned.update(argv=args[1:], env=kwargs["env"])
        return Child()

    calls = {"n": 0}

    def reachable(*_a: object, **_k: object) -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    monkeypatch.setattr(local_infra.subprocess, "Popen", popen)
    monkeypatch.setattr(local_infra, "_tcp_reachable", reachable)
    monkeypatch.setattr(local_infra, "verify_local_gateway", lambda *_a, **_k: None)
    local_infra.ensure_local_gateway(**launch_inputs, workspace_digest="a" * 64, security_snapshot_digest="b" * 64,
                                     policy_version="P9.99-v1", runtime_root=tmp_path / "runtime", expected_identity=expected)

    served = _served_by_real_gateway(monkeypatch, spawned["argv"], spawned["env"], _Keyring())
    assert served.identity == expected
    nonce = gi.new_nonce()
    assert gi.read_reply(json.loads(json.dumps(served.reply(nonce))), nonce=nonce, hmac_key=_KEY) == expected


@pytest.mark.parametrize("auto", [False, True])
def test_an_agent_under_the_same_approval_can_reuse_what_run_gateway_starts(monkeypatch, tmp_path, auto: bool) -> None:
    """The documented persistent-Gateway flow. A tool setting from the shell, not the file, was the difference Codex found."""
    # run-gateway reads the workspace's file and an agent its operator config root's; they must say the same.
    workspace, config = tmp_path / "workspace", tmp_path / "config"
    for root in (workspace, config):
        root.mkdir()
        (root / ".env.gateway").write_text(
            f"OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\nOPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY={_API_KEY}\n"
            f"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET={_SECRET}\nOPTIMUS_LOCAL_GATEWAY_BASE_URL={_BASE_URL}\n"
            "OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS=example.com\n",
            encoding="utf-8",
        )
        (root / ".env.gateway").chmod(0o600)  # the launch gate refuses anything wider on POSIX
    monkeypatch.setenv("OPTIMUS_GATEWAY_TOOL_MAX_CALLS_PER_TOOL", "2")
    registry = auto_approval_literal() if auto else trusted_approval_literal()
    approved = SimpleNamespace(security_literals={
        APPROVAL_LITERAL_NAME: registry, **({COMPOSITION_LITERAL_NAME: AUTO_COMPOSITION} if auto else {}),
    })
    monkeypatch.setattr(launch_approval_cli.KeyringApprovalStore, "read_durable", lambda self, digest: approved)
    keyring = FakeKeyring()
    roots = TrustedOperatorRoots(default_config_root=config, approval_runtime_root=tmp_path / "runtime")
    spawned: dict[str, Any] = {}

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        spawned.update(argv=args[1:], env=kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(launch_approval_cli.subprocess, "run", run)
    monkeypatch.setattr(launch_approval_cli, "_require_tty", lambda: None)
    assert launch_approval_cli._cmd_run_gateway(workspace, bind_host="127.0.0.1", bind_port=8765, trusted_roots=roots,
                                                credential_keyring_backend=keyring, auto=auto) == 0

    key = launch_approval_cli.KeyringApprovalStore(keyring_backend=keyring, runtime_root=roots.approval_runtime_root).hmac_key
    expected = local_infra.expected_gateway_identity(
        gateway_url="http://127.0.0.1:8765", provider_credentials=_credentials(), shared_secret=_SECRET, manifest_hmac_key=key,
        system_env={"OPTIMUS_GATEWAY_TOOL_MAX_CALLS_PER_TOOL": "2"}, config_root=config, model_registry=registry,
        auto_composition=auto, usage_accounting=True, approved_accounting_config=None,
    )
    assert expected is not None
    assert _served_by_real_gateway(monkeypatch, spawned["argv"], spawned["env"], keyring).identity == expected
