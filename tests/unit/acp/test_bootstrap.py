import pytest

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server


def test_bootstrap_reports_missing_optimus_credentials(tmp_path):
    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(environ={"OPTIMUS_REDIS_URL": "redis://localhost:6379/0"}, workspace_root=tmp_path)

    assert exc_info.value.exit_code == 2
    assert exc_info.value.missing_names == ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY")
    assert "Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY" in exc_info.value.user_message


def test_bootstrap_reports_missing_redis_url(tmp_path):
    env = {"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai", "OPTIMUS_API_KEY": "opt-test"}

    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(environ=env, workspace_root=tmp_path)

    assert exc_info.value.missing_names == ("OPTIMUS_REDIS_URL",)
    assert "Set OPTIMUS_REDIS_URL=redis://localhost:6379/0" in exc_info.value.user_message


def test_bootstrap_builds_agent_configured_server(tmp_path, monkeypatch):
    class FakeStore:
        def ping(self):
            return None

    fake_store = FakeStore()
    monkeypatch.setattr("optimus.acp.bootstrap.RedisAgentStateStore.from_url", lambda url, ttl_seconds=3600: fake_store)
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
    class DownRedisStore:
        def ping(self):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr("optimus.acp.bootstrap.RedisAgentStateStore.from_url", lambda url, ttl_seconds=3600: DownRedisStore())

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
