import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from optimus.acp import errors
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import PARSE_ERROR
from optimus.acp.framing import encode_message
from optimus.acp.server import AcpStreamServer
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard


class MemoryReader:
    """Test fake for optimus.acp.server.AsyncByteReader.

    Replays scripted byte chunks so integration tests can feed fragmented input
    without a real stdin/socket. Production uses asyncio.StreamReader instead.
    """

    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, size: int) -> bytes:
        # Match stream semantics: return up to size bytes; b"" means EOF.
        await asyncio.sleep(0)
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if len(chunk) <= size:
            return chunk
        self._chunks.insert(0, chunk[size:])
        return chunk[:size]


class MemoryWriter:
    """Test fake for optimus.acp.server.AsyncByteWriter.

    Captures framed response bytes in memory for assertions. Production would
    write to stdout (or another stream) and await drain() to flush.
    """

    def __init__(self):
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)


def decode_framed_response(data: bytes) -> dict:
    _, body = data.split(b"\r\n\r\n", 1)
    return json.loads(body.decode("utf-8"))


def decode_all_framed_responses(data: bytes) -> list[dict]:
    responses: list[dict] = []
    offset = 0
    while offset < len(data):
        header_end = data.find(b"\r\n\r\n", offset)
        if header_end < 0:
            break
        header = data[offset:header_end]
        length = int(header.decode("ascii").split(":", 1)[1].strip())
        body_start = header_end + 4
        body_end = body_start + length
        responses.append(json.loads(data[body_start:body_end].decode("utf-8")))
        offset = body_end
    return responses


async def test_stream_handler_handles_fragmented_ping():
    framed = encode_message({"jsonrpc": "2.0", "id": 1, "method": "optimus.ping"})
    reader = MemoryReader([framed[:2], framed[2:9], framed[9:]])
    writer = MemoryWriter()

    await AcpStreamServer().handle_one(reader, writer)

    assert decode_framed_response(bytes(writer.data)) == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"message": "pong"},
    }


async def test_stream_handler_maps_framing_error_to_json_rpc_error():
    reader = MemoryReader([b"Content-Length: 1\r\n\r\n{"])
    writer = MemoryWriter()

    await AcpStreamServer().handle_one(reader, writer)

    response = decode_framed_response(bytes(writer.data))
    assert response["id"] is None
    assert response["error"]["code"] == PARSE_ERROR
    assert response["error"]["message"] == "invalid JSON body"


async def test_serve_handles_two_framed_ping_messages_before_eof():
    framed_one = encode_message({"jsonrpc": "2.0", "id": 1, "method": "optimus.ping"})
    framed_two = encode_message({"jsonrpc": "2.0", "id": 2, "method": "optimus.ping"})
    reader = MemoryReader([framed_one, framed_two, b""])
    writer = MemoryWriter()
    server = AcpStreamServer()

    await server.serve(reader, writer)

    responses = decode_all_framed_responses(bytes(writer.data))
    assert len(responses) == 2
    assert responses[0]["result"]["message"] == "pong"
    assert responses[1]["id"] == 2


async def test_serve_exits_cleanly_on_eof_after_framing_error():
    reader = MemoryReader([b"Content-Length: 1\r\n\r\n{", b""])
    writer = MemoryWriter()
    server = AcpStreamServer()

    await server.serve(reader, writer)

    responses = decode_all_framed_responses(bytes(writer.data))
    assert len(responses) == 1
    assert responses[0]["error"]["message"] == "invalid JSON body"


class FakeGatewayClient:
    def __init__(self, output_text: str = "Plan text") -> None:
        self.calls: list[dict[str, Any]] = []
        self.output_text = output_text

    def create_response(self, *, model: str, input_text: str, metadata=None):
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        return GatewayResponse(
            response_id="resp-1",
            output_text=self.output_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                billing_units=5,
                cost_usd=Decimal("0.002"),
            ),
            raw={"id": "resp-1"},
        )


@dataclass
class ConfiguredTestAgentServer:
    server: AcpStreamServer
    gateway: FakeGatewayClient

    @property
    def fake_gateway_call_count(self) -> int:
        return len(self.gateway.calls)


