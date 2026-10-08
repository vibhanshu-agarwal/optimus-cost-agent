"""Plan 12.2 Task 2: runner producers report real starts and terminals to the turn lifecycle.

Each approved READ, WRITE and TEST takes a lease immediately before its producer runs and publishes
one terminal. The known WRITE and TEST operations are registered before anything executes, so a
cancellation suppresses whatever has not started and the settled effect stays exact. Cancellation
never interrupts an operation that is already running.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from optimus.acp.lifecycle import DirectiveKind, StartLease, TurnControl
from optimus.acp.settlement import EffectState
from optimus.agent import tools as agent_tools
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolRequest, PreToolResult, PreToolVerdict
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext

WRITE_THEN_TEST = "WRITE example.py\nnew\nTEST pytest -q"


class _PlanGateway:
    def __init__(self, plan_text: str) -> None:
        self._plan_text = plan_text

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, Any] | None = None) -> GatewayResponse:
        del model, input_text, metadata
        return GatewayResponse(
            response_id="resp-1",
            output_text=self._plan_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="test",
                billing_units=1,
                cost_usd=Decimal("0.001"),
            ),
            raw={"id": "resp-1"},
        )


class _RecordingControl(TurnControl):
    """The real TurnControl, plus an ordered log of its calls and of producer runs.

    ``cancel_after_write`` cancels the turn right after the WRITE's terminal is published, before
    the TEST's lease: the window in which cancellation leaves a stale COMPLETE behind.
    """

    def __init__(self, *, cancel_after_write: bool = False) -> None:
        super().__init__(session_id="sess-1", turn_seq=1)
        self.events: list[tuple[str, ...]] = []
        self._cancel_after_write = cancel_after_write

    def register_operations(self, directives: Any) -> None:
        for kind, operation_id in directives:
            self.events.append(("register", kind.value, operation_id))
        super().register_operations(directives)

    def try_start(self, operation_kind: Any, operation_id: str) -> StartLease:
        lease = super().try_start(operation_kind, operation_id)
        if isinstance(operation_kind, DirectiveKind):
            self.events.append(("start", operation_kind.value, operation_id, str(lease.granted)))
        return lease

    def complete_directive(self, kind: DirectiveKind, operation_id: str, terminal: str) -> None:
        self.events.append(("complete", kind.value, operation_id, terminal))
        super().complete_directive(kind, operation_id, terminal)
        if self._cancel_after_write and kind is DirectiveKind.WRITE:
            self.request_session_cancel()

    def ids(self, action: str, kind: DirectiveKind) -> list[str]:
        return [event[2] for event in self.events if event[0] == action and event[1] == kind.value]

    def terminal(self, kind: DirectiveKind, operation_id: str) -> str | None:
        return self.directive_state(kind, operation_id)


class _Shell:
    def __init__(self, control: _RecordingControl | None = None, *, returncode: int = 0) -> None:
        self.commands: list[list[str]] = []
        self._control = control
        self._returncode = returncode

    def __call__(self, command: list[str]) -> CompletedProcess[str]:
        self.commands.append(command)
        if self._control is not None:
            self._control.events.append(("produce", "test"))
        return CompletedProcess(command, self._returncode, "out", "")


class _BlockWrites:
    """A real pre-tool guard verdict: file writes are blocked, everything else is allowed."""

    def check(self, request: PreToolRequest) -> PreToolResult:
        if request.tool_surface is ToolSurface.FILE_WRITE:
            return PreToolResult(verdict=PreToolVerdict.BLOCK, rule_id="test.block-writes", reason="writes are blocked")
        return PreToolResult(verdict=PreToolVerdict.ALLOW, rule_id="test.allow", reason="allowed")


def _approved(tmp_path: Path, plan_text: str, shell: _Shell, *, guard: Any = None) -> tuple[AgentRunner, AgentRunRequest]:
    runner = AgentRunner(
        gateway_client=_PlanGateway(plan_text),
        model="test-model",
        guard=guard,
        state_store=InMemoryAgentStateStore(),
        shell_runner=shell,
    )
    base: dict[str, Any] = {
        "run_id": "run-1",
        "session_id": "sess-1",
        "task": "Change example.py",
        "execution_mode": ExecutionMode.AGENT,
        "workspace_root": tmp_path,
    }
    plan = runner.run(AgentRunRequest(**base))
    assert plan.status is AgentRunStatus.AWAITING_APPROVAL
    approval = AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan.plan_hash)
    return runner, AgentRunRequest(**base, approval=approval)


def _record_writes(monkeypatch: pytest.MonkeyPatch, control: _RecordingControl) -> None:
    """Log the real write producer's run, so the lease order around it can be asserted."""
    original = agent_tools.guarded_write_file

    def recording_write(*args: Any, **kwargs: Any) -> None:
        control.events.append(("produce", "write"))
        original(*args, **kwargs)

    monkeypatch.setattr(agent_tools, "guarded_write_file", recording_write)


def _single(control: _RecordingControl, kind: DirectiveKind) -> str:
    (operation_id,) = control.ids("register", kind)
    return operation_id


