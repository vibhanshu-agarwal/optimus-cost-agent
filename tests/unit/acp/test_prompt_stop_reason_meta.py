"""#268 (P11.25-FU-2, MT-FU-2): the prompt response carries the run's own stop code and settled outcome in ``_meta``.

The real ACP adapter, behind it a real AgentRunner with only the Gateway and the shell scripted, or the scripted
runner the context-engine tests use where a cancel must land at a fixed point. The wire ``stopReason`` is unchanged,
and ``_meta.outcome`` is the semantic settlement the turn's own settlement event reports, so a check can tell a
no-work turn from a completed one without reading prose.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

from optimus.acp.spec import CONTEXT_PLAN_TOO_LARGE_TEXT, AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_context_engine_admission import Runner, make_attachment

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
    def __init__(self, tmp_path: Path, text: str | None, *, scripted: Runner | None = None, attachment: Any = None) -> None:
        (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
        self.gateway = _Gateway(text)
        runner: Any = checked_agent_runner(scripted) if scripted is not None else AgentRunner(
            gateway_client=self.gateway,
            model="test-model",
            state_store=InMemoryAgentStateStore(),
            shell_runner=lambda command: CompletedProcess(command, 0, "ok", ""),
        )
        self.outbound = RecordingOutboundChannel()
        self.settlements: list[Any] = []
        self.adapter = AcpDuplexAdapter(
            runner=runner, workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=self.outbound,
            settlement_sink=self.settlements.append, context_attachment=attachment,
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

    def settlement_event_outcome(self) -> str:
        """The semantic outcome the turn's own settlement event reports (not a conversation record)."""
        [event] = self.settlements
        return event.payload["settlement"]

    def texts(self) -> list[str]:
        updates = [n["params"]["update"] for n in self.outbound.notifications if n["method"] == "session/update"]
        return [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"]


async def test_an_approved_agent_turn_reports_completed(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, WRITE_PLAN)
    await turn.open()

    result = await turn.prompt(answer_permission="approve")

    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": None, "outcome": "completed"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome(), "the response reports the outcome the turn settles"
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "new\n"


async def test_a_rejected_plan_reports_rejected_under_the_cancelled_stop_reason(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, WRITE_PLAN)
    await turn.open()

    result = await turn.prompt(answer_permission="cancel")

    assert result == {"stopReason": "cancelled", "_meta": {"runStopReason": None, "outcome": "rejected"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "old\n"


async def test_an_unknown_cost_planning_stop_is_a_failed_no_work_turn_not_a_completed_one(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, None)
    await turn.open()

    result = await turn.prompt()

    # The wire still says end_turn; only `_meta` tells this no-work turn from a completed one.
    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": "PLANNING_GATEWAY_COST_UNKNOWN", "outcome": "failed"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()
    assert turn.outbound.requests == [], "no permission is asked"
    assert turn.gateway.calls == 1


async def test_a_chat_answer_reports_completed(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, ANSWER)
    await turn.open("chat")

    result = await turn.prompt()

    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": None, "outcome": "completed"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()


async def test_an_unknown_cost_chat_turn_reports_failed(tmp_path: Path) -> None:
    turn = _Turn(tmp_path, None)
    await turn.open("chat")

    result = await turn.prompt()

    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": "CHAT_GATEWAY_COST_UNKNOWN", "outcome": "failed"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()


BIG_PLAN = "WRITE example.py\n" + "z" * 6000  # over the 4096-byte record a small attachment keeps


class _Scripted(Runner):
    """The context-engine tests' scripted runner. ``cancel_in`` names the run ("planning", "approved" or "chat")
    inside which the turn accepts a cancel, exactly as a client's session/cancel arriving then would."""

    def __init__(self, *, cancel_in: str | None = None, plan_text: str = "WRITE example.py\ncontent", hashed: bool = True) -> None:
        super().__init__(plan_text=plan_text)
        self.cancel_in = cancel_in
        self.hashed = hashed

    def run(self, request: Any, **kwargs: Any) -> AgentRunResult:
        result = super().run(request, **kwargs)
        stage = "chat" if request.execution_mode is ExecutionMode.CHAT else "approved" if request.approval.approved else "planning"
        if stage == self.cancel_in:
            assert kwargs["operation_control"].request_session_cancel().value == "accepted"
        if not self.hashed and result.status is AgentRunStatus.AWAITING_APPROVAL:
            result = result.model_copy(update={"plan_hash": None})
        return result


def _scripted_turn(tmp_path: Path, runner: _Scripted, *, small_record: bool = False) -> _Turn:
    return _Turn(tmp_path, None, scripted=runner, attachment=make_attachment(source_max=4096) if small_record else None)


async def test_a_cancel_accepted_before_the_oversized_plan_terminal_reports_cancelled(tmp_path: Path) -> None:
    turn = _scripted_turn(tmp_path, _Scripted(cancel_in="planning", plan_text=BIG_PLAN), small_record=True)
    await turn.open()

    result = await turn.prompt()

    # The oversized-plan branch commits FAILED, but the accepted cancel settles the turn as cancelled.
    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": None, "outcome": "cancelled"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()
    assert any(CONTEXT_PLAN_TOO_LARGE_TEXT in text for text in turn.texts()), "the oversized-plan branch answered"


async def test_a_cancel_accepted_while_the_approved_run_is_in_flight_reports_cancelled(tmp_path: Path) -> None:
    turn = _scripted_turn(tmp_path, _Scripted(cancel_in="approved"))
    await turn.open()

    result = await turn.prompt(answer_permission="approve")

    # The approved run returns COMPLETED, yet the turn settles cancelled.
    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": None, "outcome": "cancelled"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()


async def test_a_halt_after_planning_reports_cancelled(tmp_path: Path) -> None:
    turn = _scripted_turn(tmp_path, _Scripted(cancel_in="planning"))
    await turn.open()

    result = await turn.prompt()

    assert result == {"stopReason": "cancelled", "_meta": {"runStopReason": None, "outcome": "cancelled"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()
    assert turn.outbound.requests == [], "no permission is asked"


async def test_a_cancelled_chat_turn_reports_cancelled(tmp_path: Path) -> None:
    turn = _scripted_turn(tmp_path, _Scripted(cancel_in="chat"))
    await turn.open("chat")

    result = await turn.prompt()

    assert result == {"stopReason": "cancelled", "_meta": {"runStopReason": None, "outcome": "cancelled"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()


async def test_awaiting_approval_without_a_plan_hash_reports_rejected(tmp_path: Path) -> None:
    turn = _scripted_turn(tmp_path, _Scripted(hashed=False))
    await turn.open()

    result = await turn.prompt()

    assert result == {"stopReason": "refusal", "_meta": {"runStopReason": None, "outcome": "rejected"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()
    assert turn.outbound.requests == [], "no permission is asked"


async def test_a_plan_too_large_for_its_record_reports_failed(tmp_path: Path) -> None:
    turn = _scripted_turn(tmp_path, _Scripted(plan_text=BIG_PLAN), small_record=True)
    await turn.open()

    result = await turn.prompt()

    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": None, "outcome": "failed"}}
    assert result["_meta"]["outcome"] == turn.settlement_event_outcome()
    assert any(CONTEXT_PLAN_TOO_LARGE_TEXT in text for text in turn.texts())
