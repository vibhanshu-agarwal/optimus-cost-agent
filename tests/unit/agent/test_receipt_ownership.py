"""Codex CP3 ruling R1: receipt and control attribution belong to one `run` invocation.

The ACP adapter shares one runner across sessions and excludes only a second turn of the same session,
so two sessions' runs interleave on one runner. Each run's receipt sink and the control its receipts
are classified against travel with that invocation; nothing on the shared runner can route one
session's receipt to another, lose it, or classify it against another session's teardown. A nested
run on the same thread cannot clear its caller's state either.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.acp.lifecycle import TurnControl
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.gateway.models import GatewayResponse, GatewayRouteAttempt, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.usage.turn_settlement import StageReceipt


def _usage(gateway_id: str, cost: str = "0.002") -> GatewayUsage:
    return GatewayUsage(gateway_request_id=gateway_id, provider="fake", billing_units=1, cost_usd=Decimal(cost))


def _answer(gateway_id: str) -> GatewayResponse:
    return GatewayResponse(output_text="An answer.", gateway_usage=_usage(gateway_id), raw={}, finish_reason="stop")


def _routed_answer(gateway_id: str) -> GatewayResponse:
    attempts = (
        GatewayRouteAttempt(attempt=1, gateway_request_id=f"{gateway_id}-1", outcome="not_sent"),
        GatewayRouteAttempt(attempt=2, gateway_request_id=gateway_id, outcome="completed"),
    )
    return GatewayResponse(output_text="An answer.", gateway_usage=_usage(gateway_id), raw={}, finish_reason="stop", route_attempts=attempts)


class _TransportLost(Exception):
    pass


def _lost() -> GatewayResponse:
    raise _TransportLost("connection reset after send")


class OrderedGateway:
    """Each session's request blocks until the test releases it, so the test fixes which session's
    request is in flight while the other finishes, and in which order they complete."""

    def __init__(self, behaviour: dict[str, Callable[[], GatewayResponse]]) -> None:
        self.behaviour = behaviour
        self.entered = {sid: threading.Event() for sid in behaviour}
        self.release = {sid: threading.Event() for sid in behaviour}

    def create_response(self, *, model, input_text, metadata=None, **kwargs):
        sid = metadata["session_id"]
        self.entered[sid].set()
        if not self.release[sid].wait(5):
            raise AssertionError(f"session {sid} was never released")
        return self.behaviour[sid]()


def _chat(sid: str, tmp_path: Path) -> AgentRunRequest:
    return AgentRunRequest(run_id=f"{sid}:1", session_id=sid, task="A question?", workspace_root=tmp_path, execution_mode=ExecutionMode.CHAT)


def _run_two(tmp_path, behaviour, order, *, abandon: str | None = None):
    gateway = OrderedGateway(behaviour)
    runner = AgentRunner(gateway_client=gateway, model="fake/model")
    sinks: dict[str, list[StageReceipt]] = {sid: [] for sid in behaviour}
    controls = {sid: TurnControl(session_id=sid, turn_seq=1) for sid in behaviour}
    results, errors = {}, []

    def run(sid: str) -> None:
        try:
            results[sid] = runner.run(_chat(sid, tmp_path), stage_receipts=sinks[sid].append, operation_control=controls[sid])
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append((sid, exc))

    threads = {sid: threading.Thread(target=run, args=(sid,), name=f"run-{sid}") for sid in behaviour}
    for sid, thread in threads.items():
        thread.start()
        assert gateway.entered[sid].wait(5), f"{sid} never reached the Gateway"
    if abandon is not None:
        controls[abandon].request_transport_teardown()
    for sid in order:
        gateway.release[sid].set()
        threads[sid].join(5)
        assert not threads[sid].is_alive(), f"{sid} did not finish"
    assert errors == []
    return results, sinks


@pytest.mark.parametrize("order", [("A", "B"), ("B", "A")], ids=["A-first", "B-first"])
def test_interleaved_sessions_each_keep_exactly_their_own_receipts(tmp_path, order) -> None:
    results, sinks = _run_two(tmp_path, {"A": lambda: _answer("gw-A"), "B": lambda: _answer("gw-B")}, order)

    for sid in ("A", "B"):
        [receipt] = sinks[sid]
        assert (receipt.turn_id, receipt.attempt_id, receipt.gateway_request_id) == (f"{sid}:1", f"{sid}:1:answer:1:1", f"gw-{sid}")
        assert receipt.reported_cost_usd == results[sid].total_cost_usd == Decimal("0.002")


@pytest.mark.parametrize("order", [("A", "B"), ("B", "A")], ids=["A-first", "B-first"])
def test_an_unknown_attempt_stays_with_its_own_session(tmp_path, order) -> None:
    results, sinks = _run_two(tmp_path, {"A": _lost, "B": lambda: _answer("gw-B")}, order)

    [unknown] = sinks["A"]
    assert (unknown.attempt_id, unknown.outcome, unknown.reported_cost_usd) == ("A:1:answer:1:1", "uncertain", None)
    assert results["A"].cost_complete is False
    [known] = sinks["B"]
    assert (known.attempt_id, known.reported_cost_usd) == ("B:1:answer:1:1", Decimal("0.002"))
    assert results["B"].cost_complete is True


@pytest.mark.parametrize("order", [("A", "B"), ("B", "A")], ids=["A-first", "B-first"])
def test_one_session_abandoned_by_teardown_never_marks_the_other(tmp_path, order) -> None:
    _, sinks = _run_two(tmp_path, {"A": lambda: _answer("gw-A"), "B": lambda: _answer("gw-B")}, order, abandon="A")

    assert [(r.attempt_id, r.post_teardown) for r in sinks["A"]] == [("A:1:answer:1:1", True)]
    assert [(r.attempt_id, r.post_teardown) for r in sinks["B"]] == [("B:1:answer:1:1", False)]


def test_every_provider_attempt_is_one_receipt_in_its_own_session(tmp_path) -> None:
    _, sinks = _run_two(tmp_path, {"A": lambda: _routed_answer("gw-A"), "B": lambda: _answer("gw-B")}, ("B", "A"))

    assert [(r.attempt_id, r.outcome, r.reported_cost_usd) for r in sinks["A"]] == [
        ("A:1:answer:1:1:1", "not_sent", Decimal("0")),
        ("A:1:answer:1:1:2", "completed", Decimal("0.002")),
    ]
    assert [r.attempt_id for r in sinks["B"]] == ["B:1:answer:1:1"]


def test_a_nested_run_cannot_clear_or_take_its_callers_receipts(tmp_path) -> None:
    """A run started on the same thread while another is in flight finishes first; the outer run's
    receipt still reaches its own sink, classified against its own control."""
    outer_sink: list[StageReceipt] = []
    inner_sink: list[StageReceipt] = []
    outer_control = TurnControl(session_id="A", turn_seq=1)

    class NestingGateway:
        def __init__(self) -> None:
            self.runner: AgentRunner | None = None

        def create_response(self, *, model, input_text, metadata=None, **kwargs):
            sid = metadata["session_id"]
            if sid == "A":
                assert self.runner is not None
                self.runner.run(_chat("B", tmp_path), stage_receipts=inner_sink.append)
                outer_control.request_transport_teardown()
            return _answer(f"gw-{sid}")

    gateway = NestingGateway()
    runner = AgentRunner(gateway_client=gateway, model="fake/model")
    gateway.runner = runner

    runner.run(_chat("A", tmp_path), stage_receipts=outer_sink.append, operation_control=outer_control)

    assert [(r.attempt_id, r.post_teardown) for r in outer_sink] == [("A:1:answer:1:1", True)]
    assert [(r.attempt_id, r.post_teardown) for r in inner_sink] == [("B:1:answer:1:1", False)]


def test_the_runner_keeps_no_invocation_state_between_runs(tmp_path) -> None:
    runner = AgentRunner(gateway_client=OrderedGateway({}), model="fake/model")

    assert not [name for name in vars(runner) if "receipt" in name or "active" in name]
