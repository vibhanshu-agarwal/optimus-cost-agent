from __future__ import annotations

from pathlib import Path

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


def test_shadow_deleted_file_is_removed_after_gates_pass(tmp_path):
    target = tmp_path / "obsolete.py"
    target.write_text("remove me\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "obsolete.py").unlink(),
    )

    assert result.passed is True
    assert not target.exists()


def test_shadow_delete_and_write_promote_together(tmp_path):
    delete_me = tmp_path / "delete_me.py"
    keep_me = tmp_path / "keep_me.py"
    delete_me.write_text("old\n", encoding="utf-8")
    keep_me.write_text("old\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    def apply_candidate(shadow_root: Path) -> None:
        (shadow_root / "delete_me.py").unlink()
        (shadow_root / "keep_me.py").write_text("new\n", encoding="utf-8")

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=apply_candidate,
    )

    assert result.passed is True
    assert not delete_me.exists()
    assert keep_me.read_text(encoding="utf-8") == "new\n"


def test_shadow_deletion_diff_does_not_delete_ignored_workspace_content(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = python\n", encoding="utf-8")
    obsolete = tmp_path / "obsolete.py"
    obsolete.write_text("remove me\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "obsolete.py").unlink(),
    )

    assert result.passed is True
    assert not obsolete.exists()
    assert (tmp_path / ".git" / "config").read_text(encoding="utf-8") == "[core]\n"
    assert (tmp_path / ".venv" / "pyvenv.cfg").read_text(encoding="utf-8") == "home = python\n"


def test_shadow_workspace_skips_large_default_ignored_directories(tmp_path):
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "secret_provider.py").write_text("OPENAI_API_KEY='sk-test'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text("value = 1\n", encoding="utf-8")

    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    seen_shadow_paths: list[Path] = []

    def apply_candidate(shadow_root: Path) -> None:
        seen_shadow_paths.extend(path.relative_to(shadow_root) for path in shadow_root.rglob("*"))
        (shadow_root / "src" / "module.py").write_text("value = 2\n", encoding="utf-8")

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=apply_candidate,
    )

    assert result.passed is True
    assert Path(".venv") not in seen_shadow_paths
    assert Path(".venv/secret_provider.py") not in seen_shadow_paths
    assert (tmp_path / "src" / "module.py").read_text(encoding="utf-8") == "value = 2\n"


def test_shadow_workspace_accepts_extra_ignore_patterns(tmp_path):
    (tmp_path / ".local-cache").mkdir()
    (tmp_path / ".local-cache" / "large.bin").write_text("skip\n", encoding="utf-8")
    (tmp_path / "module.py").write_text("value = 1\n", encoding="utf-8")

    runner = ShadowWorkspaceMutationRunner(
        checks_factory=lambda shadow_root: (PassingCheck(),),
        ignore_patterns=(".local-cache",),
    )

    def apply_candidate(shadow_root: Path) -> None:
        assert not (shadow_root / ".local-cache").exists()
        (shadow_root / "module.py").write_text("value = 2\n", encoding="utf-8")

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=apply_candidate,
    )

    assert result.passed is True
    assert (tmp_path / "module.py").read_text(encoding="utf-8") == "value = 2\n"
