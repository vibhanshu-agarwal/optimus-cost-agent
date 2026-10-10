"""Plan 12.2 Task 5: `optimus-trust run-gateway` stops on an untrustworthy registry with a typed message."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from optimus.acp import launch_approval_cli
from optimus.acp.trusted_paths import TrustedOperatorRoots
from optimus_model_policy.binding import BindingError
from tests.unit.acp.test_launch_approval_cli import _FakeKeyring, _sys_platform_is_posix


def test_run_gateway_refuses_an_untrustworthy_registry_before_starting_anything(tmp_path, monkeypatch, capsys) -> None:
    env_gateway = tmp_path / ".env.gateway"
    env_gateway.write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"  # pragma: allowlist secret - synthetic test fixture
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-or-test\n"  # pragma: allowlist secret - synthetic test fixture
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=shared-secret\n",  # pragma: allowlist secret - synthetic test fixture
        encoding="utf-8",
    )
    if _sys_platform_is_posix():
        env_gateway.chmod(0o600)

    def refuse() -> str:
        raise BindingError("FIXTURE_POLICY", "a fixture registry cannot be trusted at launch")

    started: list[object] = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args and isinstance(args, list) and "optimus_gateway" in args:
            started.append(args)
        return real_run(args, **kwargs)

    monkeypatch.setattr(launch_approval_cli, "trusted_approval_literal", refuse)
    monkeypatch.setattr("subprocess.run", fake_run)
    with patch("sys.stdin") as stdin, patch("sys.stdout") as stdout:
        stdin.isatty.return_value = True
        stdout.isatty.return_value = True
        result = launch_approval_cli._cmd_run_gateway(
            tmp_path,
            bind_host="127.0.0.1",
            bind_port=8765,
            trusted_roots=TrustedOperatorRoots(default_config_root=tmp_path / "config", approval_runtime_root=tmp_path / "runtime"),
            credential_keyring_backend=_FakeKeyring(),
        )

    assert result == 2
    assert started == []
    err = capsys.readouterr().err
    assert "model registry is not trustworthy (FIXTURE_POLICY)" in err
    assert "a fixture registry" not in err
