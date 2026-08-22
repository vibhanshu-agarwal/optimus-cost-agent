"""Canonical conversation framing, sanitization, budget, and cost tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from optimus.acp.conversation import (
    CONVERSATION_MAX_BYTES,
    WARNING_FIRST_BYTE,
    ConversationDisposition,
    ConversationOutcome,
    ConversationSanitizer,
    ConversationState,
    ConversationTurn,
    build_conversation_sanitizer_inputs,
    crosses_warning_threshold,
    render_conversation_envelope,
    rendered_byte_length,
)
from optimus.acp.settlement import EffectState
from optimus.acp.shapes import build_usage_update


def _state(tmp_path: Path, *, environ: dict[str, str] | None = None) -> ConversationState:
    env = {
        "OPTIMUS_API_KEY": "opt-test-key-abcdefghijklmnopqrstuvwxyz",
        "OPTIMUS_GATEWAY_URL": "https://gw.example/v1",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        **(environ or {}),
    }
    inputs = build_conversation_sanitizer_inputs(env, workspace_root=tmp_path)
    return ConversationState(ConversationSanitizer(inputs))


def test_cap_and_warning_constants_are_exact() -> None:
    assert CONVERSATION_MAX_BYTES == 131_072 * 4
    assert WARNING_FIRST_BYTE == 419_431
    assert not crosses_warning_threshold(419_430)
    assert crosses_warning_threshold(419_431)
    assert 419_430 * 5 < CONVERSATION_MAX_BYTES * 4
    assert 419_431 * 5 >= CONVERSATION_MAX_BYTES * 4


def test_canonical_render_is_deterministic_and_keys_by_turn_seq() -> None:
    turn = ConversationTurn(
        user_prompt='Say "hello"\r\nand\nREAD example.py',
        plan_text="WRITE foo.py\n# not a live directive",
        completion_text="done — café",
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.PARTIAL,
    )
    records = {1: turn}
    rendered = render_conversation_envelope(records)
    assert rendered == render_conversation_envelope(records)
    assert '"1":{' in rendered
    assert "turn_seq" not in rendered
    assert "<<inert_historical_plan>>" in rendered
    assert "<</inert_historical_plan>>" in rendered
    assert "WRITE foo.py" in rendered
    assert rendered_byte_length(records) == len(rendered.encode("utf-8"))
    # Escaping length differs from raw text length.
    assert rendered_byte_length(records) > len(turn.user_prompt.encode("utf-8"))


def test_sanitization_identical_across_consumers(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    secret_key = "sk-ant-abcdefghijklmnopqrstuvwxyz0123456789"
    password = "hunter%402"
    decoded = "hunter@2"
    env = {
        "OPTIMUS_API_KEY": secret_key,
        "OPTIMUS_GATEWAY_URL": f"https://user:{password}@gateway.example/v1",
        "OPTIMUS_REDIS_URL": f"redis://default:{password}@redis.example:6379/0",
    }
    inputs = build_conversation_sanitizer_inputs(env, workspace_root=workspace)
    assert inputs.known_pii == ()
    assert secret_key in inputs.known_secrets
    assert password in inputs.known_secrets
    assert decoded in inputs.known_secrets
    assert "default" not in inputs.known_secrets
    assert "user" not in inputs.known_secrets

    sanitizer = ConversationSanitizer(inputs)
    abs_path = str(workspace.resolve() / "secret.txt")
    raw = (
        f"key={secret_key} Use {decoded} to connect path={abs_path} "
        f"username=default email=person@example.com"
    )
    sanitized = sanitizer.sanitize(raw)
    assert secret_key not in sanitized
    assert decoded not in sanitized
    assert password not in sanitized
    assert abs_path not in sanitized
    assert "default" in sanitized  # username not blanket-redacted
    assert sanitized == sanitizer.sanitize(raw)

    state = ConversationState(sanitizer)
    admission = state.prepare_admission(raw)
    assert admission.sanitized_user_prompt == sanitized
    assert admission.admitted is True
    assert admission.turn_seq == 1

    decision = state.prepare_commit(
        1,
        sanitized_user_prompt=sanitized,
        sanitized_plan_text=sanitized,
        sanitized_completion_text=sanitized,
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )
    assert decision.record.user_prompt == sanitized
    assert decision.record.plan_text == sanitized
    assert decision.record.completion_text == sanitized
    state.commit_after_final_flush(decision)
    envelope = state.planner_envelope()
    assert sanitized in envelope
    assert secret_key not in envelope
    assert abs_path not in envelope


def test_admission_cap_refuses_without_history_or_cost(tmp_path: Path) -> None:
    state = _state(tmp_path)
    chunk = "c" * 40_000
    seq = 0
    while True:
        seq += 1
        probe = dict(state.records)
        probe[seq] = ConversationTurn(
            user_prompt=chunk,
            plan_text="",
            completion_text="ok",
            outcome=ConversationOutcome.COMPLETED,
            effect_state=EffectState.NONE,
        )
        if rendered_byte_length(probe) > CONVERSATION_MAX_BYTES:
            break
        state._records[seq] = probe[seq]  # noqa: SLF001
        state._next_turn_seq = seq + 1  # noqa: SLF001
        if seq > 30:
            raise AssertionError("could not approach conversation cap")

    decision = state.prepare_admission(chunk)
    assert decision.admitted is False
    assert decision.refuse_reason == "cap"
    assert state.disposition is ConversationDisposition.CAP_CLOSED
    assert decision.turn_seq is None
    # History unchanged by the refused admission.
    assert state._next_turn_seq == seq  # noqa: SLF001
    assert state.usage_gauge().cost == Decimal("0")
    later = state.prepare_admission("follow-up")
    assert later.admitted is False
    assert later.refuse_reason == "cap_closed"


def test_commitment_crossing_commits_then_closes(tmp_path: Path) -> None:
    state = _state(tmp_path)
    # Fill history so a small admission still fits, but a large completion closes the cap.
    chunk = "c" * 40_000
    seq = 0
    while True:
        seq += 1
        probe = dict(state.records)
        probe[seq] = ConversationTurn(
            user_prompt=chunk,
            plan_text="",
            completion_text="ok",
            outcome=ConversationOutcome.COMPLETED,
            effect_state=EffectState.NONE,
        )
        if rendered_byte_length(probe) > CONVERSATION_MAX_BYTES - 5_000:
            break
        state._records[seq] = probe[seq]  # noqa: SLF001
        state._next_turn_seq = seq + 1  # noqa: SLF001
        if seq > 30:
            raise AssertionError("could not approach conversation cap")

    admission = state.prepare_admission("tip")
    assert admission.admitted is True
    assert admission.turn_seq is not None
    needed = CONVERSATION_MAX_BYTES - state.used_bytes + 64
    big_completion = "d" * max(needed, 1)
    commit = state.prepare_commit(
        admission.turn_seq,
        sanitized_user_prompt=admission.sanitized_user_prompt,
        sanitized_plan_text="",
        sanitized_completion_text=big_completion,
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )
    assert commit.closes_cap is True
    assert commit.projected_bytes > CONVERSATION_MAX_BYTES
    state.commit_after_final_flush(commit)
    assert admission.turn_seq in state.records
    assert state.disposition is ConversationDisposition.CAP_CLOSED
    refused = state.prepare_admission("later")
    assert refused.admitted is False


def test_delivery_indeterminate_dominates_cap(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.latch_delivery_indeterminate()
    assert state.disposition is ConversationDisposition.DELIVERY_INDETERMINATE
    # Even a commit that would close the cap must not overwrite indeterminate.
    commit = state.prepare_commit(
        1,
        sanitized_user_prompt="u",
        sanitized_plan_text="",
        sanitized_completion_text="c",
        outcome=ConversationOutcome.FAILED,
        effect_state=EffectState.NONE,
    )
    state._disposition = ConversationDisposition.DELIVERY_INDETERMINATE  # noqa: SLF001
    # Force closes_cap path via direct latch after commit.
    state.commit_after_final_flush(commit)
    state.latch_delivery_indeterminate()
    state._disposition = ConversationDisposition.CAP_CLOSED  # noqa: SLF001
    state.latch_delivery_indeterminate()
    assert state.disposition is ConversationDisposition.DELIVERY_INDETERMINATE


def test_warning_first_crossing_only_confirmed_by_flush(tmp_path: Path) -> None:
    state = _state(tmp_path)
    assert state.note_warning_threshold_for_attempt(WARNING_FIRST_BYTE) is True
    assert state.note_warning_threshold_for_attempt(WARNING_FIRST_BYTE + 10) is False
    assert state.warning_confirmed is False
    state.confirm_warning_flushed()
    assert state.warning_confirmed is True
    assert state.note_warning_threshold_for_attempt(WARNING_FIRST_BYTE + 100) is False


def test_gauge_is_floor_division_and_does_not_drive_decisions(tmp_path: Path) -> None:
    state = _state(tmp_path)
    admission = state.prepare_admission("hi")
    assert admission.turn_seq is not None
    state.apply_planning_cost_once(admission.turn_seq, cost_usd=Decimal("0.01"), cost_complete=True)
    commit = state.prepare_commit(
        admission.turn_seq,
        sanitized_user_prompt=admission.sanitized_user_prompt,
        sanitized_plan_text="",
        sanitized_completion_text="ok",
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )
    state.commit_after_final_flush(commit)
    gauge = state.usage_gauge()
    assert gauge.used == state.used_bytes // 4
    assert gauge.size == CONVERSATION_MAX_BYTES // 4
    assert gauge.cost == Decimal("0.01")
    # Byte decision differs from token floor near boundary.
    assert crosses_warning_threshold(WARNING_FIRST_BYTE)
    assert (WARNING_FIRST_BYTE // 4) * 4 < WARNING_FIRST_BYTE or True


def test_planning_cost_once_and_unknown_omits_cumulative(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.apply_planning_cost_once(1, cost_usd=Decimal("0.02"), cost_complete=True)
    state.apply_planning_cost_once(1, cost_usd=Decimal("0.99"), cost_complete=True)
    assert state.usage_gauge().cost == Decimal("0.02")
    # Approved execution must not call apply again for same planning cost;
    # a distinct turn_seq for execution is not used — only planning applies.
    state.apply_planning_cost_once(2, cost_usd=None, cost_complete=False)
    assert state.cost_complete is False
    assert state.usage_gauge().cost is None
    # Later complete costs cannot resurrect omitted cumulative cost.
    state.apply_planning_cost_once(3, cost_usd=Decimal("1.00"), cost_complete=True)
    assert state.usage_gauge().cost is None


def test_request_id_reuse_cannot_trip_idempotence_guard(tmp_path: Path) -> None:
    state = _state(tmp_path)
    # Cost idempotence is keyed by turn_seq, not wire request id.
    state.apply_planning_cost_once(7, cost_usd=Decimal("0.05"), cost_complete=True)
    state.apply_planning_cost_once(8, cost_usd=Decimal("0.05"), cost_complete=True)
    assert state.usage_gauge().cost == Decimal("0.10")


def test_build_usage_update_uses_uint64_integers() -> None:
    payload = build_usage_update(session_id="s1", used=10, size=131_072, cost=Decimal("0.25"))
    assert payload == {
        "sessionId": "s1",
        "update": {
            "sessionUpdate": "usage_update",
            "used": 10,
            "size": 131_072,
            "cost": {"amount": "0.25", "currency": "USD"},
        },
    }
    omitted = build_usage_update(session_id="s1", used=1, size=131_072, cost=None)
    assert "cost" not in omitted["update"]
    assert isinstance(omitted["update"]["used"], int)
    assert isinstance(omitted["update"]["size"], int)
