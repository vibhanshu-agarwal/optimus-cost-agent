"""Plan 12.2 Stage C launch rehearsal: an inert stdio ACP agent (Codex's review f381e730, item 1).

It stands exactly where acpx launches optimus-agent.exe and is never an Optimus subprocess: no Gateway, model,
provider, credential or network. It answers acpx as Optimus advertises itself (ACP protocol 1, no session/load,
the Agent and Chat modes); an Agent prompt asks one write permission with Optimus's approve / cancel options and a
Chat prompt answers in text. It appends what it saw - its argv, working folder and process id, each ACP method and
the permission outcome - as JSON lines to the record file named by the PLAN12_REHEARSAL_RECORD environment
variable, and writes nothing else. Standard library only, so it can be packed as a standalone launcher.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

RECORD_ENV = "PLAN12_REHEARSAL_RECORD"
MODES = [{"id": "agent", "name": "Agent"}, {"id": "chat", "name": "Chat"}]
PERMISSION_ID = "rehearsal-permission-1"


def _record(event: dict[str, Any]) -> None:
    path = os.environ.get(RECORD_ENV)
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), **event}) + "\n")


def _send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: dict[str, Any]) -> None:
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _initialize_result() -> dict[str, Any]:
    capabilities = {
        "promptCapabilities": {"image": False, "audio": False, "embeddedContext": False},
        "sessionCapabilities": {},
        "mcpCapabilities": {"http": False, "sse": False},
    }
    return {"protocolVersion": 1, "agentCapabilities": capabilities, "agentInfo": {"name": "stage-c-rehearsal-double", "version": "1"}, "authMethods": []}


class Double:
    def __init__(self, stdin: Any) -> None:
        self.stdin = stdin
        self.modes: dict[str, str] = {}

    def _read(self) -> dict[str, Any] | None:
        while True:
            line = self.stdin.readline()
            if not line:
                return None
            if line.strip():
                return json.loads(line)

    def run(self) -> int:
        _record({"event": "start", "argv0": sys.argv[0], "args": sys.argv[1:], "cwd": os.getcwd()})
        while (message := self._read()) is not None:
            self.handle(message)
        _record({"event": "exit", "reason": "stdin closed"})
        return 0

    def handle(self, message: dict[str, Any]) -> None:
        method, params, request_id = message.get("method"), message.get("params") or {}, message.get("id")
        if method is None:
            _record({"event": "unexpected-response", "id": request_id})
            return
        if method == "initialize":
            _record({"event": "request", "method": method, "protocolVersion": params.get("protocolVersion")})
            _result(request_id, _initialize_result())
        elif method == "session/new":
            session_id = f"double-{os.getpid()}-{len(self.modes) + 1}"
            self.modes[session_id] = "agent"
            _record({"event": "request", "method": method, "cwd": params.get("cwd"), "sessionId": session_id})
            _result(request_id, {"sessionId": session_id, "modes": {"currentModeId": "agent", "availableModes": MODES}})
        elif method == "session/set_mode":
            self.modes[params.get("sessionId")] = params.get("modeId")
            _record({"event": "request", "method": method, "sessionId": params.get("sessionId"), "modeId": params.get("modeId")})
            _result(request_id, {})
            update = {"sessionUpdate": "current_mode_update", "currentModeId": params.get("modeId")}
            _send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": params.get("sessionId"), "update": update}})
        elif method == "session/prompt":
            self.prompt(request_id, params)
        elif request_id is not None:
            _record({"event": "request", "method": method})
            _send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}})
        else:
            _record({"event": "notification", "method": method})

    def prompt(self, request_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        mode = self.modes.get(session_id)
        _record({"event": "request", "method": "session/prompt", "sessionId": session_id, "mode": mode})
        if mode == "agent":
            tool_call = {"toolCallId": "rehearsal-write-1", "title": "Write the requested file", "kind": "edit", "status": "pending"}
            options = [{"optionId": "approve", "name": "Approve", "kind": "allow_once"}, {"optionId": "cancel", "name": "Cancel", "kind": "reject_once"}]
            _send({"jsonrpc": "2.0", "id": PERMISSION_ID, "method": "session/request_permission",
                   "params": {"sessionId": session_id, "toolCall": tool_call, "options": options}})  # fmt: skip
            while (reply := self._read()) is not None:
                if reply.get("id") == PERMISSION_ID and "method" not in reply:
                    _record({"event": "permission", "outcome": (reply.get("result") or {}).get("outcome"), "error": reply.get("error")})
                    break
                self.handle(reply)
            text = "The rehearsal double wrote nothing."
        else:
            text = "A Chat answer from the rehearsal double."
        chunk = {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}
        _send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": chunk}})
        _result(request_id, {"stopReason": "end_turn"})


def main() -> int:
    return Double(sys.stdin).run()


if __name__ == "__main__":
    raise SystemExit(main())