def test_approved_write_and_test_publish_real_terminals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    control = _RecordingControl()
    shell = _Shell(control)
    runner, request = _approved(tmp_path, WRITE_THEN_TEST, shell)
    _record_writes(monkeypatch, control)

    result = runner.run(request, operation_control=control)

    assert result.status is AgentRunStatus.COMPLETED
    write_id, test_id = _single(control, DirectiveKind.WRITE), _single(control, DirectiveKind.TEST)
    assert control.terminal(DirectiveKind.WRITE, write_id) == "succeeded"
    assert control.terminal(DirectiveKind.TEST, test_id) == "succeeded"
    assert control.refresh_effect_state() is EffectState.COMPLETE
    events = control.events
    # Both effectful operations are registered before anything starts.
    first_start = next(index for index, event in enumerate(events) if event[0] == "start")
    registered_before = {event[2] for event in events[:first_start] if event[0] == "register"}
    assert {write_id, test_id} <= registered_before
    # Each lease is taken immediately before its producer, and its terminal immediately after.
    write_start = events.index(("start", "write", write_id, "True"))
    assert events[write_start + 1] == ("produce", "write")
    assert events[write_start + 2] == ("complete", "write", write_id, "succeeded")
    test_start = events.index(("start", "test", test_id, "True"))
    assert events[test_start + 1] == ("produce", "test")
    assert events[test_start + 2] == ("complete", "test", test_id, "succeeded")


