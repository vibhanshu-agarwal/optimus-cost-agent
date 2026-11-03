"""The diagnostic-only ACP host of a launch refused its Gateway (#465, ADR-036).

A process that exits at startup shows the person in Zed nothing useful, and stderr is a log nobody reads while typing.
This host answers `initialize` and `session/new`, so the Agent Panel opens, and answers every prompt with the stated
reason and a normal `end_turn` (a `refusal` stop reason can be shown as a content-policy banner in place of the text).

It is given no Gateway client, Redis, model, tool or MCP path, so by construction nothing it runs can reach a provider. A
session is only an identifier to answer with; it has no modes or configuration to offer.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from optimus.acp.errors import (
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcError,
    error_response,
    success_response,
)
from optimus.acp.framing import FramingError, encode_message, read_message
from optimus.acp.server import NdjsonOutboundChannel
from optimus.acp.shapes import build_agent_message_chunk_notification

_PROTOCOL_VERSION = 1  # `spec.ACP_PROTOCOL_VERSION`, by value: importing `spec` would bring the model paths in


class GatewayRefusalServer:
    def __init__(self, *, code: str, reason: str) -> None:
        self._text = f"**This agent did not start.** {reason}\n\nRefusal code: `{code}`"
        self._sessions: set[str] = set()

    async def serve_ndjson(self, reader: Any, writer: Any, *, dedicated_writer: Any = None, **_transport: Any) -> None:
        # The channel the serving process's cleanup observes: a blocked client write stays owned until it ends.
        outbound = NdjsonOutboundChannel(writer, dedicated_writer=dedicated_writer)
        while line := await reader.readline():
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                await outbound.submit_message(error_response(None, JsonRpcError(code=PARSE_ERROR, message="invalid JSON")))
                continue
            for outgoing in self._answer(message):
                await outbound.submit_message(outgoing)

    async def serve(self, reader: Any, writer: Any, **_transport: Any) -> None:
        while True:
            try:
                message = await read_message(reader)
            except FramingError as exc:
                if str(exc) == "unexpected end of stream":
                    return
                writer.write(encode_message(error_response(None, JsonRpcError(code=exc.code, message="invalid frame"))))
                await writer.drain()
                if str(exc) in {"body too large", "header too large"}:
                    return
                continue
            for outgoing in self._answer(message):
                writer.write(encode_message(outgoing))
            await writer.drain()

    def _answer(self, message: Any) -> list[dict[str, Any]]:
        """What to send for one message. A notification or a client response needs nothing."""
        if not isinstance(message, Mapping) or "method" not in message or "id" not in message:
            return []
        request_id, method, params = message["id"], message["method"], message.get("params")
        if method == "initialize":
            return [success_response(request_id, _initialize_result())]
        if method == "session/new":
            created = f"refused-{uuid.uuid4().hex}"
            self._sessions.add(created)
            return [success_response(request_id, {"sessionId": created})]
        if method == "session/prompt":
            session_id = params.get("sessionId") if isinstance(params, Mapping) else None
            if not isinstance(session_id, str) or session_id not in self._sessions:
                return [error_response(request_id, JsonRpcError(code=INVALID_REQUEST, message="unknown session"))]
            update = build_agent_message_chunk_notification(session_id=session_id, text=self._text)
            return [
                {"jsonrpc": "2.0", "method": "session/update", "params": update},
                success_response(request_id, {"stopReason": "end_turn"}),
            ]
        return [error_response(request_id, JsonRpcError(code=METHOD_NOT_FOUND, message="this agent did not start"))]


def _initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": _PROTOCOL_VERSION,
        "agentCapabilities": {
            "promptCapabilities": {"image": False, "audio": False, "embeddedContext": False},
            "sessionCapabilities": {},
            "mcpCapabilities": {"http": False, "sse": False},
        },
        "agentInfo": {"name": "optimus", "version": "0.1.0"},
        "authMethods": [],
    }
