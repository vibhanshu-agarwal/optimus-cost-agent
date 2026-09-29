"""Plan 12.1: ACP Agent/Chat mode contract and Chat answer delivery.

One canonical per-session ``ExecutionMode`` is projected through classic ACP
``modes`` and a ``mode``-category select ``configOptions`` entry. Both setters
share one validation-and-update path. A prompt snapshots the mode at
admission; a mode change during a turn applies to the next prompt only.
"""

from __future__ import annotations

import asyncio
import json
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from optimus.acp.errors import INTERNAL_ERROR, INVALID_REQUEST, AcpOutboundError
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.runtime.modes import ExecutionMode

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "acp" / "acp-v1-schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))

CHAT_ANSWER = "calc.py defines add() and subtract(); nothing else is visible in the provided context."


def _validator(definition: str) -> Draft202012Validator:
    return Draft202012Validator({"$defs": _SCHEMA["$defs"], "$ref": f"#/$defs/{definition}"})


def _assert_schema(definition: str, payload: dict[str, Any]) -> None:
    errors = [error.message for error in _validator(definition).iter_errors(payload)]
    assert errors == [], f"{definition} schema errors: {errors}"


async def _rpc(adapter: AcpDuplexAdapter, request: dict[str, Any]) -> dict[str, Any]:
    envelope = await adapter.handle_client_request(request)
    return envelope.response


class _ModeRunner:
    """Answers by the request's mode; can block inside run() on a threading.Event."""

    def __init__(self, *, block: threading.Event | None = None) -> None:
        self.requests: list[Any] = []
        self.entered = threading.Event()
        self._block = block

    def run(self, request, **kwargs):
        del kwargs
        self.requests.append(request)
        self.entered.set()
        if self._block is not None and not request.approval.approved:
            assert self._block.wait(timeout=10), "test runner was never released"
        if request.execution_mode is ExecutionMode.CHAT:
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=ExecutionMode.CHAT,
                status=AgentRunStatus.COMPLETED,
                final_state="CHAT_ONLY",
                output_text=CHAT_ANSWER,
                tool_calls=(),
                total_cost_usd=Decimal("0.001"),
                mutation_count=0,
                provider_keys_resolvable=(),
            )
        if not request.approval.approved:
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=ExecutionMode.AGENT,
                status=AgentRunStatus.AWAITING_APPROVAL,
                final_state="AWAITING_APPROVAL",
                output_text="WRITE example.py\ncontent",
                tool_calls=(),
                total_cost_usd=Decimal("0.002"),
                mutation_count=0,
                provider_keys_resolvable=(),
                plan_hash="hash-1",
            )
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=ExecutionMode.AGENT,
            status=AgentRunStatus.COMPLETED,
            final_state="COMPLETED",
            output_text="done",
            tool_calls=(AgentToolCall(tool_name="write_file", summary="wrote example.py"),),
            total_cost_usd=Decimal("0.002"),
            mutation_count=1,
            provider_keys_resolvable=(),
            plan_hash="hash-1",
        )


def _adapter(
    tmp_path: Path, runner: Any | None = None, *, outbound: RecordingOutboundChannel | None = None
) -> tuple[AcpDuplexAdapter, RecordingOutboundChannel, Any]:
    if outbound is None:
        outbound = RecordingOutboundChannel()
    runner = runner or _ModeRunner()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    return adapter, outbound, runner


async def _new_session(adapter: AcpDuplexAdapter, tmp_path: Path) -> dict[str, Any]:
    response = await _rpc(
        adapter,
        {"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}},
    )
    assert "result" in response, response
    return response["result"]


def _set_mode_request(session_id: str, value: Any, *, via: str, request_id: str = "set") -> dict[str, Any]:
    if via == "set_mode":
        return {"jsonrpc": "2.0", "id": request_id, "method": "session/set_mode", "params": {"sessionId": session_id, "modeId": value}}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/set_config_option",
        "params": {"sessionId": session_id, "configId": "mode", "value": value},
    }


def _prompt_request(session_id: str, text: str, request_id: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/prompt",
        "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
    }


