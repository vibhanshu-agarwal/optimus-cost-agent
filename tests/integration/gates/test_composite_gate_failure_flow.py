from __future__ import annotations

from optimus.gates.fitness import GateResult
from optimus.gates.mutation_flow import ShadowWorkspaceMutationRunner
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


class FailingCompositeCheck:
    name = "coverage"
    required = True

    def run(self) -> GateResult:
        return GateResult.fail(name=self.name, summary="aggregate coverage below 80")


def test_composite_gate_failure_leaves_working_file_untouched(tmp_path):
    target = tmp_path / "module.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (FailingCompositeCheck(),))
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-1",
    )

    result = runner.run(
        context=context,
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "module.py").write_text("def value():\n    return 2\n", encoding="utf-8"),
    )

    assert result.passed is False
    assert target.read_text(encoding="utf-8") == original
