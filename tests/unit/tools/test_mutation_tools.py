import pytest

from optimus.guardrails.pre_tool import PreToolGuard, PreToolResult, PreToolVerdict
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools.mutation_tools import shell_exec, shadow_apply, write_file


class ProbeRunner:
    """Test double for shell_exec runner; records whether execution reached I/O."""

    def __init__(self) -> None:
        self.called = False

    def __call__(self, command: list[str]) -> object:
        self.called = True
        return {"returncode": 0, "command": command}


class ProbeApplier:
    """Test double for shadow_apply applier; records whether patch apply was attempted."""

    def __init__(self) -> None:
        self.called = False

    def __call__(self, patch_text: str) -> object:
        self.called = True
        return {"applied": True, "patch_text": patch_text}


def plan_context() -> RuntimeContext:
    return RuntimeContext(execution_mode=ExecutionMode.PLAN, state=AgentState.CHAT_ONLY)


def approved_agent_context() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-123",
    )


def test_write_file_checks_guard_before_writing(tmp_path):
    target = tmp_path / "blocked.txt"

    with pytest.raises(MutationForbidden):
        write_file(target, "blocked", context=plan_context())

    assert not target.exists()


def test_shell_exec_checks_guard_before_runner_call():
    runner = ProbeRunner()

    with pytest.raises(MutationForbidden):
        shell_exec(["pytest", "-q"], context=plan_context(), runner=runner)

    assert runner.called is False


def test_shadow_apply_checks_guard_before_applier_call():
    applier = ProbeApplier()

    with pytest.raises(MutationForbidden):
        shadow_apply("diff --git a/x b/x", context=plan_context(), applier=applier)

    assert applier.called is False


def test_write_file_allowed_after_agent_approval(tmp_path):
    target = tmp_path / "allowed.txt"
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    write_file(target, "allowed", context=approved_agent_context(), guard=guard)

    assert target.read_text(encoding="utf-8") == "allowed"


def test_shell_exec_allowed_after_agent_approval():
    runner = ProbeRunner()

    result = shell_exec(["pytest", "-q"], context=approved_agent_context(), runner=runner)

    assert runner.called is True
    assert result == {"returncode": 0, "command": ["pytest", "-q"]}


class DenyGuard:
    def __init__(self) -> None:
        self.requests = []

    def check(self, request):
        self.requests.append(request)
        return PreToolResult(PreToolVerdict.BLOCK, "test.block", "blocked by test guard")


def test_shell_exec_checks_pre_tool_guard_before_runner_call():
    runner = ProbeRunner()
    guard = DenyGuard()

    with pytest.raises(MutationForbidden, match="blocked by test guard"):
        shell_exec(["pytest", "-q"], context=approved_agent_context(), runner=runner, guard=guard)

    assert runner.called is False
    assert guard.requests[-1].command == ("pytest", "-q")


def test_write_file_checks_pre_tool_guard_before_write(tmp_path):
    guard = DenyGuard()
    target = tmp_path / "blocked.txt"

    with pytest.raises(MutationForbidden, match="blocked by test guard"):
        write_file(target, "blocked", context=approved_agent_context(), guard=guard)

    assert not target.exists()
    assert guard.requests[-1].target_path == str(target)
