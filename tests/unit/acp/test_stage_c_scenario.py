"""Plan 12.2 Task 13 (Stage C): the attached test profile's real-host engine and its fixed scenario (Codex
scope agreement, 2026-10-11, sections 1-3).

Only an approved Stage C launch of the attached test composition attaches the existing engine, with the
accepted limits, the profile's estimator and its receipt's route. The scenario seeds the launch's first new
session with its pinned synthetic history (labelled synthetic, no authority), makes the engine unavailable
on its scheduled live turns (the real unavailable path, never a canned summary) and, on its cancellation
turn, pauses after the first maintenance call until the client's real cancel, which suppresses the second
call; without one the case is UNRUN and makes no further call. The real adapter, engine and attached
composition run here; only the Gateway and the planner are fakes. No service or provider.
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from context_engine.summary import SECTIONS
from optimus.acp import stage_c as host
from optimus.acp.conversation import CONVERSATION_MAX_BYTES, ConversationDisposition, ConversationOutcome, rendered_byte_length
from optimus.acp.settlement import EffectState
from optimus.acp.test_composition import compose_test_composition
from optimus.gateway.models import GatewayResponse
from optimus.runtime.modes import ExecutionMode
from optimus_model_policy import stage_c
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import BindingError, approval_literal
from tests.unit.acp.test_context_engine_admission import Runner, make_adapter, new_session, prompt, prompt_request, rpc, session_of, texts
from tests.unit.usage.test_summary_ledger import _usage

HAIKU = "anthropic/claude-haiku-5.5"
SUMMARY = "\n".join(f"## {name}\nNone." for name in SECTIONS)
T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
SECRET = "stage-c-test-shared-secret"  # pragma: allowlist secret - synthetic test fixture


def _composition(name: str):
    return compose_test_composition(name, approved_literal=approval_literal(profiles.compose_test_profile_snapshot(name)))


class Gateway:
    """A fake Gateway client: answers every summary request with a valid summary and a known charge."""

    def __init__(self) -> None:
        self.summaries = 0
        self.bindings: list[Any] = []

    def create_response(self, *, model, input_text, metadata=None, route_binding=None, **kwargs):
        assert metadata["purpose"] == "context_summary" and model == HAIKU
        self.summaries += 1
        self.bindings.append(route_binding)
        return GatewayResponse(output_text=SUMMARY, gateway_usage=_usage(f"gw-{self.summaries}", cost_usd=Decimal("0.0004")), raw={}, finish_reason="stop")


@pytest.fixture
def launch(tmp_path: Path) -> host.StageCLaunch:
    """An initialized ledger whose window opened at T0 (as the first Gateway open records it)."""
    ledger = stage_c.stage_c_ledger_path(tmp_path / ".optimus")
    envelope = stage_c.compose_stage_c_envelope(ledger=ledger)
    stage_c.initialize_stage_c_ledger(ledger, envelope, clock=lambda: T0)
    stage_c.StageCGuard.open(ledger, envelope, clock=lambda: T0).close()
    return host.StageCLaunch(envelope=envelope, ledger=ledger)


def _attached(launch: host.StageCLaunch, gateway: Gateway, **kwargs: Any):
    return host.compose_stage_c_attachment(composition=_composition("attached"), gateway_client=gateway, shared_secret=SECRET, launch=launch, clock=lambda: T0, **kwargs)


def _adapter(tmp_path: Path, attachment, scenario, runner: Runner | None = None):
    adapter, outbound, runner = make_adapter(tmp_path, attachment, runner)
    adapter._session_seeder = scenario.seed  # noqa: SLF001 - as the server passes it
    return adapter, outbound, runner


# --- Composition --------------------------------------------------------------------------------------------


def test_only_an_attached_stage_c_launch_attaches_the_engine(launch) -> None:
    gateway = Gateway()
    attachment, seeder = host.stage_c_attachment(composition=_composition("attached"), launch=launch, gateway_client=gateway, shared_secret=SECRET)
    assert attachment is not None and seeder is not None
    for composition, staged in ((_composition("qualification"), launch), (_composition("attached"), None), (None, launch), (None, None)):
        assert host.stage_c_attachment(composition=composition, launch=staged, gateway_client=gateway, shared_secret=SECRET) == (None, None)
    with pytest.raises(BindingError) as caught:
        host.compose_stage_c_attachment(composition=_composition("qualification"), gateway_client=gateway, shared_secret=SECRET, launch=launch)
    assert caught.value.code == "STAGE_C_ATTACHMENT_PROFILE"


def test_the_attachment_uses_the_accepted_limits_on_the_profiles_route(launch) -> None:
    attachment, _ = _attached(launch, Gateway())
    p, lim = attachment.parameters, attachment.limits

    assert (p.anchor_input_tokens, p.compaction_tail_input_tokens, p.hybrid_tail_input_tokens, p.summary_output_tokens, p.max_maintenance_calls) == (
        16_384, 32_768, 65_536, 8_192, 18
    )  # fmt: skip
    assert (lim.source_max_bytes, lim.transient_max_bytes, lim.maintenance_input_tokens, lim.maintenance_output_tokens, lim.summary_max_bytes) == (
        1_048_576, 524_288, 131_072, 8_192, 8_192
    )  # fmt: skip
    assert (attachment.usable_input_tokens, lim.history_input_tokens) == (262_144 - 32_768, 131_072)
    assert (attachment.source_max_bytes, attachment.record_reservation_bytes, attachment.max_repacks, attachment.initial_strategy) == (1_048_576, 131_072, 1, "compaction")
    assert lim.estimate_history("é") == 2 and attachment.estimate_request("é") == 2 + 16 + 256  # one token per byte plus the framing
    route = attachment.summarizer_route
    assert (route.model_id, route.role, route.route, route.reasoning, route.quantizations) == (HAIKU, "summarizer", ("anthropic",), "low", ("unknown",))
    assert (attachment.registry_hash, attachment.model_id) == (profiles.TEST_PROFILES["attached"].effective_hash, HAIKU)


# --- The seed -------------------------------------------------------------------------------------------------


def test_the_seed_is_the_pinned_synthetic_history_over_the_floor() -> None:
    records, approvals = host.seed_history(host._PLAIN_SANITIZER)  # noqa: SLF001
    seed = stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["seed"]

    assert host.seed_identity(records, approvals) == (seed["records_sha256"], seed["records_bytes"])
    assert CONVERSATION_MAX_BYTES < rendered_byte_length(records) < host.SOURCE_MAX_BYTES - host.RECORD_RESERVATION_BYTES
    assert len(records) == 64 and all(r.user_prompt.startswith("Synthetic Stage C seed turn") and r.completion_text.startswith("Synthetic seed reply") for r in records.values())
    assert {(r.outcome, r.effect_state, r.plan_text) for r in records.values()} == {(ConversationOutcome.COMPLETED, EffectState.NONE, "")}
    facts = [fact for seq in sorted(approvals) for fact in approvals[seq]]
    assert [(f.turn_seq, f.artifact_hash, f.scope) for f in facts] == [
        (16, "synthetic-stage-c-seed-artifact-16", ("synthetic-seed/notes-16.md",)),
        (48, "synthetic-stage-c-seed-artifact-48", ("synthetic-seed/notes-48.md",)),
    ]


def test_a_seed_that_is_not_the_pinned_one_refuses(launch, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["seed"], "completion_bytes", 8999)
    with pytest.raises(BindingError) as caught:
        _attached(launch, Gateway())
    assert caught.value.code == "STAGE_C_SEED_MISMATCH"


async def test_only_the_launchs_first_new_session_is_seeded(tmp_path: Path, launch) -> None:
    attachment, scenario = _attached(launch, Gateway())
    adapter, _outbound, _runner = _adapter(tmp_path, attachment, scenario)

    first = await new_session(adapter, tmp_path, mode="chat")
    second = await new_session(adapter, tmp_path, mode="chat")

    seeded, fresh = session_of(adapter, first), session_of(adapter, second)
    assert scenario.designated_session == first
    assert len(seeded.conversation.records) == 64 and sorted(seeded.context_approvals) == [16, 48]
    assert seeded.conversation.used_bytes == stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["seed"]["records_bytes"]
    assert fresh.conversation.records == {} and fresh.context_approvals == {}


async def test_a_session_whose_sanitizer_would_change_the_seed_is_not_seeded(tmp_path: Path, launch, monkeypatch: pytest.MonkeyPatch) -> None:
    attachment, scenario = _attached(launch, Gateway())
    adapter, _outbound, _runner = _adapter(tmp_path, attachment, scenario)
    monkeypatch.setitem(stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["seed"], "records_bytes", 1)  # as if sanitized differently

    session_id = await new_session(adapter, tmp_path, mode="chat")

    assert session_of(adapter, session_id).conversation.records == {} and session_of(adapter, session_id).context_approvals == {}
    assert scenario.events == ["seed refused: the session's sanitized seed is not the pinned seed"]


async def test_turns_of_another_session_never_drive_the_schedule(tmp_path: Path, launch) -> None:
    """Another session's live turns neither hit the schedule nor shift the designated session's turn count."""
    gateway = Gateway()
    attachment, scenario = _attached(launch, gateway)
    adapter, outbound, runner = _adapter(tmp_path, attachment, scenario)
    designated = await new_session(adapter, tmp_path, mode="chat")  # the seeded session
    other = await new_session(adapter, tmp_path, mode="chat")
    for n in (1, 2, 3):
        await prompt(adapter, outbound, designated, f"Live turn {n}: where does the work stand?", f"p{n}")
    summaries = gateway.summaries

    for n in range(1, 6):
        await prompt(adapter, outbound, other, f"Other session turn {n}.", f"o{n}")

    assert len(runner.requests) == 8 and gateway.summaries == summaries  # small history: answers only
    assert scenario.current_turn(other) is None and host.UNAVAILABLE_NOTICE not in texts(outbound)
    assert [e for e in scenario.events if e.startswith("turn")] == []

    outbound.notifications.clear()
    await prompt(adapter, outbound, designated, "Live turn 4: and now?", "p4")
    assert texts(outbound)[0] == host.UNAVAILABLE_NOTICE  # still the designated session's fourth live turn
    assert [e for e in scenario.events if e.startswith("turn")] == ["turn 4: simulated engine unavailability"]


async def test_the_synthetic_seed_authorizes_nothing(tmp_path: Path, launch) -> None:
    """An Agent turn in the seeded session still needs the operator's exact approval; denying it applies nothing."""
    attachment, scenario = _attached(launch, Gateway())
    adapter, outbound, runner = _adapter(tmp_path, attachment, scenario)
    session_id = await new_session(adapter, tmp_path, mode="agent")

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Write the notes file.", "a1")))
    permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=30)
    outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "reject"}})
    await asyncio.wait_for(task, timeout=30)

    assert all(not request.approval.approved for request in runner.requests)  # nothing ran approved
    assert [r.execution_mode for r in runner.requests] == [ExecutionMode.AGENT]


