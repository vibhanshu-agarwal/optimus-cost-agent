from optimus.acp import __main__ as acp_main
from optimus.acp.preflight import PreflightFailure
from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test


def _base_env(tmp_path) -> dict[str, str]:
    return {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "test-key",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
    }


def _authorize(monkeypatch, tmp_path, env):
    fake_keyring = FakeKeyring()
    authorize_workspace_for_test(env=env, workspace_root=tmp_path, fake_keyring=fake_keyring)
    monkeypatch.setattr(acp_main, "keyring", fake_keyring)
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def test_check_config_uses_preflight_and_exits_zero(monkeypatch, tmp_path):
    env = _base_env(tmp_path)
    _authorize(monkeypatch, tmp_path, env)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "run_preflight", lambda environ, **kwargs: "redis://127.0.0.1:6379/0")

    assert acp_main.main(["--workspace-root", str(tmp_path), "--check-config"]) == 0


def test_check_config_strict_passes_flag_to_preflight(monkeypatch, tmp_path):
    env = _base_env(tmp_path)
    _authorize(monkeypatch, tmp_path, env)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    captured: dict[str, object] = {}

    def _fake_preflight(environ, **kwargs):
        captured.update(kwargs)
        return "redis://127.0.0.1:6379/0"

    monkeypatch.setattr(acp_main, "run_preflight", _fake_preflight)

    assert acp_main.main(["--workspace-root", str(tmp_path), "--check-config", "--strict"]) == 0
    assert captured["strict"] is True
    assert captured["require_timeseries"] is True


def test_check_config_prints_preflight_failure(monkeypatch, tmp_path, capsys):
    env = _base_env(tmp_path)
    _authorize(monkeypatch, tmp_path, env)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(
        acp_main,
        "run_preflight",
        lambda environ, **kwargs: (_ for _ in ()).throw(
            PreflightFailure(exit_code=2, user_message="Redis is not reachable.")
        ),
    )

    assert acp_main.main(["--workspace-root", str(tmp_path), "--check-config"]) == 2
    assert "Redis is not reachable." in capsys.readouterr().err


def test_check_config_without_approval_fails_closed_before_redis_or_preflight(monkeypatch, tmp_path, capsys):
    """Plan 9.96, Task 5: --check-config is gated identically to the serve
    path. An unapproved workspace must fail closed (NO_APPROVAL) BEFORE any
    Redis or preflight probe — proving --check-config is not a bypass door
    around the launch gate."""
    env = _base_env(tmp_path)
    fake_keyring = FakeKeyring()
    monkeypatch.setattr(acp_main, "keyring", fake_keyring)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    redis_calls: list[object] = []
    preflight_calls: list[object] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "run_preflight", lambda *a, **k: preflight_calls.append((a, k)))

    exit_code = acp_main.main(["--workspace-root", str(tmp_path), "--check-config"])

    assert exit_code == 2
    assert redis_calls == []
    assert preflight_calls == []
    err = capsys.readouterr().err
    assert "no launch approval found" in err
    assert "optimus-trust" in err
    assert "approve" in err