def test_implicit_pre_write_read_has_its_own_lease(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    control = _RecordingControl()
    runner, request = _approved(tmp_path, "READ example.py\n" + WRITE_THEN_TEST, _Shell(control))

    runner.run(request, operation_control=control)

    read_ids = control.ids("start", DirectiveKind.READ)
    assert len(read_ids) == 2
    assert len(set(read_ids)) == 2
    assert all(control.terminal(DirectiveKind.READ, operation_id) == "succeeded" for operation_id in read_ids)


def test_cancel_before_approved_execution_starts_no_producer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    control = _RecordingControl()
    shell = _Shell(control)
    runner, request = _approved(tmp_path, "READ example.py\n" + WRITE_THEN_TEST, shell)
    _record_writes(monkeypatch, control)
    control.request_session_cancel()

    result = runner.run(request, operation_control=control)

    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "cancelled"
    assert result.mutation_count == 0
    assert not any(event[0] == "produce" for event in control.events)
    assert shell.commands == []
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "old\n"
    assert control.terminal(DirectiveKind.WRITE, _single(control, DirectiveKind.WRITE)) == "suppressed"
    assert control.terminal(DirectiveKind.TEST, _single(control, DirectiveKind.TEST)) == "suppressed"
    assert control.refresh_effect_state() is EffectState.NONE


def test_cancel_between_write_and_test_keeps_the_write_and_suppresses_the_test(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    # The cancel lands after the WRITE's terminal and before the TEST's lease, so no later
    # complete_directive recomputes the effect: only refresh_effect_state() can settle PARTIAL.
    control = _RecordingControl(cancel_after_write=True)
    shell = _Shell(control)
    runner, request = _approved(tmp_path, WRITE_THEN_TEST, shell)

    result = runner.run(request, operation_control=control)

    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "cancelled"
    assert result.mutation_count == 1
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "new"
    assert shell.commands == []
    assert control.terminal(DirectiveKind.WRITE, _single(control, DirectiveKind.WRITE)) == "succeeded"
    assert control.terminal(DirectiveKind.TEST, _single(control, DirectiveKind.TEST)) == "suppressed"
    assert control.refresh_effect_state() is EffectState.PARTIAL


def test_non_zero_test_exit_counts_as_executed(tmp_path: Path) -> None:
    control = _RecordingControl()
    shell = _Shell(control, returncode=1)
    runner, request = _approved(tmp_path, "TEST pytest -q", shell)

    result = runner.run(request, operation_control=control)

    assert shell.commands == [["pytest", "-q"]]
    assert control.terminal(DirectiveKind.TEST, _single(control, DirectiveKind.TEST)) == "succeeded"
    assert [call.summary for call in result.tool_calls] == ["ran pytest -q exit=1"]
    assert control.refresh_effect_state() is EffectState.COMPLETE


def test_typed_guard_denial_before_the_write_is_no_effect(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    control = _RecordingControl()
    runner, request = _approved(tmp_path, WRITE_THEN_TEST, _Shell(control), guard=_BlockWrites())

    with pytest.raises(PermissionError):
        runner.run(request, operation_control=control)

    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "old\n"
    assert control.terminal(DirectiveKind.WRITE, _single(control, DirectiveKind.WRITE)) == "failed_no_effect"
    assert control.refresh_effect_state() is EffectState.NONE


def test_a_refused_start_without_cancellation_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    control = _RecordingControl()
    shell = _Shell(control)
    runner, request = _approved(tmp_path, WRITE_THEN_TEST, shell)
    # The same identity already settled on this control, and nothing cancelled the turn: a refused
    # start is then a duplicate, which must not be reported as a cancellation.
    write_id = "run-1:approved:write:0"
    assert control.try_start(DirectiveKind.WRITE, write_id).granted is True
    control.complete_directive(DirectiveKind.WRITE, write_id, "succeeded")

    with pytest.raises(RuntimeError, match="refused a start"):
        runner.run(request, operation_control=control)

    assert control.halt_requested() is False
    assert shell.commands == []
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "old\n"


@pytest.mark.parametrize(
    "error",
    [OSError("disk full"), PermissionError("denied by the operating system")],
    ids=["os-error", "untyped-permission-error"],
)
def test_failure_after_a_write_may_have_started_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    control = _RecordingControl()
    runner, request = _approved(tmp_path, WRITE_THEN_TEST, _Shell(control))

    def failing(*args: Any, **kwargs: Any) -> None:
        raise error

    monkeypatch.setattr(agent_tools, "guarded_write_file", failing)

    with pytest.raises(type(error)):
        runner.run(request, operation_control=control)

    assert control.terminal(DirectiveKind.WRITE, _single(control, DirectiveKind.WRITE)) == "failed_effect_unknown"
    assert control.refresh_effect_state() is EffectState.INDETERMINATE


def test_test_runner_failure_after_start_is_indeterminate(tmp_path: Path) -> None:
    control = _RecordingControl()

    def broken_shell(command: list[str]) -> CompletedProcess[str]:
        raise OSError("runner crashed")

    runner = AgentRunner(
        gateway_client=_PlanGateway("TEST pytest -q"),
        model="test-model",
        state_store=InMemoryAgentStateStore(),
        shell_runner=broken_shell,
    )
    base: dict[str, Any] = {
        "run_id": "run-1",
        "session_id": "sess-1",
        "task": "Run tests",
        "execution_mode": ExecutionMode.AGENT,
        "workspace_root": tmp_path,
    }
    plan = runner.run(AgentRunRequest(**base))
    approval = AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan.plan_hash)

    with pytest.raises(OSError):
        runner.run(AgentRunRequest(**base, approval=approval), operation_control=control)

    assert control.terminal(DirectiveKind.TEST, _single(control, DirectiveKind.TEST)) == "failed_effect_unknown"
    assert control.refresh_effect_state() is EffectState.INDETERMINATE


def test_operation_ids_are_per_call_deterministic_and_distinct(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    plan_text = "READ a.py\nREAD a.py\nWRITE a.py\nnew\nTEST pytest -q\nTEST pytest -q"
    first, second = _RecordingControl(), _RecordingControl()
    runner, request = _approved(tmp_path, plan_text, _Shell())

    runner.run(request, operation_control=first)
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    runner.run(request, operation_control=second)

    started = [(event[1], event[2]) for event in first.events if event[0] == "start"]
    assert len(started) == len(set(started)) == 6  # two plan reads, one pre-write read, a write, two tests
    assert started == [(event[1], event[2]) for event in second.events if event[0] == "start"]
    assert all(operation_id.startswith("run-1:") for _kind, operation_id in started)


def test_runs_without_a_control_keep_their_behavior(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    shell = _Shell()
    runner, request = _approved(tmp_path, WRITE_THEN_TEST, shell)

    result = runner.run(request)

    assert result.status is AgentRunStatus.COMPLETED
    assert result.mutation_count == 1
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "new"
    assert shell.commands == [["pytest", "-q"]]


def test_unreachable_pre_approved_branch_threads_the_control(tmp_path: Path) -> None:
    """``_finish_agent_planning``'s approved branch is unreachable through ``run()``: every approved
    Agent request takes the stored-plan path. Its wiring is still pinned so a future caller is exact."""
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    control = _RecordingControl()
    shell = _Shell(control)
    runner = AgentRunner(
        gateway_client=_PlanGateway(WRITE_THEN_TEST),
        model="test-model",
        state_store=InMemoryAgentStateStore(),
        shell_runner=shell,
    )
    plan_hash = hashlib.sha256(WRITE_THEN_TEST.encode("utf-8")).hexdigest()
    request = AgentRunRequest(
        run_id="run-1",
        session_id="sess-1",
        task="Change example.py",
        execution_mode=ExecutionMode.AGENT,
        workspace_root=tmp_path,
        approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_hash),
    )
    context = RuntimeContext(execution_mode=ExecutionMode.AGENT, state=AgentState.PLANNING)
    toolbox = agent_tools.AgentToolbox.for_workspace(workspace_root=tmp_path, context=context, run_id="run-1")

    result = runner._finish_agent_planning(  # noqa: SLF001
        request=request,
        context=context,
        toolbox=toolbox,
        tool_calls=[],
        output_text=WRITE_THEN_TEST,
        total_cost_usd=Decimal("0"),
        gateway_request_id="gw-1",
        gateway_request_ids=("gw-1",),
        planning_turns=1,
        provider="test",
        operation_control=control,
    )

    assert result.status is AgentRunStatus.COMPLETED
    assert control.terminal(DirectiveKind.WRITE, _single(control, DirectiveKind.WRITE)) == "succeeded"
    assert control.terminal(DirectiveKind.TEST, _single(control, DirectiveKind.TEST)) == "succeeded"
    assert control.refresh_effect_state() is EffectState.COMPLETE
