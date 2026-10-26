"""Plan 12.4 Task 4, slice 3: the launch-scoped stop set (Task 4 implementation note r3, section 5).

The only stop predicate is the existing one (`stops_experimental_route`). Its writes: every planning and Chat report
(in `_report_attempts`' `finally`, so a stop is kept even when the receipts raise), the single-call planning path, and
both summarizer failure branches. Its reads: the resolver (slice 2) and the summarizer, which never calls a stopped
model again. An ordinary failure never stops a model. No network or paid call is made.
"""

from __future__ import annotations

import contextlib
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.acp.auto_composition import StopSet
from optimus.agent.runner import AgentRunner
from optimus.context.maintenance import GatewaySummarizerCall, MaintenanceIdentity
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayRouteAttempt, GatewayUsage
from optimus.gateway.route_binding import registry_route_identity
from optimus.runtime.modes import ExecutionMode
from tests.unit.acp.test_auto_turn_routing import GEMINI, HAIKU, LUNA, Classifier, _adapter, _router
from tests.unit.acp.test_context_engine_admission import new_session, prompt
from tests.unit.agent.test_route_binding import STANDARD, Notices, _policy, _request
from tests.unit.optimus_gateway.model_policy_support import verified_snapshot

STOPPED = GatewayHttpError(409, "route stopped", gateway_code="EMPIRICAL_ROUTE_STOPPED", retryable=False)
ORDINARY = GatewayHttpError(502, "upstream failed", gateway_code="UPSTREAM_ATTEMPT_FAILED", retryable=False)


@pytest.fixture
def snapshot(tmp_path: Path):
    (tmp_path / "registry").mkdir()
    return verified_snapshot(tmp_path / "registry")


class Failing:
    """A Gateway client whose every request fails with `error`."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def create_response(self, **kwargs: Any) -> Any:
        self.calls += 1
        raise self.error


def _run(tmp_path: Path, snapshot: Any, mode: ExecutionMode, error: BaseException, *, receipts: Any = None) -> StopSet:
    stops = StopSet()
    binder = _policy(snapshot, STANDARD).capture(session_id="s", turn_seq=1, deliver_notice=Notices())
    runner = AgentRunner(gateway_client=Failing(error), model=STANDARD)
    with contextlib.suppress(Exception):
        runner.run(_request(tmp_path, mode), route_binder=binder, model_stops=stops.add, stage_receipts=receipts)
    return stops


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT, ExecutionMode.PLAN], ids=["chat", "planning-loop", "single-call"])
def test_a_proven_stop_on_any_planning_or_answer_path_is_recorded_for_the_launch(tmp_path, snapshot, mode) -> None:
    assert STANDARD in _run(tmp_path, snapshot, mode, STOPPED)


def test_an_ordinary_failure_never_stops_a_model(tmp_path, snapshot) -> None:
    assert STANDARD not in _run(tmp_path, snapshot, ExecutionMode.CHAT, ORDINARY)


def test_the_stop_is_recorded_even_when_receipt_reporting_raises(tmp_path, snapshot) -> None:
    def refusing(receipt: Any) -> None:
        raise RuntimeError("the receipt sink failed")

    assert STANDARD in _run(tmp_path, snapshot, ExecutionMode.CHAT, STOPPED, receipts=refusing)


def _summarizer(client: Any, stops: StopSet) -> GatewaySummarizerCall:
    return GatewaySummarizerCall(gateway_client=client, model_id=HAIKU, session_id="s", request_ids=lambda: "s:1:summary:1", model_stops=stops)


def test_the_summarizers_proven_stop_is_recorded_and_the_stopped_model_is_never_called_again() -> None:
    stops, client = StopSet(), Failing(STOPPED)
    first = _summarizer(client, stops)(prompt="Summarize.", max_output_tokens=64)
    assert first.route_stopped and HAIKU in stops and client.calls == 1

    second = _summarizer(client, stops)(prompt="Summarize.", max_output_tokens=64)
    assert client.calls == 1, "a known-stopped summarizer is not called"
    assert second.route_stopped and second.text is None
    assert [(a.outcome, a.cost_usd) for a in second.attempts] == [("not_sent", Decimal("0"))]


def test_the_summarizers_integrity_branch_records_a_proven_stop_before_it_returns() -> None:
    usage = GatewayUsage(gateway_request_id="gw-reported", provider="fake", billing_units=3, input_tokens=2, output_tokens=1, cost_usd=Decimal("0.004"))
    unattributable = GatewayHttpError(
        409,
        "route stopped",
        gateway_code="EMPIRICAL_ROUTE_STOPPED",
        retryable=False,
        gateway_usage=usage,
        route_attempts=(GatewayRouteAttempt(attempt=1, gateway_request_id="gw-other", outcome="completed"),),
    )
    stops = StopSet()
    response = _summarizer(Failing(unattributable), stops)(prompt="Summarize.", max_output_tokens=64)
    assert response.integrity_error is not None, "the integrity branch ran"
    assert HAIKU in stops


def test_an_ordinary_summarizer_failure_stops_nothing() -> None:
    stops = StopSet()
    _summarizer(Failing(ORDINARY), stops)(prompt="Summarize.", max_output_tokens=64)
    assert HAIKU not in stops


# --- One launch, one stop set ----------------------------------------------------------------------------------------


async def test_an_auto_launch_shares_one_stop_set_between_its_runner_its_summarizer_and_its_resolver(tmp_path) -> None:
    router = _router(Classifier(["easy"]))
    adapter, outbound, runner = _adapter(tmp_path, router)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await prompt(adapter, outbound, session_id, "Hello?", "q1")

    runner.kwargs[0]["model_stops"](LUNA)
    assert LUNA in router.stops, "the runner's stops reach the launch's stop set"
    assert router.resolve(Classifier(["easy"])(None, router.stops)).model_id == HAIKU

    trusted = registry_route_identity(router.snapshot, model_id=HAIKU, role="summarizer")
    identity = MaintenanceIdentity(
        session_id="s", turn_seq=1, model_id=trusted.model_id, role=trusted.role, route=trusted.route, reasoning=trusted.reasoning,
        quantizations=trusted.quantizations, strategy="compaction", revision_digest="d" * 64, registry_hash=router.snapshot.effective_hash,
    )  # fmt: skip
    router.stops.add(HAIKU)
    for model_id in (LUNA, GEMINI):
        factory = router.attachments[model_id].summarizer
        assert factory is not None
        call = factory(identity, lambda text: True)
        # The client is a bare object: any request would fail, so a stopped summary must not reach it.
        response = call(prompt="Summarize.", max_output_tokens=64)
        assert response.route_stopped and [a.outcome for a in response.attempts] == ["not_sent"]