def _updates(outbound: RecordingOutboundChannel) -> list[dict[str, Any]]:
    return [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]


def _mode_updates(outbound: RecordingOutboundChannel) -> list[dict[str, Any]]:
    return [u for u in _updates(outbound) if u["sessionUpdate"] in {"current_mode_update", "config_option_update"}]


def _mode_option(config_options: list[dict[str, Any]]) -> dict[str, Any]:
    matching = [option for option in config_options if option["id"] == "mode"]
    assert len(matching) == 1, config_options
    return matching[0]


def _update_mode(update: dict[str, Any]) -> str:
    if update["sessionUpdate"] == "current_mode_update":
        return update["currentModeId"]
    return _mode_option(update["configOptions"])["currentValue"]


# --- advertised projections -------------------------------------------------


async def test_session_new_advertises_synchronized_modes_and_mode_config_option(tmp_path):
    adapter, _, _ = _adapter(tmp_path)
    result = await _new_session(adapter, tmp_path)

    _assert_schema("NewSessionResponse", result)
    assert result["modes"]["currentModeId"] == "agent"
    assert [(mode["id"], mode["name"]) for mode in result["modes"]["availableModes"]] == [
        ("agent", "Agent"),
        ("chat", "Chat"),
    ]
    assert len(result["configOptions"]) == 1
    option = _mode_option(result["configOptions"])
    assert option["type"] == "select"
    assert option["category"] == "mode"
    assert option["name"] == "Mode"
    assert option["currentValue"] == "agent"
    assert [(choice["value"], choice["name"]) for choice in option["options"]] == [("agent", "Agent"), ("chat", "Chat")]


async def test_initialize_still_does_not_advertise_session_load(tmp_path):
    adapter, _, _ = _adapter(tmp_path)
    response = await _rpc(adapter, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}})
    capabilities = response["result"]["agentCapabilities"]
    assert "loadSession" not in capabilities
    assert "loadSession" not in capabilities.get("sessionCapabilities", {})


# --- setters -----------------------------------------------------------------


@pytest.mark.parametrize("via", ["set_mode", "set_config_option"])
async def test_setter_changes_mode_once_and_sends_paired_updates_before_response(tmp_path, via):
    adapter, outbound, _ = _adapter(tmp_path)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]

    response = await _rpc(adapter, _set_mode_request(session_id, "chat", via=via))

    assert "error" not in response, response
    if via == "set_mode":
        _assert_schema("SetSessionModeResponse", response["result"])
        assert response["result"] == {}
    else:
        _assert_schema("SetSessionConfigOptionResponse", response["result"])
        assert _mode_option(response["result"]["configOptions"])["currentValue"] == "chat"
    updates = _mode_updates(outbound)
    assert [u["sessionUpdate"] for u in updates] == ["current_mode_update", "config_option_update"]
    assert updates[0]["currentModeId"] == "chat"
    assert _mode_option(updates[1]["configOptions"])["currentValue"] == "chat"
    for notification in outbound.notifications:
        _assert_schema("SessionNotification", notification["params"])
    assert adapter._sessions.get(session_id).execution_mode is ExecutionMode.CHAT  # noqa: SLF001


