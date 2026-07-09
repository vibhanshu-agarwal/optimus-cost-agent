from optimus.acp import __main__ as acp_main
from optimus.acp.preflight import PreflightFailure


def _patch_check_config_infra(monkeypatch) -> None:
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        },
    )
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)


def test_check_config_uses_preflight_and_exits_zero(monkeypatch, tmp_path):
    _patch_check_config_infra(monkeypatch)
    monkeypatch.setattr(
        acp_main,
        "run_preflight",
        lambda environ, **kwargs: "redis://127.0.0.1:6379/0",
    )

    assert acp_main.main(["--workspace-root", str(tmp_path), "--check-config"]) == 0


def test_check_config_strict_passes_flag_to_preflight(monkeypatch, tmp_path):
    _patch_check_config_infra(monkeypatch)
    captured: dict[str, object] = {}

    def _fake_preflight(environ, **kwargs):
        captured.update(kwargs)
        return "redis://127.0.0.1:6379/0"

    monkeypatch.setattr(acp_main, "run_preflight", _fake_preflight)

    assert acp_main.main(["--workspace-root", str(tmp_path), "--check-config", "--strict"]) == 0
    assert captured["strict"] is True
    assert captured["require_timeseries"] is True


def test_check_config_prints_preflight_failure(monkeypatch, tmp_path, capsys):
    _patch_check_config_infra(monkeypatch)
    monkeypatch.setattr(
        acp_main,
        "run_preflight",
        lambda environ, **kwargs: (_ for _ in ()).throw(
            PreflightFailure(exit_code=2, user_message="Redis is not reachable.")
        ),
    )

    assert acp_main.main(["--workspace-root", str(tmp_path), "--check-config"]) == 2
    assert "Redis is not reachable." in capsys.readouterr().err
