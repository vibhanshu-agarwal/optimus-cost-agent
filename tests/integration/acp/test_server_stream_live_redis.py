from __future__ import annotations

import os

import pytest

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.framing import encode_message
from optimus.acp.server import AcpStreamServer
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import RedisAgentStateStore
from optimus.guardrails.pre_tool import PreToolGuard
from tests.conftest import FakeGatewayClient
from tests.integration.acp.test_server_stream import MemoryReader, MemoryWriter, decode_framed_response

pytestmark = pytest.mark.requires_redis


async def roundtrip(server: AcpStreamServer, request: dict) -> dict:
    framed = encode_message(request)
    reader = MemoryReader([framed])
    writer = MemoryWriter()
    await server.handle_one(reader, writer)
    return decode_framed_response(bytes(writer.data))


@pytest.fixture
def live_redis_acp_server(tmp_path, live_redis_store):
    _store, _run_id = live_redis_store
    workspace_root = tmp_path.resolve()
    gateway = FakeGatewayClient('WRITE example.py\ndef f():\n    """Return one."""\n    return 1\n')
    guard = PreToolGuard.for_workspace(workspace_root=workspace_root, allowed_network_hosts=())
    store = RedisAgentStateStore.from_url(os.environ["OPTIMUS_REDIS_URL"])
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        guard=guard,
        state_store=store,
    )
    dispatcher = JsonRpcDispatcher(
        gateway_client=gateway,
        agent_runner=runner,
        pre_tool_guard=guard,
        workspace_root=workspace_root,
    )
    server = AcpStreamServer(dispatcher=dispatcher)
    yield server, gateway, tmp_path, store
    run_ids = {"run-live-acp-1"}
    client = store._client
    for run_id in run_ids:
        for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
            client.delete(key)


async def test_live_framed_acp_agent_approval_replay_uses_redis(live_redis_acp_server):
    server, gateway, tmp_path, _store = live_redis_acp_server
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    workspace = str(tmp_path.resolve())

    first = await roundtrip(
        server,
        {
            "jsonrpc": "2.0",
            "id": "agent-plan",
            "method": "optimus.agent.run",
            "params": {
                "run_id": "run-live-acp-1",
                "task": "Add a docstring",
                "execution_mode": "agent",
                "workspace_root": workspace,
            },
        },
    )
    assert first["result"]["status"] == "awaiting_approval"
    plan_hash = first["result"]["plan_hash"]

    gateway.output_text = "WRITE example.py\nBROKEN SECOND PLAN\n"
    second = await roundtrip(
        server,
        {
            "jsonrpc": "2.0",
            "id": "agent-approve",
            "method": "optimus.agent.run",
            "params": {
                "run_id": "run-live-acp-1",
                "task": "Add a docstring",
                "execution_mode": "agent",
                "workspace_root": workspace,
                "approval": {"approved": True, "approval_id": "approval-live-1", "plan_hash": plan_hash},
            },
        },
    )

    assert second["result"]["status"] == "completed"
    assert len(gateway.calls) == 1
    assert "Return one" in target.read_text(encoding="utf-8")