@pytest.mark.parametrize("via", ["set_mode", "set_config_option"])
async def test_repeating_the_current_mode_is_idempotent(tmp_path, via):
    adapter, outbound, _ = _adapter(tmp_path)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]

    response = await _rpc(adapter, _set_mode_request(session_id, "agent", via=via))

    assert "error" not in response, response
    if via == "set_mode":
        assert response["result"] == {}
    else:
        assert _mode_option(response["result"]["configOptions"])["currentValue"] == "agent"
    assert _mode_updates(outbound) == []


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("session/set_mode", {"sessionId": "session-missing", "modeId": "chat"}),
        ("session/set_mode", {"sessionId": "{sid}", "modeId": "plan"}),
        ("session/set_mode", {"sessionId": "{sid}", "modeId": 7}),
        ("session/set_mode", {"sessionId": "{sid}"}),
        ("session/set_mode", "not-an-object"),
        ("session/set_config_option", {"sessionId": "session-missing", "configId": "mode", "value": "chat"}),
        ("session/set_config_option", {"sessionId": "{sid}", "configId": "model", "value": "chat"}),
        ("session/set_config_option", {"sessionId": "{sid}", "configId": "mode", "value": "plan"}),
        ("session/set_config_option", {"sessionId": "{sid}", "configId": "mode", "type": "boolean", "value": True}),
        ("session/set_config_option", {"sessionId": "{sid}", "configId": "mode", "value": 1}),
        ("session/set_config_option", {"sessionId": "{sid}", "configId": "mode"}),
    ],
)
async def test_invalid_mode_changes_are_atomic(tmp_path, method, params):
    adapter, outbound, _ = _adapter(tmp_path)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]
    if isinstance(params, dict):
        params = {key: (session_id if value == "{sid}" else value) for key, value in params.items()}

    response = await _rpc(adapter, {"jsonrpc": "2.0", "id": "bad", "method": method, "params": params})

    assert "result" not in response, response
    # The adapter's existing request-validation error form, not "method not found".
    assert response["error"]["code"] == INVALID_REQUEST, response
    assert _mode_updates(outbound) == []
    assert adapter._sessions.get(session_id).execution_mode is ExecutionMode.AGENT  # noqa: SLF001


# --- concurrency: setters are serialized per session --------------------------


class _GatedOutbound(RecordingOutboundChannel):
    """Pauses the first ``current_mode_update`` until released, or fails one mode update."""

    def __init__(self, *, pause: bool = False, fail_update: str | None = None) -> None:
        super().__init__()
        self.paused = asyncio.Event()
        self.release = asyncio.Event()
        self._pause = pause
        self._fail_update = fail_update

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        kind = params.get("update", {}).get("sessionUpdate")
        if self._pause and kind == "current_mode_update":
            self._pause = False
            self.paused.set()
            await self.release.wait()
        if kind == self._fail_update:
            self._fail_update = None
            raise AcpOutboundError(code=INTERNAL_ERROR, message="outbound delivery failed")
        await super().notify(method, params)


@pytest.mark.parametrize(
    ("first_via", "second_via"),
    [("set_config_option", "set_mode"), ("set_mode", "set_config_option"), ("set_config_option", "set_config_option")],
)
async def test_concurrent_setters_are_serialized_per_session(tmp_path, first_via, second_via):
    outbound = _GatedOutbound(pause=True)
    adapter, _, _ = _adapter(tmp_path, outbound=outbound)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]

    first = asyncio.create_task(_rpc(adapter, _set_mode_request(session_id, "chat", via=first_via, request_id="first")))
    await asyncio.wait_for(outbound.paused.wait(), timeout=2)
    second = asyncio.create_task(
        _rpc(adapter, _set_mode_request(session_id, "agent", via=second_via, request_id="second"))
    )
    for _ in range(5):
        await asyncio.sleep(0)
    assert not second.done(), "the second setter must wait for the first setter's paired updates"
    assert _mode_updates(outbound) == []

    outbound.release.set()
    first_response, second_response = await asyncio.wait_for(asyncio.gather(first, second), timeout=2)

    assert [(u["sessionUpdate"], _update_mode(u)) for u in _mode_updates(outbound)] == [
        ("current_mode_update", "chat"),
        ("config_option_update", "chat"),
        ("current_mode_update", "agent"),
        ("config_option_update", "agent"),
    ]
    for response, expected, via in ((first_response, "chat", first_via), (second_response, "agent", second_via)):
        assert "error" not in response, response
        if via == "set_mode":
            assert response["result"] == {}
        else:
            assert _mode_option(response["result"]["configOptions"])["currentValue"] == expected
    assert adapter._sessions.get(session_id).execution_mode is ExecutionMode.AGENT  # noqa: SLF001


