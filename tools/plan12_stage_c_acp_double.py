"""Plan 12.2 Stage C launch rehearsal: an inert stdio ACP agent (Codex's review f381e730, item 1).

It stands exactly where acpx or Zed launches optimus-agent.exe and is never an Optimus subprocess: no Gateway,
model, provider, credential or network. It answers as Optimus advertises itself (ACP protocol 1, no session/load):
session/new returns Optimus's modes and its configOptions - the mode select, plus the context-strategy select
(initially compaction) on an attached launch - and the mode changes through session/set_mode or
session/set_config_option with Optimus's results and updates (Zed 1.24.2 drives the config options; r6 preparation).
An Agent prompt asks one write permission with Optimus's approve / cancel options and a Chat prompt answers in
text. It appends what it saw - its argv, working folder and process id, each ACP method, each setting change and
the permission outcome - as JSON lines to the record file named by the PLAN12_REHEARSAL_RECORD environment
variable, and writes nothing else. Standard library only, so it can be packed as a standalone launcher; the
shapes are pinned to Optimus's own builders by its tests.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

RECORD_ENV = "PLAN12_REHEARSAL_RECORD"
PERMISSION_ID = "rehearsal-permission-1"
INVALID_REQUEST = -32600
# Optimus's own choices (optimus.acp.shapes.SESSION_MODE_CHOICES, optimus.acp.session_config.STRATEGY_CHOICES).
MODE_CHOICES = (
    ("agent", "Agent", "Plans workspace changes and applies them only after your approval."),
    ("chat", "Chat", "Answers questions from the workspace context without changing any files."),
)
STRATEGY_CHOICES = (
    ("compaction", "Compaction", "Summarizes older complete turns and keeps the newest turns exact. Execution outcomes and approval facts "
     "remain exact."),
    ("hybrid", "Hybrid", "Keeps the first turn and a larger set of the newest turns exact, and summarizes the turns between them. "
     "Execution outcomes and approval facts remain exact."),
    ("sliding_window", "Sliding window", "Keeps only the newest complete ordinary turns that fit. Older ordinary conversation content "
     "is dropped from model context."),
)  # fmt: skip
ATTACHED_INITIAL_STRATEGY = "compaction"  # optimus.acp.stage_c: the attached Stage C session's initial strategy
MODE_IDS = tuple(mode_id for mode_id, _, _ in MODE_CHOICES)
STRATEGY_IDS = tuple(value for value, _, _ in STRATEGY_CHOICES)


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


def _error(request_id: Any, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": request_id, "error": {"code": INVALID_REQUEST, "message": message}})


def _update(session_id: Any, update: dict[str, Any]) -> None:
    _send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": update}})


def mode_state(mode_id: str) -> dict[str, Any]:
    return {"currentModeId": mode_id, "availableModes": [{"id": i, "name": n, "description": d} for i, n, d in MODE_CHOICES]}


def config_options(mode_id: str, strategy: str | None) -> list[dict[str, Any]]:
    """Optimus's full configOptions set: the mode select, then the context-strategy select on an attached session."""
    options = [{"id": "mode", "name": "Mode", "category": "mode", "type": "select", "currentValue": mode_id,
                "options": [{"value": i, "name": n, "description": d} for i, n, d in MODE_CHOICES]}]  # fmt: skip
    if strategy is not None:
        options.append({"id": "context_strategy", "name": "Context strategy", "category": "_context_strategy", "type": "select",
                        "currentValue": strategy, "options": [{"value": v, "name": n, "description": d} for v, n, d in STRATEGY_CHOICES]})  # fmt: skip
    return options


def _profile(args: list[str]) -> str | None:
    return args[args.index("--plan12-test-profile") + 1] if "--plan12-test-profile" in args[:-1] else None


def _initialize_result() -> dict[str, Any]:
    capabilities = {
        "promptCapabilities": {"image": False, "audio": False, "embeddedContext": False},
        "sessionCapabilities": {},
        "mcpCapabilities": {"http": False, "sse": False},
    }
    return {"protocolVersion": 1, "agentCapabilities": capabilities, "agentInfo": {"name": "stage-c-rehearsal-double", "version": "1"}, "authMethods": []}


class Double:
    def __init__(self, stdin: Any, args: list[str] | None = None) -> None:
        self.stdin = stdin
        self.args = list(sys.argv[1:] if args is None else args)
        self.attached = _profile(self.args) == "attached"
        self.modes: dict[str, str] = {}
        self.strategies: dict[str, str | None] = {}

    def _read(self) -> dict[str, Any] | None:
        while True:
            line = self.stdin.readline()
            if not line:
                return None
            if line.strip():
                return json.loads(line)

    def run(self) -> int:
        _record({"event": "start", "argv0": sys.argv[0], "args": self.args, "cwd": os.getcwd()})
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
            self.strategies[session_id] = ATTACHED_INITIAL_STRATEGY if self.attached else None
            _record({"event": "request", "method": method, "cwd": params.get("cwd"), "sessionId": session_id})
            _result(request_id, {"sessionId": session_id, "modes": mode_state("agent"), "configOptions": config_options("agent", self.strategies[session_id])})
        elif method == "session/set_mode":
            _record({"event": "request", "method": method, "sessionId": params.get("sessionId"), "modeId": params.get("modeId")})
            self.change(request_id, params.get("sessionId"), mode=params.get("modeId"), setter=method)
        elif method == "session/set_config_option":
            config_id, value = params.get("configId"), params.get("value")
            _record({"event": "request", "method": method, "sessionId": params.get("sessionId"), "configId": config_id, "value": value})
            if config_id == "mode":
                self.change(request_id, params.get("sessionId"), mode=value, setter=method)
            elif config_id == "context_strategy" and self.attached:
                self.change(request_id, params.get("sessionId"), strategy=value, setter=method)
            else:
                _error(request_id, "unknown config option")
        elif method == "session/prompt":
            self.prompt(request_id, params)
        elif request_id is not None:
            _record({"event": "request", "method": method})
            _send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}})
        else:
            _record({"event": "notification", "method": method})

    def change(self, request_id: Any, session_id: Any, *, setter: str, mode: Any = None, strategy: Any = None) -> None:
        """Optimus's one setter path: validate, change, publish a current_mode_update for a mode change and the full
        configOptions set for any change, then answer: set_mode with {}, set_config_option with the full set."""
        if mode is not None and mode not in MODE_IDS or setter == "session/set_mode" and mode is None:
            _error(request_id, "unsupported mode")
            return
        if strategy is not None and strategy not in STRATEGY_IDS:
            _error(request_id, "unsupported context strategy")
            return
        if session_id not in self.modes:
            _error(request_id, "unknown session")
            return
        mode_changed = mode is not None and mode != self.modes[session_id]
        strategy_changed = strategy is not None and strategy != self.strategies[session_id]
        if mode_changed:
            self.modes[session_id] = mode
        if strategy_changed:
            self.strategies[session_id] = strategy
        options = config_options(self.modes[session_id], self.strategies[session_id])
        if mode_changed:
            _update(session_id, {"sessionUpdate": "current_mode_update", "currentModeId": self.modes[session_id]})
        if mode_changed or strategy_changed:
            _update(session_id, {"sessionUpdate": "config_option_update", "configOptions": options})
        _result(request_id, {} if setter == "session/set_mode" else {"configOptions": options})

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
