from __future__ import annotations

import pytest

from optimus.gates.fitness import GateResult
from optimus.gates.mutation_flow import ShadowWorkspaceMutationRunner
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext


class PassingCheck:
    name = "tests"
    required = True

    def run(self) -> GateResult:
        return GateResult.pass_(name=self.name, summary="passed")


class FailingCheck:
    name = "tests"
    required = True

    def run(self) -> GateResult:
        return GateResult.fail(name=self.name, summary="failed")


def approved_context() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-1",
    )


def test_shadow_changes_promote_only_after_gates_pass(tmp_path):
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "module.py").write_text("value = 2\n", encoding="utf-8"),
    )

    assert result.passed is True
    assert target.read_text(encoding="utf-8") == "value = 2\n"


def test_gate_failure_discards_shadow_changes(tmp_path):
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (FailingCheck(),))

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "module.py").write_text("value = 2\n", encoding="utf-8"),
    )

    assert result.passed is False
    assert target.read_text(encoding="utf-8") == "value = 1\n"


def test_promote_failure_rolls_back_previous_file(tmp_path):
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("value = 1\n", encoding="utf-8")
    second.write_text("value = 1\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(
        checks_factory=lambda shadow_root: (PassingCheck(),),
        fail_after_promoted_paths=1,
    )

    with pytest.raises(RuntimeError, match="simulated promotion failure"):
        runner.run(
            context=approved_context(),
            workspace_root=tmp_path,
            apply_candidate=lambda shadow_root: (
                (shadow_root / "first.py").write_text("value = 2\n", encoding="utf-8"),
                (shadow_root / "second.py").write_text("value = 2\n", encoding="utf-8"),
            ),
        )

    assert first.read_text(encoding="utf-8") == "value = 1\n"
    assert second.read_text(encoding="utf-8") == "value = 1\n"


def test_plan_mode_blocks_before_gates_and_mutation(tmp_path):
    target = tmp_path / "changed.txt"
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))
    context = RuntimeContext(execution_mode=ExecutionMode.PLAN, state=AgentState.PLANNING)

    with pytest.raises(MutationForbidden, match="mutation forbidden"):
        runner.run(
            context=context,
            workspace_root=tmp_path,
            apply_candidate=lambda shadow_root: (shadow_root / "changed.txt").write_text("changed", encoding="utf-8"),
        )

    assert not target.exists()