async def test_a_prompt_is_not_blocked_by_a_setter_mid_update(tmp_path):
    outbound = _GatedOutbound(pause=True)
    adapter, _, runner = _adapter(tmp_path, outbound=outbound)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]
    setter = asyncio.create_task(
        _rpc(adapter, _set_mode_request(session_id, "chat", via="set_config_option", request_id="to-chat"))
    )
    await asyncio.wait_for(outbound.paused.wait(), timeout=2)

    response = await asyncio.wait_for(_rpc(adapter, _prompt_request(session_id, "What does calc.py do?", "p1")), timeout=5)

    assert response["result"]["stopReason"] == "end_turn"
    # The change is committed before its updates go out, so the prompt admits as Chat.
    assert runner.requests[0].execution_mode is ExecutionMode.CHAT
    assert not setter.done()
    outbound.release.set()
    assert "error" not in await asyncio.wait_for(setter, timeout=2)


@pytest.mark.parametrize("failing_update", ["current_mode_update", "config_option_update"])
@pytest.mark.parametrize("retry_via", ["set_mode", "set_config_option"])
async def test_a_retry_resynchronizes_the_client_after_a_failed_mode_update(tmp_path, failing_update, retry_via):
    outbound = _GatedOutbound(fail_update=failing_update)
    adapter, _, _ = _adapter(tmp_path, outbound=outbound)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]

    with pytest.raises(AcpOutboundError):
        await _rpc(adapter, _set_mode_request(session_id, "chat", via="set_config_option", request_id="first"))
    assert adapter._sessions.get(session_id).execution_mode is ExecutionMode.CHAT  # noqa: SLF001
    outbound.notifications.clear()

    retry = await asyncio.wait_for(
        _rpc(adapter, _set_mode_request(session_id, "chat", via=retry_via, request_id="retry")), timeout=2
    )

    assert "error" not in retry, retry
    assert [(u["sessionUpdate"], _update_mode(u)) for u in _mode_updates(outbound)] == [
        ("current_mode_update", "chat"),
        ("config_option_update", "chat"),
    ]
    outbound.notifications.clear()
    again = await _rpc(adapter, _set_mode_request(session_id, "chat", via=retry_via, request_id="again"))
    assert "error" not in again, again
    assert _mode_updates(outbound) == [], "once synchronized, repeating the mode is idempotent again"


# --- concurrency: snapshot at admission ---------------------------------------


async def test_mode_change_during_a_chat_turn_applies_to_the_next_prompt_only(tmp_path):
    release = threading.Event()
    runner = _ModeRunner(block=release)
    adapter, outbound, _ = _adapter(tmp_path, runner)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]
    assert "error" not in await _rpc(adapter, _set_mode_request(session_id, "chat", via="set_mode", request_id="to-chat"))
    outbound.notifications.clear()

    prompt = asyncio.create_task(_rpc(adapter, _prompt_request(session_id, "What does calc.py do?", "p1")))
    assert await asyncio.to_thread(runner.entered.wait, 5)

    switch = await asyncio.wait_for(
        _rpc(adapter, _set_mode_request(session_id, "agent", via="set_config_option", request_id="to-agent")),
        timeout=2,
    )
    assert "error" not in switch
    assert not prompt.done(), "the set-mode response must not wait for the in-flight turn"
    assert [u["sessionUpdate"] for u in _mode_updates(outbound)] == ["current_mode_update", "config_option_update"]

    release.set()
    response = await asyncio.wait_for(prompt, timeout=5)

    assert response["result"]["stopReason"] == "end_turn"
    assert runner.requests[0].execution_mode is ExecutionMode.CHAT
    turn_updates = [u for u in _updates(outbound) if u["sessionUpdate"] not in {"current_mode_update", "config_option_update"}]
    assert [u["sessionUpdate"] for u in turn_updates if u["sessionUpdate"] == "plan"] == []
    answers = [u["content"]["text"] for u in turn_updates if u["sessionUpdate"] == "agent_message_chunk"]
    assert answers == [CHAT_ANSWER]
    assert outbound.requests == [], "a Chat turn must never request permission"

    runner.entered.clear()
    next_prompt = asyncio.create_task(_rpc(adapter, _prompt_request(session_id, "Add a docstring", "p2")))
    permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)
    assert runner.requests[1].execution_mode is ExecutionMode.AGENT
    outbound.respond(permission["id"], {"outcome": {"outcome": "cancelled"}})
    await asyncio.wait_for(next_prompt, timeout=5)


