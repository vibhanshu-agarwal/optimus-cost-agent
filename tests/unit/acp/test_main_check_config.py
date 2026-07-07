from optimus.acp import __main__ as acp_main
from optimus.acp.preflight import PreflightFailure


def test_check_config_uses_preflight_and_exits_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(
        acp_main,
        "run_preflight",
        lambda environ, **kwargs: "redis://127.0.0.1:6379/0",
    )

    assert acp_main.main(["--workspace-root", str(tmp_path), "--check-config"]) == 0


def test_check_config_strict_passes_flag_to_preflight(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def _fake_preflight(environ, **kwargs):
        captured.update(kwargs)
        return "redis://127.0.0.1:6379/0"

    monkeypatch.setattr(acp_main, "run_preflight", _fake_preflight)

    assert acp_main.main(["--workspace-root", str(tmp_path), "--check-config", "--strict"]) == 0
    assert captured["strict"] is True
    assert captured["require_timeseries"] is True


def test_check_config_prints_preflight_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        acp_main,
        "run_preflight",
        lambda environ, **kwargs: (_ for _ in ()).throw(
            PreflightFailure(exit_code=2, user_message="Redis is not reachable.")
        ),
    )

    assert acp_main.main(["--workspace-root", str(tmp_path), "--check-config"]) == 2
    assert "Redis is not reachable." in capsys.readouterr().err
