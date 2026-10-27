"""#397, loop control Phase 3 (ADR-009 rung 2): the escalation target, its launch-time route and the host's switch.

One edge, read from configuration: a struggling Auto turn moves to the ``escalation`` role's first routable model, unless
the turn already runs it or its usable input is smaller. The role's later models are fallbacks for a stopped first one,
never further steps. Built from the real approved Auto composition: escalation is Gemini, so only easy-tier turns (Luna,
Haiku) have a step. No network or paid call is made.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace

import pytest

from optimus.acp import auto_composition
from optimus.acp import spec as spec_module
from optimus.acp.lifecycle import TurnControl
from optimus.acp.spec import AcpPromptTurn, RecordingOutboundChannel
from optimus.agent.planning_loop import EscalationGrant, EscalationRefusal, PlanningEscalation
from tests.unit.acp.test_auto_turn_routing import GEMINI, HAIKU, LUNA, _adapter, _outcome, _router
from tests.unit.agent.test_route_binding import Notices

OTHER = "z-ai/glm-5.3"


@pytest.mark.parametrize("current", [LUNA, HAIKU])
def test_an_easy_tier_model_steps_to_the_escalation_roles_model(current: str) -> None:
    assert _router().escalation_target(current) == GEMINI


def test_a_turn_already_on_the_escalation_model_has_no_step() -> None:
    assert _router().escalation_target(GEMINI) is None


def test_a_stopped_first_model_falls_back_to_the_next_routable_one_but_never_to_the_current_model(monkeypatch) -> None:
    router = _router()
    monkeypatch.setattr(auto_composition, "select_eligible_models", lambda snapshot, role: (GEMINI, OTHER) if role.value == "escalation" else ())
    monkeypatch.setattr(auto_composition, "attachment_limits", lambda snapshot, model_id: _Limits(229376))
    router.stops.add(GEMINI)
    assert router.escalation_target(LUNA) == OTHER
    assert router.escalation_target(OTHER) is None
    router.stops.add(OTHER)
    assert router.escalation_target(LUNA) is None


def test_an_empty_escalation_role_has_no_step(monkeypatch) -> None:
    router = _router()
    monkeypatch.setattr(auto_composition, "select_eligible_models", lambda snapshot, role: ())
    assert router.escalation_target(LUNA) is None


def test_a_target_with_less_usable_input_than_the_current_model_has_no_step(monkeypatch) -> None:
    router = _router()
    sizes = {LUNA: 229376, GEMINI: 100000}
    monkeypatch.setattr(auto_composition, "attachment_limits", lambda snapshot, model_id: _Limits(sizes[model_id]))
    assert router.escalation_target(LUNA) is None


def test_the_escalation_role_has_its_own_route_policy_and_attachment_built_at_launch() -> None:
    router = _router()
    policy = router.route_policies[(GEMINI, "escalation")]
    assert (policy.identity.model_id, policy.identity.role) == (GEMINI, "escalation")
    assert router.attachments[GEMINI].model_id == GEMINI


class _Limits:
    def __init__(self, usable: int) -> None:
        self.usable_input_tokens = usable


# --- The host's switch (spec.py `_recovery_escalation_for`) ----------------------------------------------------------

MOVE = PlanningEscalation(cause="REPEATED_READ", planning_steps=4, what="repeated the read of a.py#bytes=0:5 with unchanged results")


class ParkedNotices(RecordingOutboundChannel):
    """Never confirms the escalation notice's flush; everything else is recorded as usual."""

    def __init__(self) -> None:
        super().__init__()
        self.parked = asyncio.Event()

    async def notify(self, method, params, *, require_flushed=False):
        if params["update"]["content"]["text"].startswith("Auto: escalating"):
            self.parked.set()
            await asyncio.Event().wait()
        await super().notify(method, params, require_flushed=require_flushed)


def _turn(router, tier: str = "easy") -> AcpPromptTurn:
    turn = AcpPromptTurn(session_id="s", turn_seq=1, turn_control=TurnControl(session_id="s", turn_seq=1))
    turn.auto_decision = router.resolve(_outcome(tier))
    turn.route_binder = router.route_policy(turn.auto_decision).capture(session_id="s", turn_seq=1, deliver_notice=Notices())
    turn.route_binder.record_dispatch("an earlier planning request")
    return turn


