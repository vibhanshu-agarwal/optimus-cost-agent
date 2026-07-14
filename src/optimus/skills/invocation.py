from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult, PreToolVerdict
from optimus.runtime.modes import ExecutionMode, GenerationScope
from optimus.skills.models import SkillManifest, SkillTrustLevel
from optimus.telemetry.events import TelemetryEvent


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
    """
    SkillInvocationPolicy handles the process of authorizing and managing skill
    invocations, ensuring compliance with defined trust policies and operational
    constraints.

    The class is responsible for validating requested tools against skill
    manifests, invoking pre-tool guards, and emitting telemetry events for skill
    invocation decisions. It provides mechanisms to determine if a skill is
    authorized to perform certain actions based on its manifest's trust
    declaration and runtime parameters.

    :ivar trust_policy: Defines how trust is evaluated for each skill invocation.
    :type trust_policy: SkillTrustPolicy | None
    :ivar event_sink: Function to emit telemetry events for skill invocations.
    :type event_sink: Callable[[TelemetryEvent], None] | None
    :ivar now: Callable to get the current datetime, allowing for injection
        of custom time sources for testing and other purposes.
    :type now: Callable[[], datetime] | None
    """
    def __init__(
        self,
        *,
        trust_policy: SkillTrustPolicy | None = None,
        event_sink: Callable[[TelemetryEvent], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._trust_policy = trust_policy or SkillTrustPolicy()
        self._event_sink = event_sink
        self._now = now or (lambda: datetime.now(tz=UTC))

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
        self._emit(
            manifest=manifest,
            run_id=run_id,
            session_id=session_id,
            requested_tool=requested_tool,
            decision=decision,
        )
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

    def _emit(
        self,
        *,
        manifest: SkillManifest,
        run_id: str,
        session_id: str | None,
        requested_tool: ToolSurface,
        decision: SkillInvocationDecision,
    ) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.skill_invocation(
                run_id=run_id,
                session_id=session_id,
                request_id=f"{run_id}:skill-invocation:{manifest.name}",
                occurred_at=self._now(),
                skill_name=manifest.name,
                manifest_hash=manifest.manifest_hash,
                verdict=decision.verdict.value,
                rule_id=decision.rule_id,
                requested_tool=requested_tool.value,
            )
        )
