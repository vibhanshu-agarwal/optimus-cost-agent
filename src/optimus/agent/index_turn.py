"""Running the model's index tool requests inside a turn (Plan 12.10 Task 4; ADR-038), the same way for Chat and Agent.

Each request passes the toolbox's guard, gets a tool card, and is bounded. A repeat within the turn is answered from nothing: the
model is told it already has that result, and a reply of only repeats counts as no progress. Results are untrusted data for the next
model call; a tool never changes policy, and these tools cannot write.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from optimus.agent.directives import IndexToolRequest
from optimus.agent.models import AgentToolCall
from optimus.agent.tools import AgentToolbox

MAX_INDEX_ROUNDS: Final = 4
MAX_INDEX_EVIDENCE_BYTES: Final = 32 * 1024
LIMIT_OBSERVATION: Final = "You have used every search round. Answer now from what you have, and state plainly what you could not inspect."
LIMIT_NOTICE: Final = "Optimus stopped searching after its limit of search rounds, so what it did not reach is not covered by this answer."


class IndexedTurn(Protocol):
    """The host's turn. The agent package sees only this, so it stays independent of the index."""

    tools: object
    on_tool: Callable[[str, str, str, str], None] | None
    seen_requests: set[tuple[str, str]]


@dataclass(frozen=True)
class IndexRound:
    envelope: str
    calls: tuple[AgentToolCall, ...]
    novel: bool


def run_index_tools(requests: Sequence[IndexToolRequest], memory: IndexedTurn, toolbox: AgentToolbox, *, halted: Callable[[], bool] = lambda: False) -> IndexRound:
    blocks: list[str] = []
    calls: list[AgentToolCall] = []
    novel = False
    for request in requests:
        if halted():
            break
        key = (request.tool, request.argument)
        if key in memory.seen_requests:
            blocks.append(f"INDEX_TOOL {request.tool} {request.argument}\nThis exact request was already answered earlier in this turn.\nEND_INDEX_TOOL\n")
            continue
        memory.seen_requests.add(key)
        novel = True
        if memory.on_tool is not None:
            memory.on_tool("started", request.tool, request.argument, "")
        try:
            text, call = toolbox.index_tool(request, memory.tools)
        except PermissionError as refused:
            text = f"Refused: {refused}"
            call = AgentToolCall(tool_name=toolbox.index_tool_name(request), summary=f"{request.tool} {request.argument[:80]}: refused", authorization_outcome="BLOCK")
        if memory.on_tool is not None:
            memory.on_tool("completed" if call.authorization_outcome == "ALLOW" else "failed", request.tool, request.argument, call.summary)
        calls.append(call)
        blocks.append(f"INDEX_TOOL {request.tool} {request.argument}\n{text}\nEND_INDEX_TOOL\n")
    return IndexRound("".join(blocks), tuple(calls), novel)


def keep_newest(envelope: str) -> str:
    """Earlier results give way to later ones, as whole blocks, so the evidence stays bounded."""
    data = envelope.encode("utf-8")
    if len(data) <= MAX_INDEX_EVIDENCE_BYTES:
        return envelope
    tail = data[-MAX_INDEX_EVIDENCE_BYTES:].decode("utf-8", errors="ignore")
    start = tail.find("INDEX_TOOL ")
    return tail[start:] if start >= 0 else ""
