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
