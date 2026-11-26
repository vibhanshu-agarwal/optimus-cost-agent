"""#512: how an Agent-mode question settles, through the real ACP adapter and a real AgentRunner, with only the Gateway
scripted (no paid or live call). An ANSWER settles as a completed run with no plan; a REFUSE settles exactly as before."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

from optimus.acp.shapes import LOOP_CONTINUE_OPTION_ID, LOOP_STOP_OPTION_ID
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage

QUESTION = "Should I run the tests before pushing?"
ANSWER = "Yes, run the tests before every push; the README documents no exception."
NL = chr(10)


class _Gateway:
    """Replies with each scripted text in turn and keeps every request's input."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.inputs: list[str] = []

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, Any] | None = None, **_: Any) -> GatewayResponse:
        del model, metadata
        self.inputs.append(input_text)
        n = len(self.inputs)
        return GatewayResponse(
            response_id=f"resp-{n}", output_text=self._replies.pop(0),
            gateway_usage=GatewayUsage(gateway_request_id=f"gw-{n}", provider="test", billing_units=1, cost_usd=Decimal("0.001")),
            raw={"id": f"resp-{n}"}, finish_reason="stop",
        )  # fmt: skip


class _Asked:
    def __init__(self, result: dict[str, Any], gateway: _Gateway, updates: list[dict[str, Any]], checkpointed: list[Any]) -> None:
        self.result, self.gateway, self.updates, self.checkpointed = result, gateway, updates, checkpointed

    @property
    def texts(self) -> list[str]:
        return [u["content"]["text"] for u in self.updates if u["sessionUpdate"] == "agent_message_chunk"]

    @property
    def plans(self) -> list[Any]:
        return [u["entries"] for u in self.updates if u["sessionUpdate"] == "plan"]


async def _ask(tmp_path: Path, replies: list[str], *, check_in: bool = False) -> _Asked:
    """``check_in``: the turn stops at loop control's check-in, and the person chooses Stop."""
    (tmp_path / "README.md").write_text("Run the tests.\n", encoding="utf-8")
    gateway = _Gateway(replies)
    runner = AgentRunner(
        gateway_client=gateway, model="test-model", state_store=InMemoryAgentStateStore(),
        shell_runner=lambda command: CompletedProcess(command, 0, "ok", ""),
    )  # fmt: skip
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(runner=runner, workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound)
    checkpointed: list[Any] = []
    adapter._checkpoint_turn = lambda _turn, _prompt, result, outcome: checkpointed.append((result.stop_reason, outcome.value))  # noqa: SLF001
    created = (await adapter.handle_client_request(
        {"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
    )).response  # fmt: skip
    session_id = created["result"]["sessionId"]
    prompt = {"jsonrpc": "2.0", "id": "p1", "method": "session/prompt",
              "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": QUESTION}]}}  # fmt: skip
    task = asyncio.create_task(adapter.handle_client_request(prompt))
    if check_in:
        asked = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=10)
        assert [o["optionId"] for o in asked["params"]["options"]] == [LOOP_CONTINUE_OPTION_ID, LOOP_STOP_OPTION_ID]
        outbound.respond(asked["id"], {"outcome": {"outcome": "selected", "optionId": LOOP_STOP_OPTION_ID}})
    result = (await asyncio.wait_for(task, timeout=10)).response["result"]
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    assert len(outbound.requests) == check_in, "no permission is asked, except the check-in"
    return _Asked(result, gateway, updates, checkpointed)


async def test_an_answer_settles_completed_with_its_own_stop_code_and_no_plan(tmp_path: Path) -> None:
    asked = await _ask(tmp_path, [f"ANSWER: {ANSWER}"])

    assert asked.result == {"stopReason": "end_turn", "_meta": {"runStopReason": "PLANNING_ANSWERED", "outcome": "completed"}}
    assert asked.texts[-1].strip() == ANSWER, "the person reads the answer"
    assert asked.plans == [], "an answer sends no plan update, pending or completed"
    assert len(asked.gateway.inputs) == 1
    assert asked.checkpointed == [("PLANNING_ANSWERED", "completed")]


async def test_a_multi_line_answer_keeps_its_lines(tmp_path: Path) -> None:
    lines = ["Yes.", chr(9) + "The README says to run the tests.", "No exception is documented."]
    asked = await _ask(tmp_path, ["ANSWER: " + NL.join(lines)])

    assert asked.result["_meta"] == {"runStopReason": "PLANNING_ANSWERED", "outcome": "completed"}
    assert asked.texts[-1].strip().split(NL) == lines
    assert asked.plans == []


async def test_a_genuine_refusal_settles_exactly_as_before(tmp_path: Path) -> None:
    reason = "The task needs a file that is not visible."
    asked = await _ask(tmp_path, [f"REFUSE: {reason}"])

    assert asked.result == {"stopReason": "end_turn", "_meta": {"runStopReason": "PLANNING_MODEL_REFUSED", "outcome": "failed"}}
    assert asked.texts[-1].strip() == reason
    assert asked.plans == []
    assert len(asked.gateway.inputs) == 1
    assert asked.checkpointed == [("PLANNING_MODEL_REFUSED", "failed")]


async def test_an_answer_mixed_with_a_directive_is_unparseable_and_gets_its_notice(tmp_path: Path) -> None:
    asked = await _ask(tmp_path, [f"ANSWER: {ANSWER}" + NL + "WRITE README.md" + NL + "x", f"ANSWER: {ANSWER}"])

    assert len(asked.gateway.inputs) == 2
    assert "an ANSWER: reply must be the whole reply, with no directive line in it." in asked.gateway.inputs[1]
    assert asked.result["_meta"] == {"runStopReason": "PLANNING_ANSWERED", "outcome": "completed"}
    assert asked.plans == [], "the WRITE never became a plan"


async def test_bare_prose_is_never_an_answer_or_a_refusal(tmp_path: Path) -> None:
    asked = await _ask(tmp_path, [ANSWER] * 8, check_in=True)

    # Prose matches no planning-turn form: each reply is unparseable, loop control nudges, then asks the person.
    assert asked.result == {"stopReason": "end_turn", "_meta": {"runStopReason": "PLANNING_UNPARSEABLE_RESPONSE", "outcome": "failed"}}
    assert len(asked.gateway.inputs) == 4
    assert all(ANSWER not in text for text in asked.texts), "an unparseable answer never reaches the person"


async def test_an_observe_only_turn_one_is_unparseable_and_costs_a_second_request(tmp_path: Path) -> None:
    """#512 decision 2: the live turn-1 reply was OBSERVE: with no READ:. Scripted, it still costs a second request; whether
    a real model answers on turn 1 now that the grammar has an answer form is unproved until a live run."""
    asked = await _ask(tmp_path, [f"OBSERVE: {ANSWER}", f"ANSWER: {ANSWER}"])

    assert len(asked.gateway.inputs) == 2
    assert "an intermediate turn needs at least one ranged READ: line after its OBSERVE: line." in asked.gateway.inputs[1]
    assert asked.result["_meta"] == {"runStopReason": "PLANNING_ANSWERED", "outcome": "completed"}
    first = asked.gateway.inputs[0]
    assert "Typed refusal:" + NL + "REFUSE: <one-line sanitized reason>" in first
    assert "ANSWER: <the answer, in plain prose>" in first
    assert "Use ANSWER only for a request that asks for information and needs no file change or command;" in first