def configured_test_agent_server(tmp_path: Path, *, output_text: str) -> ConfiguredTestAgentServer:
    workspace_root = tmp_path.resolve()
    gateway = FakeGatewayClient(output_text)
    guard = PreToolGuard.for_workspace(workspace_root=workspace_root, allowed_network_hosts=())
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        guard=guard,
        state_store=InMemoryAgentStateStore(),
    )
    dispatcher = JsonRpcDispatcher(
        gateway_client=gateway,
        agent_runner=runner,
        pre_tool_guard=guard,
        workspace_root=workspace_root,
    )
    return ConfiguredTestAgentServer(server=AcpStreamServer(dispatcher=dispatcher), gateway=gateway)


async def roundtrip(server: AcpStreamServer, request: dict[str, Any]) -> dict[str, Any]:
    framed = encode_message(request)
    reader = MemoryReader([framed])
    writer = MemoryWriter()
    await server.handle_one(reader, writer)
    return decode_framed_response(bytes(writer.data))


class InteractiveLineReader:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def readline(self) -> bytes:
        line = await self._queue.get()
        return b"" if line is None else line

    async def send(self, message: Mapping[str, Any]) -> None:
        await self._queue.put((json.dumps(message) + "\n").encode("utf-8"))

    def close(self) -> None:
        self._queue.put_nowait(None)


class MemoryLineWriter:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._response_events: dict[str | int, asyncio.Event] = {}
        self._request_events: dict[str, asyncio.Event] = {}

    async def write_line(self, message: Mapping[str, Any]) -> None:
        payload = dict(message)
        self.messages.append(payload)
        request_id = payload.get("id")
        if request_id is None:
            return
        if "result" in payload or "error" in payload:
            event = self._response_events.setdefault(request_id, asyncio.Event())
            event.set()
            return
        if "method" in payload:
            method = str(payload["method"])
            event = self._request_events.setdefault(method, asyncio.Event())
            event.set()

    async def wait_for_response(self, request_id: str | int) -> dict[str, Any]:
        while True:
            for message in self.messages:
                if message.get("id") == request_id and ("result" in message or "error" in message):
                    return message
            event = self._response_events.setdefault(request_id, asyncio.Event())
            event.clear()
            await event.wait()

    async def wait_for_request(self, method: str) -> dict[str, Any]:
        while True:
            for message in self.messages:
                if message.get("method") == method and "result" not in message and "error" not in message:
                    return message
            event = self._request_events.setdefault(method, asyncio.Event())
            event.clear()
            await event.wait()


