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
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",  # Gateway settings accept loopback only; never contacted here
        "OPTIMUS_API_KEY": "opt-live-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
        "OPTIMUS_REDIS_URL": redis_url,
    }


def test_live_bootstrap_builds_server_with_real_redis_ping(tmp_path, live_redis_store):
    _store, run_id = live_redis_store
    sentinel_key = f"agent:bootstrap:{run_id}:sentinel"

    server = build_configured_server(
        environ=_bootstrap_env(os.environ["OPTIMUS_REDIS_URL"]),
        ephemeral_hmac=True,  # the launch-approval key is the keyring tier's subject; this tier's is Redis
        workspace_root=tmp_path,
        model="anthropic/claude-haiku-5.5",
    )

    async def _sentinel_roundtrip() -> None:
        client = runner_store.redis_client
        await client.set(sentinel_key, "ping-ok")
        assert await client.get(sentinel_key) == "ping-ok"
        await client.delete(sentinel_key)

    # The build started the MCP supervisor and the Redis runtime: both are closed, MCP first, even on a failed assertion.
    try:
        assert server._dispatcher.agent_runner is not None
        assert server._dispatcher.workspace_root == tmp_path.resolve()

        runner_store = server._dispatcher.agent_runner._state_store
        assert isinstance(runner_store, RedisAgentStateStore)
        # Seam 2, checkpoint B: the server retains the runtime the bootstrap built, and the
        # store's client is driven only through that runtime's owner -- never a second loop.
        assert server.redis_runtime is not None
        assert runner_store.redis_client is server.redis_runtime.client
        runner_store.submit(_sentinel_roundtrip)
    finally:
        server.client_mcp_runtime.close()
        record = server.redis_runtime.close(timeout=10.0)
    assert record.is_clean


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
