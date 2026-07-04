from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from optimus.guardrails.audit import InMemoryAuditSink, ToolInvocationAuditEvent
from optimus.guardrails.command_safety import CommandSafetyValidator
from optimus.guardrails.network_safety import NetworkSafetyValidator
from optimus.guardrails.path_safety import PathSafetyValidator
from optimus.guardrails.permissions import PermissionPolicy, PermissionRequest, PermissionVerdict, ToolSurface
from optimus.guardrails.validation import ValidationVerdict
from optimus.runtime.modes import ExecutionMode, GenerationScope


class PreToolVerdict(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    HOLD = "HOLD"


@dataclass(frozen=True)
class PreToolRequest:
    run_id: str
    session_id: str | None
    execution_mode: ExecutionMode
    tool_surface: ToolSurface
    action: str
    command: tuple[str, ...] = ()
    target_path: str | None = None
    generation_scope: GenerationScope = GenerationScope.INLINE_SNIPPET
    approval_granted: bool = False
    first_time_tool: bool = False
    approver: str | None = None


@dataclass(frozen=True)
class PreToolResult:
    verdict: PreToolVerdict
    rule_id: str
    reason: str
    requires_human_approval: bool = False

    @property
    def allowed(self) -> bool:
        return self.verdict is PreToolVerdict.ALLOW


class PreToolGuard:
    def __init__(
        self,
        *,
        permission_policy: PermissionPolicy,
        command_validator: CommandSafetyValidator,
        path_validator: PathSafetyValidator,
        network_validator: NetworkSafetyValidator,
        workspace_root: str | Path | None = None,
        audit_sink: InMemoryAuditSink | None = None,
    ) -> None:
        self._permission_policy = permission_policy
        self._command_validator = command_validator
        self._path_validator = path_validator
        self._network_validator = network_validator
        self._workspace_root = Path(workspace_root).resolve() if workspace_root is not None else None
        self._audit_sink = audit_sink or InMemoryAuditSink()

    @classmethod
    def for_workspace(cls, *, workspace_root: str | Path, allowed_network_hosts: tuple[str, ...]) -> "PreToolGuard":
        return cls(
            permission_policy=PermissionPolicy(),
            command_validator=CommandSafetyValidator(workspace_root=workspace_root, allowed_network_hosts=allowed_network_hosts),
            path_validator=PathSafetyValidator(workspace_root=workspace_root),
            network_validator=NetworkSafetyValidator(allowed_hosts=allowed_network_hosts),
            workspace_root=workspace_root,
        )

    def check(self, request: PreToolRequest) -> PreToolResult:
        permission = self._permission_policy.decide(
            PermissionRequest(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=request.execution_mode,
                tool_surface=request.tool_surface,
                action=request.action,
                command=request.command,
                target_path=request.target_path,
                generation_scope=request.generation_scope,
                approval_granted=request.approval_granted,
                first_time_tool=request.first_time_tool,
            )
        )
        if permission.verdict is PermissionVerdict.DENY:
            result = PreToolResult(PreToolVerdict.BLOCK, permission.rule_id, permission.reason)
            self._audit(request, result, permission.layer.value, (permission.rule_id,))
            return result
        if permission.verdict is PermissionVerdict.HOLD:
            result = PreToolResult(PreToolVerdict.HOLD, permission.rule_id, permission.reason, True)
            self._audit(request, result, permission.layer.value, (permission.rule_id,))
            return result

        validation_result = self._validate_surface(request)
        if validation_result is not None:
            self._audit(request, validation_result, "pre_tool", (validation_result.rule_id,))
            return validation_result

        result = PreToolResult(PreToolVerdict.ALLOW, permission.rule_id, permission.reason)
        self._audit(request, result, permission.layer.value, ())
        return result

    def audit_events(self) -> tuple[ToolInvocationAuditEvent, ...]:
        return self._audit_sink.events()

    def _validate_surface(self, request: PreToolRequest) -> PreToolResult | None:
        if request.tool_surface is ToolSurface.SHELL:
            validation = self._command_validator.validate(request.command)
            return _pre_tool_result(validation.verdict, validation.rule_id, validation.reason)
        if request.tool_surface is ToolSurface.FILE_WRITE and request.target_path:
            validation = self._path_validator.validate_write(request.target_path)
            return _pre_tool_result(validation.verdict, validation.rule_id, validation.reason)
        if request.tool_surface is ToolSurface.FILE_READ and request.target_path:
            validation = self._path_validator.validate_read(request.target_path)
            return _pre_tool_result(validation.verdict, validation.rule_id, validation.reason)
        if request.tool_surface is ToolSurface.WEB and request.target_path:
            validation = self._network_validator.validate_url(request.target_path)
            return _pre_tool_result(validation.verdict, validation.rule_id, validation.reason)
        if request.tool_surface is ToolSurface.MCP:
            return PreToolResult(
                PreToolVerdict.HOLD,
                "mcp.requires_plan6_trust_registry",
                "MCP calls require the Plan 6 trust registry",
                True,
            )
        return None

    def _audit(self, request: PreToolRequest, result: PreToolResult, layer: str, failed_checks: tuple[str, ...]) -> None:
        self._audit_sink.append(
            ToolInvocationAuditEvent(
                run_id=request.run_id,
                session_id=request.session_id,
                tool_surface=request.tool_surface.value,
                verdict=result.verdict.value,
                layer=layer,
                rule_id=result.rule_id,
                reason=result.reason,
                failed_checks=failed_checks,
                sanitized_subject=_sanitize_subject(request, workspace_root=self._workspace_root),
                requires_human_approval=result.requires_human_approval,
                approver=request.approver,
            )
        )


def _pre_tool_result(verdict: ValidationVerdict, rule_id: str, reason: str) -> PreToolResult | None:
    if verdict is ValidationVerdict.ALLOW:
        return None
    if verdict is ValidationVerdict.BLOCK:
        return PreToolResult(PreToolVerdict.BLOCK, rule_id, reason)
    return PreToolResult(PreToolVerdict.HOLD, rule_id, reason, True)


def _sanitize_subject(request: PreToolRequest, *, workspace_root: Path | None) -> str:
    subject = " ".join(request.command) if request.command else request.target_path or request.action
    if subject is None:
        return ""
    subject = subject.replace("\\", "/")
    if workspace_root is not None:
        workspace_text = workspace_root.as_posix().rstrip("/")
        subject = subject.replace(workspace_text, "<workspace>")
    return _redact_secret_values(subject)


def _redact_secret_values(subject: str) -> str:
    subject = re.sub(r"(?i)(https?://)[^/\s:@]+:[^@\s/]+@", r"\1**********@", subject)
    redactions = (
        re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
        re.compile(r"(?i)(bearer\s+)[^\s]+"),
        re.compile(r"(?i)(--password(?:=|\s+))[^\s]+"),
        re.compile(r"(?i)(api[_-]?key(?:=|\s+))[^\s]+"),
        re.compile(r"(?i)(token(?:=|\s+))[^\s]+"),
    )
    for pattern in redactions:
        subject = pattern.sub(r"\1**********", subject)
    return subject