def _escalation_texts(outbound) -> list[str]:
    return [n["params"]["update"]["content"]["text"] for n in outbound.notifications if "Auto: escalating" in str(n)]


async def test_the_switch_moves_the_binder_and_model_keeps_the_meter_and_the_routing_decision(tmp_path) -> None:
    # Engine-absent: no attached turn and no attachments, so only the binder and model move.
    router = replace(_router(), attachments={})
    adapter, outbound, _ = _adapter(tmp_path, router)
    turn = _turn(router)
    before, reading = turn.route_binder, turn.route_binder.largest_dispatch()

    outcome = await asyncio.to_thread(adapter._recovery_escalation_for(turn, asyncio.get_running_loop()), MOVE)  # noqa: SLF001

    assert isinstance(outcome, EscalationGrant) and (outcome.model_id, outcome.notice_delivered) == (GEMINI, True)
    assert turn.route_binder is outcome.route_binder is not before
    assert (turn.route_binder.identity.model_id, turn.route_binder.identity.role) == (GEMINI, "escalation")
    assert (turn.escalated_model, turn.turn_model, turn.auto_decision.model_id) == (GEMINI, GEMINI, LUNA)
    assert turn.route_binder.largest_dispatch() == reading
    [text] = _escalation_texts(outbound)
    assert text.startswith(f"Auto: escalating to {GEMINI}: the model repeated the read of a.py#bytes=0:5")


async def test_a_turn_already_on_the_escalation_model_is_not_moved_and_nothing_is_said(tmp_path) -> None:
    router = _router()
    adapter, outbound, _ = _adapter(tmp_path, router)
    turn = _turn(router, "medium")
    outcome = await asyncio.to_thread(adapter._recovery_escalation_for(turn, asyncio.get_running_loop()), MOVE)  # noqa: SLF001
    assert outcome is EscalationRefusal.NO_TARGET and turn.escalated_model is None and _escalation_texts(outbound) == []


async def test_a_halt_before_the_switch_wins_and_leaves_the_turn_as_it_was(tmp_path) -> None:
    router = _router()
    adapter, outbound, _ = _adapter(tmp_path, router)
    turn = _turn(router)
    before = turn.route_binder
    turn.turn_control.request_session_cancel()
    outcome = await asyncio.to_thread(adapter._recovery_escalation_for(turn, asyncio.get_running_loop()), MOVE)  # noqa: SLF001
    assert outcome is EscalationRefusal.HALTED
    assert (turn.route_binder, turn.escalated_model, _escalation_texts(outbound)) == (before, None, [])


