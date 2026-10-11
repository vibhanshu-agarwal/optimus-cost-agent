"""Plan 12.2 Task 3: the context floor's notices and meter, made visible without changing the floor.

Main computed the 80% warning but discarded it and never sent a usage meter. This port of the sandbox
floor (tag ``sandbox-plan12-context-floor``) delivers both, words the capacity refusal so a client
shows it, and ends every agent message block with a paragraph break. The 512 KiB source limit, its
80% threshold and the admission and commit predicates are unchanged.

Main has no ``session/load``, so the notices and the meter are live-only by construction: nothing
stores or replays them.
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

from optimus.acp.conversation import (
    CONVERSATION_MAX_BYTES,
    WARNING_FIRST_BYTE,
    ConversationDisposition,
    ConversationOutcome,
    ConversationSanitizer,
    ConversationSanitizerInputs,
    ConversationState,
    ConversationTurn,
    rendered_byte_length,
)
from optimus.acp.errors import INTERNAL_ERROR, AcpOutboundError
from optimus.acp.outbound_writer import DedicatedOutboundWriter
from optimus.acp.server import NdjsonOutboundChannel
from optimus.acp.settlement import EffectState
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.runtime.modes import ExecutionMode

SEPARATOR = "\n\n"
WARNING_TEXT = (
    "Heads-up: this conversation has used about 80% of its context budget. "
    "Please start a new thread soon; once it is full, new prompts in this thread will be refused."
)
REFUSAL_TEXT = (
    "This conversation has reached its context limit, so this prompt was refused. "
    "Please start a new thread to continue."
)
REACHED_TEXT = (
    "This conversation has now reached its context limit. "
    "Please start a new thread to continue; new prompts in this thread will be refused."
)
INDETERMINATE_TEXT = "Conversation delivery is indeterminate; this prompt was refused."
COMPLETED_TEXT = "Turn completed."
CHAT_ANSWER = "calc.py defines add()."

_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures" / "acp" / "acp-v1-schema.json").read_text(encoding="utf-8")
)


def _assert_session_notification(params: dict[str, Any]) -> None:
    validator = Draft202012Validator({"$defs": _SCHEMA["$defs"], "$ref": "#/$defs/SessionNotification"})
    assert [error.message for error in validator.iter_errors(params)] == []


class _FloorRunner:
    """Completes every prompt without a plan card; the next result's plan text and cost are settable."""

    def __init__(self, *, block: threading.Event | None = None) -> None:
        self.requests: list[Any] = []
        self.entered = threading.Event()
        self.plan_text: str | None = None
        self.answer = CHAT_ANSWER
        self.cost = Decimal("0.002")
        self.cost_complete = True
        self._block = block

    def run(self, request: Any, **kwargs: Any) -> AgentRunResult:
        del kwargs
        self.requests.append(request)
        self.entered.set()
        if self._block is not None:
            assert self._block.wait(timeout=10), "test runner was never released"
        chat = request.execution_mode is ExecutionMode.CHAT
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="CHAT_ONLY" if chat else "COMPLETED",
            output_text=self.answer if chat else "No repository change was needed.",
            tool_calls=(),
            total_cost_usd=self.cost,
            cost_complete=self.cost_complete,
            mutation_count=0,
            provider_keys_resolvable=(),
            candidate_plan_text=self.plan_text,
        )


def _adapter(tmp_path: Path, runner: _FloorRunner, outbound: Any | None = None) -> tuple[AcpDuplexAdapter, Any]:
    outbound = outbound if outbound is not None else RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    return adapter, outbound


async def _rpc(adapter: AcpDuplexAdapter, request: dict[str, Any]) -> dict[str, Any]:
    return (await adapter.handle_client_request(request)).response


