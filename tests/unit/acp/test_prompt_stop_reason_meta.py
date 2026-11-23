"""#268 (P11.25-FU-2, MT-FU-2): the prompt response carries the run's own stop code and committed outcome in ``_meta``.

A real AgentRunner behind the real ACP adapter; only the Gateway and the shell are scripted. The wire ``stopReason``
is unchanged, and ``_meta.outcome`` is the outcome the turn committed, so a check can tell a no-work turn from a
completed one without reading prose.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage

WRITE_PLAN = "WRITE example.py\nnew\nTEST pytest -q"
ANSWER = "example.py holds one line."


class _Gateway:
    """Answers every call with ``text``, or raises an unexpected error (a sent request whose cost is unknown)."""

    def __init__(self, text: str | None) -> None:
        self._text = text
        self.calls = 0

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, Any] | None = None, **_: Any) -> GatewayResponse:
        del model, input_text, metadata
        self.calls += 1
        if self._text is None:
            raise TypeError("unexpected failure after the request was sent")
        return GatewayResponse(
            response_id=f"resp-{self.calls}",
            output_text=self._text,
            gateway_usage=GatewayUsage(gateway_request_id=f"gw-{self.calls}", provider="test", billing_units=1, cost_usd=Decimal("0.001")),
            raw={"id": f"resp-{self.calls}"},
            finish_reason="stop",
        )


class _Turn:
    def __init__(self, tmp_path: Path, text: str | None) -> None:
        (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
        self.gateway = _Gateway(text)
        runner = AgentRunner(
            gateway_client=self.gateway,
            model="test-model",
            state_store=InMemoryAgentStateStore(),
            shell_runner=lambda command: CompletedProcess(command, 0, "ok", ""),
        )
        self.outbound = RecordingOutboundChannel()
        self.settlements: list[Any] = []
        self.adapter = AcpDuplexAdapter(
            runner=runner, workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=self.outbound,
            settlement_sink=self.settlements.append,
        )
        self._cwd = str(tmp_path)
        self.session_id = ""

    async def open(self, mode: str | None = None) -> None:
        created = (await self.adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": self._cwd, "mcpServers": []}}
        )).response
        self.session_id = created["result"]["sessionId"]
        if mode is not None:
            changed = (await self.adapter.handle_client_request({
                "jsonrpc": "2.0", "id": "mode", "method": "session/set_mode", "params": {"sessionId": self.session_id, "modeId": mode},
            })).response
            assert "error" not in changed, changed

    def _prompt(self) -> asyncio.Task[Any]:
        request = {
            "jsonrpc": "2.0",
            "id": "p1",
            "method": "session/prompt",
            "params": {"sessionId": self.session_id, "prompt": [{"type": "text", "text": "Change example.py"}]},
        }
        return asyncio.create_task(self.adapter.handle_client_request(request))

    async def prompt(self, *, answer_permission: str | None = None) -> dict[str, Any]:
        task = self._prompt()
        if answer_permission is not None:
            permission = await asyncio.wait_for(self.outbound.wait_for_request("session/request_permission"), timeout=5)
            self.outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": answer_permission}})
        return (await asyncio.wait_for(task, timeout=10)).response["result"]

    def committed_outcome(self) -> str:
        """The outcome the turn recorded, from its own settlement event."""
        [event] = self.settlements
        return event.payload["settlement"]


async def test_an_approved_agent_turn_reports_completed(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, WRITE_PLAN)
    await turn.open()

    result = await turn.prompt(answer_permission="approve")

    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": None, "outcome": "completed"}}
    assert result["_meta"]["outcome"] == turn.committed_outcome(), "the response reports the outcome the turn committed"
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "new\n"


async def test_a_rejected_plan_reports_rejected_under_the_cancelled_stop_reason(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, WRITE_PLAN)
    await turn.open()

    result = await turn.prompt(answer_permission="cancel")

    assert result == {"stopReason": "cancelled", "_meta": {"runStopReason": None, "outcome": "rejected"}}
    assert result["_meta"]["outcome"] == turn.committed_outcome()
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "old\n"


async def test_an_unknown_cost_planning_stop_is_a_failed_no_work_turn_not_a_completed_one(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, None)
    await turn.open()

    result = await turn.prompt()

    # The wire still says end_turn; only `_meta` tells this no-work turn from a completed one.
    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": "PLANNING_GATEWAY_COST_UNKNOWN", "outcome": "failed"}}
    assert result["_meta"]["outcome"] == turn.committed_outcome()
    assert turn.outbound.requests == [], "no permission is asked"
    assert turn.gateway.calls == 1


async def test_a_chat_answer_reports_completed(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, ANSWER)
    await turn.open("chat")

    result = await turn.prompt()

    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": None, "outcome": "completed"}}
    assert result["_meta"]["outcome"] == turn.committed_outcome()


async def test_an_unknown_cost_chat_turn_reports_failed(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, None)
    await turn.open("chat")

    result = await turn.prompt()

    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": "CHAT_GATEWAY_COST_UNKNOWN", "outcome": "failed"}}
    assert result["_meta"]["outcome"] == turn.committed_outcome()
