
import subprocess

import pytest

from optimus.agent.tools import AgentToolbox
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


def approved_context() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-1",
    )


def test_toolbox_reads_workspace_file_and_records_tool_call(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    toolbox = AgentToolbox.for_workspace(workspace_root=tmp_path, context=approved_context(), run_id="run-1")

    text, call = toolbox.read_file(target)

    assert "return 1" in text
    assert call.tool_name == "file_reader"
    assert call.authorization_outcome == "ALLOW"


def test_toolbox_blocks_secret_file_write(tmp_path):
    toolbox = AgentToolbox.for_workspace(workspace_root=tmp_path, context=approved_context(), run_id="run-1")

    with pytest.raises(PermissionError, match="secret or credential path access is denied"):
        toolbox.write_file(tmp_path / ".env", "OPENAI_API_KEY=local")


def test_toolbox_runs_pytest_through_guard(tmp_path):
    calls = []
    toolbox = AgentToolbox.for_workspace(
        workspace_root=tmp_path,
        context=approved_context(),
        run_id="run-1",
        shell_runner=lambda command: calls.append(command) or subprocess.CompletedProcess(command, 0, "1 passed", ""),
    )

    call = toolbox.run_tests(("pytest", "tests/unit/agent", "-q"))

    assert calls == [["pytest", "tests/unit/agent", "-q"]]
    assert call.tool_name == "test_runner"
    assert call.authorization_outcome == "ALLOW"
