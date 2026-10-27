"""Plan 12.4 Task 4, slice 2: each Auto turn is classified off the event loop, routed to one model and bound to that
model's route and context limits for the whole turn (Task 4 implementation note r3, sections 2-4 and 6).

The router is built from the real approved Auto composition (the shipped defaults plus the Auto overlay, no override):
easy is Luna, then Haiku; medium and complex are Gemini, which is also the default planner. The classifier is injected;
no network or paid call is made.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import auto_composition
from optimus.acp.auto_composition import (
    AutoComposition,
    AutoRouter,
    AutoTurnRefused,
    ClassificationAccountingError,
    ClassifierOutcome,
    Escalation,
    auto_router,
)
from optimus.acp.auto_hybrid import HybridClassifier
from optimus.acp.conversation import ConversationOutcome
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.context.shipped_policy import attachment_limits
from optimus.gateway.attempts import AttemptIntegrityError
from optimus.gateway.route_binding import RouteIdentityError
from optimus.runtime.modes import ExecutionMode
from optimus_model_policy.binding import auto_snapshot
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_context_engine_admission import Runner, new_session, prompt, prompt_request, rpc, session_of, texts
from tests.unit.agent.test_route_binding import STANDARD, InProcessGateway, Notices, ScriptedUpstream, _client, _policy, _request
from tests.unit.optimus_gateway.model_policy_support import verified_snapshot

LUNA, HAIKU, GEMINI = "openai/gpt-6-luna", "anthropic/claude-haiku-5.5", "google/gemini-3.8-flash"
SECRET = "s" * 32


def _router(classifier: Any = None) -> AutoRouter:
    snapshot = auto_snapshot()
    assert snapshot is not None
    return auto_router(AutoComposition(snapshot), gateway_client=object(), shared_secret=SECRET, attempt_observer=None, classifier=classifier)


def _outcome(tier: Any, **extra: Any) -> ClassifierOutcome:
    return ClassifierOutcome(tier=tier, confidence_band="high", **extra)


# --- The resolver ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("tier", "model"), [("easy", LUNA), ("medium", GEMINI), ("complex", GEMINI)])
def test_each_tier_routes_to_the_cheapest_model_in_its_role(tier: str, model: str) -> None:
    decision = _router().resolve(_outcome(tier))
    assert (decision.tier, decision.role, decision.model_id, decision.escalations, decision.default_fallback) == (tier, tier, model, (), False)


def test_a_low_confidence_route_up_is_the_classifiers_alone_and_never_applied_again() -> None:
    decision = _router().resolve(ClassifierOutcome(tier="medium", confidence_band="low", routed_up_for_confidence=True))
    assert (decision.tier, decision.model_id, decision.routed_up_for_confidence) == ("medium", GEMINI, True)


def test_a_classifier_failure_counts_as_a_medium_abstention_routed_up_to_complex() -> None:
    router = _router()
    assert router.resolve(ClassifierOutcome(tier=None, confidence_band="none")).failure_kind == "abstention"
    decision = router.resolve(ClassifierOutcome(tier=None, confidence_band="none", failure_kind="timeout"))
    assert (decision.classifier_tier, decision.tier, decision.model_id, decision.failure_kind) == (None, "complex", GEMINI, "timeout")


def test_a_stopped_model_falls_through_its_role_and_a_fully_stopped_role_routes_up() -> None:
    router = _router()
    router.stops.add(LUNA)
    assert (router.resolve(_outcome("easy")).model_id, router.resolve(_outcome("easy")).escalations) == (HAIKU, ())
    router.stops.add(HAIKU)
    decision = router.resolve(_outcome("easy"))
    assert (decision.tier, decision.model_id, decision.escalations) == ("medium", GEMINI, (Escalation(from_tier="easy", reason="stopped"),))


def test_an_empty_role_routes_up_and_the_unstopped_default_planner_is_the_last_fallback(monkeypatch) -> None:
    router = _router()
    roles = {"easy": (LUNA,), "medium": (), "complex": ()}
    monkeypatch.setattr(auto_composition, "select_eligible_models", lambda snapshot, role: roles[role.value])
    decision = router.resolve(_outcome("medium"))
    assert (decision.tier, decision.role, decision.model_id, decision.default_fallback) == ("medium", "medium", GEMINI, True)
    assert decision.escalations == (Escalation(from_tier="medium", reason="empty"), Escalation(from_tier="complex", reason="empty"))


def test_with_no_routable_tier_and_a_stopped_default_the_turn_is_refused() -> None:
    router = _router()
    router.stops.add(GEMINI)
    with pytest.raises(AutoTurnRefused) as refused:
        router.resolve(_outcome("medium"))
    assert refused.value.code == "AUTO_NO_ROUTABLE_MODEL"


def test_every_routable_model_has_its_own_route_policy_and_context_limits_and_the_summarizer_stays() -> None:
    router = _router()
    assert router.base_attachment is not None
    assert sorted(router.route_policies) == sorted(
        {(LUNA, "easy"), (HAIKU, "easy"), (GEMINI, "medium"), (GEMINI, "complex"), (GEMINI, "escalation")}
    )
    for (model_id, role), policy in router.route_policies.items():
        assert (policy.identity.model_id, policy.identity.role) == (model_id, role)
    for model_id in (LUNA, HAIKU, GEMINI):
        limits, attachment = attachment_limits(router.snapshot, model_id), router.attachments[model_id]
        assert (attachment.model_id, attachment.usable_input_tokens, attachment.parameters) == (model_id, limits.usable_input_tokens, limits.parameters)
        # Each composition builds its own estimator closure; everything else in the limits is equal.
        assert replace(attachment.limits, estimate_history=len) == replace(limits.limits, estimate_history=len)
        assert attachment.summarizer_route == router.base_attachment.summarizer_route


# --- The turn path ---------------------------------------------------------------------------------------------------


class Classifier:
    """Answers each turn with the next scripted tier (or raises it), recording its input and thread."""

    def __init__(self, answers: list[Any], *, entered: threading.Event | None = None, release: threading.Event | None = None) -> None:
        self.answers = list(answers)
        self.contracts: list[Any] = []
        self.on_loop_thread: list[bool] = []
        self.entered, self.release = entered, release

    def __call__(self, contract: Any, stops: Any, call: Any = None) -> ClassifierOutcome:
        self.contracts.append(contract)
        self.on_loop_thread.append(threading.current_thread() is threading.main_thread())
        if self.entered is not None and self.release is not None:
            self.entered.set()
            assert self.release.wait(5)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer if isinstance(answer, ClassifierOutcome) else _outcome(answer)


def _adapter(tmp_path: Path, router: AutoRouter, runner: Runner | None = None):
    outbound, runner = RecordingOutboundChannel(), runner or Runner()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound, auto_router=router
    )
    return adapter, outbound, runner


def _bound(kwargs: dict[str, Any]) -> tuple[str, str, str]:
    """What one runner invocation was told to send: its turn model, its binder's model, its packer's model."""
    return kwargs["turn_model"], kwargs["route_binder"].identity.model_id, kwargs["context_packer"].model_id


async def test_successive_turns_route_to_different_models_each_bound_for_its_whole_turn(tmp_path) -> None:
    classifier = Classifier(["easy", "complex"])
    adapter, outbound, runner = _adapter(tmp_path, _router(classifier))
    session_id = await new_session(adapter, tmp_path, mode="chat")

    for n in (1, 2):
        assert (await prompt(adapter, outbound, session_id, f"Question {n}?", f"q{n}"))["result"]["stopReason"] == "end_turn"

    assert [_bound(kwargs) for kwargs in runner.kwargs] == [(LUNA, LUNA, LUNA), (GEMINI, GEMINI, GEMINI)]
    assert [kwargs["route_binder"].identity.role for kwargs in runner.kwargs] == ["easy", "complex"]
    assert classifier.on_loop_thread == [False, False], "classification runs in the turn's worker"
    assert [c.previous_tier for c in classifier.contracts] == [None, "easy"]
    assert [c.mode for c in classifier.contracts] == ["CHAT", "CHAT"]
    routes = session_of(adapter, session_id).auto_routes
    assert [(seq, d.tier, d.model_id) for seq, d in sorted(routes.items())] == [(1, "easy", LUNA), (2, "complex", GEMINI)]
    assert len(session_of(adapter, session_id).conversation.records) == 2


async def test_planning_and_the_approved_application_use_the_one_selected_model(tmp_path) -> None:
    adapter, outbound, runner = _adapter(tmp_path, _router(Classifier(["easy"])))
    session_id = await new_session(adapter, tmp_path)

    await prompt(adapter, outbound, session_id, "Add example.py.", "p1", approve=True)

    assert len(runner.requests) == 2 and runner.requests[1].approval.approved
    assert [kwargs["turn_model"] for kwargs in runner.kwargs] == [LUNA, LUNA]
    assert runner.kwargs[0]["route_binder"] is runner.kwargs[1]["route_binder"]


def test_an_auto_launch_installs_h_for_the_compositions_classifier_model() -> None:
    router = _router()
    assert isinstance(router.classifier, HybridClassifier)
    assert AutoComposition(router.snapshot).classifier_model() == "typesafe/jev-1.14"


@pytest.mark.parametrize(
    ("answer", "text"),
    [
        (AttemptIntegrityError("ledger refused"), "could not account"),
        (ClassificationAccountingError("a receipt was refused"), "could not account"),
        (_outcome("complex"), "no model left"),
    ],
    ids=["attempt-integrity", "classification-accounting", "nothing-routable"],
)
async def test_an_integrity_failure_or_no_routable_model_refuses_without_dispatch(tmp_path, answer: Any, text: str) -> None:
    router = _router(Classifier([answer]))
    router.stops.add(GEMINI)
    adapter, outbound, runner = _adapter(tmp_path, router)
    session_id = await new_session(adapter, tmp_path, mode="chat")

    response = await prompt(adapter, outbound, session_id, "Hello?", "q1")

    assert response["result"]["stopReason"] == "end_turn" and runner.requests == []
    assert any(text in chunk for chunk in texts(outbound))
    assert session_of(adapter, session_id).conversation.records == {}


async def test_an_unmapped_classifier_failure_takes_the_failure_rule_to_complex(tmp_path) -> None:
    adapter, outbound, runner = _adapter(tmp_path, _router(Classifier([RuntimeError("upstream timed out")])))
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "Hello?", "q1")

    assert [kwargs["turn_model"] for kwargs in runner.kwargs] == [GEMINI]
    decision = session_of(adapter, session_id).auto_routes[1]
    assert (decision.classifier_tier, decision.tier, decision.failure_kind) == (None, "complex", "error")


@pytest.mark.parametrize("attached", [True, False], ids=["attached", "absent-engine"])
async def test_a_cancel_during_classification_makes_no_answer_call_and_publishes_no_route(tmp_path, attached: bool) -> None:
    entered, release = threading.Event(), threading.Event()
    router = _router(Classifier(["easy"], entered=entered, release=release))
    adapter, outbound, runner = _adapter(tmp_path, router if attached else replace(router, attachments={}))
    session_id = await new_session(adapter, tmp_path, mode="chat")

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Hello?", "q1")))
    assert await asyncio.to_thread(entered.wait, 5)
    await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
    release.set()
    response = await asyncio.wait_for(task, timeout=5)

    assert response["result"]["stopReason"] == "cancelled" and runner.requests == []
    session = session_of(adapter, session_id)
    assert session.auto_routes == {}
    assert session.conversation.records[1].outcome is ConversationOutcome.CANCELLED


async def test_a_mode_change_while_classification_is_outstanding_does_not_alter_the_frozen_turn(tmp_path) -> None:
    entered, release = threading.Event(), threading.Event()
    classifier = Classifier(["easy"], entered=entered, release=release)
    adapter, outbound, runner = _adapter(tmp_path, _router(classifier))
    session_id = await new_session(adapter, tmp_path, mode="chat")

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Hello?", "q1")))
    assert await asyncio.to_thread(entered.wait, 5)
    set_mode = {"jsonrpc": "2.0", "id": "m", "method": "session/set_mode", "params": {"sessionId": session_id, "modeId": "agent"}}
    assert "result" in await rpc(adapter, set_mode)
    release.set()
    await asyncio.wait_for(task, timeout=5)

    assert classifier.contracts[0].mode == "CHAT"
    assert [request.execution_mode for request in runner.requests] == [ExecutionMode.CHAT]


class _FailingFirstRunner(Runner):
    def run(self, request, **kwargs):
        result = super().run(request, **kwargs)
        if len(self.requests) == 1:
            return AgentRunResult(**{**result.model_dump(), "status": AgentRunStatus.FAILED, "final_state": "FAILED", "output_text": "failed"})
        return result


async def test_a_failed_turn_publishes_no_route_so_the_next_previous_tier_skips_it(tmp_path) -> None:
    classifier = Classifier(["complex", "easy", "medium"])
    adapter, outbound, runner = _adapter(tmp_path, _router(classifier), _FailingFirstRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")

    for n in (1, 2, 3):
        await prompt(adapter, outbound, session_id, f"Question {n}?", f"q{n}")

    assert sorted(session_of(adapter, session_id).auto_routes) == [2, 3]
    assert [c.previous_tier for c in classifier.contracts] == [None, None, "easy"]


async def test_two_concurrent_sessions_route_independently(tmp_path) -> None:
    def by_text(contract: Any, stops: Any, call: Any) -> ClassifierOutcome:
        return _outcome("easy" if contract.prompt.startswith("easy") else "complex")

    adapter, outbound, runner = _adapter(tmp_path, _router(by_text))
    first, second = await new_session(adapter, tmp_path, mode="chat"), await new_session(adapter, tmp_path, mode="chat")

    await asyncio.gather(prompt(adapter, outbound, first, "easy one", "a"), prompt(adapter, outbound, second, "hard one", "b"))

    sent = {request.session_id: kwargs["turn_model"] for request, kwargs in zip(runner.requests, runner.kwargs, strict=True)}
    assert sent == {first: LUNA, second: GEMINI}


# --- The runner's identity check -------------------------------------------------------------------------------------


@pytest.fixture
def snapshot(tmp_path: Path):
    (tmp_path / "registry").mkdir()
    return verified_snapshot(tmp_path / "registry")


def test_the_runner_sends_the_turns_model_instead_of_its_launch_model(tmp_path, snapshot) -> None:
    gateway = InProcessGateway(snapshot, ScriptedUpstream())
    binder = _policy(snapshot, STANDARD).capture(session_id="s", turn_seq=1, deliver_notice=Notices())
    AgentRunner(gateway_client=_client(gateway), model="launch/never-sent").run(
        _request(tmp_path, ExecutionMode.CHAT), route_binder=binder, turn_model=STANDARD
    )
    [payload] = gateway.payloads
    assert payload["model"] == STANDARD


def test_a_binder_or_packer_for_another_model_than_the_turns_is_refused_before_any_send(tmp_path, snapshot) -> None:
    gateway = InProcessGateway(snapshot, ScriptedUpstream())
    runner = AgentRunner(gateway_client=_client(gateway), model="launch/model")
    binder = _policy(snapshot, STANDARD).capture(session_id="s", turn_seq=1, deliver_notice=Notices())

    class Packer:
        model_id = "other/model"

    with pytest.raises(RouteIdentityError):
        runner.run(_request(tmp_path, ExecutionMode.CHAT), route_binder=binder, turn_model="other/model")
    with pytest.raises(RouteIdentityError):
        runner.run(_request(tmp_path, ExecutionMode.CHAT), route_binder=binder, turn_model=STANDARD, context_packer=Packer())
    assert gateway.payloads == []