async def test_mode_change_during_an_agent_turn_keeps_its_permission_request(tmp_path):
    adapter, outbound, runner = _adapter(tmp_path)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]

    prompt = asyncio.create_task(_rpc(adapter, _prompt_request(session_id, "Add a docstring", "p1")))
    permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)

    switch = await asyncio.wait_for(
        _rpc(adapter, _set_mode_request(session_id, "chat", via="set_mode", request_id="to-chat")), timeout=2
    )
    assert "error" not in switch
    assert not prompt.done(), "switching mode must not cancel the pending Agent permission request"

    outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
    response = await asyncio.wait_for(prompt, timeout=5)

    assert response["result"]["stopReason"] == "end_turn"
    assert [request.execution_mode for request in runner.requests] == [ExecutionMode.AGENT, ExecutionMode.AGENT]
    assert runner.requests[1].approval.approved is True
    assert adapter._sessions.get(session_id).execution_mode is ExecutionMode.CHAT  # noqa: SLF001


# --- Chat conversation carriage (P11.25-FU-1) --------------------------------


class _ScriptedRunner:
    """Returns one scripted Chat result per Chat call; Agent calls use _ModeRunner."""

    def __init__(self, chat_results: list[AgentRunResult] | None = None) -> None:
        self.requests: list[Any] = []
        self._chat_results = list(chat_results or [])
        self._agent = _ModeRunner()

    def run(self, request, **kwargs):
        self.requests.append(request)
        if request.execution_mode is ExecutionMode.CHAT and self._chat_results:
            return self._chat_results.pop(0).model_copy(
                update={"run_id": request.run_id, "session_id": request.session_id}
            )
        return self._agent.run(request, **kwargs)


def _chat_result(*, status=AgentRunStatus.COMPLETED, output_text=CHAT_ANSWER, stop_reason=None):
    return AgentRunResult(
        run_id="placeholder",
        session_id=None,
        execution_mode=ExecutionMode.CHAT,
        status=status,
        final_state="CHAT_ONLY" if status is AgentRunStatus.COMPLETED else status.value.upper(),
        output_text=output_text,
        tool_calls=(),
        total_cost_usd=Decimal("0.001"),
        mutation_count=0,
        provider_keys_resolvable=(),
        stop_reason=stop_reason,
    )


async def _prompt_and_settle(adapter, outbound, session_id, text, request_id, *, approve=False):
    task = asyncio.create_task(_rpc(adapter, _prompt_request(session_id, text, request_id)))
    if approve:
        permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)
        outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
        outbound.requests.clear()
    return await asyncio.wait_for(task, timeout=5)


async def test_chat_turns_share_the_canonical_history_with_agent_turns(tmp_path):
    runner = _ScriptedRunner(
        chat_results=[_chat_result(output_text="First answer."), _chat_result(output_text="Second answer.")]
    )
    adapter, outbound, _ = _adapter(tmp_path, runner)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]
    conversation = adapter._sessions.get(session_id).conversation  # noqa: SLF001

    await _prompt_and_settle(adapter, outbound, session_id, "Add a docstring", "a1", approve=True)
    envelope_after_agent = conversation.planner_envelope()
    await _rpc(adapter, _set_mode_request(session_id, "chat", via="set_mode", request_id="to-chat"))
    await _prompt_and_settle(adapter, outbound, session_id, "What changed?", "c1")
    envelope_after_chat = conversation.planner_envelope()
    await _prompt_and_settle(adapter, outbound, session_id, "And why?", "c2")
    await _rpc(adapter, _set_mode_request(session_id, "agent", via="set_config_option", request_id="to-agent"))
    await _prompt_and_settle(adapter, outbound, session_id, "Now add a test", "a2", approve=True)

    chat_requests = [r for r in runner.requests if r.execution_mode is ExecutionMode.CHAT]
    assert [r.task for r in chat_requests] == ["What changed?", "And why?"]
    assert [r.conversation_envelope for r in chat_requests] == [envelope_after_agent, envelope_after_chat]
    agent_planning = [r for r in runner.requests if r.execution_mode is ExecutionMode.AGENT and not r.approval.approved]
    # Agent keeps the envelope-inside-task form, now including the Chat turns.
    assert agent_planning[-1].task.endswith("\nNow add a test")
    assert "Second answer." in agent_planning[-1].task
    assert agent_planning[-1].conversation_envelope == ""
    records = [conversation.records[seq] for seq in sorted(conversation.records)]
    assert [record.user_prompt for record in records] == ["Add a docstring", "What changed?", "And why?", "Now add a test"]
    chat_records = records[1:3]
    assert [record.completion_text for record in chat_records] == ["First answer.", "Second answer."]
    assert all(record.plan_text == "" for record in chat_records)
    assert all(record.outcome.value == "completed" for record in chat_records)
    assert all(record.effect_state.value == "none" for record in chat_records)


