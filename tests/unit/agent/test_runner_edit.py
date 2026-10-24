"""EDIT through the real AgentRunner (#407): bound to the evidence digest, applied byte-exactly after approval,
and failing closed with a typed code, nothing written and no TEST run."""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from optimus.acp.lifecycle import DirectiveKind, TurnControl
from optimus.acp.settlement import EffectState
from optimus.acp.spec import _completion_message
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.planning_loop import PlanningTurnKind, PlanningTurnParseError, parse_planning_turn
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolRequest, PreToolResult, PreToolVerdict
from optimus.runtime.modes import ExecutionMode

HEADER = "# edited by Optimus"
FIRST_LINE = '"""A large module."""'
TOP_EDIT = f"EDIT big.py\n<<<<<<< OLD\n{FIRST_LINE}\n======= NEW\n{HEADER}\n{FIRST_LINE}\n>>>>>>> END\n"


def _big_file(tmp_path: Path) -> bytes:
    data = (FIRST_LINE + "\n" + "".join(f"def helper_{i:04d}():\n    return {i}\n\n" for i in range(900))).encode()
    assert len(data) > 16 * 1024  # too large for the initial context: the oversized multi-turn path
    (tmp_path / "big.py").write_bytes(data)
    return data


def _response(text: str, request_id: str) -> GatewayResponse:
    usage = GatewayUsage(gateway_request_id=request_id, provider="glm", billing_units=1, cost_usd=Decimal("0.001"))
    return GatewayResponse(response_id=request_id, output_text=text, gateway_usage=usage, raw={"id": request_id})


class _TopReadThenPlan:
    """Turn 1 reads the top of big.py, sized from the size line it receives; turn 2 returns ``plan``.
    ``before_plan`` runs just before the plan is returned (a file changed while the model was answering)."""

    def __init__(self, plan: str, *, before_plan: Any = None) -> None:
        self._plan = plan
        self._before_plan = before_plan
        self.calls: list[str] = []

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, Any] | None = None) -> GatewayResponse:
        del model, metadata
        self.calls.append(input_text)
        if len(self.calls) == 1:
            (size,) = re.findall(r"^- big\.py: size (\d+) bytes", input_text, re.MULTILINE)
            return _response(f"OBSERVE: the module header\nREAD: big.py#bytes=0:{min(int(size), 200)}\n", "gw-1")
        if len(self.calls) == 2:
            assert "Current guarded read evidence" in input_text and FIRST_LINE in input_text
            if self._before_plan is not None:
                self._before_plan()
            return _response(self._plan, "gw-2")
        raise AssertionError("no model call is expected after the plan")


class _Plan:
    def __init__(self, plan: str) -> None:
        self._plan = plan
        self.calls = 0

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, Any] | None = None) -> GatewayResponse:
        del model, input_text, metadata
        self.calls += 1
        if self.calls > 1:
            raise AssertionError("no model call is expected after the plan")
        return _response(self._plan, "gw-1")


class _Shell:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> CompletedProcess[str]:
        self.commands.append(command)
        return CompletedProcess(command, 0, "ok", "")


class _BlockWrites:
    def check(self, request: PreToolRequest) -> PreToolResult:
        if request.tool_surface is ToolSurface.FILE_WRITE:
            return PreToolResult(verdict=PreToolVerdict.BLOCK, rule_id="test.block-writes", reason="writes are blocked")
        return PreToolResult(verdict=PreToolVerdict.ALLOW, rule_id="test.allow", reason="allowed")


def _request(tmp_path: Path, task: str, approval: AgentApproval | None = None) -> AgentRunRequest:
    extra = {} if approval is None else {"approval": approval}
    return AgentRunRequest(run_id="run-1", task=task, execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path, **extra)


def _plan_then_approve(runner: AgentRunner, tmp_path: Path, task: str, between: Any = None, control: Any = None):
    plan = runner.run(_request(tmp_path, task))
    assert plan.status is AgentRunStatus.AWAITING_APPROVAL, plan.output_text
    if between is not None:
        between()
    approval = AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan.plan_hash)
    kwargs = {} if control is None else {"operation_control": control}
    return plan, runner.run(_request(tmp_path, task, approval), **kwargs)