async def _new_session(adapter: AcpDuplexAdapter, tmp_path: Path) -> str:
    created = await _rpc(
        adapter,
        {"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}},
    )
    return created["result"]["sessionId"]


async def _set_mode(adapter: AcpDuplexAdapter, session_id: str, mode_id: str) -> None:
    response = await _rpc(
        adapter,
        {
            "jsonrpc": "2.0",
            "id": f"to-{mode_id}",
            "method": "session/set_mode",
            "params": {"sessionId": session_id, "modeId": mode_id},
        },
    )
    assert "error" not in response, response


def _prompt_request(session_id: str, text: str, request_id: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/prompt",
        "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
    }


async def _prompt(adapter: AcpDuplexAdapter, session_id: str, text: str, request_id: str) -> dict[str, Any]:
    return await asyncio.wait_for(_rpc(adapter, _prompt_request(session_id, text, request_id)), timeout=10)


def _words(length: int) -> str:
    """ASCII text of exactly ``length`` bytes. Words, not one long token: the sanitizer that every
    committed plan passes through scans a single unbroken token slowly."""
    return ("plan line " * (length // 10 + 1))[:length]


def _seed_used_bytes(adapter: AcpDuplexAdapter, session_id: str, target_bytes: int) -> ConversationState:
    """Give the session one committed turn whose storage size is exactly ``target_bytes``."""
    state = ConversationState(ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=())))
    empty = ConversationTurn(
        user_prompt="",
        plan_text="",
        completion_text=COMPLETED_TEXT,
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )
    filler = _words(target_bytes - rendered_byte_length({1: empty}))
    decision = state.prepare_commit(
        1,
        sanitized_user_prompt=filler,
        sanitized_plan_text="",
        sanitized_completion_text=COMPLETED_TEXT,
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )
    state.commit_after_final_flush(decision)
    assert state.used_bytes == target_bytes
    adapter._sessions.get(session_id).conversation = state  # noqa: SLF001
    return state


def _session_updates(outbound: RecordingOutboundChannel) -> list[dict[str, Any]]:
    return [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]


def _texts(outbound: RecordingOutboundChannel) -> list[str]:
    return [u["content"]["text"] for u in _session_updates(outbound) if u["sessionUpdate"] == "agent_message_chunk"]


def _meters(outbound: RecordingOutboundChannel) -> list[dict[str, Any]]:
    return [u for u in _session_updates(outbound) if u["sessionUpdate"] == "usage_update"]


# --- notices: separation, readable cap refusal, end_turn ------------------------------------------


async def test_notice_separation_and_cap_end_turn(tmp_path: Path) -> None:
    runner = _FloorRunner()
    adapter, outbound = _adapter(tmp_path, runner)
    session_id = await _new_session(adapter, tmp_path)

    # Admission crosses 80%: the warning is its own block, ahead of the turn's own message.
    _seed_used_bytes(adapter, session_id, WARNING_FIRST_BYTE - 1)
    crossing = await _prompt(adapter, session_id, "Crossing task", "p1")
    assert crossing["result"] == {"stopReason": "end_turn"}
    assert _texts(outbound) == [WARNING_TEXT + SEPARATOR, COMPLETED_TEXT + SEPARATOR]

    # A full conversation is refused readably and ends the turn normally, without a provider call.
    full = _seed_used_bytes(adapter, session_id, CONVERSATION_MAX_BYTES)
    records_before = dict(full.records)
    calls_before = len(runner.requests)
    outbound.notifications.clear()
    for request_id in ("cap", "cap-closed"):
        refused = await _prompt(adapter, session_id, "One more task", request_id)
        assert refused["result"] == {"stopReason": "end_turn"}
        assert _texts(outbound)[-1] == REFUSAL_TEXT + SEPARATOR
    assert len(runner.requests) == calls_before
    assert full.disposition is ConversationDisposition.CAP_CLOSED
    assert dict(full.records) == records_before
    assert _meters(outbound) == [], "a refusal dispatches nothing, so it sends no new reading"

    # Delivery-indeterminate refusals keep stopReason "refusal".
    unsure = _seed_used_bytes(adapter, session_id, 1_000)
    unsure.latch_delivery_indeterminate()
    outbound.notifications.clear()
    refused = await _prompt(adapter, session_id, "Another task", "unsure")
    assert refused["result"] == {"stopReason": "refusal"}
    assert _texts(outbound) == [INDETERMINATE_TEXT + SEPARATOR]
    assert len(runner.requests) == calls_before

    # Every agent message block ends with the separator, so a client never runs two together.
    for notification in outbound.notifications:
        _assert_session_notification(notification["params"])


async def test_every_agent_message_block_ends_with_a_paragraph_break(tmp_path: Path) -> None:
    runner = _FloorRunner()
    adapter, outbound = _adapter(tmp_path, runner)
    session_id = await _new_session(adapter, tmp_path)
    await _prompt(adapter, session_id, "Agent task", "a1")
    await _set_mode(adapter, session_id, "chat")
    await _prompt(adapter, session_id, "Chat question", "c1")

    texts = _texts(outbound)
    assert texts == [COMPLETED_TEXT + SEPARATOR, CHAT_ANSWER + SEPARATOR]
    # The canonical record keeps the text without the presentation separator.
    conversation = adapter._sessions.get(session_id).conversation  # noqa: SLF001
    assert [conversation.records[seq].completion_text for seq in (1, 2)] == [COMPLETED_TEXT, CHAT_ANSWER]


async def test_the_warning_is_sent_once(tmp_path: Path) -> None:
    runner = _FloorRunner()
    adapter, outbound = _adapter(tmp_path, runner)
    session_id = await _new_session(adapter, tmp_path)
    state = _seed_used_bytes(adapter, session_id, WARNING_FIRST_BYTE - 1)

    for request_id in ("p1", "p2", "p3"):
        assert "result" in await _prompt(adapter, session_id, "Next task", request_id)

    assert _texts(outbound).count(WARNING_TEXT + SEPARATOR) == 1
    assert state.warning_confirmed is True


async def test_a_reply_that_crosses_80_percent_warns_after_the_reply(tmp_path: Path) -> None:
    runner = _FloorRunner()
    adapter, outbound = _adapter(tmp_path, runner)
    session_id = await _new_session(adapter, tmp_path)
    state = _seed_used_bytes(adapter, session_id, WARNING_FIRST_BYTE - 20_000)

    runner.plan_text = _words(30_000)
    assert "result" in await _prompt(adapter, session_id, "Short prompt", "p1")

    assert WARNING_FIRST_BYTE <= state.used_bytes <= CONVERSATION_MAX_BYTES
    assert _texts(outbound) == [COMPLETED_TEXT + SEPARATOR, WARNING_TEXT + SEPARATOR]
    assert state.warning_confirmed is True
    assert [u["sessionUpdate"] for u in _session_updates(outbound)][-1] == "usage_update"


async def test_a_reply_that_fills_the_conversation_says_so_at_once(tmp_path: Path) -> None:
    runner = _FloorRunner()
    adapter, outbound = _adapter(tmp_path, runner)
    session_id = await _new_session(adapter, tmp_path)
    state = _seed_used_bytes(adapter, session_id, WARNING_FIRST_BYTE - 20_000)

    runner.plan_text = _words(150_000)
    assert "result" in await _prompt(adapter, session_id, "Short prompt", "p1")

    assert state.disposition is ConversationDisposition.CAP_CLOSED
    assert _texts(outbound) == [COMPLETED_TEXT + SEPARATOR, REACHED_TEXT + SEPARATOR]
    refused = await _prompt(adapter, session_id, "And now?", "p2")
    assert refused["result"] == {"stopReason": "end_turn"}
    assert _texts(outbound)[-1] == REFUSAL_TEXT + SEPARATOR


class _LatchingRunner(_FloorRunner):
    """Latches the conversation's delivery-indeterminate disposition while the turn runs."""

    def __init__(self, conversation: ConversationState) -> None:
        super().__init__()
        self._conversation = conversation

    def run(self, request: Any, **kwargs: Any) -> AgentRunResult:
        self._conversation.latch_delivery_indeterminate()
        return super().run(request, **kwargs)


async def test_a_reply_past_the_cap_never_gets_the_soon_warning(tmp_path: Path) -> None:
    """No production path latches delivery-indeterminate mid-turn today; this pins the precedence.

    The commit closes the cap, but the earlier disposition keeps the conversation from becoming
    CAP_CLOSED. Telling the user to start a new thread "soon" would then be wrong, so no capacity
    notice is sent; the disposition is kept and the meter still follows the commit.
    """
    adapter, outbound = _adapter(tmp_path, _FloorRunner())
    session_id = await _new_session(adapter, tmp_path)
    state = _seed_used_bytes(adapter, session_id, WARNING_FIRST_BYTE - 20_000)
    runner = _LatchingRunner(state)
    runner.plan_text = _words(150_000)
    adapter._runner = runner  # noqa: SLF001

    assert "result" in await _prompt(adapter, session_id, "Short prompt", "p1")

    assert state.used_bytes > CONVERSATION_MAX_BYTES
    assert state.disposition is ConversationDisposition.DELIVERY_INDETERMINATE
    assert _texts(outbound) == [COMPLETED_TEXT + SEPARATOR]
    assert [u["sessionUpdate"] for u in _session_updates(outbound)][-1] == "usage_update"


def test_rearm_allows_another_attempt_only_until_the_warning_is_confirmed() -> None:
    state = ConversationState(ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=())))
    assert state.note_warning_threshold_for_attempt(WARNING_FIRST_BYTE) is True
    assert state.note_warning_threshold_for_attempt(WARNING_FIRST_BYTE) is False, "one attempt at a time"

    state.rearm_warning_attempt()
    assert state.note_warning_threshold_for_attempt(WARNING_FIRST_BYTE + 10) is True

    state.confirm_warning_flushed()
    state.rearm_warning_attempt()
    assert state.warning_confirmed is True
    assert state.note_warning_threshold_for_attempt(WARNING_FIRST_BYTE + 100) is False


