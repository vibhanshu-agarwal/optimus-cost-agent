from optimus.guardrails.permissions import (
    ImpactClass,
    PermissionLayer,
    PermissionPolicy,
    PermissionRequest,
    PermissionVerdict,
    ToolSurface,
)
from optimus.runtime.modes import ExecutionMode, GenerationScope


def test_user_deny_precedes_project_allow_for_read_only_git_force_push():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="git push --force origin main",
            command=("git", "push", "--force", "origin", "main"),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert decision.verdict is PermissionVerdict.DENY
    assert decision.layer is PermissionLayer.USER_DENY
    assert decision.rule_id == "deny.git.force_push_main"


def test_user_deny_catches_short_force_push_to_main():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="git push -f origin main",
            command=("git", "push", "-f", "origin", "main"),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert decision.verdict is PermissionVerdict.DENY
    assert decision.rule_id == "deny.git.force_push_main"


def test_user_deny_catches_plus_refspec_force_push_to_main():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="git push origin +HEAD:main",
            command=("git", "push", "origin", "+HEAD:main"),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert decision.verdict is PermissionVerdict.DENY
    assert decision.rule_id == "deny.git.force_push_main"


def test_user_deny_catches_force_with_lease_value_to_main():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="git push --force-with-lease=main origin HEAD:main",
            command=("git", "push", "--force-with-lease=main", "origin", "HEAD:main"),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert decision.verdict is PermissionVerdict.DENY
    assert decision.rule_id == "deny.git.force_push_main"


def test_plan_mode_short_circuits_shell_mutation_before_allow_rules():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.PLAN,
            tool_surface=ToolSurface.SHELL,
            action="pytest -q",
            command=("pytest", "-q"),
        )
    )

    assert decision.verdict is PermissionVerdict.DENY
    assert decision.layer is PermissionLayer.MODE
    assert decision.rule_id == "mode.plan_chat.no_shell"


def test_low_impact_project_allow_rule_allows_pytest_in_agent_mode():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
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

    assert decision.verdict is PermissionVerdict.ALLOW
    assert decision.layer is PermissionLayer.PROJECT_ALLOW
    assert decision.rule_id == "allow.shell.pytest"


def test_approved_shell_command_reaches_pre_tool_validation():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="rm -rf src",
            command=("rm", "-rf", "src"),
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert decision.verdict is PermissionVerdict.ALLOW
    assert decision.rule_id == "allow.shell.agent_pre_tool_validation"


def test_approved_file_write_reaches_pre_tool_validation():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.FILE_WRITE,
            action="write file",
            target_path="src/optimus/guardrails/permissions.py",
            generation_scope=GenerationScope.FILE_MUTATION,
            approval_granted=True,
        )
    )

    assert decision.verdict is PermissionVerdict.ALLOW
    assert decision.rule_id == "allow.file_write.approved_pre_tool_validation"


def test_approved_mcp_reaches_pre_tool_validation():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.MCP,
            action="call_server_tool",
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=True,
        )
    )

    assert decision.verdict is PermissionVerdict.ALLOW
    assert decision.rule_id == "allow.mcp.approved_pre_tool_validation"


def test_high_impact_file_mutation_holds_for_human_approval():
    policy = PermissionPolicy()

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.FILE_WRITE,
            action="write many files",
            target_path="src/optimus/guardrails/permissions.py",
            generation_scope=GenerationScope.MULTI_FILE_CHANGESET,
            approval_granted=False,
        )
    )

    assert decision.verdict is PermissionVerdict.HOLD
    assert decision.layer is PermissionLayer.IMPACT
    assert decision.impact_class is ImpactClass.HIGH
    assert decision.requires_human_approval is True


def test_classifier_cannot_overturn_user_deny():
    def allow_classifier(request):
        return PermissionVerdict.ALLOW, "classifier.allow"

    policy = PermissionPolicy(borderline_classifier=allow_classifier)

    decision = policy.decide(
        PermissionRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.FILE_READ,
            action="read .env",
            target_path=".env",
            approval_granted=True,
        )
    )

    assert decision.verdict is PermissionVerdict.DENY
    assert decision.layer is PermissionLayer.USER_DENY
    assert decision.rule_id == "deny.path.secret"