def test_an_oversized_file_is_edited_at_its_top_after_approval_and_replay(tmp_path: Path) -> None:
    original = _big_file(tmp_path)
    gateway = _TopReadThenPlan("READ big.py\n" + TOP_EDIT)
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=InMemoryAgentStateStore())

    plan, result = _plan_then_approve(runner, tmp_path, "Add a comment line at the very top of big.py")

    base = hashlib.sha256(original).hexdigest()
    # The approved text is the bound plan: the hash covers the base, and the candidate shown is the same text.
    assert f"EDIT big.py base_sha256={base}\n" in plan.output_text
    assert plan.candidate_plan_text == plan.output_text
    assert plan.plan_hash == hashlib.sha256(plan.output_text.encode("utf-8")).hexdigest()
    # Replay applied the stored plan with no further model call (the double would raise).
    assert len(gateway.calls) == 2
    assert result.status is AgentRunStatus.COMPLETED, result.output_text
    assert result.mutation_count == 1
    assert (tmp_path / "big.py").read_bytes() == (HEADER + "\n").encode() + original


def test_a_file_shown_in_the_initial_context_keeps_its_crlf_bytes(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_bytes(b"a = 1\r\nb = 2\r\n")
    plan = "EDIT small.py\n<<<<<<< OLD\nb = 2\n======= NEW\nb = 3\nc = 4\n>>>>>>> END\n"
    runner = AgentRunner(gateway_client=_Plan(plan), model="glm-5.2", state_store=InMemoryAgentStateStore())

    _, result = _plan_then_approve(runner, tmp_path, "Change b in small.py")

    assert result.status is AgentRunStatus.COMPLETED, result.output_text
    assert (tmp_path / "small.py").read_bytes() == b"a = 1\r\nb = 3\r\nc = 4\r\n"


def test_a_change_outside_old_after_approval_writes_nothing_and_runs_no_test(tmp_path: Path) -> None:
    _big_file(tmp_path)
    shell = _Shell()
    runner = AgentRunner(
        gateway_client=_TopReadThenPlan(TOP_EDIT + "TEST pytest -q\n"),
        model="glm-5.2",
        state_store=InMemoryAgentStateStore(),
        shell_runner=shell,
    )
    target = tmp_path / "big.py"

    def edit_the_tail() -> None:
        target.write_bytes(target.read_bytes() + b"# a user edit far from OLD\n")

    _, result = _plan_then_approve(runner, tmp_path, "Add a comment line at the very top of big.py", between=edit_the_tail)

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "EDIT_NOT_APPLICABLE"
    assert "EDIT_SOURCE_CHANGED" in result.output_text and "Nothing was written" in result.output_text
    assert target.read_bytes().endswith(b"# a user edit far from OLD\n")
    assert not target.read_bytes().startswith(HEADER.encode())
    assert shell.commands == []
    assert _completion_message(result) == result.output_text


def test_a_file_changed_while_the_model_answered_is_never_bound(tmp_path: Path) -> None:
    _big_file(tmp_path)
    target = tmp_path / "big.py"
    store = InMemoryAgentStateStore()
    gateway = _TopReadThenPlan(TOP_EDIT, before_plan=lambda: target.write_bytes(target.read_bytes() + b"x = 1\n"))
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=store)

    result = runner.run(_request(tmp_path, "Add a comment line at the very top of big.py"))

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "EDIT_NOT_APPLICABLE"
    assert "EDIT_SOURCE_CHANGED" in result.output_text
    assert store.latest_plan_for_run(run_id="run-1") is None


def test_an_edit_without_raw_evidence_of_its_file_is_never_bound(tmp_path: Path) -> None:
    _big_file(tmp_path)
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=_Plan(TOP_EDIT), model="glm-5.2", state_store=store)

    result = runner.run(_request(tmp_path, "Add a comment line at the very top of big.py"))

    assert result.stop_reason == "EDIT_NOT_APPLICABLE"
    assert "EDIT_SOURCE_UNSEEN" in result.output_text
    assert store.latest_plan_for_run(run_id="run-1") is None


