"""Plan 12.11 Z0 (P5-b, P5-c): what real Zed shows for model-free memory notices, the first-response brief and `/welcome`.

Zed launches this as an ACP agent over stdio. Every notice is built by `optimus.acp.memory_notices` from a synthetic
`MemoryNotice` and written by the host's own NDJSON line writer, so the bytes Zed renders are the ones Optimus will emit.
No Gateway, model or network is involved: nothing here opens a socket. Labels are synthetic and adversarial (Markdown,
bidi overrides, controls), so the screenshot shows whether escaping holds. It proves rendering and delivery only, never
privacy (P5-d).

    <venv python> tools/plan12_memory/m3_notice_probe.py --log FILE
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from context_engine.memory_contracts import MemoryNotice
from optimus.acp import memory_notices
from optimus.acp.server import StdioNdjsonLineWriter

PROTOCOL_VERSION = 1
HOSTILE_LABEL = "**bold** [link](http://x) `code` \u202eevil\u202c\x07 <img src=x> # head"
_SAVED = MemoryNotice("e-z0-saved", "m-00000000000000a1", 1, "admit", "confirmed", "current")
_UPDATED = MemoryNotice("e-z0-updated", "m-00000000000000a1", 2, "update", "confirmed", "current")
_PENDING = MemoryNotice("e-z0-pending", "m-00000000000000a2", 1, "admit", "unconfirmed", "pending")
_FORGOTTEN = MemoryNotice("e-z0-forgotten", "m-00000000000000a1", 3, "withdraw", "confirmed", "current")
BRIEF = ("Welcome back. Your last session on this branch ended 8 days ago, settled, with one decision pending. "
         f"You asked me to keep plain pytest asserts {memory_notices.citation(_SAVED)}.")


class Probe:
    def __init__(self, writer: StdioNdjsonLineWriter, log: Path) -> None:
        self._writer = writer
        self._log = log
        self._prompts = 0

    def record(self, row: dict[str, Any]) -> None:
        with self._log.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"at": time.time(), **row}, ensure_ascii=True) + "\n")

    async def send(self, message: dict[str, Any]) -> None:
        self.record({"direction": "out", "message": message})
        await self._writer.write_line(message)

    async def update(self, session: str, update: dict[str, Any]) -> None:
        await self.send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session, "update": update}})

    async def text(self, session: str, text: str) -> None:
        await self.update(session, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}})

    async def card(self, session: str, notice: MemoryNotice, label: str) -> None:
        await self.send({"jsonrpc": "2.0", "method": "session/update", "params": memory_notices.card(session, notice, label)})

    async def handle(self, message: dict[str, Any]) -> None:
        self.record({"direction": "in", "message": message})
        method, request_id, params = message.get("method"), message.get("id"), message.get("params") or {}
        if method == "initialize":
            await self.send({"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": PROTOCOL_VERSION, "agentCapabilities": {"loadSession": False}, "authMethods": []}})
        elif method == "session/new":
            session = "z0-session"
            await self.send({"jsonrpc": "2.0", "id": request_id, "result": {"sessionId": session}})
            await self.update(session, {"sessionUpdate": "available_commands_update", "availableCommands": [
                {"name": "welcome", "description": "Show where you left off", "input": None}]})
            await self.text(session, f"(pre-prompt) {BRIEF}")  # optional surface: does Zed show text before any prompt?
        elif method == "session/prompt":
            await self.prompt(params.get("sessionId", ""), params.get("prompt") or [], request_id)
        elif request_id is not None:
            await self.send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}})

    async def prompt(self, session: str, blocks: list[Any], request_id: Any) -> None:
        self._prompts += 1
        typed = " ".join(block.get("text", "") for block in blocks if isinstance(block, dict)).strip()
        if typed.startswith("/welcome"):
            await self.text(session, BRIEF)
        elif self._prompts == 1:
            await self.text(session, BRIEF + "\n\n")  # P5-b: the brief leads the first response
            await self.text(session, "Synthetic answer: no model ran for this turn.")
            await self.card(session, _SAVED, HOSTILE_LABEL)
            await self.card(session, _PENDING, "second synthetic memory")
            await self.text(session, memory_notices.appended_text(_SAVED, HOSTILE_LABEL))  # P5-c fallback
        else:
            await self.card(session, _UPDATED, HOSTILE_LABEL)
            await self.card(session, _UPDATED, HOSTILE_LABEL)  # a resend on reconnect: same id and state, one card
            await self.card(session, _FORGOTTEN, "")
            await self.text(session, "Synthetic answer two." + memory_notices.appended_text(_FORGOTTEN, ""))
        await self.send({"jsonrpc": "2.0", "id": request_id, "result": {"stopReason": "end_turn"}})


async def serve(log: Path) -> None:
    probe = Probe(StdioNdjsonLineWriter(sys.stdout.buffer), log)
    probe.record({"event": "start", "argv": sys.argv[1:]})
    while True:
        line = await asyncio.to_thread(sys.stdin.buffer.readline)
        if not line:
            probe.record({"event": "eof"})
            return
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            probe.record({"event": "unparsed", "bytes": len(line)})
            continue
        if isinstance(message, dict):
            await probe.handle(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args(argv)
    asyncio.run(serve(args.log))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