class _FailOnceForWarningTransport:
    """Physical NDJSON transport that fails the first warning send, either before or after writing it.

    ``write`` fails before any byte lands, but the dedicated writer has already marked the write as
    started, so it cannot prove nothing reached the client and reports an ambiguous send. ``flush``
    lands the bytes, then the flush fails: also ambiguous. Neither may confirm the warning.
    """

    def __init__(self, fail_at: str) -> None:
        self.messages: list[dict[str, Any]] = []
        self._fail_at: str | None = fail_at
        self._lock = threading.Lock()

    @staticmethod
    def _is_warning(message: dict[str, Any]) -> bool:
        params = message.get("params")
        update = params.get("update", {}) if isinstance(params, dict) else {}
        content = update.get("content")
        return isinstance(content, dict) and content.get("text") == WARNING_TEXT + SEPARATOR

    def write_bytes(self, data: bytes) -> None:
        batch = [json.loads(line) for line in data.splitlines() if line.strip()]
        with self._lock:
            if self._fail_at == "write" and any(self._is_warning(m) for m in batch):
                self._fail_at = None
                raise OSError("write failed before any byte landed")
            self.messages.extend(batch)

    def flush(self) -> None:
        with self._lock:
            last = self.messages[-1] if self.messages else {}
            if self._fail_at == "flush" and self._is_warning(last):
                self._fail_at = None
                raise OSError("flush failed after the write")

    def warning_count(self) -> int:
        with self._lock:
            return sum(1 for message in self.messages if self._is_warning(message))


