from __future__ import annotations

import os

import pytest

from optimus.acp.bootstrap import build_configured_server

pytestmark = pytest.mark.requires_redis


def test_live_bootstrap_builds_server_with_real_redis_ping(tmp_path, live_redis_store):
    _store, _run_id = live_redis_store
    server = build_configured_server(
        environ={
            "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
            "OPTIMUS_API_KEY": "opt-live-test",
            "OPTIMUS_REDIS_URL": os.environ["OPTIMUS_REDIS_URL"],
        },
        workspace_root=tmp_path,
        model="glm-5.2",
    )

    assert server is not None
    assert server._dispatcher.agent_runner is not None
    assert server._dispatcher.workspace_root == tmp_path.resolve()
