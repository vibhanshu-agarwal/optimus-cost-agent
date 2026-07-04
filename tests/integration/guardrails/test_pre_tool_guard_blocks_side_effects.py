import pytest

from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools.mutation_tools import shell_exec, write_file


class ProbeRunner:
    def __init__(self) -> None:
        self.called = False

    def __call__(self, command):
        self.called = True
        return {"command": command}


def approved_context() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-guardrails",
    )


def test_blocked_shell_command_never_reaches_runner(tmp_path):
    runner = ProbeRunner()
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    with pytest.raises(MutationForbidden, match="recursive force delete denied"):
        shell_exec(("rm", "-rf", str(tmp_path / "src")), context=approved_context(), runner=runner, guard=guard)

    assert runner.called is False
    assert guard.audit_events()[-1].rule_id == "shell.destructive.rm_rf"


def test_blocked_secret_write_never_creates_file(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))
    target = tmp_path / ".env"

    with pytest.raises(MutationForbidden, match="secret or credential path access is denied"):
        write_file(target, "OPTIMUS_API_KEY=secret", context=approved_context(), guard=guard)

    assert not target.exists()
    assert guard.audit_events()[-1].rule_id == "deny.path.secret"