def test_an_old_that_no_longer_matches_settles_the_write_suppressed(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_text("a = 1\n", encoding="utf-8")
    plan = "EDIT small.py\n<<<<<<< OLD\nb = 2\n======= NEW\nb = 3\n>>>>>>> END\nTEST pytest -q\n"
    shell = _Shell()
    control = TurnControl(session_id="sess-1", turn_seq=1)
    runner = AgentRunner(gateway_client=_Plan(plan), model="glm-5.2", state_store=InMemoryAgentStateStore(), shell_runner=shell)

    _, result = _plan_then_approve(runner, tmp_path, "Change small.py", control=control)

    assert result.stop_reason == "EDIT_NOT_APPLICABLE"
    assert "EDIT_OLD_NOT_FOUND" in result.output_text
    assert (tmp_path / "small.py").read_text(encoding="utf-8") == "a = 1\n"
    assert shell.commands == []
    assert control.directive_state(DirectiveKind.WRITE, "run-1:approved:write:0") == "suppressed"
    assert control.directive_state(DirectiveKind.TEST, "run-1:approved:test:0") == "suppressed"
    assert control.refresh_effect_state() is EffectState.NONE


def test_a_guard_denied_edit_keeps_the_typed_no_effect_classification(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_text("a = 1\n", encoding="utf-8")
    plan = "EDIT small.py\n<<<<<<< OLD\na = 1\n======= NEW\na = 2\n>>>>>>> END\n"
    control = TurnControl(session_id="sess-1", turn_seq=1)
    runner = AgentRunner(
        gateway_client=_Plan(plan), model="glm-5.2", guard=_BlockWrites(), state_store=InMemoryAgentStateStore()
    )
    planned = runner.run(_request(tmp_path, "Change small.py"))
    approval = AgentApproval(approved=True, approval_id="approval-1", plan_hash=planned.plan_hash)

    with pytest.raises(PermissionError):
        runner.run(_request(tmp_path, "Change small.py", approval), operation_control=control)

    assert (tmp_path / "small.py").read_text(encoding="utf-8") == "a = 1\n"
    assert control.directive_state(DirectiveKind.WRITE, "run-1:approved:write:0") == "failed_no_effect"


def test_a_change_inside_the_guarded_write_is_caught_after_the_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from optimus.tools import mutation_tools

    target = tmp_path / "small.py"
    target.write_text("a = 1\n", encoding="utf-8")
    plan = "EDIT small.py\n<<<<<<< OLD\na = 1\n======= NEW\na = 2\n>>>>>>> END\n"
    control = TurnControl(session_id="sess-1", turn_seq=1)
    runner = AgentRunner(gateway_client=_Plan(plan), model="glm-5.2", state_store=InMemoryAgentStateStore())
    original_assert = mutation_tools._assert_pre_tool_allowed

    def guard_then_external_write(result: Any) -> None:
        original_assert(result)
        target.write_text("a = 1\nb = 9\n", encoding="utf-8")  # lands between the guard and the write

    planned = runner.run(_request(tmp_path, "Change small.py"))
    monkeypatch.setattr(mutation_tools, "_assert_pre_tool_allowed", guard_then_external_write)
    approval = AgentApproval(approved=True, approval_id="approval-1", plan_hash=planned.plan_hash)
    result = runner.run(_request(tmp_path, "Change small.py", approval), operation_control=control)

    assert result.stop_reason == "EDIT_NOT_APPLICABLE"
    assert "EDIT_SOURCE_CHANGED" in result.output_text
    assert target.read_text(encoding="utf-8") == "a = 1\nb = 9\n"
    assert control.directive_state(DirectiveKind.WRITE, "run-1:approved:write:0") == "failed_no_effect"


def test_a_cancelled_turn_starts_no_edit(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_text("a = 1\n", encoding="utf-8")
    plan = "EDIT small.py\n<<<<<<< OLD\na = 1\n======= NEW\na = 2\n>>>>>>> END\n"
    control = TurnControl(session_id="sess-1", turn_seq=1)
    control.request_session_cancel()
    runner = AgentRunner(gateway_client=_Plan(plan), model="glm-5.2", state_store=InMemoryAgentStateStore())

    _, result = _plan_then_approve(runner, tmp_path, "Change small.py", control=control)

    assert result.status is AgentRunStatus.TERMINATED
    assert (tmp_path / "small.py").read_text(encoding="utf-8") == "a = 1\n"
    assert control.directive_state(DirectiveKind.WRITE, "run-1:approved:write:0") == "suppressed"


def test_a_stored_edit_without_a_base_is_refused_not_rebound(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_text("a = 1\n", encoding="utf-8")
    plan = "EDIT small.py\n<<<<<<< OLD\na = 1\n======= NEW\na = 2\n>>>>>>> END\n"
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=_Plan(plan), model="glm-5.2", state_store=store)
    planned = runner.run(_request(tmp_path, "Change small.py"))
    record = store.latest_plan_for_run(run_id="run-1")
    unbound = record.plan_text.replace(re.search(r" base_sha256=[0-9a-f]{64}", record.plan_text).group(0), "")
    unbound_hash = hashlib.sha256(unbound.encode("utf-8")).hexdigest()
    store.persist_plan(record.model_copy(update={"plan_text": unbound, "plan_hash": unbound_hash}))
    assert planned.plan_hash != unbound_hash

    result = runner.run(_request(tmp_path, "Change small.py", AgentApproval(approved=True, approval_id="a", plan_hash=unbound_hash)))

    assert result.stop_reason == "EDIT_NOT_APPLICABLE"
    assert "EDIT_SOURCE_UNSEEN" in result.output_text
    assert (tmp_path / "small.py").read_text(encoding="utf-8") == "a = 1\n"


def test_planning_turns_treat_edit_blocks_as_opaque() -> None:
    literals = "OBSERVE: not a note\nREAD: big.py#bytes=0:10\nMCP_CALL srv tool {}\nREFUSE: no"
    plan = f"EDIT big.py\n<<<<<<< OLD\n{literals}\n======= NEW\n{literals}\n>>>>>>> END\n"

    decision = parse_planning_turn(plan)

    assert decision.kind is PlanningTurnKind.FINAL_PLAN
    assert decision.directives.write.blocks[0].old_lines == tuple(literals.split("\n"))


def test_a_model_supplied_base_is_not_a_final_plan() -> None:
    plan = TOP_EDIT.replace("EDIT big.py", "EDIT big.py base_sha256=" + "a" * 64)

    with pytest.raises(PlanningTurnParseError):
        parse_planning_turn(plan)


def test_an_edit_target_no_longer_utf8_after_approval_fails_typed_and_runs_no_test(tmp_path: Path) -> None:
    target = tmp_path / "small.py"
    target.write_text("a = 1\n", encoding="utf-8")
    plan = "READ small.py\nEDIT small.py\n<<<<<<< OLD\na = 1\n======= NEW\na = 2\n>>>>>>> END\nTEST pytest -q\n"
    shell = _Shell()
    control = TurnControl(session_id="sess-1", turn_seq=1)
    runner = AgentRunner(gateway_client=_Plan(plan), model="glm-5.2", state_store=InMemoryAgentStateStore(), shell_runner=shell)

    _, result = _plan_then_approve(
        runner, tmp_path, "Change small.py", between=lambda: target.write_bytes(b"a = \xff\n"), control=control
    )

    assert result.stop_reason == "EDIT_NOT_APPLICABLE"
    assert "EDIT_NOT_UTF8" in result.output_text
    assert target.read_bytes() == b"a = \xff\n"
    assert shell.commands == []
    assert control.directive_state(DirectiveKind.WRITE, "run-1:approved:write:0") == "suppressed"
    assert control.directive_state(DirectiveKind.TEST, "run-1:approved:test:0") == "suppressed"


def test_a_read_of_the_edit_target_by_an_equivalent_path_leaves_the_failure_typed(tmp_path: Path) -> None:
    target = tmp_path / "small.py"
    target.write_text("a = 1\n", encoding="utf-8")
    plan = "READ ./small.py\nEDIT small.py\n<<<<<<< OLD\na = 1\n======= NEW\na = 2\n>>>>>>> END\n"
    runner = AgentRunner(gateway_client=_Plan(plan), model="glm-5.2", state_store=InMemoryAgentStateStore())

    _, result = _plan_then_approve(runner, tmp_path, "Change small.py", between=lambda: target.write_bytes(b"a = \xff\n"))

    assert result.stop_reason == "EDIT_NOT_APPLICABLE"
    assert "EDIT_NOT_UTF8" in result.output_text


def test_planning_turns_end_edit_blocks_at_cr_lf_lines_only() -> None:
    plan = "EDIT big.py\n<<<<<<< OLD\nx\u2028>>>>>>> END\nOBSERVE: still OLD content\n======= NEW\ny\n>>>>>>> END\n"

    decision = parse_planning_turn(plan)

    assert decision.kind is PlanningTurnKind.FINAL_PLAN
    assert decision.directives.write.blocks[0].old_lines == ("x\u2028>>>>>>> END", "OBSERVE: still OLD content")
