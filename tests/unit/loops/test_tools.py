import pytest

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolVerdict
from optimus.loops.tools import GuardedLoopToolExecutor, LoopToolBlocked
from optimus.runtime.modes import ExecutionMode, GenerationScope


def executor(tmp_path) -> GuardedLoopToolExecutor:
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))
    return GuardedLoopToolExecutor(guard=guard)


def test_loop_tool_executor_blocks_plan_mode_shell(tmp_path):
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked) as exc:
        tools.preflight(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.PLAN,
            tool_surface=ToolSurface.SHELL,
            action="pytest tests/unit -q",
            command=("pytest", "tests/unit", "-q"),
            approval_granted=True,
        )

    assert exc.value.result.verdict is PreToolVerdict.BLOCK
    assert exc.value.result.rule_id == "mode.plan_chat.no_shell"


def test_loop_tool_executor_allows_agent_mode_safe_pytest(tmp_path):
    tools = executor(tmp_path)

    result = tools.preflight(
        run_id="run-1",
        session_id="session-1",
        execution_mode=ExecutionMode.AGENT,
        tool_surface=ToolSurface.SHELL,
        action="pytest tests/unit -q",
        command=("pytest", "tests/unit", "-q"),
        approval_granted=True,
    )

    assert result.verdict is PreToolVerdict.ALLOW


def test_loop_tool_executor_preserves_multi_file_approval_hold(tmp_path):
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked) as exc:
        tools.preflight(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.FILE_WRITE,
            action="write",
            target_path=str(tmp_path / "src" / "optimus" / "x.py"),
            generation_scope=GenerationScope.MULTI_FILE_CHANGESET,
            approval_granted=False,
        )

    assert exc.value.result.verdict is PreToolVerdict.HOLD
    assert exc.value.result.requires_human_approval is True
