import pytest

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server
from optimus.acp.preflight import PreflightFailure


def test_bootstrap_reports_missing_optimus_credentials(tmp_path):
    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(environ={"OPTIMUS_REDIS_URL": "redis://localhost:6379/0"}, workspace_root=tmp_path)

    assert exc_info.value.exit_code == 2
    assert "Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY" in exc_info.value.user_message


def test_bootstrap_reports_missing_redis_url(tmp_path):
    env = {"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai", "OPTIMUS_API_KEY": "opt-test"}

    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(environ=env, workspace_root=tmp_path)

    assert exc_info.value.exit_code == 2
    assert "Set OPTIMUS_REDIS_URL" in exc_info.value.user_message


def test_bootstrap_builds_agent_configured_server(tmp_path, monkeypatch):
    class FakeStore:
        def ping(self):
            return None

    class FakeRuntime:
        def ping(self):
            return None

        def sync_state_store(self):
            return FakeStore()

        def telemetry_adapter(self):
            return object()

    monkeypatch.setattr(
        "optimus.acp.preflight.run_preflight",
        lambda environ, **kwargs: "redis://localhost:6379/0",
    )
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRuntime())
    server = build_configured_server(
        environ={
            "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
            "OPTIMUS_API_KEY": "opt-test",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
        workspace_root=tmp_path,
        model="glm-5.2",
    )

    assert server is not None


def test_bootstrap_reports_unreachable_redis(tmp_path, monkeypatch):
    def _raise_unreachable(*args, **kwargs):
        raise PreflightFailure(exit_code=2, user_message="Redis is not reachable.")

    monkeypatch.setattr("optimus.acp.preflight.run_preflight", _raise_unreachable)

    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(
            environ={
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt-test",
                "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
            },
            workspace_root=tmp_path,
        )

    assert exc_info.value.exit_code == 2
    assert "Redis is not reachable" in exc_info.value.user_message