class _UnusedLineWriter:
    async def write_line(self, message: Any) -> None:
        raise AssertionError("the dedicated writer owns every physical write")


@pytest.mark.parametrize(("fail_at", "warnings_on_the_wire"), [("write", 1), ("flush", 2)])
async def test_an_undelivered_warning_is_sent_again_when_the_turn_commits(
    tmp_path: Path, fail_at: str, warnings_on_the_wire: int
) -> None:
    """A possible duplicate warning is preferred to a lost one: only a confirmed flush confirms it."""
    transport = _FailOnceForWarningTransport(fail_at)
    dedicated = DedicatedOutboundWriter(transport)
    dedicated.start()
    try:
        runner = _FloorRunner()
        adapter, _ = _adapter(tmp_path, runner, NdjsonOutboundChannel(_UnusedLineWriter(), dedicated_writer=dedicated))
        session_id = await _new_session(adapter, tmp_path)
        state = _seed_used_bytes(adapter, session_id, WARNING_FIRST_BYTE - 1)

        crossing = await _prompt(adapter, session_id, "Crossing task", "p1")
        assert crossing["result"] == {"stopReason": "end_turn"}, "a failed notice never fails the turn"
        assert transport.warning_count() == warnings_on_the_wire
        assert state.warning_confirmed is True

        assert "result" in await _prompt(adapter, session_id, "Next task", "p2")
        assert transport.warning_count() == warnings_on_the_wire
    finally:
        dedicated.close_and_join()


# --- the usage meter --------------------------------------------------------------------------


class _MeterFailsChannel(RecordingOutboundChannel):
    async def notify(self, method: str, params: dict[str, Any], *, require_flushed: bool = False) -> None:
        if params.get("update", {}).get("sessionUpdate") == "usage_update":
            raise AcpOutboundError(code=INTERNAL_ERROR, message="outbound delivery failed")
        await super().notify(method, params, require_flushed=require_flushed)


