from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from optimus.runtime.modes import ExecutionMode, GenerationScope


class ToolSurface(StrEnum):
    SHELL = "shell"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    SHADOW_APPLY = "shadow_apply"
    WEB = "web"
    MCP = "mcp"


class PermissionVerdict(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    HOLD = "HOLD"


class PermissionLayer(StrEnum):
    MODE = "mode"
    USER_DENY = "user_deny"
    PROJECT_ALLOW = "project_allow"
    IMPACT = "impact"
    CLASSIFIER = "classifier"


class ImpactClass(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


BorderlineClassifier = Callable[["PermissionRequest"], tuple[PermissionVerdict, str]]


@dataclass(frozen=True)
class PermissionRequest:
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
    network_host: str | None = None
    metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class PermissionDecision:
    verdict: PermissionVerdict
    layer: PermissionLayer
    rule_id: str
    reason: str
    impact_class: ImpactClass
    requires_human_approval: bool = False

    @property
    def allowed(self) -> bool:
        return self.verdict is PermissionVerdict.ALLOW


class PermissionPolicy:
    def __init__(self, *, borderline_classifier: BorderlineClassifier | None = None) -> None:
        self._borderline_classifier = borderline_classifier

    def decide(self, request: PermissionRequest) -> PermissionDecision:
        mode_decision = _mode_decision(request)
        if mode_decision is not None:
            return mode_decision

        deny_decision = _user_deny_decision(request)
        if deny_decision is not None:
            return deny_decision

        impact = classify_impact(request)
        if _requires_human_hold(request, impact):
            return PermissionDecision(
                verdict=PermissionVerdict.HOLD,
                layer=PermissionLayer.IMPACT,
                rule_id="impact.high.requires_approval",
                reason="high impact or first-time tool requires human approval",
                impact_class=impact,
                requires_human_approval=True,
            )

        allow_decision = _project_allow_decision(request, impact)
        if allow_decision is not None:
            return allow_decision

        if self._borderline_classifier is None:
            return PermissionDecision(
                verdict=PermissionVerdict.HOLD,
                layer=PermissionLayer.CLASSIFIER,
                rule_id="classifier.not_configured",
                reason="borderline call requires human approval",
                impact_class=impact,
                requires_human_approval=True,
            )

        verdict, rule_id = self._borderline_classifier(request)
        if verdict is PermissionVerdict.DENY:
            return PermissionDecision(verdict, PermissionLayer.CLASSIFIER, rule_id, "classifier denied", impact)
        if verdict is PermissionVerdict.ALLOW and request.approval_granted:
            return PermissionDecision(verdict, PermissionLayer.CLASSIFIER, rule_id, "classifier allowed", impact)
        return PermissionDecision(
            verdict=PermissionVerdict.HOLD,
            layer=PermissionLayer.CLASSIFIER,
            rule_id=rule_id,
            reason="classifier did not produce an approved allow",
            impact_class=impact,
            requires_human_approval=True,
        )


def classify_impact(request: PermissionRequest) -> ImpactClass:
    if request.first_time_tool:
        return ImpactClass.HIGH
    if request.generation_scope is GenerationScope.MULTI_FILE_CHANGESET:
        return ImpactClass.HIGH
    if request.generation_scope is GenerationScope.FILE_MUTATION:
        return ImpactClass.HIGH
    if request.tool_surface in {ToolSurface.FILE_WRITE, ToolSurface.SHADOW_APPLY, ToolSurface.WEB, ToolSurface.MCP}:
        return ImpactClass.MEDIUM
    return ImpactClass.LOW


def _mode_decision(request: PermissionRequest) -> PermissionDecision | None:
    if request.execution_mode in {ExecutionMode.PLAN, ExecutionMode.CHAT}:
        if request.tool_surface is ToolSurface.SHELL:
            return _deny("mode.plan_chat.no_shell", "Plan/Chat mode cannot execute shell commands", PermissionLayer.MODE)
        if request.tool_surface in {ToolSurface.FILE_WRITE, ToolSurface.SHADOW_APPLY, ToolSurface.WEB, ToolSurface.MCP}:
            return _deny("mode.plan_chat.no_side_effects", "Plan/Chat mode cannot perform side effects", PermissionLayer.MODE)
        if request.tool_surface is ToolSurface.FILE_READ:
            return None
    if request.execution_mode is not ExecutionMode.AGENT:
        return _deny("mode.unknown", f"unknown execution mode: {request.execution_mode}", PermissionLayer.MODE)
    return None


def _user_deny_decision(request: PermissionRequest) -> PermissionDecision | None:
    text = " ".join((*request.command, request.action)).lower()
    if _is_force_push_to_protected_branch(request.command, text):
        return _deny("deny.git.force_push_main", "force-push to main is denied", PermissionLayer.USER_DENY)
    if request.target_path and _looks_like_secret_path(request.target_path):
        return _deny("deny.path.secret", "secret or credential path access is denied", PermissionLayer.USER_DENY)
    if any(token in text for token in ("chmod 777", "icacls everyone:f", "set-acl")):
        return _deny("deny.permissions.world_writable", "broad permission changes are denied", PermissionLayer.USER_DENY)
    return None


def _is_force_push_to_protected_branch(command: tuple[str, ...], text: str) -> bool:
    tokens = tuple(token.lower() for token in command)
    if len(tokens) >= 2 and tokens[0] == "git" and tokens[1] == "push":
        has_force_flag = any(token == "-f" or token.startswith("--force") for token in tokens)
        has_plus_refspec = any(token.startswith("+") and _mentions_protected_ref(token) for token in tokens)
        has_protected_ref = any(_mentions_protected_ref(token) for token in tokens)
        return has_plus_refspec or (has_force_flag and has_protected_ref)
    return "git push" in text and (
        (" --force" in text or " --force-with-lease" in text or " -f" in text)
        and (" main" in f" {text}" or " master" in f" {text}" or ":main" in text or ":master" in text)
        or "+main" in text
        or "+master" in text
        or "+head:main" in text
        or "+head:master" in text
    )


def _mentions_protected_ref(token: str) -> bool:
    normalized = token.removeprefix("+")
    return normalized in {"main", "master", "refs/heads/main", "refs/heads/master"} or normalized.endswith(
        (":main", ":master", ":refs/heads/main", ":refs/heads/master")
    )


def _project_allow_decision(request: PermissionRequest, impact: ImpactClass) -> PermissionDecision | None:
    if request.tool_surface is ToolSurface.SHELL and request.command:
        command = request.command
        if command[0] == "pytest":
            return PermissionDecision(PermissionVerdict.ALLOW, PermissionLayer.PROJECT_ALLOW, "allow.shell.pytest", "pytest is project-allowed", impact)
        if command[:2] == ("git", "status") or command[:2] == ("git", "diff") or command[:2] == ("git", "log") or command[:2] == ("git", "show"):
            return PermissionDecision(PermissionVerdict.ALLOW, PermissionLayer.PROJECT_ALLOW, "allow.shell.git_readonly", "read-only git inspection is project-allowed", impact)
        if request.approval_granted:
            return PermissionDecision(
                PermissionVerdict.ALLOW,
                PermissionLayer.PROJECT_ALLOW,
                "allow.shell.agent_pre_tool_validation",
                "approved shell command may proceed to deterministic pre-tool validation",
                impact,
            )
    if request.tool_surface is ToolSurface.FILE_READ:
        return PermissionDecision(PermissionVerdict.ALLOW, PermissionLayer.PROJECT_ALLOW, "allow.file_read.pre_tool_validation", "file read may proceed to deterministic path validation", impact)
    if request.tool_surface is ToolSurface.FILE_WRITE and request.approval_granted:
        return PermissionDecision(PermissionVerdict.ALLOW, PermissionLayer.PROJECT_ALLOW, "allow.file_write.approved_pre_tool_validation", "approved file write may proceed to deterministic path validation", impact)
    if request.tool_surface is ToolSurface.SHADOW_APPLY and request.approval_granted:
        return PermissionDecision(PermissionVerdict.ALLOW, PermissionLayer.PROJECT_ALLOW, "allow.shadow_apply.approved_pre_tool_validation", "approved shadow apply may proceed to deterministic pre-tool validation", impact)
    if request.tool_surface is ToolSurface.WEB and request.approval_granted:
        return PermissionDecision(PermissionVerdict.ALLOW, PermissionLayer.PROJECT_ALLOW, "allow.web.approved_pre_tool_validation", "approved web call may proceed to deterministic pre-tool validation", impact)
    if request.tool_surface is ToolSurface.MCP and request.approval_granted:
        return PermissionDecision(PermissionVerdict.ALLOW, PermissionLayer.PROJECT_ALLOW, "allow.mcp.approved_pre_tool_validation", "approved MCP call may proceed to deterministic pre-tool validation", impact)
    return None


def _requires_human_hold(request: PermissionRequest, impact: ImpactClass) -> bool:
    return impact is ImpactClass.HIGH and not request.approval_granted


def _looks_like_secret_path(path: str) -> bool:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix().lower()
    secret_names = (".env", ".pypirc", ".netrc", "id_rsa", "id_ed25519", "credentials", "token", "secrets")
    return any(part in secret_names or part.endswith(".pem") or part.endswith(".key") for part in normalized.split("/"))


def _deny(rule_id: str, reason: str, layer: PermissionLayer) -> PermissionDecision:
    return PermissionDecision(
        verdict=PermissionVerdict.DENY,
        layer=layer,
        rule_id=rule_id,
        reason=reason,
        impact_class=ImpactClass.HIGH if layer is PermissionLayer.USER_DENY else ImpactClass.LOW,
    )
