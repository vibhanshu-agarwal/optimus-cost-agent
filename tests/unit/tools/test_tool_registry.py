import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import (
    EvidenceReasonCode,
    ToolClass,
    ToolInvocationPolicy,
    ToolInvocationRequest,
    ToolPolicySignal,
)
from optimus.tools.registry import ToolCallRejected, ToolRegistry


def search_request(run_id: str) -> ToolInvocationRequest:
    return ToolInvocationRequest(
        run_id=run_id,
        tool_class=ToolClass.WEB_SEARCH,
        execution_mode=ExecutionMode.PLAN,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        reason=EvidenceReasonCode.USER_REQUESTED,
        allowed_domains=("example.com",),
    )


def test_authorize_and_record_call_rejects_without_recording():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)

    with pytest.raises(ToolCallRejected, match="no policy trigger matched"):
        registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id="run-1",
                tool_class=ToolClass.WEB_SEARCH,
                execution_mode=ExecutionMode.CHAT,
                policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
                reason=EvidenceReasonCode.NONE,
                allowed_domains=("example.com",),
            )
        )

    assert registry.call_count("run-1") == 0


def test_max_calls_per_run_is_atomic_under_concurrent_calls():
    from concurrent.futures import ThreadPoolExecutor

    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)

    def attempt_call(index: int) -> bool:
        try:
            registry.authorize_and_record_call(search_request("run-1"))
            return True
        except ToolCallRejected:
            return False

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(attempt_call, range(50)))

    assert results.count(True) == 10
    assert results.count(False) == 40
    assert registry.call_count("run-1") == 10
    assert sorted(record.sequence_number for record in registry.records("run-1")) == list(range(1, 11))


def test_max_calls_per_run_is_atomic():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=2)

    registry.authorize_and_record_call(search_request("run-1"))
    registry.authorize_and_record_call(search_request("run-1"))

    with pytest.raises(ToolCallRejected, match="max_calls_per_run exceeded"):
        registry.authorize_and_record_call(search_request("run-1"))

    assert registry.call_count("run-1") == 2


def test_search_result_urls_are_tracked_per_run():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)

    registry.record_search_results(
        run_id="run-1",
        urls=("https://docs.example.com/a", "https://docs.example.com/b"),
    )

    assert registry.search_result_urls("run-1") == frozenset(
        {"https://docs.example.com/a", "https://docs.example.com/b"}
    )
    assert registry.search_result_urls("other-run") == frozenset()


def test_extract_uses_recorded_search_result_provenance():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)
    registry.record_search_results(run_id="run-1", urls=("https://docs.example.com/a",))

    registry.authorize_and_record_call(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_EXTRACT,
            execution_mode=ExecutionMode.PLAN,
            policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
            reason=EvidenceReasonCode.USER_REQUESTED,
            target_url="https://docs.example.com/a",
            prior_search_result_urls=registry.search_result_urls("run-1"),
        )
    )

    assert registry.call_count("run-1") == 1


def test_extract_rejects_url_not_from_prior_search():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)

    with pytest.raises(ToolCallRejected, match="URL not in approved search-result set"):
        registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id="run-1",
                tool_class=ToolClass.WEB_EXTRACT,
                execution_mode=ExecutionMode.PLAN,
                policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
                reason=EvidenceReasonCode.USER_REQUESTED,
                target_url="https://docs.example.com/a",
                prior_search_result_urls=registry.search_result_urls("run-1"),
            )
        )

    assert registry.call_count("run-1") == 0


def test_extract_requires_approved_provenance_signal():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)
    registry.record_search_results(run_id="run-1", urls=("https://docs.example.com/a",))

    with pytest.raises(ToolCallRejected, match="web extract requires approved search-result provenance"):
        registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id="run-1",
                tool_class=ToolClass.WEB_EXTRACT,
                execution_mode=ExecutionMode.PLAN,
                policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
                reason=EvidenceReasonCode.USER_REQUESTED,
                target_url="https://docs.example.com/a",
                prior_search_result_urls=registry.search_result_urls("run-1"),
            )
        )

    assert registry.call_count("run-1") == 0


def test_extract_rejects_non_https_url_before_provenance_match():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)
    registry.record_search_results(run_id="run-1", urls=("http://docs.example.com/a",))

    with pytest.raises(ToolCallRejected, match="https URL required for web extract"):
        registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id="run-1",
                tool_class=ToolClass.WEB_EXTRACT,
                execution_mode=ExecutionMode.PLAN,
                policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
                reason=EvidenceReasonCode.USER_REQUESTED,
                target_url="http://docs.example.com/a",
                prior_search_result_urls=registry.search_result_urls("run-1"),
            )
        )

    assert registry.call_count("run-1") == 0
