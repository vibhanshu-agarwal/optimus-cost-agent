"""Local ACP fixture counterparty for the Plan 11.26 SDK qualification only."""

from __future__ import annotations

import json
import sys
from typing import Any


def _reply(request_id: object, result: dict[str, object]) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
    sys.stdout.flush()


def _error(request_id: object, message: str) -> None:
    sys.stdout.write(
        json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": message}}) + "\n"
    )
    sys.stdout.flush()


def _handle(message: dict[str, Any]) -> None:
    if "id" not in message or not isinstance(message.get("method"), str):
        return
    request_id = message["id"]
    method = message["method"]
    if method == "initialize":
        protocol_version = message.get("params", {}).get("protocolVersion", 1)
        _reply(
            request_id,
            {
                "protocolVersion": protocol_version,
                "agentInfo": {"name": "plan1126-fixture-agent", "version": "0.0.0"},
                "agentCapabilities": {"sessionCapabilities": {"close": True}},
            },
        )
    elif method == "session/new":
        _reply(request_id, {"sessionId": "plan1126-fixture-session"})
    elif method == "session/prompt":
        _reply(request_id, {"stopReason": "end_turn"})
    elif method == "session/close":
        _reply(request_id, {})
    else:
        _error(request_id, "unsupported fixture method")


def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            _handle(message)


if __name__ == "__main__":
    main()
