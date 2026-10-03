"""Plan 12.2 Task 3, F3: the model sees history in numeric turn order with the declared field order.

The storage serializer sorts its keys, so turn 10 sorted before turn 2 and every record's fields came
out alphabetically. The model-facing renderer keeps the same keys and values in their real order. The
storage serializer is unchanged and alone measures the 512 KiB floor, its 80% warning and its cap.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from optimus.acp import conversation as conversation_module
from optimus.acp.conversation import (
    _RECORD_FIELD_ORDER,
    CONVERSATION_MAX_BYTES,
    WARNING_FIRST_BYTE,
    ConversationOutcome,
    ConversationSanitizer,
    ConversationSanitizerInputs,
    ConversationState,
    ConversationTurn,
    render_conversation_envelope,
    rendered_byte_length,
)
from optimus.acp.settlement import EffectState
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.runtime.modes import ExecutionMode

# Text the JSON encoder must escape or encode as several UTF-8 bytes.
_AWKWARD = 'é ü 漢字 😀 "quoted" back\\slash tab\tnew\nline </script>  '


def _state() -> ConversationState:
    return ConversationState(ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=())))


def _turn(seq: int) -> ConversationTurn:
    return ConversationTurn(
        user_prompt=f"prompt {seq} {_AWKWARD}",
        plan_text=f"WRITE f{seq}.py {_AWKWARD}" if seq % 2 else "",
        completion_text=f"done {seq} {_AWKWARD}",
        outcome=ConversationOutcome.COMPLETED if seq % 3 else ConversationOutcome.REJECTED,
        effect_state=EffectState.COMPLETE if seq % 2 else EffectState.NONE,
    )


def _seed(state: ConversationState, records: dict[int, ConversationTurn]) -> None:
    for seq, record in records.items():
        decision = state.prepare_commit(
            seq,
            sanitized_user_prompt=record.user_prompt,
            sanitized_plan_text=record.plan_text,
            sanitized_completion_text=record.completion_text,
            outcome=record.outcome,
            effect_state=record.effect_state,
        )
        state.commit_after_final_flush(decision)


def _pairs(rendered: str) -> list[tuple[str, list[tuple[str, str]]]]:
    return json.loads(rendered, object_pairs_hook=list)


def test_model_turn_and_field_order() -> None:
    # Inserted out of order on purpose: the renderer must sort numerically, not trust insertion order.
    records = {seq: _turn(seq) for seq in (11, 2, 10, 1, 9)}

    rendered = conversation_module.render_model_conversation(records)

    parsed = _pairs(rendered)
    assert [turn_key for turn_key, _ in parsed] == ["1", "2", "9", "10", "11"]
    for turn_key, fields in parsed:
        assert [name for name, _ in fields] == list(_RECORD_FIELD_ORDER)
        assert dict(fields) == records[int(turn_key)].as_record_dict()

    # The storage serializer is byte-for-byte the old algorithm: sorted keys, so lexical turns and
    # alphabetical fields.
    legacy = render_conversation_envelope(records)
    assert legacy == json.dumps(
        {str(seq): record.as_record_dict() for seq, record in records.items()},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    legacy_pairs = _pairs(legacy)
    assert [turn_key for turn_key, _ in legacy_pairs] == ["1", "10", "11", "2", "9"]
    assert [name for name, _ in legacy_pairs[0][1]] == sorted(_RECORD_FIELD_ORDER)

    # Same keys and values, so the same bytes in a different order.
    assert len(rendered.encode("utf-8")) == len(legacy.encode("utf-8"))
    assert sorted(rendered) == sorted(legacy)

    # The planner reads the model order; the canonical records are untouched.
    state = _state()
    _seed(state, records)
    assert state.planner_envelope() == rendered
    assert dict(state.records) == records
    assert state.used_bytes == len(legacy.encode("utf-8"))


def _admission_prompt(state: ConversationState, target_bytes: int) -> str:
    """A prompt with awkward text whose admission projects exactly ``target_bytes``."""
    prefix = state.sanitize_text(_AWKWARD)
    seq = max(state.records, default=0) + 1
    provisional = dict(state.records)
    provisional[seq] = ConversationTurn(
        user_prompt=prefix,
        plan_text="",
        completion_text="",
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )
    padding = target_bytes - rendered_byte_length(provisional)
    assert padding > 0
    # Words, not one long token: the sanitizer's scan of a single unbroken token is slow.
    return prefix + ("word " * (padding // 5 + 1))[:padding]


def _both_lengths(records: dict[int, ConversationTurn]) -> tuple[int, int]:
    legacy = len(render_conversation_envelope(records).encode("utf-8"))
    model = len(conversation_module.render_model_conversation(records).encode("utf-8"))
    return legacy, model


def test_order_fix_preserves_floor_bytes_and_admission() -> None:
    history = {seq: _turn(seq) for seq in (1, 2, 9, 10, 11)}
    assert WARNING_FIRST_BYTE == 419_431
    assert CONVERSATION_MAX_BYTES == 524_288

    cases = [
        (WARNING_FIRST_BYTE - 1, True, False),
        (WARNING_FIRST_BYTE, True, True),
        (CONVERSATION_MAX_BYTES, True, True),
        (CONVERSATION_MAX_BYTES + 1, False, False),
    ]
    for target, admitted, warns in cases:
        state = _state()
        _seed(state, history)
        prompt = _admission_prompt(state, target)

        decision = state.prepare_admission(prompt)

        assert decision.projected_bytes == target
        assert decision.admitted is admitted, target
        assert decision.crosses_warning is warns, target
        provisional = dict(state.records)
        provisional[12] = ConversationTurn(
            user_prompt=decision.sanitized_user_prompt,
            plan_text="",
            completion_text="",
            outcome=ConversationOutcome.COMPLETED,
            effect_state=EffectState.NONE,
        )
        assert _both_lengths(provisional) == (target, target)
        if not admitted:
            assert decision.refuse_reason == "cap"

    # The commit-time projection and the usage meter also keep counting storage bytes.
    state = _state()
    _seed(state, history)
    commit = state.prepare_commit(
        12,
        sanitized_user_prompt=_AWKWARD,
        sanitized_plan_text="",
        sanitized_completion_text=_AWKWARD,
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )
    state.commit_after_final_flush(commit)
    legacy_bytes, model_bytes = _both_lengths(dict(state.records))
    assert commit.projected_bytes == legacy_bytes == model_bytes == state.used_bytes
    assert state.usage_gauge().used == legacy_bytes // 4


class _EnvelopeRunner:
    """Records each planning request and completes it without a plan."""

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def run(self, request: Any, **kwargs: Any) -> AgentRunResult:
        del kwargs
        self.requests.append(request)
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="CHAT_ONLY" if request.execution_mode is ExecutionMode.CHAT else "COMPLETED",
            output_text="answer",
            tool_calls=(),
            total_cost_usd=Decimal("0"),
            mutation_count=0,
            provider_keys_resolvable=(),
        )


async def _rpc(adapter: AcpDuplexAdapter, request: dict[str, Any]) -> dict[str, Any]:
    return (await adapter.handle_client_request(request)).response


async def test_both_modes_send_the_model_order_to_the_planner(tmp_path: Path) -> None:
    runner = _EnvelopeRunner()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=RecordingOutboundChannel(),
    )
    created = await _rpc(
        adapter,
        {"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}},
    )
    session_id = created["result"]["sessionId"]
    session = adapter._sessions.get(session_id)  # noqa: SLF001
    history = {seq: _turn(seq) for seq in range(1, 12)}
    session.conversation = _state()
    _seed(session.conversation, history)
    expected = conversation_module.render_model_conversation(history)

    for mode_id, request_id in (("chat", "c"), ("agent", "a")):
        await _rpc(
            adapter,
            {
                "jsonrpc": "2.0",
                "id": f"to-{mode_id}",
                "method": "session/set_mode",
                "params": {"sessionId": session_id, "modeId": mode_id},
            },
        )
        prompt = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "What changed?"}]},
        }
        assert "result" in await asyncio.wait_for(_rpc(adapter, prompt), timeout=5)

    chat_request, agent_request = runner.requests
    assert chat_request.conversation_envelope == expected
    assert [turn_key for turn_key, _ in _pairs(chat_request.conversation_envelope)] == [str(n) for n in range(1, 12)]
    # The Agent prompt was admitted after the Chat turn committed as turn 12.
    with_chat_turn = {seq: session.conversation.records[seq] for seq in range(1, 13)}
    assert agent_request.task == conversation_module.render_model_conversation(with_chat_turn) + "\nWhat changed?"
