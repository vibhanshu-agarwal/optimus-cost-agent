"""Pre-tool permission and safety guardrails."""

from optimus.guardrails.audit import InMemoryAuditSink, ToolInvocationAuditEvent
from optimus.guardrails.permissions import (
    ImpactClass,
    PermissionDecision,
    PermissionLayer,
    PermissionPolicy,
    PermissionRequest,
    PermissionVerdict,
    ToolSurface,
    classify_impact,
)
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult, PreToolVerdict
from optimus.guardrails.prompt_injection import (
    ConfigTrustScanner,
    TrustScanFinding,
    TrustScanResult,
    TrustScanSubject,
    TrustScanVerdict,
)

__all__ = [
    "ImpactClass",
    "InMemoryAuditSink",
    "PermissionDecision",
    "PermissionLayer",
    "PermissionPolicy",
    "PermissionRequest",
    "PermissionVerdict",
    "PreToolGuard",
    "PreToolRequest",
    "PreToolResult",
    "PreToolVerdict",
    "ToolInvocationAuditEvent",
    "ToolSurface",
    "classify_impact",
    "ConfigTrustScanner",
    "TrustScanFinding",
    "TrustScanResult",
    "TrustScanSubject",
    "TrustScanVerdict",
]