# --- Scheduled unavailability and recovery ------------------------------------------------------------------------


async def test_the_scheduled_turns_are_unavailable_then_the_engine_recovers(tmp_path: Path, launch) -> None:
    gateway = Gateway()
    attachment, scenario = _attached(launch, gateway)
    adapter, outbound, runner = _adapter(tmp_path, attachment, scenario)
    session_id = await new_session(adapter, tmp_path, mode="chat")

    for n in (1, 2, 3):
        await prompt(adapter, outbound, session_id, f"Live turn {n}: where does the work stand?", f"p{n}")
    assert len(runner.requests) == 3 and gateway.summaries >= 2  # the cold compaction of the seed made real calls
    summaries_before = gateway.summaries

    for n in (4, 5):
        outbound.notifications.clear()
        response = await prompt(adapter, outbound, session_id, f"Live turn {n}: and now?", f"p{n}")
        assert response["result"]["stopReason"] == "end_turn"
        assert texts(outbound)[0] == host.UNAVAILABLE_NOTICE
        assert len(runner.requests) == 3 and gateway.summaries == summaries_before  # zero calls of any kind
    assert session_of(adapter, session_id).conversation.disposition is ConversationDisposition.OPEN

    await prompt(adapter, outbound, session_id, "Live turn 6: recovered?", "p6")
    assert len(runner.requests) == 4
    assert [e for e in scenario.events if "simulated" in e] == ["turn 4: simulated engine unavailability", "turn 5: simulated engine unavailability"]
    assert all(binding is not None and binding.registry_hash == profiles.TEST_PROFILES["attached"].effective_hash for binding in gateway.bindings)


