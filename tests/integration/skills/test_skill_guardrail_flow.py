from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from optimus.skills.invocation import SkillInvocationPolicy, SkillInvocationVerdict
from optimus.skills.models import SkillManifest, SkillTrustLevel


def trusted_shell_skill() -> SkillManifest:
    return SkillManifest(
        name="unsafe-shell-example",
        description="Example shell skill",
        globs=(),
        allowed_tools=("shell",),
        owner="maintainer",
        version="1.0.0",
        trust_level=SkillTrustLevel.TRUSTED,
        source_path="skills/shell/SKILL.md",
        manifest_hash="b" * 64,
        content_hash="b" * 64,
    )


def test_skill_cannot_override_user_deny_rules(tmp_path):
    policy = SkillInvocationPolicy()
    skill_decision = policy.authorize_tool(
        manifest=trusted_shell_skill(),
        requested_tool=ToolSurface.SHELL,
        execution_mode=ExecutionMode.AGENT,
    )
    assert skill_decision.verdict is SkillInvocationVerdict.ALLOW

    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    result = policy.preflight_with_guard(
        guard=guard,
        manifest=trusted_shell_skill(),
        run_id="run-1",
        session_id=None,
        execution_mode=ExecutionMode.AGENT,
        requested_tool=ToolSurface.SHELL,
        action="rm -rf src",
        command=("rm", "-rf", "src"),
        approval_granted=True,
    )

    assert result.verdict.name == "BLOCK"
    assert result.rule_id == "shell.destructive.rm_rf"
