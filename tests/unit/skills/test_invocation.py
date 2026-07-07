from optimus.guardrails.permissions import ToolSurface
from optimus.runtime.modes import ExecutionMode
from optimus.skills.invocation import SkillInvocationPolicy, SkillInvocationVerdict, SkillTrustPolicy
from optimus.skills.models import SkillManifest, SkillTrustLevel


def manifest(*, trust_level: SkillTrustLevel, allowed_tools=("shell",)) -> SkillManifest:
    return SkillManifest(
        name="pytest-debugging",
        description="Debug pytest failures",
        globs=("tests/**/*.py",),
        allowed_tools=allowed_tools,
        owner="maintainer",
        version="1.0.0",
        trust_level=trust_level,
        source_path="skills/pytest/SKILL.md",
        manifest_hash="a" * 64,
        content_hash="a" * 64,
    )


def test_draft_skill_is_blocked_in_agent_mode():
    decision = SkillTrustPolicy().check(manifest=manifest(trust_level=SkillTrustLevel.DRAFT), execution_mode=ExecutionMode.AGENT)

    assert decision.verdict is SkillInvocationVerdict.BLOCK
    assert decision.rule_id == "skill.draft_blocked_agent_mode"


def test_draft_skill_can_be_suggested_in_plan_mode():
    decision = SkillTrustPolicy().check(manifest=manifest(trust_level=SkillTrustLevel.DRAFT), execution_mode=ExecutionMode.PLAN)

    assert decision.verdict is SkillInvocationVerdict.HOLD
    assert decision.requires_human_approval is True


def test_skill_invocation_policy_blocks_tool_not_declared_by_skill():
    decision = SkillInvocationPolicy().authorize_tool(
        manifest=manifest(trust_level=SkillTrustLevel.TRUSTED, allowed_tools=("file_read",)),
        requested_tool=ToolSurface.SHELL,
        execution_mode=ExecutionMode.AGENT,
    )

    assert decision.verdict is SkillInvocationVerdict.BLOCK
    assert decision.rule_id == "skill.tool_not_declared"


def test_skill_invocation_policy_allows_declared_tool_to_continue_to_pre_tool_guard():
    decision = SkillInvocationPolicy().authorize_tool(
        manifest=manifest(trust_level=SkillTrustLevel.TRUSTED, allowed_tools=("shell",)),
        requested_tool=ToolSurface.SHELL,
        execution_mode=ExecutionMode.AGENT,
    )

    assert decision.verdict is SkillInvocationVerdict.ALLOW
    assert decision.rule_id == "skill.declared_tool_allowed"
