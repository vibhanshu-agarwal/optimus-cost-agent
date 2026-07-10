from __future__ import annotations

import asyncio

import pytest

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.framing import encode_message
from optimus.acp.server import AcpStreamServer
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import RedisAgentStateStore
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.redis.async_bridge import sync_await
from tests.conftest import FakeGatewayClient
from tests.integration.acp.test_server_stream import (
    InteractiveLineReader,
    MemoryLineWriter,
    MemoryReader,
    MemoryWriter,
    decode_framed_response,
)

pytestmark = pytest.mark.requires_redis

_PLAN_TEXT = 'WRITE example.py\ndef f():\n    """Return one."""\n    return 1\n'
_BROKEN_PLAN_TEXT = "WRITE example.py\nBROKEN SECOND PLAN\n"


def _plan_record_key(*, run_id: str, plan_hash: str) -> str:
    return f"agent:plan:{run_id}:{plan_hash}"


def _build_live_server(*, tmp_path, store: RedisAgentStateStore, gateway: FakeGatewayClient) -> AcpStreamServer:
    workspace_root = tmp_path.resolve()
    guard = PreToolGuard.for_workspace(workspace_root=workspace_root, allowed_network_hosts=())
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
    return AcpStreamServer(dispatcher=dispatcher)


async def _roundtrip(server: AcpStreamServer, request: dict) -> dict:
    framed = encode_message(request)
    reader = MemoryReader([framed])
    writer = MemoryWriter()
    await server.handle_one(reader, writer)
    return decode_framed_response(bytes(writer.data))


def _delete_plan_keys(client: object, run_id: str) -> None:
    async def _delete() -> None:
        async for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
            await client.delete(key)

    sync_await(_delete())


@pytest.fixture
def live_redis_acp_server(tmp_path, live_redis_store):
    store, _run_id = live_redis_store
    gateway = FakeGatewayClient(_PLAN_TEXT)
    server = _build_live_server(tmp_path=tmp_path, store=store, gateway=gateway)
    tracked_run_ids: set[str] = set()
    yield server, gateway, tmp_path, store, tracked_run_ids
    for run_id in tracked_run_ids:
        _delete_plan_keys(store.redis_client, run_id)


async def test_live_ndjson_session_prompt_permission_flow_persists_plan_to_redis(live_redis_acp_server):
    server, gateway, tmp_path, store, tracked_run_ids = live_redis_acp_server
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    reader = InteractiveLineReader()
    writer = MemoryLineWriter()
    serve_task = asyncio.create_task(server.serve_ndjson(reader, writer))

    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": True},
                "clientInfo": {"name": "zed", "version": "1.0.0"},
            },
        }
    )
    initialize_response = await writer.wait_for_response(1)
    assert initialize_response["result"]["protocolVersion"] == 1

    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/new",
            "params": {"cwd": str(tmp_path.resolve()), "mcpServers": []},
        }
    )
    session_response = await writer.wait_for_response(2)
    session_id = session_response["result"]["sessionId"]

    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
        }
    )
    permission_request = await writer.wait_for_request("session/request_permission")
    assert permission_request["params"]["sessionId"] == session_id
    plan_hash = permission_request["params"]["options"][0]["metadata"]["planHash"]
    run_id = permission_request["params"]["_meta"]["runId"]
    tracked_run_ids.add(run_id)

    loaded = store.load_plan(run_id=run_id, plan_hash=plan_hash)
    assert loaded.plan_hash == plan_hash
    assert "Return one" in loaded.plan_text

    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": permission_request["id"],
            "result": {
                "outcome": {"outcome": "selected", "optionId": "approve"},
            },
        }
    )
    prompt_response = await writer.wait_for_response(3)

    assert prompt_response["result"]["stopReason"] == "end_turn"
    assert len(gateway.calls) == 1
    assert "Return one" in target.read_text(encoding="utf-8")
    assert "BROKEN SECOND PLAN" not in target.read_text(encoding="utf-8")
    reader.close()
    await serve_task


async def test_live_ndjson_server_restart_replays_approval_on_second_server(live_redis_acp_server):
    server_one, gateway_one, tmp_path, store, tracked_run_ids = live_redis_acp_server
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    reader = InteractiveLineReader()
    writer = MemoryLineWriter()
    serve_task = asyncio.create_task(server_one.serve_ndjson(reader, writer))

    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": True},
                "clientInfo": {"name": "zed", "version": "1.0.0"},
            },
        }
    )
    await writer.wait_for_response(1)
    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/new",
            "params": {"cwd": str(tmp_path.resolve()), "mcpServers": []},
        }
    )
    session_response = await writer.wait_for_response(2)
    session_id = session_response["result"]["sessionId"]
    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
        }
    )
    permission_request = await writer.wait_for_request("session/request_permission")
    plan_hash = permission_request["params"]["options"][0]["metadata"]["planHash"]
    run_id = permission_request["params"]["_meta"]["runId"]
    tracked_run_ids.add(run_id)
    assert len(gateway_one.calls) == 1

    reader.close()
    await asyncio.wait_for(serve_task, timeout=5.0)

    gateway_two = FakeGatewayClient(_BROKEN_PLAN_TEXT)
    server_two = _build_live_server(tmp_path=tmp_path, store=store, gateway=gateway_two)
    approval_response = await _roundtrip(
        server_two,
        {
            "jsonrpc": "2.0",
            "id": "agent-approve-restart",
            "method": "optimus.agent.run",
            "params": {
                "run_id": run_id,
                "task": "Add a docstring",
                "execution_mode": "agent",
                "workspace_root": str(tmp_path.resolve()),
                "approval": {"approved": True, "approval_id": "approval-live-restart", "plan_hash": plan_hash},
            },
        },
    )

    assert approval_response["result"]["status"] == "completed"
    assert gateway_two.calls == []
    assert len(gateway_one.calls) == 1
    assert "Return one" in target.read_text(encoding="utf-8")
    assert "BROKEN SECOND PLAN" not in target.read_text(encoding="utf-8")
