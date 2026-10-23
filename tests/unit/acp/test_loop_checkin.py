"""Plan 12.3 Design 5-6: the recovery check-in bridge, separate from plan approval, and the setting that
selects interactive or headless recovery."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.acp.launch_gate import _MONOTONIC_DEFAULTS
from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES
from optimus.acp.shapes import build_loop_checkin_params
from optimus.acp.spec import (
    _PLANNING_TERMINAL_STOP_REASONS,
    AcpDuplexAdapter,
    InMemoryAcpSpecSessionStore,
    RecordingOutboundChannel,
    _permission_approved,
    checkin_decision,
    resolve_interactive_recovery,
)
from optimus.agent.planning_loop import CheckInDecision
from optimus.agent.runner import AgentRunner
from optimus.gateway.models import GatewayResponse, GatewayUsage

READ_A = "OBSERVE: need the header\nREAD: a.py#bytes=0:5\n"
PROSE = "Here is prose only."
FINAL_PLAN = "READ a.py\nWRITE a.py\nupdated\n"
SOURCE = "0123456789abcdef"
CONTINUE = {"outcome": {"outcome": "selected", "optionId": "loop-continue"}}
STOP = {"outcome": {"outcome": "selected", "optionId": "loop-stop"}}


def test_the_check_in_has_its_own_options_with_the_plan_approval_kinds():
    params = build_loop_checkin_params(session_id="s", tool_call_id="t", text="paused", run_id="r")
    assert [(o["optionId"], o["kind"]) for o in params["options"]] == [
        ("loop-continue", "allow_once"),
        ("loop-stop", "reject_once"),
    ]
    assert params["toolCall"]["content"][0]["content"]["text"] == "paused"


@pytest.mark.parametrize(
    ("response", "decision"),
    [
        (CONTINUE, CheckInDecision.CONTINUE),
        (STOP, CheckInDecision.STOP),
        ({"outcome": {"outcome": "cancelled"}}, CheckInDecision.STOP),
        ({"outcome": {"outcome": "selected", "optionId": "approve"}}, CheckInDecision.INVALID),
        ({"outcome": {"outcome": "selected"}}, CheckInDecision.INVALID),
        ({"outcome": "selected"}, CheckInDecision.INVALID),
        ("garbage", CheckInDecision.INVALID),
    ],
)
def test_only_the_check_ins_own_options_count(response, decision):
    assert checkin_decision(response) is decision


def test_continue_can_never_approve_a_plan():
    assert not _permission_approved(CONTINUE)


def test_the_new_stop_reasons_end_the_turn_with_their_text():
    assert {"PLANNING_REPEATED_MCP_REQUEST", "PLANNING_ACTION_CYCLE", "PLANNING_NO_PROGRESS"} <= _PLANNING_TERMINAL_STOP_REASONS


@pytest.mark.parametrize(
    ("environ", "caller_default", "interactive"),
    [
        ({}, True, True),
        ({}, False, False),
        ({"OPTIMUS_LOOP_RECOVERY": " "}, True, True),
        ({"OPTIMUS_LOOP_RECOVERY": "headless"}, True, False),
        ({"OPTIMUS_LOOP_RECOVERY": "Interactive"}, False, True),
    ],
)
def test_the_explicit_setting_wins_over_the_callers_default(environ, caller_default, interactive):
    assert resolve_interactive_recovery(environ, caller_default=caller_default) is interactive


def test_an_unknown_recovery_mode_is_refused():
    with pytest.raises(ValueError, match="interactive or headless"):
        resolve_interactive_recovery({"OPTIMUS_LOOP_RECOVERY": "auto"}, caller_default=True)


def test_the_launch_gate_treats_headless_as_a_free_tightening():
    parser = LAUNCH_VARIABLE_POLICIES["OPTIMUS_LOOP_RECOVERY"].parser
    assert (parser("headless"), parser("interactive")) == (0, 1)
    assert _MONOTONIC_DEFAULTS["OPTIMUS_LOOP_RECOVERY"] == 1
    with pytest.raises(ValueError):
        parser("auto")


# --- through the adapter and the real runner ---


class Gateway:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls = 0

    def create_response(self, *, model, input_text, metadata=None):
        self.calls += 1
        text = self._replies.pop(0)
        return GatewayResponse(
            response_id=f"gw-{self.calls}",
            output_text=text,
            gateway_usage=GatewayUsage(gateway_request_id=f"gw-{self.calls}", provider="glm", billing_units=1, cost_usd=Decimal("0.001")),
            raw={"id": f"gw-{self.calls}"},
        )


class FailingCheckInOutbound(RecordingOutboundChannel):
    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("_meta", {}).get("loopCheckIn"):
            raise RuntimeError("the client does not support this request")
        return await super().request(method, params)


async def _start(tmp_path: Path, replies: list[str], *, outbound=None, interactive_recovery: bool = True):
    (tmp_path / "a.py").write_text(SOURCE, encoding="utf-8")
    gateway = Gateway(replies)
    outbound = outbound or RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=AgentRunner(gateway_client=gateway, model="glm-5.2"),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
        interactive_recovery=interactive_recovery,
    )
    new = await adapter.handle_client_request(
        {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
    )
    session_id = new.response["result"]["sessionId"]
    prompt = asyncio.create_task(
        adapter.handle_client_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Update a.py"}]},
            }
        )
    )
    return adapter, gateway, outbound, session_id, prompt


async def _next_request(outbound: RecordingOutboundChannel, seen: int) -> dict[str, Any]:
    while len(outbound.requests) <= seen:
        await asyncio.sleep(0.01)
    return outbound.requests[seen]


def _messages(outbound: RecordingOutboundChannel) -> str:
    return "".join(
        item["params"]["update"]["content"]["text"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    )


async def test_stop_at_the_check_in_ends_the_turn_with_the_actual_cause(tmp_path):
    _, gateway, outbound, _, prompt = await _start(tmp_path, [READ_A] * 4)
    checkin = await _next_request(outbound, 0)
    assert checkin["method"] == "session/request_permission"
    assert checkin["params"]["_meta"]["loopCheckIn"] is True
    assert "repeated the read of a.py#bytes=0:5" in checkin["params"]["toolCall"]["content"][0]["content"]["text"]
    outbound.respond(checkin["id"], STOP)

    response = (await prompt).response
    assert response["result"]["stopReason"] == "end_turn"
    assert "Planning stopped after repeated non-progress read requests." in _messages(outbound)
    assert len(outbound.requests) == 1  # no plan approval
    assert gateway.calls == 4


async def test_continue_leads_to_the_normal_plan_approval_and_approves_nothing_itself(tmp_path):
    _, _, outbound, _, prompt = await _start(tmp_path, [PROSE] * 3 + [FINAL_PLAN])
    checkin = await _next_request(outbound, 0)
    outbound.respond(checkin["id"], CONTINUE)

    approval = await _next_request(outbound, 1)
    assert [o["optionId"] for o in approval["params"]["options"]] == ["approve", "cancel"]
    outbound.respond(approval["id"], {"outcome": {"outcome": "selected", "optionId": "cancel"}})

    response = (await prompt).response
    assert response["result"]["stopReason"] == "cancelled"
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == SOURCE  # Continue granted no WRITE


async def test_cancel_while_the_check_in_waits_cancels_the_turn(tmp_path):
    adapter, gateway, outbound, session_id, prompt = await _start(tmp_path, [READ_A] * 4 + [READ_A] * 3)
    await _next_request(outbound, 0)
    await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})

    response = (await prompt).response
    assert response["result"]["stopReason"] == "cancelled"
    assert gateway.calls == 4  # nothing ran after the cancel


async def test_a_check_in_the_client_cannot_answer_ends_the_turn_recoverably(tmp_path):
    _, gateway, outbound, _, prompt = await _start(tmp_path, [READ_A] * 4, outbound=FailingCheckInOutbound())
    response = (await prompt).response
    assert response["result"]["stopReason"] == "end_turn"
    assert "check-in to continue could not be shown" in _messages(outbound)
    assert gateway.calls == 4


async def test_a_headless_adapter_keeps_the_hard_stop(tmp_path):
    _, gateway, outbound, _, prompt = await _start(tmp_path, [READ_A] * 2, interactive_recovery=False)
    response = (await prompt).response
    assert response["result"]["stopReason"] == "end_turn"
    assert outbound.requests == []
    assert gateway.calls == 2
