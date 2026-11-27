"""#669: an API key pasted into the provider variable never reaches the refusal that agent start prints to stderr (kept
in the IDE's log). Fake keyring only; synthetic values."""

from __future__ import annotations

from pathlib import Path

import pytest

from optimus.acp.launch_gate import LaunchEnvironmentSnapshot, LaunchGateError, resolve_launch_candidate
from tests.unit.acp.test_launch_gate import (
    _HMAC_KEY,
    _REQUIRED_LAUNCH_ENV,
    _sample_operator_paths,
    _sample_workspace_identity,
)

_PASTED_KEY = "sk-or-v1-" + "a" * 24  # key-shaped, synthetic
_PROVIDER_VAR = "OPTIMUS_LOCAL_GATEWAY_PROVIDER"


class _Store:
    def __init__(self, entries: dict[str, str]) -> None:
        self.entries = entries

    def get_password(self, _service: str, key: str) -> str | None:
        return self.entries.get(key)


@pytest.mark.parametrize("layer", ["environment", "config_file", "keyring"])
def test_a_key_in_the_provider_variable_is_never_echoed(tmp_path: Path, layer: str) -> None:
    paths = _sample_operator_paths(tmp_path)
    env = dict(_REQUIRED_LAUNCH_ENV)
    store = _Store({})
    if layer == "environment":
        env[_PROVIDER_VAR] = _PASTED_KEY
    elif layer == "config_file":
        paths.config_root.mkdir(parents=True)
        env_gateway = paths.config_root / ".env.gateway"
        env_gateway.write_text(f"{_PROVIDER_VAR}={_PASTED_KEY}\n", encoding="utf-8")
        env_gateway.chmod(0o600)  # owner-only, or POSIX refuses on permissions first (Codex #669 M1)
    else:
        store = _Store({"model_provider": _PASTED_KEY})

    with pytest.raises(LaunchGateError) as caught:
        resolve_launch_candidate(
            snapshot=LaunchEnvironmentSnapshot.capture(env),
            workspace_identity=_sample_workspace_identity(),
            operator_paths=paths,
            hmac_key=_HMAC_KEY,
            credential_keyring_backend=store,
        )
    exc = caught.value
    assert exc.code == "GATEWAY_PROVIDER_UNSUPPORTED"
    # What __main__ prints (code and detail), and the resolver message run-gateway prints (the cause's user_message).
    for surface in (exc.detail, str(exc), str(exc.__cause__)):
        assert _PASTED_KEY not in surface and _PASTED_KEY[:12] not in surface
    source = {"environment": "the environment", "config_file": ".env.gateway", "keyring": "the OS keychain"}[layer]
    for message in (exc.detail, exc.__cause__.user_message):
        assert f"{_PROVIDER_VAR} from {source} " in message and "openrouter" in message, message


def test_agent_start_prints_the_refusal_without_the_value(monkeypatch, tmp_path: Path, capsys) -> None:
    """The real stderr surface: __main__'s LaunchGateError handler (what Zed keeps in its log)."""
    from optimus.acp import __main__ as acp_main
    from tests.unit.acp.conftest import FakeKeyring
    from tests.unit.acp.test_main_wiring import _base_env

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(tmp_path / "config"))
    for name, value in {**_base_env(), _PROVIDER_VAR: _PASTED_KEY}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(acp_main, "keyring", FakeKeyring())
    started: list[str] = []
    for starter in ("ensure_local_redis", "ensure_local_gateway", "build_configured_server"):
        monkeypatch.setattr(acp_main, starter, lambda *_a, _n=starter, **_k: started.append(_n))

    assert acp_main.main(["--workspace-root", str(workspace)]) == 2
    err = capsys.readouterr().err
    assert "GATEWAY_PROVIDER_UNSUPPORTED" in err and _PROVIDER_VAR in err, err
    assert _PASTED_KEY not in err and _PASTED_KEY[:12] not in err
    assert started == []


def test_run_gateway_prints_the_refusal_without_the_value(monkeypatch, tmp_path: Path, capsys) -> None:
    from optimus.acp import launch_approval_cli
    from optimus.acp.launch_approval_cli import _cmd_run_gateway
    from optimus.acp.trusted_paths import TrustedOperatorRoots

    env_gateway = tmp_path / ".env.gateway"
    env_gateway.write_text(f"{_PROVIDER_VAR}={_PASTED_KEY}\n", encoding="utf-8")
    env_gateway.chmod(0o600)
    monkeypatch.setattr(launch_approval_cli, "_require_tty", lambda: None)

    result = _cmd_run_gateway(
        tmp_path,
        bind_host="127.0.0.1",
        bind_port=8765,
        trusted_roots=TrustedOperatorRoots(
            default_config_root=tmp_path.parent / (tmp_path.name + "-config"), approval_runtime_root=tmp_path / "runtime"
        ),
        credential_keyring_backend=_Store({}),
    )
    err = capsys.readouterr().err
    assert result == 2
    assert "optimus-trust run-gateway:" in err and _PROVIDER_VAR in err, err
    assert _PASTED_KEY not in err and _PASTED_KEY[:12] not in err