# --- Chat terminal failures and cancellation ----------------------------------

_FAILURES = [
    (AgentRunStatus.FAILED, "CHAT_EMPTY_ANSWER", "Chat received an empty answer from the model."),
    (AgentRunStatus.FAILED, "CHAT_GATEWAY_FAILURE", "Chat could not get an answer: the gateway failed."),
    (AgentRunStatus.FAILED, "CHAT_GATEWAY_COST_UNKNOWN", "Chat stopped: the call's cost is unknown."),
    (AgentRunStatus.TERMINATED, "BUDGET_EXHAUSTED", "Chat's answer exceeded this prompt's cost limit."),
]


@pytest.mark.parametrize(("status", "stop_reason", "message"), _FAILURES)
async def test_chat_failures_are_visible_non_success_turns_that_end_normally(tmp_path, status, stop_reason, message):
    runner = _ScriptedRunner(chat_results=[_chat_result(status=status, output_text=message, stop_reason=stop_reason)])
    adapter, outbound, _ = _adapter(tmp_path, runner)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]
    await _rpc(adapter, _set_mode_request(session_id, "chat", via="set_mode", request_id="to-chat"))
    outbound.notifications.clear()

    response = await _prompt_and_settle(adapter, outbound, session_id, "What does calc.py do?", "c1")

    assert response["result"]["stopReason"] == "end_turn"
    updates = _updates(outbound)
    assert [u for u in updates if u["sessionUpdate"] == "plan"] == []
    assert [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"] == [message]
    assert "Turn completed." not in json.dumps(updates)
    record = adapter._sessions.get(session_id).conversation.records[1]  # noqa: SLF001
    assert record.outcome.value != "completed"
    assert record.completion_text == message


async def test_cancelled_chat_turn_returns_cancelled_without_a_plan_card(tmp_path):
    release = threading.Event()
    runner = _ModeRunner(block=release)
    adapter, outbound, _ = _adapter(tmp_path, runner)
    session_id = (await _new_session(adapter, tmp_path))["sessionId"]
    await _rpc(adapter, _set_mode_request(session_id, "chat", via="set_mode", request_id="to-chat"))
    outbound.notifications.clear()

    prompt = asyncio.create_task(_rpc(adapter, _prompt_request(session_id, "What does calc.py do?", "c1")))
    assert await asyncio.to_thread(runner.entered.wait, 5)
    await adapter.handle_client_notification(
        {"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}}
    )
    release.set()
    response = await asyncio.wait_for(prompt, timeout=5)

    assert response["result"]["stopReason"] == "cancelled"
    assert [u for u in _updates(outbound) if u["sessionUpdate"] == "plan"] == []
    record = adapter._sessions.get(session_id).conversation.records[1]  # noqa: SLF001
    assert record.outcome.value == "cancelled"
    # A cancelled Chat turn must not carry a success-shaped completion.
    assert record.completion_text not in {CHAT_ANSWER, "Turn completed."}


def test_mode_setters_are_approved_diagnostic_method_categories():
    from optimus.acp.server import APPROVED_METHOD_CATEGORIES

    assert {"session/set_mode", "session/set_config_option"} <= APPROVED_METHOD_CATEGORIES
