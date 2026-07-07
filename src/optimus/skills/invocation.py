from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult, PreToolVerdict
from optimus.runtime.modes import ExecutionMode, GenerationScope
from optimus.skills.models import SkillManifest, SkillTrustLevel


class SkillInvocationVerdict(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    HOLD = "HOLD"


class SkillInvocationDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: SkillInvocationVerdict
    rule_id: str
    reason: str
    requires_human_approval: bool = False

    @property
    def allowed(self) -> bool:
        return self.verdict is SkillInvocationVerdict.ALLOW


class SkillTrustPolicy:
    def check(self, *, manifest: SkillManifest, execution_mode: ExecutionMode) -> SkillInvocationDecision:
        if manifest.trust_level is SkillTrustLevel.TRUSTED:
            return SkillInvocationDecision(
                verdict=SkillInvocationVerdict.ALLOW,
                rule_id="skill.trusted",
                reason="trusted skill may be considered for invocation",
            )
        if execution_mode is ExecutionMode.AGENT:
            return SkillInvocationDecision(
                verdict=SkillInvocationVerdict.BLOCK,
                rule_id="skill.draft_blocked_agent_mode",
                reason="draft skills cannot load in Agent mode",
            )
        return SkillInvocationDecision(
            verdict=SkillInvocationVerdict.HOLD,
            rule_id="skill.draft_requires_review",
            reason="draft skill requires review before use",
            requires_human_approval=True,
        )


class SkillInvocationPolicy:
    def __init__(self, *, trust_policy: SkillTrustPolicy | None = None) -> None:
        self._trust_policy = trust_policy or SkillTrustPolicy()

    def authorize_tool(
        self,
        *,
        manifest: SkillManifest,
        requested_tool: ToolSurface,
        execution_mode: ExecutionMode,
    ) -> SkillInvocationDecision:
        trust = self._trust_policy.check(manifest=manifest, execution_mode=execution_mode)
        if not trust.allowed:
            return trust
        if requested_tool.value not in manifest.allowed_tools:
            return SkillInvocationDecision(
                verdict=SkillInvocationVerdict.BLOCK,
                rule_id="skill.tool_not_declared",
                reason="skill did not declare the requested tool surface",
            )
        return SkillInvocationDecision(
            verdict=SkillInvocationVerdict.ALLOW,
            rule_id="skill.declared_tool_allowed",
            reason="skill declared the requested tool surface; pre-tool guard must still authorize it",
        )

    def preflight_with_guard(
        self,
        *,
        guard: PreToolGuard,
        manifest: SkillManifest,
        run_id: str,
        session_id: str | None,
        execution_mode: ExecutionMode,
        requested_tool: ToolSurface,
        action: str,
        command: tuple[str, ...] = (),
        target_path: str | None = None,
        generation_scope: GenerationScope = GenerationScope.INLINE_SNIPPET,
        approval_granted: bool = False,
    ) -> PreToolResult:
        decision = self.authorize_tool(manifest=manifest, requested_tool=requested_tool, execution_mode=execution_mode)
        if not decision.allowed:
            return PreToolResult(
                verdict=PreToolVerdict.BLOCK if decision.verdict is SkillInvocationVerdict.BLOCK else PreToolVerdict.HOLD,
                rule_id=decision.rule_id,
                reason=decision.reason,
                requires_human_approval=decision.requires_human_approval,
            )
        return guard.check(
            PreToolRequest(
                run_id=run_id,
                session_id=session_id,
                execution_mode=execution_mode,
                tool_surface=requested_tool,
                action=action,
                command=command,
                target_path=target_path,
                generation_scope=generation_scope,
                approval_granted=approval_granted,
            )
        )
