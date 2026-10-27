"""#397 (ADR-009 rung 2) through the real launch composition, offline: unit-tier composition coverage, not live
acceptance (that is the plan's acpx slice and the Zed UI test).

The launch is ``test_auto_launch_end_to_end``'s: the real harness, server, adapter, ``AgentRunner`` and H, with the
Gateway's network replaced by the real Gateway handlers over a scripted provider. An easy-tier Agent turn plans on Luna,
repeats one read past its nudge, and is moved once to the escalation model (Gemini) with a live notice. Gemini settles a
plan, the episode's check-in is continued, the plan is approved, and the application writes the file on the moved-to
model and binder. Nothing is called while the check-in waits. No network or paid call is made.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from optimus.acp.shapes import LOOP_CONTINUE_OPTION_ID
from optimus.telemetry.events import TelemetryEventKind
from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter
from tests.unit.acp.test_auto_launch_end_to_end import GEMINI, LUNA, launch  # noqa: F401 - fixture

READ_A = "OBSERVE: need the header\nREAD: a.py#bytes=0:5\n"
PLAN = "WRITE b.py\nCODE_NAME = 'TANGERINE-47'\n"


@pytest.fixture
def escalating(launch, tmp_path):  # noqa: F811
    server, provider, gateway, events, adapters = launch
    provider.tiers, provider.answers = ["easy"], [READ_A] * 4 + [PLAN]
    (tmp_path / "a.py").write_text("0123456789abcdef", encoding="utf-8")
    return launch


def _texts(writer: MemoryLineWriter) -> list[str]:
    updates = [m["params"]["update"] for m in writer.messages if m.get("method") == "session/update"]
    return [u["content"]["text"] for u in updates if u.get("sessionUpdate") == "agent_message_chunk"]


async def _next_permission(writer: MemoryLineWriter, seen: set[Any]) -> dict[str, Any]:
    while True:
        for message in writer.messages:
            if message.get("method") == "session/request_permission" and message["id"] not in seen:
                seen.add(message["id"])
                return message
        await asyncio.sleep(0.01)


async def test_an_easy_turn_escalates_once_then_its_plan_is_approved_and_applied_on_the_moved_to_model(escalating, tmp_path) -> None:
    server, provider, gateway, events, adapters = escalating
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serving = asyncio.create_task(server.serve_ndjson(reader, writer))

    async def call(request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await reader.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=10)

    try:
        await call("init", "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        session_id = (await call("new", "session/new", {"cwd": str(tmp_path), "mcpServers": []}))["result"]["sessionId"]
        prompt = {"sessionId": session_id, "prompt": [{"type": "text", "text": "What is the release code name? Record it in b.py."}]}
        await reader.send({"jsonrpc": "2.0", "id": "t1", "method": "session/prompt", "params": prompt})

        seen: set[Any] = set()
        checkin = await asyncio.wait_for(_next_permission(writer, seen), timeout=10)
        assert checkin["params"]["_meta"]["loopCheckIn"] is True
        # Nothing runs while the user is asked (ADR-009 requirement 3).
        calls_at_checkin = len(provider.messages)
        await asyncio.sleep(0.3)
        assert len(provider.messages) == calls_at_checkin
        await reader.send(
            {"jsonrpc": "2.0", "id": checkin["id"], "result": {"outcome": {"outcome": "selected", "optionId": LOOP_CONTINUE_OPTION_ID}}}
        )
        approval = await asyncio.wait_for(_next_permission(writer, seen), timeout=10)
        await reader.send({"jsonrpc": "2.0", "id": approval["id"], "result": {"outcome": {"outcome": "selected", "optionId": "approve"}}})
        assert (await asyncio.wait_for(writer.wait_for_response("t1"), timeout=10))["result"]["stopReason"] == "end_turn"

        [adapter] = adapters
        receipts = list(adapter._sessions.get(session_id).cost_settlement.receipts(f"{session_id}:1"))  # noqa: SLF001
    finally:
        reader.close()
        await asyncio.wait_for(serving, timeout=10)

    # Luna planned the three steps and the nudge; the escalation moved the rest of the turn to Gemini, once.
    assert [m for m in provider.messages] == [LUNA] * 4 + [GEMINI]
    turn_requests = [p for p in gateway.payloads if p["model"] in (LUNA, GEMINI)]
    assert [p["model"] for p in turn_requests] == [LUNA] * 4 + [GEMINI]
    assert "moved this planning to you" in turn_requests[4]["input"]

    # The user saw the routing line, then the escalation notice with the signal and the price change.
    texts = _texts(writer)
    [escalation] = [t for t in texts if t.startswith("Auto: escalating to ")]
    assert escalation.startswith(f"Auto: escalating to {GEMINI}: the model repeated the read of a.py#bytes=0:5")
    assert "and one nudge did not help. Price per million tokens: $0.75 in / $3.75 out (was $0.20 in / $1.00 out)." in escalation
    routed_line = next(i for i, text in enumerate(texts) if text.startswith(f"Auto: easy → {LUNA}"))
    assert texts.index(escalation) > routed_line
    checkin_text = checkin["params"]["toolCall"]["content"][0]["content"]["text"]
    assert f"then moved to {GEMINI}" in checkin_text and "A final plan is ready" in checkin_text

    # The application ran on the moved-to model and binder, and the file was written.
    assert (tmp_path / "b.py").read_text(encoding="utf-8") == "CODE_NAME = 'TANGERINE-47'\n"

    # The routing record stays the classifier's; the loop record names the move; each planning receipt settled.
    [routed] = [e.payload for e in events if e.kind is TelemetryEventKind.AUTO_ROUTING]
    assert (routed["tier"], routed["model_id"]) == ("easy", LUNA)
    loop = [e.payload for e in events if e.kind is TelemetryEventKind.LOOP_RECOVERY]
    [moved] = [r for r in loop if r["record"] == "escalation"]
    assert (moved["decision"], moved["from_model"], moved["to_model"], moved["notice_delivered"]) == ("granted", LUNA, GEMINI, True)
    assert [r["record"] for r in loop][-1] == "check_in"
    planning = [r for r in receipts if r.stage == "planning"]
    assert len(planning) == 5 and {r.outcome for r in planning} == {"completed"}
    # Each request's receipt names the route that sent it: Luna's tier role, then Gemini's escalation role.
    assert [(r.requested_model, r.role) for r in planning] == [(LUNA, "easy")] * 4 + [(GEMINI, "escalation")]

    # The turn's meter still covers every request it sent (the attached packer keeps its readings across the switch).
    usage = [m["params"]["update"] for m in writer.messages if m.get("method") == "session/update"]
    [meter] = [u for u in usage if u.get("sessionUpdate") == "usage_update"][-1:]
    assert meter["used"] > 0 and meter["size"] > 0


async def test_a_medium_turn_already_on_the_escalation_model_goes_straight_to_the_check_in_and_says_so(launch, tmp_path) -> None:  # noqa: F811
    server, provider, gateway, events, adapters = launch
    provider.tiers, provider.answers = ["medium"], [READ_A] * 4
    (tmp_path / "a.py").write_text("0123456789abcdef", encoding="utf-8")
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serving = asyncio.create_task(server.serve_ndjson(reader, writer))

    async def call(request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await reader.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=10)

    try:
        await call("init", "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        session_id = (await call("new", "session/new", {"cwd": str(tmp_path), "mcpServers": []}))["result"]["sessionId"]
        prompt = {"sessionId": session_id, "prompt": [{"type": "text", "text": "What is the release code name? Record it in b.py."}]}
        await reader.send({"jsonrpc": "2.0", "id": "t1", "method": "session/prompt", "params": prompt})
        checkin = await asyncio.wait_for(_next_permission(writer, set()), timeout=10)
        await reader.send({"jsonrpc": "2.0", "id": checkin["id"], "result": {"outcome": {"outcome": "selected", "optionId": "loop-stop"}}})
        assert (await asyncio.wait_for(writer.wait_for_response("t1"), timeout=10))["result"]["stopReason"] == "end_turn"
    finally:
        reader.close()
        await asyncio.wait_for(serving, timeout=10)

    assert provider.messages == [GEMINI] * 4
    assert not [t for t in _texts(writer) if t.startswith("Auto: escalating to ")]
    assert "Auto had no stronger eligible model to try." in checkin["params"]["toolCall"]["content"][0]["content"]["text"]
    [moved] = [e.payload for e in events if e.kind is TelemetryEventKind.LOOP_RECOVERY and e.payload["record"] == "escalation"]
    assert moved["decision"] == "no_target" and "to_model" not in moved


async def test_the_meter_keeps_a_larger_request_sent_before_the_switch(launch, tmp_path) -> None:  # noqa: F811
    # Luna's three repeats of a large read each carry 6,000 bytes of new evidence; the nudge step reads a small range,
    # so the allowance ends without a plan and the turn moves. Gemini's request then carries only the small read, so
    # the turn's largest request was sent before the switch, and the meter must still show it.
    from optimus.context.shipped_policy import attachment_limits
    from optimus_model_policy.binding import auto_snapshot

    server, provider, gateway, events, adapters = launch
    big = "OBSERVE: need the whole header\nREAD: a.py#bytes=0:6000\n"
    provider.tiers, provider.answers = ["easy"], [big] * 3 + [READ_A, PLAN]
    (tmp_path / "a.py").write_text("x" * 6000, encoding="utf-8")
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serving = asyncio.create_task(server.serve_ndjson(reader, writer))

    async def call(request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await reader.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=10)

    try:
        await call("init", "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        session_id = (await call("new", "session/new", {"cwd": str(tmp_path), "mcpServers": []}))["result"]["sessionId"]
        prompt = {"sessionId": session_id, "prompt": [{"type": "text", "text": "What is the release code name? Record it in b.py."}]}
        await reader.send({"jsonrpc": "2.0", "id": "t1", "method": "session/prompt", "params": prompt})
        seen: set[Any] = set()
        checkin = await asyncio.wait_for(_next_permission(writer, seen), timeout=10)
        await reader.send(
            {"jsonrpc": "2.0", "id": checkin["id"], "result": {"outcome": {"outcome": "selected", "optionId": LOOP_CONTINUE_OPTION_ID}}}
        )
        approval = await asyncio.wait_for(_next_permission(writer, seen), timeout=10)
        await reader.send({"jsonrpc": "2.0", "id": approval["id"], "result": {"outcome": {"outcome": "selected", "optionId": "approve"}}})
        assert (await asyncio.wait_for(writer.wait_for_response("t1"), timeout=10))["result"]["stopReason"] == "end_turn"
    finally:
        reader.close()
        await asyncio.wait_for(serving, timeout=10)

    turn_requests = [p for p in gateway.payloads if p["model"] in (LUNA, GEMINI)]
    assert [p["model"] for p in turn_requests] == [LUNA] * 4 + [GEMINI]
    snapshot = auto_snapshot()
    sizes = [attachment_limits(snapshot, p["model"]).estimate_request(p["input"]) for p in turn_requests]
    largest = max(range(len(sizes)), key=sizes.__getitem__)
    assert largest < 4 and sizes[largest] > sizes[4]  # the arrangement: a pre-switch request is the largest
    usage = [m["params"]["update"] for m in writer.messages if m.get("method") == "session/update"]
    meter = [u for u in usage if u.get("sessionUpdate") == "usage_update"][-1]
    assert (meter["used"], meter["size"]) == (sizes[largest], attachment_limits(snapshot, LUNA).usable_input_tokens)
