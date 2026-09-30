"""Plan 12.1: concurrent mode setters on the real ``serve_ndjson`` path.

The server handles each request in its own task. Mode setters for one session
are serialized, and each setter's response is queued before the next setter's
paired updates, so the wire never shows a response that a later update
contradicts or an update pair split by another setter.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.server import AcpStreamServer
from optimus.guardrails.pre_tool import PreToolGuard
from tests.e2e.acp.test_multi_turn_conversation import PhysicalCapturingWriter
from tests.integration.acp.test_server_stream import InteractiveLineReader


class _UnusedRunner:
    def run(self, request, **kwargs):
        raise AssertionError("no prompt is sent in this test")


def _server(tmp_path: Path) -> AcpStreamServer:
    workspace = tmp_path.resolve()
    guard = PreToolGuard.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    dispatcher = JsonRpcDispatcher(
        gateway_client=object(),
        agent_runner=_UnusedRunner(),
        pre_tool_guard=guard,
        workspace_root=workspace,
    )
    return AcpStreamServer(dispatcher=dispatcher)


def _wire_label(message: dict[str, Any]) -> tuple[str, str] | None:
    if message.get("id") in {"first", "second"}:
        return ("response", message["id"])
    update = message.get("params", {}).get("update", {}) if message.get("method") == "session/update" else {}
    kind = update.get("sessionUpdate")
    if kind == "current_mode_update":
        return (kind, update["currentModeId"])
    if kind == "config_option_update":
        (option,) = [option for option in update["configOptions"] if option["id"] == "mode"]
        return (kind, option["currentValue"])
    return None


async def test_concurrent_setters_keep_each_response_after_its_own_paired_updates(tmp_path):
    reader = InteractiveLineReader()
    writer = PhysicalCapturingWriter()
    writer.bind_loop(asyncio.get_running_loop())
    serve_task = asyncio.create_task(_server(tmp_path).serve_ndjson(reader, writer))
    try:
        await reader.send({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}})
        session_id = (await writer.wait_for_response(1))["result"]["sessionId"]

        await reader.send(
            {
                "jsonrpc": "2.0",
                "id": "first",
                "method": "session/set_config_option",
                "params": {"sessionId": session_id, "configId": "mode", "value": "chat"},
            }
        )
        await reader.send(
            {
                "jsonrpc": "2.0",
                "id": "second",
                "method": "session/set_mode",
                "params": {"sessionId": session_id, "modeId": "agent"},
            }
        )
        first = await writer.wait_for_response("first")
        second = await writer.wait_for_response("second")

        assert "error" not in first and "error" not in second, (first, second)
        (option,) = [option for option in first["result"]["configOptions"] if option["id"] == "mode"]
        assert option["currentValue"] == "chat"
        assert second["result"] == {}
        labels = [label for message in list(writer.messages) if (label := _wire_label(message)) is not None]
        assert labels == [
            ("current_mode_update", "chat"),
            ("config_option_update", "chat"),
            ("response", "first"),
            ("current_mode_update", "agent"),
            ("config_option_update", "agent"),
            ("response", "second"),
        ]
    finally:
        reader.close()
        await asyncio.wait_for(serve_task, timeout=5)