# --- The cancellation pause -------------------------------------------------------------------------------------


@pytest.fixture
def cancel_first_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Move the scheduled cancellation pause to live turn 1 (its cold compaction makes several calls)."""
    monkeypatch.setitem(stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["schedule"], "cancel_pause_turn", 1)


async def test_a_cancel_during_the_pause_suppresses_the_second_call_and_keeps_the_first(tmp_path: Path, launch, cancel_first_turn) -> None:
    paused, resume = threading.Event(), threading.Event()

    def sleep(_seconds: float) -> None:
        paused.set()
        assert resume.wait(10)

    gateway = Gateway()
    attachment, scenario = _attached(launch, gateway, sleep=sleep)
    adapter, outbound, runner = _adapter(tmp_path, attachment, scenario)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    session = session_of(adapter, session_id)

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Live turn 1: cancel me during maintenance.", "c1")))
    assert await asyncio.to_thread(paused.wait, 30)
    assert gateway.summaries == 1  # the first call completed; the second has not been dispatched
    await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
    resume.set()
    response = await asyncio.wait_for(task, timeout=30)

    assert response["result"]["stopReason"] == "cancelled"
    assert gateway.summaries == 1 and runner.requests == []  # no second maintenance call, no answer
    assert session.context_checkpoint is None  # nothing published
    assert any(text.startswith("Stage C test scenario: maintenance paused") and "30 seconds" in text for text in texts(outbound))
    assert scenario.events[-2:] == ["turn 1: paused before maintenance call 2 for at most 30 s", "turn 1: cancelled during the pause"]
    settled = session.cost_settlement.settle_turn(f"{session_id}:65")
    assert settled.known_subtotal_usd == Decimal("0.0004")  # the first call's charge is kept


async def test_without_a_cancel_the_case_is_unrun_and_makes_no_further_call(tmp_path: Path, launch, cancel_first_turn) -> None:
    gateway = Gateway()
    attachment, scenario = _attached(launch, gateway, sleep=lambda _seconds: None)
    adapter, outbound, runner = _adapter(tmp_path, attachment, scenario)
    session_id = await new_session(adapter, tmp_path, mode="chat")

    response = await prompt(adapter, outbound, session_id, "Live turn 1: nobody cancels.", "u1")

    assert response["result"]["stopReason"] == "end_turn"
    assert gateway.summaries == 1 and runner.requests == []
    assert host.UNRUN_NOTICE in texts(outbound)
    assert scenario.events[-1] == "turn 1: UNRUN, cancellation not exercised"


def test_the_pause_is_shortened_by_the_rest_of_the_shared_window(launch) -> None:
    """Five seconds before the deadline the pause waits at most five seconds."""
    ticks: list[float] = []
    scenario = host.StageCScenario(ledger=launch.ledger, clock=lambda: T0 + timedelta(minutes=59, seconds=55), sleep=ticks.append, poll_seconds=1.0)
    notices: list[str] = []
    scenario._turns, scenario._designated = 1, "s"  # noqa: SLF001
    scenario._notices[1] = lambda text: notices.append(text) or True  # noqa: SLF001
    call = scenario._pausing(1, lambda request: "called", lambda: False)  # noqa: SLF001

    assert call("first") == "called"
    with pytest.raises(host.ScenarioCancellationNotExercised):
        call("second")
    assert len(ticks) == 5 and "at most 5 seconds" in notices[0] and notices[1] == host.UNRUN_NOTICE


def test_the_scenario_is_part_of_the_envelope(launch) -> None:
    scenario = json.loads(json.dumps(stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]))
    assert scenario["schedule"] == {"engine_unavailable_turns": [4, 5], "cancel_pause_turn": 7, "cancel_pause_before_call": 2, "cancel_wait_seconds": 30}
    assert launch.envelope.scenarios == stage_c.scenario_catalogue_digest()
