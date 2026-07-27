from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import (
    EvidenceReasonCode,
    PolicyDecision,
    ToolClass,
    ToolInvocationPolicy,
    ToolInvocationRequest,
    ToolPolicySignal,
)


def test_web_search_without_trigger_rejects():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode=ExecutionMode.CHAT,
            policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
            reason=EvidenceReasonCode.NONE,
            allowed_domains=("docs.python.org",),
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "no policy trigger matched"


def test_user_requested_web_search_with_domains_allows():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode=ExecutionMode.PLAN,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            reason=EvidenceReasonCode.USER_REQUESTED,
            allowed_domains=("docs.python.org",),
        )
    )

    assert decision.decision is PolicyDecision.ALLOW
    assert decision.reason == "policy trigger matched"


def test_web_search_requires_allowed_domains():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode=ExecutionMode.PLAN,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            reason=EvidenceReasonCode.USER_REQUESTED,
            allowed_domains=(),
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "allowed_domains required for web search"


def test_unknown_execution_mode_rejects_before_tool_specific_policy():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode="SURPRISE",  # type: ignore[arg-type]
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            reason=EvidenceReasonCode.USER_REQUESTED,
            allowed_domains=("docs.python.org",),
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "unknown execution mode"


def test_local_repo_read_is_allowed_in_plan_chat_mode():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.LOCAL_REPO_READ,
            execution_mode=ExecutionMode.CHAT,
            policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
            reason=EvidenceReasonCode.NONE,
        )
    )

    assert decision.decision is PolicyDecision.ALLOW


def test_dependency_version_check_no_longer_authorizes_web_search():
    """P11-FU-2: dependency/CVE signals must not route through generic web search."""
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode=ExecutionMode.AGENT,
            policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
            reason=EvidenceReasonCode.PACKAGE_VERSION,
            allowed_domains=("pypi.org",),
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "no policy trigger matched"


def test_security_or_cve_check_no_longer_authorizes_web_search():
    """P11-FU-2: dependency/CVE signals must not route through generic web search."""
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode=ExecutionMode.AGENT,
            policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK,
            reason=EvidenceReasonCode.SECURITY_ADVISORY,
            allowed_domains=("osv.dev",),
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "no policy trigger matched"


def test_dependency_version_check_authorizes_package_and_advisory_metadata():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
            execution_mode=ExecutionMode.AGENT,
            policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
            reason=EvidenceReasonCode.PACKAGE_VERSION,
        )
    )

    assert decision.decision is PolicyDecision.ALLOW
    assert decision.tool_class is ToolClass.PACKAGE_AND_ADVISORY_METADATA


def test_security_or_cve_check_authorizes_package_and_advisory_metadata():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
            execution_mode=ExecutionMode.AGENT,
            policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK,
            reason=EvidenceReasonCode.SECURITY_ADVISORY,
        )
    )

    assert decision.decision is PolicyDecision.ALLOW
    assert decision.tool_class is ToolClass.PACKAGE_AND_ADVISORY_METADATA


def test_package_and_advisory_metadata_rejects_without_matching_trigger():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
            execution_mode=ExecutionMode.AGENT,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            reason=EvidenceReasonCode.USER_REQUESTED,
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "no policy trigger matched"


def test_package_and_advisory_metadata_rejects_mismatched_signal_reason_pair():
    """Signal and reason must be from the same pair; cross-pairing must not authorize."""
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
            execution_mode=ExecutionMode.AGENT,
            policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
            reason=EvidenceReasonCode.SECURITY_ADVISORY,
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "no policy trigger matched"