async def test_an_unconfirmed_notice_is_recorded_and_never_gates_the_move(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(spec_module, "_NOTICE_FLUSH_TIMEOUT_SECONDS", 0.2)
    router = replace(_router(), attachments={})
    adapter, _, _ = _adapter(tmp_path, router)
    adapter._outbound = ParkedNotices()  # noqa: SLF001
    turn = _turn(router)
    outcome = await asyncio.to_thread(adapter._recovery_escalation_for(turn, asyncio.get_running_loop()), MOVE)  # noqa: SLF001
    assert isinstance(outcome, EscalationGrant) and outcome.notice_delivered is False and turn.escalated_model == GEMINI


@pytest.mark.parametrize("stop", ["cancel", "teardown"])
async def test_a_cancel_or_teardown_while_the_notice_is_parked_ends_the_wait_and_halts(tmp_path, stop: str) -> None:
    router = _router()
    adapter, _, _ = _adapter(tmp_path, router)
    outbound = adapter._outbound = ParkedNotices()  # noqa: SLF001
    turn = _turn(router)
    before = turn.route_binder
    bridge = adapter._recovery_escalation_for(turn, asyncio.get_running_loop())  # noqa: SLF001
    started = time.monotonic()
    pending = asyncio.create_task(asyncio.to_thread(bridge, MOVE))
    await asyncio.wait_for(outbound.parked.wait(), timeout=5)
    if stop == "cancel":
        # What session/cancel does (spec.py): a handle not yet registered is cancelled by the bridge's own halt check.
        turn.turn_control.request_session_cancel()
        if turn.permission_handle is not None:
            turn.permission_handle.cancel()
    else:
        turn.turn_control.request_transport_teardown()
    outcome = await asyncio.wait_for(pending, timeout=5)
    assert outcome is EscalationRefusal.HALTED and time.monotonic() - started < 5  # never the 30-second flush timeout
    assert (turn.route_binder, turn.escalated_model, turn.permission_handle) == (before, None, None)


async def test_a_switch_that_cannot_be_prepared_fails_with_its_cause_recorded_and_nothing_published(tmp_path, monkeypatch, capsys) -> None:
    router = _router()
    adapter, outbound, _ = _adapter(tmp_path, router)
    turn = _turn(router)
    before = turn.route_binder
    logged: list[dict] = []

    def broken(target):
        raise KeyError(target)

    monkeypatch.setattr(type(router), "escalation_route", lambda self, target: broken(target))
    monkeypatch.setattr(spec_module, "log_auto_route", lambda **kwargs: logged.append(kwargs))
    outcome = await asyncio.to_thread(adapter._recovery_escalation_for(turn, asyncio.get_running_loop()), MOVE)  # noqa: SLF001

    assert outcome is EscalationRefusal.FAILED
    assert (turn.route_binder, turn.escalated_model, _escalation_texts(outbound)) == (before, None, [])
    [record] = logged
    assert (record["outcome"], record["reason"], type(record["failure"])) == ("escalation_failed", "error", KeyError)
    err = capsys.readouterr().err
    assert "optimus.acp: auto escalation failed" in err and "error=KeyError" in err


def test_an_escalation_failures_record_keeps_the_class_and_never_the_text() -> None:
    from optimus.acp.debug_trace import log_auto_route

    events: list = []

    class Writer:
        def append(self, event):
            events.append(event)

    log_auto_route(run_id="s:1", outcome="escalation_failed", reason="error", telemetry=Writer(), failure=KeyError("secret-path/a.py"))
    [event] = events
    assert '"class":"KeyError"' in event.payload["message"] and "secret-path" not in event.payload["message"]


# --- The attached turn's switch (assembly.py `escalate_attachment`) ---------------------------------------------------


def _heavier(text: str) -> int:
    """Test-only: the target's estimator counts twice the tokens of the turn's (bytes / 2 against bytes / 4)."""
    return (len(text.encode("utf-8")) + 1) // 2


def test_after_the_switch_a_request_that_overflows_only_for_the_target_is_repacked_in_its_units_and_sent() -> None:
    from tests.unit.agent.test_context_selection import _attached_turn, _build, limits

    attached, _ = _attached_turn(usable=1100)
    assert attached.prepare().kind == "view"
    admitted = attached.admitted
    assert attached.fit(_build(600)) is not None and attached.repacks == 0
    target = replace(
        attached._attachment,  # noqa: SLF001 - equal capacity; only the estimator, its id and the allocation differ
        model_id="test/strong",
        estimate_request=_heavier,
        limits=replace(limits(history=4000), estimate_history=_heavier, estimator_id="utf8-bytes-div-2-test", summary_max_bytes=600),
    )

    attached.escalate_attachment(target)
    sent = attached.fit(_build(600))

    # Taking only the request estimator would mix units and refuse this request after its one repack.
    assert sent is not None and _heavier(sent) <= 1100 and attached.repacks == 1
    assert attached.model_id == "test/strong"
    assert attached.admitted is admitted  # the admission stays the turn's historical identity


# --- The Gateway admits the escalation role and nothing else changes in its binding ----------------------------------


def _escalation_only_snapshot(tmp_path, version: str = "task5-verified-test"):
    from tests.unit.optimus_gateway.model_policy_support import VERIFIED_POLICY, verified_snapshot

    # us/idle holds no tier role, only the escalation role (appended to the policy's closing `roles:` block).
    text = VERIFIED_POLICY.replace('"task5-verified-test"', f'"{version}"') + "  escalation: [us/idle]\n"
    (tmp_path / version).mkdir()
    return verified_snapshot(tmp_path / version, text)


def _escalation_binder(snapshot):
    from optimus.gateway.route_binding import RoutePolicy
    from optimus_model_policy.binding import disclosure_key
    from tests.unit.optimus_gateway.model_policy_support import CAP, SHARED_SECRET

    policy = RoutePolicy(snapshot=snapshot, disclosure_key=disclosure_key(SHARED_SECRET), model_id="us/idle", role="escalation", output_cap=CAP)
    return policy.capture(session_id="s", turn_seq=1, deliver_notice=Notices())


def test_a_model_eligible_only_for_escalation_is_bound_and_admitted_by_the_real_gateway(tmp_path) -> None:
    from optimus.agent.runner import AgentRunner
    from optimus.runtime.modes import ExecutionMode
    from tests.unit.agent.test_route_binding import InProcessGateway, ScriptedUpstream, _client, _request

    snapshot = _escalation_only_snapshot(tmp_path)
    gateway = InProcessGateway(snapshot, ScriptedUpstream(["Answered."]))
    binder = _escalation_binder(snapshot)
    result = AgentRunner(gateway_client=_client(gateway), model="us/idle").run(_request(tmp_path, ExecutionMode.CHAT), route_binder=binder)

    assert [status for status, _ in gateway.replies] == [200]
    assert [call["model"] for call in gateway.upstream.calls] == ["us/idle"]
    assert binder.identity.role == "escalation" and result.cost_complete is True


def test_an_escalation_binding_for_another_registry_snapshot_is_refused_before_any_upstream_call(tmp_path) -> None:
    from optimus.agent.runner import AgentRunner
    from optimus.runtime.modes import ExecutionMode
    from tests.unit.agent.test_route_binding import InProcessGateway, ScriptedUpstream, _client, _request

    snapshot = _escalation_only_snapshot(tmp_path)
    other = _escalation_only_snapshot(tmp_path, "another-snapshot")
    assert other.effective_hash != snapshot.effective_hash
    gateway = InProcessGateway(snapshot, ScriptedUpstream(["Answered."]))
    AgentRunner(gateway_client=_client(gateway), model="us/idle").run(_request(tmp_path, ExecutionMode.CHAT), route_binder=_escalation_binder(other))

    [(status, body)] = gateway.replies
    assert status != 200 and "REGISTRY_HASH_MISMATCH" in str(body)
    assert gateway.upstream.calls == []



# --- Only an interactive Auto turn is given the escalation ------------------------------------------------------------


@pytest.mark.parametrize(("auto", "interactive", "given"), [(True, True, True), (True, False, False), (False, True, False)])
async def test_only_an_interactive_auto_turns_planning_is_given_the_escalation(tmp_path, auto, interactive, given) -> None:
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore
    from tests.support.contract_doubles import checked_agent_runner
    from tests.unit.acp.test_auto_turn_routing import Classifier
    from tests.unit.acp.test_context_engine_admission import Runner, new_session, prompt

    outbound, runner = RecordingOutboundChannel(), Runner()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
        auto_router=_router(Classifier(["easy"])) if auto else None,
        interactive_recovery=interactive,
    )
    session_id = await new_session(adapter, tmp_path)
    await prompt(adapter, outbound, session_id, "Add example.py.", "p1", approve=True)

    planning, application = runner.kwargs
    assert ("recovery_escalation" in planning) is given
    assert "recovery_escalation" not in application  # the application never plans


async def test_after_a_grant_the_approved_application_runs_on_the_moved_to_model_and_binder(tmp_path) -> None:
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore
    from tests.support.contract_doubles import checked_agent_runner
    from tests.unit.acp.test_auto_turn_routing import Classifier
    from tests.unit.acp.test_context_engine_admission import Runner, new_session, prompt

    class Escalating(Runner):
        """Planning asks the host's real bridge to move the turn, as the planning loop would, then settles a plan."""

        def run(self, request, **kwargs):
            if "recovery_escalation" in kwargs:
                self.grant = kwargs["recovery_escalation"](MOVE)
            return super().run(request, **kwargs)

    outbound, runner = RecordingOutboundChannel(), Escalating()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound,
        auto_router=_router(Classifier(["easy"])),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path)
    await prompt(adapter, outbound, session_id, "Add example.py.", "p1", approve=True)

    planning, application = runner.kwargs
    assert isinstance(runner.grant, EscalationGrant) and runner.grant.model_id == GEMINI
    assert (planning["turn_model"], planning["route_binder"].identity.model_id) == (LUNA, LUNA)
    assert (application["turn_model"], application["route_binder"].identity.model_id) == (GEMINI, GEMINI)
    assert application["route_binder"] is runner.grant.route_binder
