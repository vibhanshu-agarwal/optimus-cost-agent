"""Plan 12.3 Design 8, through the approved replay: each TEST directive has a deadline and the turn's
cancellation; a timeout, a containment failure or an unconfirmed stop ends the plan, and the later
directives are suppressed. The command is a real child process standing in for pytest."""

from __future__ import annotations

import sys
import threading
import time
from decimal import Decimal

import pytest

from optimus.acp.lifecycle import DirectiveKind, TurnControl
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime import process_tree
from optimus.runtime.modes import ExecutionMode

PLAN = "WRITE a.py\nupdated\nTEST pytest tests/one -q\nTEST pytest tests/two -q\n"
HANG = [sys.executable, "-c", "import time; time.sleep(60)"]


class Gateway:
    def create_response(self, *, model, input_text, metadata=None):
        return GatewayResponse(
            response_id="gw-1",
            output_text=PLAN,
            gateway_usage=GatewayUsage(gateway_request_id="gw-1", provider="glm", billing_units=1, cost_usd=Decimal("0.001")),
            raw={"id": "gw-1"},
        )


@pytest.fixture
def launches(monkeypatch):
    """Every TEST launch, run as a hanging child instead of pytest."""
    started: list[list[str]] = []
    real_popen = process_tree.popen

    def popen(args, **kwargs):
        started.append(list(args))
        return real_popen(HANG, **kwargs)

    monkeypatch.setattr(process_tree, "popen", popen)
    return started


def _approved(tmp_path, *, deadline: float = 1.0, control: TurnControl | None = None):
    (tmp_path / "a.py").write_text("old\n", encoding="utf-8")
    runner = AgentRunner(gateway_client=Gateway(), model="glm-5.2", state_store=InMemoryAgentStateStore(), test_deadline_seconds=deadline)
    request = AgentRunRequest(run_id="run-1", task="Update a.py", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path)
    plan = runner.run(request)
    approval = AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan.plan_hash)
    started = time.monotonic()
    result = runner.run(request.model_copy(update={"approval": approval}), operation_control=control)
    return result, time.monotonic() - started


def test_a_hung_test_times_out_and_the_later_directive_is_suppressed(tmp_path, launches):
    control = TurnControl(session_id="session-1", turn_seq=1)
    result, elapsed = _approved(tmp_path, control=control)

    assert (result.status, result.stop_reason) == (AgentRunStatus.FAILED, "TEST_TIMED_OUT")
    assert launches == [["pytest", "tests/one", "-q"]]
    assert "ran pytest tests/one -q: timed out after 1 s" in [call.summary for call in result.tool_calls]
    assert "the later directives were not run" in result.output_text and "wrote a.py" in result.output_text
    assert control.directive_state(DirectiveKind.TEST, "run-1:approved:test:1") == "suppressed"
    assert elapsed < 1 + process_tree._CLEANUP_SECONDS


def test_an_unconfirmed_stop_is_reported_within_the_deadline_and_cleanup_bound(tmp_path, launches, monkeypatch):
    monkeypatch.setattr(process_tree, "_CLEANUP_SECONDS", 1.0)
    survivors: list = []
    real_kill = process_tree.kill_tree
    monkeypatch.setattr(process_tree, "kill_tree", survivors.append)  # injected: the kill does nothing
    try:
        result, elapsed = _approved(tmp_path)
        assert result.stop_reason == "TEST_STOP_UNCONFIRMED"
        assert "stop unconfirmed" in result.output_text
        assert len(launches) == 1
        assert elapsed < 1 + 1.0 + 1.0
    finally:
        for process in survivors:
            real_kill(process)
            process.wait(10)


def test_a_test_that_cannot_be_contained_is_never_launched(tmp_path, monkeypatch):
    def refuse(args, **kwargs):
        raise process_tree.ContainmentError("injected: the job refused the process")

    monkeypatch.setattr(process_tree, "popen", refuse)
    result, _ = _approved(tmp_path, deadline=60)
    assert result.stop_reason == "TEST_CONTAINMENT_FAILED"
    assert "containment failed" in result.output_text


def test_cancelling_the_turn_stops_a_running_test(tmp_path, launches):
    control = TurnControl(session_id="session-1", turn_seq=1)
    threading.Timer(1.0, control.request_session_cancel).start()
    result, elapsed = _approved(tmp_path, deadline=60, control=control)
    assert (result.status, result.stop_reason) == (AgentRunStatus.TERMINATED, "cancelled")
    assert len(launches) == 1
    assert elapsed < 1 + process_tree._CLEANUP_SECONDS + 1