async def test_floor_usage_live_only(tmp_path: Path) -> None:
    runner = _FloorRunner()
    adapter, outbound = _adapter(tmp_path, runner)
    session_id = await _new_session(adapter, tmp_path)
    conversation_used: list[int] = []

    for request_id in ("p1", "p2"):
        assert "result" in await _prompt(adapter, session_id, f"Task {request_id}", request_id)
        conversation = adapter._sessions.get(session_id).conversation  # noqa: SLF001
        conversation_used.append(conversation.used_bytes)
        # The meter is the turn's last update, after its own message.
        assert _session_updates(outbound)[-1]["sessionUpdate"] == "usage_update"

    meters = _meters(outbound)
    assert [m["used"] for m in meters] == [used // 4 for used in conversation_used]
    assert [m["size"] for m in meters] == [CONVERSATION_MAX_BYTES // 4] * 2
    # ACP v1 Cost.amount is a JSON number; the session total is summed exactly before conversion.
    assert [m["cost"] for m in meters] == [
        {"amount": 0.002, "currency": "USD"},
        {"amount": 0.004, "currency": "USD"},
    ]
    for notification in outbound.notifications:
        _assert_session_notification(notification["params"])

    # Once any cost is unknown, the session cost is incomplete and the meter omits it.
    runner.cost_complete = False
    assert "result" in await _prompt(adapter, session_id, "Task p3", "p3")
    runner.cost_complete = True
    assert "result" in await _prompt(adapter, session_id, "Task p4", "p4")
    assert ["cost" in m for m in _meters(outbound)] == [True, True, False, False]

    # Live-only: the meter is never part of canonical history, and nothing can replay it.
    conversation = adapter._sessions.get(session_id).conversation  # noqa: SLF001
    assert len(conversation.records) == 4
    assert "usage_update" not in conversation.planner_envelope()
    load = await _rpc(
        adapter,
        {"jsonrpc": "2.0", "id": "load", "method": "session/load", "params": {"sessionId": session_id}},
    )
    assert "error" in load, "main has no session/load, so no live-only signal can be replayed"


async def test_the_meter_follows_chat_answers_and_cancelled_chat_turns(tmp_path: Path) -> None:
    release = threading.Event()
    runner = _FloorRunner(block=release)
    adapter, outbound = _adapter(tmp_path, runner)
    session_id = await _new_session(adapter, tmp_path)
    await _set_mode(adapter, session_id, "chat")
    outbound.notifications.clear()

    release.set()
    assert (await _prompt(adapter, session_id, "What does calc.py do?", "c1"))["result"] == {"stopReason": "end_turn"}
    assert [u["sessionUpdate"] for u in _session_updates(outbound)] == ["agent_message_chunk", "usage_update"]

    release.clear()
    runner.entered.clear()
    outbound.notifications.clear()
    prompt = asyncio.create_task(_rpc(adapter, _prompt_request(session_id, "And why?", "c2")))
    assert await asyncio.to_thread(runner.entered.wait, 5)
    await adapter.handle_client_notification(
        {"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}}
    )
    release.set()
    cancelled = await asyncio.wait_for(prompt, timeout=10)

    assert cancelled["result"] == {"stopReason": "cancelled"}
    conversation = adapter._sessions.get(session_id).conversation  # noqa: SLF001
    assert conversation.records[2].outcome is ConversationOutcome.CANCELLED
    assert [u["sessionUpdate"] for u in _session_updates(outbound)] == ["usage_update"]
    assert _meters(outbound)[-1]["used"] == conversation.used_bytes // 4


async def test_a_failed_meter_never_fails_the_turn(tmp_path: Path) -> None:
    runner = _FloorRunner()
    adapter, outbound = _adapter(tmp_path, runner, _MeterFailsChannel())
    session_id = await _new_session(adapter, tmp_path)

    response = await _prompt(adapter, session_id, "Task", "p1")

    assert response["result"] == {"stopReason": "end_turn"}
    assert _texts(outbound) == [COMPLETED_TEXT + SEPARATOR]
    assert len(adapter._sessions.get(session_id).conversation.records) == 1  # noqa: SLF001
