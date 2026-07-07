from __future__ import annotations

import os
import time

import pytest

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server
from optimus.agent.state_store import RedisAgentStateStore

pytestmark = pytest.mark.requires_redis

_UNREACHABLE_REDIS_URL = "redis://127.0.0.1:6390/0"
_UNREACHABLE_CONNECT_BUDGET_SECONDS = 5.0


def _bootstrap_env(redis_url: str) -> dict[str, str]:
    return {
        "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
        "OPTIMUS_API_KEY": "opt-live-test",
        "OPTIMUS_REDIS_URL": redis_url,
    }


def test_live_bootstrap_builds_server_with_real_redis_ping(tmp_path, live_redis_store):
    _store, run_id = live_redis_store
    sentinel_key = f"agent:bootstrap:{run_id}:sentinel"

    server = build_configured_server(
        environ=_bootstrap_env(os.environ["OPTIMUS_REDIS_URL"]),
        workspace_root=tmp_path,
        model="glm-5.2",
    )

    assert server is not None
    assert server._dispatcher.agent_runner is not None
    assert server._dispatcher.workspace_root == tmp_path.resolve()

    runner_store = server._dispatcher.agent_runner._state_store
    assert isinstance(runner_store, RedisAgentStateStore)
    client = runner_store._client
    client.set(sentinel_key, "ping-ok")
    assert client.get(sentinel_key) == "ping-ok"
    client.delete(sentinel_key)


def test_live_bootstrap_fails_fast_when_redis_unreachable(tmp_path):
    started = time.monotonic()
    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(
            environ=_bootstrap_env(_UNREACHABLE_REDIS_URL),
            workspace_root=tmp_path,
        )
    elapsed = time.monotonic() - started

    assert exc_info.value.exit_code == 2
    assert "Redis is not reachable" in exc_info.value.user_message
    assert elapsed < _UNREACHABLE_CONNECT_BUDGET_SECONDS


def test_live_bootstrap_rejects_password_redis_url_before_connect(tmp_path):
    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(
            environ=_bootstrap_env("redis://user:secret@127.0.0.1:6379/0"),
            workspace_root=tmp_path,
        )

    assert exc_info.value.exit_code == 2
    assert "must not contain username or password" in exc_info.value.user_message
