"""#681: neither Gateway launcher puts the provider base URL on the child's command line, which other processes can read.
The manifest binds it by keyed fingerprint; the child still gets the URL from its environment, as it gets the provider key,
and verifies the manifest against it. Both real launchers with a stub child (Popen/run replaced, nothing starts), then the
real Gateway entrypoint on the exact argv and environment captured. Fake keyrings; synthetic values only."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optimus.acp import launch_approval_cli, local_infra
from optimus.acp.local_gateway_secrets import CredentialLayer, CredentialProvenance, ProviderCredentialResolution, ProviderSecrets
from optimus.acp.trusted_paths import TrustedOperatorRoots
from optimus_model_policy.binding import APPROVAL_LITERAL_NAME, trusted_approval_literal
from tests.unit.acp.conftest import FakeKeyring
from tests.unit.acp.test_gateway_attach_wiring import _API_KEY, _KEY, _SECRET, _Keyring, _served_by_real_gateway

_HOST = "gw" + "-synthetic.example"  # no part of any URL below may reach argv
_PW = "synthpw" + "q" * 14
_TOKEN = "synthtok" + "z" * 16
BASE_URLS = {
    "userinfo": f"https://user:{_PW}@{_HOST}/v1",
    "query-token": f"https://{_HOST}/v1?api_key={_TOKEN}",
    "trailing-slash": f"https://{_HOST}/v1/",
    "plain": f"https://{_HOST}/v1",
}


def _assert_argv_clean(argv: list[str]) -> None:
    joined = chr(0).join(argv)
    for part in (_HOST, _PW, _TOKEN):
        assert part not in joined, "a part of the base URL is on the child's command line"
    assert _API_KEY not in joined and _SECRET not in joined, "a Gateway credential is on the child's command line"


@pytest.mark.parametrize("form", sorted(BASE_URLS))
def test_the_acp_launcher_keeps_the_base_url_off_argv_and_its_gateway_still_verifies(monkeypatch, tmp_path: Path, form: str) -> None:
    provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, "test")
    credentials = ProviderCredentialResolution(
        secrets=ProviderSecrets(provider="openrouter", model_provider_api_key=_API_KEY, base_url=BASE_URLS[form]),
        provider_provenance=provenance, api_key_provenance=provenance, base_url_provenance=provenance,
    )
    spawned: dict[str, Any] = {}

    class Child:
        pid = 1
        returncode = None

        def poll(self) -> None:
            return None

    def popen(args: list[str], **kwargs: Any) -> Child:
        spawned.update(argv=args[1:], env=kwargs["env"], stdin=kwargs["stdin"])
        return Child()

    calls = {"n": 0}

    def reachable(*_a: object, **_k: object) -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    monkeypatch.setattr(local_infra.subprocess, "Popen", popen)
    monkeypatch.setattr(local_infra, "_tcp_reachable", reachable)
    monkeypatch.setattr(local_infra, "verify_local_gateway", lambda *_a, **_k: None)  # no listener is contacted
    local_infra.ensure_local_gateway(
        gateway_url="http://127.0.0.1:8765", provider_credentials=credentials, shared_secret=_SECRET, manifest_hmac_key=_KEY,
        workspace_digest="a" * 64, security_snapshot_digest="b" * 64, policy_version="P9.99-v1",
        runtime_root=tmp_path / "runtime", model_registry=trusted_approval_literal(),
    )

    _assert_argv_clean(spawned["argv"])
    assert spawned["stdin"] is local_infra.subprocess.DEVNULL  # an ACP child never inherits the editor's stdin (Windows)
    assert spawned["env"]["OPTIMUS_LOCAL_GATEWAY_BASE_URL"] == BASE_URLS[form]  # the channel the provider key uses
    served = _served_by_real_gateway(monkeypatch, spawned["argv"], spawned["env"], _Keyring())
    assert served.identity is not None


@pytest.mark.parametrize("form", sorted(BASE_URLS))
def test_run_gateway_keeps_the_base_url_off_argv_and_its_gateway_still_verifies(monkeypatch, tmp_path: Path, form: str) -> None:
    workspace, config = tmp_path / "workspace", tmp_path / "config"
    workspace.mkdir()
    (workspace / ".env.gateway").write_text(
        f"OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\nOPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY={_API_KEY}\n"
        f"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET={_SECRET}\nOPTIMUS_LOCAL_GATEWAY_BASE_URL={BASE_URLS[form]}\n",
        encoding="utf-8",
    )
    (workspace / ".env.gateway").chmod(0o600)  # the launch gate refuses anything wider on POSIX
    for name in ("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"):
        monkeypatch.delenv(name, raising=False)
    approved = SimpleNamespace(security_literals={APPROVAL_LITERAL_NAME: trusted_approval_literal()})
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
                                                credential_keyring_backend=keyring) == 0

    _assert_argv_clean(spawned["argv"])
    assert spawned["env"]["OPTIMUS_LOCAL_GATEWAY_BASE_URL"] == BASE_URLS[form]
    served = _served_by_real_gateway(monkeypatch, spawned["argv"], spawned["env"], keyring)
    assert served.identity is not None