async def test_stream_handler_runs_agent_plan_mode_through_framed_acp(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\nExplain it.")
    request = {
        "jsonrpc": "2.0",
        "id": "agent-plan",
        "method": "optimus.agent.run",
        "params": {
            "run_id": "run-1",
            "task": "Explain example.py",
            "execution_mode": "plan",
            "workspace_root": str(tmp_path.resolve()),
        },
    }

    response = await roundtrip(configured.server, request)

    assert response["result"]["status"] == "completed"
    assert response["result"]["tool_calls"][0]["tool_name"] == "file_reader"
    assert isinstance(response["result"]["total_cost_usd"], str)


async def test_stream_handler_approved_agent_run_replays_plan_without_second_gateway_call(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    output_text = 'WRITE example.py\ndef f():\n    """Return one."""\n    return 1\n'
    configured = configured_test_agent_server(tmp_path, output_text=output_text)
    first_response = await roundtrip(
        configured.server,
        {
            "jsonrpc": "2.0",
            "id": "agent-plan",
            "method": "optimus.agent.run",
            "params": {
                "run_id": "run-1",
                "task": "Add a docstring",
                "execution_mode": "agent",
                "workspace_root": str(tmp_path.resolve()),
            },
        },
    )

    assert first_response["result"]["status"] == "awaiting_approval"
    plan_hash = first_response["result"]["plan_hash"]
    assert plan_hash
    configured.gateway.output_text = "WRITE example.py\nBROKEN SECOND PLAN\n"

    second_response = await roundtrip(
        configured.server,
        {
            "jsonrpc": "2.0",
            "id": "agent-approve",
            "method": "optimus.agent.run",
            "params": {
                "run_id": "run-1",
                "task": "Add a docstring",
                "execution_mode": "agent",
                "workspace_root": str(tmp_path.resolve()),
                "approval": {"approved": True, "approval_id": "approval-1", "plan_hash": plan_hash},
            },
        },
    )

    assert second_response["result"]["status"] == "completed"
    assert configured.fake_gateway_call_count == 1
    assert "Return one" in target.read_text(encoding="utf-8")
    assert "BROKEN SECOND PLAN" not in target.read_text(encoding="utf-8")


async def test_ndjson_spec_session_prompt_and_permission_flow(tmp_path):
    configured = configured_test_agent_server(tmp_path, output_text="WRITE example.py\ncontent")
    reader = InteractiveLineReader()
    writer = MemoryLineWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))

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
    assert "agentCapabilities" in initialize_response["result"]

    await reader.send(
        {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": str(tmp_path.resolve()), "mcpServers": []}}
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

    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": permission_request["id"],
            "result": {
                "outcome": {"outcome": "selected", "optionId": "approve"},
                "metadata": {"approvalId": "approval-1", "planHash": plan_hash},
            },
        }
    )
    prompt_response = await writer.wait_for_response(3)

    assert prompt_response["result"]["stopReason"] == "end_turn"
    assert any(
        message.get("method") == "session/update"
        and message["params"]["update"]["sessionUpdate"] in {"plan", "tool_call", "tool_call_update"}
        for message in writer.messages
    )
    assert configured.fake_gateway_call_count == 1
    reader.close()
    await serve_task


async def test_ndjson_permission_rejection_sanitizes_live_outbound_error(tmp_path):
    configured = configured_test_agent_server(tmp_path, output_text="WRITE example.py\ncontent")
    reader = InteractiveLineReader()
    writer = MemoryLineWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))

    try:
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
            {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": str(tmp_path.resolve()), "mcpServers": []}}
        )
        session_id = (await writer.wait_for_response(2))["result"]["sessionId"]
        await reader.send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
            }
        )
        permission_request = await writer.wait_for_request("session/request_permission")
        await reader.send(
            {
                "jsonrpc": "2.0",
                "id": permission_request["id"],
                "error": {
                    "code": -32099,
                    "message": "OPTIMUS_API_KEY=top-secret-canary",
                    "data": {
                        "nested": {
                            "url": "redis://user:top-secret-canary@host/0",
                            "items": ["Bearer top-secret-canary"],
                        }
                    },
                },
            }
        )
        response = await writer.wait_for_response(3)

        assert response["error"]["code"] == -32099
        assert response["error"]["message"]
        assert "top-secret-canary" not in json.dumps(response)
        assert response["error"]["data"]["nested"]["url"] == "redis://**********@host/0"
    finally:
        reader.close()
        await serve_task


async def test_ndjson_permission_rejection_drops_data_when_sanitizer_fails(tmp_path, monkeypatch):
    configured = configured_test_agent_server(tmp_path, output_text="WRITE example.py\ncontent")
    reader = InteractiveLineReader()
    writer = MemoryLineWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))

    try:
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
            {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": str(tmp_path.resolve()), "mcpServers": []}}
        )
        session_id = (await writer.wait_for_response(2))["result"]["sessionId"]
        await reader.send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
            }
        )
        permission_request = await writer.wait_for_request("session/request_permission")
        payload = {
            "message": "OPTIMUS_API_KEY=top-secret-canary",
            "nested": {"url": "redis://user:top-secret-canary@host/0"},
        }
        await reader.send(
            {"jsonrpc": "2.0", "id": permission_request["id"], "error": {"code": -32099, "message": payload["message"], "data": payload}}
        )
        response = await writer.wait_for_response(3)

        assert response["error"]["code"] == -32099
        assert response["error"]["message"] == "internal error"
        assert "data" not in response["error"]
        assert "top-secret-canary" not in json.dumps(response)
    finally:
        reader.close()
        await serve_task
