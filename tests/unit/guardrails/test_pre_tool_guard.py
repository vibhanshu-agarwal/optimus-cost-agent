from pathlib import Path

from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.guardrails.permissions import ToolSurface
from optimus.runtime.modes import ExecutionMode, GenerationScope


def test_pre_tool_guard_blocks_shell_command_and_records_audit(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="rm -rf src",
            command=("rm", "-rf", str(tmp_path / "src")),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert result.verdict is PreToolVerdict.BLOCK
    assert result.rule_id == "shell.destructive.rm_rf"
    assert guard.audit_events()[-1].verdict == "BLOCK"
    assert guard.audit_events()[-1].sanitized_subject == "rm -rf <workspace>/src"


def test_pre_tool_guard_holds_high_impact_without_approval(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.FILE_WRITE,
            action="write",
            target_path=str(tmp_path / "src" / "optimus" / "x.py"),
            generation_scope=GenerationScope.MULTI_FILE_CHANGESET,
            approval_granted=False,
        )
    )

    assert result.verdict is PreToolVerdict.HOLD
    assert result.requires_human_approval is True


def test_pre_tool_guard_allows_safe_pytest(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="pytest tests/unit -q",
            command=("pytest", "tests/unit", "-q"),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert result.verdict is PreToolVerdict.ALLOW


def test_pre_tool_guard_holds_first_time_tool(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="pytest tests/unit -q",
            command=("pytest", "tests/unit", "-q"),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=False,
            first_time_tool=True,
        )
    )

    assert result.verdict is PreToolVerdict.HOLD
    assert result.requires_human_approval is True


def test_pre_tool_guard_holds_mcp_until_trust_registry(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.MCP,
            action="call_server_tool",
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert result.verdict is PreToolVerdict.HOLD
    assert result.rule_id == "mcp.requires_plan6_trust_registry"


def test_pre_tool_guard_holds_unexpected_web_target(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.WEB,
            action="web_extract:https://example.com/page",
            target_path="https://example.com/page",
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert result.verdict is PreToolVerdict.HOLD
    assert result.rule_id == "network.unexpected_egress"


def test_pre_tool_guard_sanitizes_workspace_root_for_file_targets(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))
    target = tmp_path / "src" / "optimus" / "guardrails" / "x.py"

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.FILE_WRITE,
            action="write",
            target_path=str(target),
            generation_scope=GenerationScope.FILE_MUTATION,
            approval_granted=True,
        )
    )

    assert result.verdict is PreToolVerdict.ALLOW
    assert guard.audit_events()[-1].sanitized_subject == "<workspace>/src/optimus/guardrails/x.py"


def test_pre_tool_guard_redacts_bearer_token_from_audit_subject(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="curl",
            command=("curl", "-H", "Authorization: Bearer secret-token-value", "https://gateway.optimus.ai/status"),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert result.verdict is PreToolVerdict.HOLD
    subject = guard.audit_events()[-1].sanitized_subject
    assert "secret-token-value" not in subject
    assert "Authorization: Bearer **********" in subject


def test_pre_tool_guard_redacts_url_userinfo_from_audit_subject(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))

    guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="curl",
            command=("curl", "https://user:secret-pass@gateway.optimus.ai/status"),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    subject = guard.audit_events()[-1].sanitized_subject
    assert "secret-pass" not in subject
    assert "https://**********@gateway.optimus.ai/status" in subject
