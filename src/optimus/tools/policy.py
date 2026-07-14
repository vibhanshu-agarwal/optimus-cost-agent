from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from optimus.net.https import https_hostname
from optimus.runtime.modes import ExecutionMode


class ToolClass(StrEnum):
    LOCAL_REPO_READ = "local_repo_read"
    VALIDATION_GATE = "validation_gate"
    WEB_SEARCH = "web_search"
    WEB_EXTRACT = "web_extract"


class EvidenceReasonCode(StrEnum):
    NONE = "NONE"
    USER_REQUESTED = "USER_REQUESTED"
    CURRENT_FACT = "CURRENT_FACT"
    API_DOCS_OUTDATED = "API_DOCS_OUTDATED"
    PACKAGE_VERSION = "PACKAGE_VERSION"
    SECURITY_ADVISORY = "SECURITY_ADVISORY"


class ToolPolicySignal(StrEnum):
    LOCAL_CODE_CHANGE = "LOCAL_CODE_CHANGE"
    USER_REQUESTED_EXTERNAL_FACT = "USER_REQUESTED_EXTERNAL_FACT"
    CURRENT_OR_LATEST_FACT = "CURRENT_OR_LATEST_FACT"
    API_OR_FRAMEWORK_FACT_NOT_IN_REPO = "API_OR_FRAMEWORK_FACT_NOT_IN_REPO"
    DEPENDENCY_VERSION_CHECK = "DEPENDENCY_VERSION_CHECK"
    SECURITY_OR_CVE_CHECK = "SECURITY_OR_CVE_CHECK"
    APPROVED_SEARCH_RESULT_PROVENANCE = "APPROVED_SEARCH_RESULT_PROVENANCE"


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ToolInvocationRequest:
    run_id: str
    tool_class: ToolClass
    execution_mode: ExecutionMode
    policy_signal: ToolPolicySignal
    reason: EvidenceReasonCode = EvidenceReasonCode.NONE
    allowed_domains: tuple[str, ...] = ()
    target_url: str | None = None
    prior_search_result_urls: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ToolInvocationDecision:
    decision: PolicyDecision
    reason: str
    tool_class: ToolClass
    policy_signal: ToolPolicySignal
    reason_code: EvidenceReasonCode

    @property
    def allowed(self) -> bool:
        return self.decision is PolicyDecision.ALLOW


class ToolInvocationPolicy:
    """
    Handles the authorization and policy enforcement for invoking tools in various execution modes.

    This class determines whether specific tools can be used based on defined rules and conditions,
    adhering to security policies, domain restrictions, and execution modes. It supports multiple
    tool classes and provides specialized handling for tools like web search and web data extraction.
    Tools' invocation is authorized or rejected based on different signals and contexts.

    :ivar SUPPORTED_EXECUTION_MODES: Set of execution modes that are supported for invoking tools.
    :type SUPPORTED_EXECUTION_MODES: frozenset

    :ivar WEB_SEARCH_TRIGGERS: Set of conditions and reason code pairs required to authorize a web search tool.
    :type WEB_SEARCH_TRIGGERS: frozenset
    """
    SUPPORTED_EXECUTION_MODES = frozenset(
        {ExecutionMode.PLAN, ExecutionMode.CHAT, ExecutionMode.AGENT}
    )

    WEB_SEARCH_TRIGGERS = frozenset(
        {
            (ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT, EvidenceReasonCode.USER_REQUESTED),
            (ToolPolicySignal.CURRENT_OR_LATEST_FACT, EvidenceReasonCode.CURRENT_FACT),
            (ToolPolicySignal.API_OR_FRAMEWORK_FACT_NOT_IN_REPO, EvidenceReasonCode.API_DOCS_OUTDATED),
            (ToolPolicySignal.DEPENDENCY_VERSION_CHECK, EvidenceReasonCode.PACKAGE_VERSION),
            (ToolPolicySignal.SECURITY_OR_CVE_CHECK, EvidenceReasonCode.SECURITY_ADVISORY),
        }
    )

    def authorize(self, request: ToolInvocationRequest) -> ToolInvocationDecision:
        if request.execution_mode not in self.SUPPORTED_EXECUTION_MODES:
            return _reject(request, "unknown execution mode")
        if request.tool_class in {ToolClass.LOCAL_REPO_READ, ToolClass.VALIDATION_GATE}:
            return _allow(request, "local deterministic tool allowed")
        if request.tool_class is ToolClass.WEB_SEARCH:
            return self._authorize_web_search(request)
        if request.tool_class is ToolClass.WEB_EXTRACT:
            return self._authorize_web_extract(request)
        return _reject(request, f"unsupported tool class: {request.tool_class}")

    def _authorize_web_search(self, request: ToolInvocationRequest) -> ToolInvocationDecision:
        if (request.policy_signal, request.reason) not in self.WEB_SEARCH_TRIGGERS:
            return _reject(request, "no policy trigger matched")
        if not request.allowed_domains:
            return _reject(request, "allowed_domains required for web search")
        return _allow(request, "policy trigger matched")

    def _authorize_web_extract(self, request: ToolInvocationRequest) -> ToolInvocationDecision:
        if (
            request.policy_signal != ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE
            or request.reason == EvidenceReasonCode.NONE
        ):
            return _reject(request, "web extract requires approved search-result provenance")
        if request.target_url is None:
            return _reject(request, "target_url required for web extract")
        # Guards direct registry/policy callers; service-layer domain policy checks HTTPS first.
        if https_hostname(request.target_url) is None:
            return _reject(request, "https URL required for web extract")
        if request.target_url not in request.prior_search_result_urls:
            return _reject(request, "URL not in approved search-result set")
        return _allow(request, "approved search result provenance matched")


def _allow(request: ToolInvocationRequest, reason: str) -> ToolInvocationDecision:
    return ToolInvocationDecision(
        decision=PolicyDecision.ALLOW,
        reason=reason,
        tool_class=request.tool_class,
        policy_signal=request.policy_signal,
        reason_code=request.reason,
    )


def _reject(request: ToolInvocationRequest, reason: str) -> ToolInvocationDecision:
    return ToolInvocationDecision(
        decision=PolicyDecision.REJECT,
        reason=reason,
        tool_class=request.tool_class,
        policy_signal=request.policy_signal,
        reason_code=request.reason,
    )

