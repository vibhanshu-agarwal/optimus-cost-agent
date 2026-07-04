from decimal import Decimal

import pytest

from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainPolicy, EvidenceDomainRejected
from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceRequest,
)
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.guardrails.pre_tool import PreToolResult, PreToolVerdict
from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.tools.registry import ToolCallRejected, ToolRegistry


def domain_policy() -> EvidenceDomainPolicy:
    return EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",))


class FakeGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append({"path": path, "payload": payload})
        if path == "/v1/tools/web/search":
            return {
                "results": [
                    {"title": "Docs", "url": "https://docs.example.com/a", "snippet": "A"},
                ],
                "credits_used": 2,
                "gateway_usage": {
                    "gateway_request_id": "gw-search-1",
                    "provider": "tavily",
                    "provider_request_id": "provider-search-1",
                    "cache_hit": False,
                    "billing_units": 2,
                    "cost_usd": "0.002",
                },
            }
        if path == "/v1/tools/web/extract":
            return {
                "url": "https://docs.example.com/a",
                "title": "Docs",
                "content": "Evidence text",
                "credits_used": 1,
                "gateway_usage": {
                    "gateway_request_id": "gw-extract-1",
                    "provider": "tavily",
                    "cache_hit": True,
                    "billing_units": 1,
                    "cost_usd": "0.001",
                },
            }
        raise AssertionError(f"unexpected path: {path}")


class OffAllowlistGatewayClient(FakeGatewayClient):
    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = super().post_tool_json(path=path, payload=payload)
        if path == "/v1/tools/web/search":
            body["results"] = [{"title": "Bad", "url": "https://evil.com/a", "snippet": "bad"}]
        return body


class FailingGatewayClient(FakeGatewayClient):
    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append({"path": path, "payload": payload})
        raise GatewayHttpError(502, "gateway unavailable")


class MalformedBodyGatewayClient(FakeGatewayClient):
    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append({"path": path, "payload": payload})
        if path == "/v1/tools/web/search":
            return {
                "results": [{"title": "Bad", "url": "not-a-url", "snippet": "bad"}],
                "credits_used": 2,
                "gateway_usage": {
                    "gateway_request_id": "gw-search-bad",
                    "provider": "tavily",
                    "cache_hit": False,
                    "billing_units": 2,
                    "cost_usd": "0.002",
                },
            }
        raise AssertionError(f"unexpected path: {path}")


def test_search_authorizes_gateway_call_and_records_ledger_entry():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com",),
    )

    response, ledger = service.search(request, execution_mode=ExecutionMode.PLAN)

    assert response.results[0].url_text == "https://docs.example.com/a"
    assert gateway.calls[0]["path"] == "/v1/tools/web/search"
    assert gateway.calls[0]["payload"]["query"] == "latest pytest release"
    assert service.registry.search_result_urls("run-1") == frozenset({"https://docs.example.com/a"})
    assert ledger.entries[0].tool_class is ToolClass.WEB_SEARCH
    assert ledger.entries[0].run_id == "run-1"
    assert ledger.entries[0].gateway_request_id == "gw-search-1"
    assert ledger.total_cost_usd() == Decimal("0.002")
    assert ledger.total_credits() == 2


def test_search_intersects_request_domains_with_configured_allowlist():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com", "evil.com"),
    )

    service.search(request, execution_mode=ExecutionMode.PLAN)

    assert gateway.calls[0]["payload"]["allowed_domains"] == ["docs.example.com"]


def test_search_rejects_unconfigured_requested_domain_before_gateway_call():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="look this up",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("evil.com",),
    )

    with pytest.raises(EvidenceDomainRejected, match="allowed_domains not in configured evidence allowlist"):
        service.search(request, execution_mode=ExecutionMode.PLAN)

    assert gateway.calls == []
    assert service.registry.call_count("run-1") == 0


def test_search_rejects_off_allowlist_gateway_result_before_provenance_recording():
    gateway = OffAllowlistGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com",),
    )

    with pytest.raises(EvidenceDomainRejected, match="URL host not in effective allowed domains"):
        service.search(request, execution_mode=ExecutionMode.PLAN)

    assert service.registry.search_result_urls("run-1") == frozenset()
    assert service.ledger.entries == ()


def test_gateway_failure_consumes_authorized_attempt_without_ledger_entry():
    gateway = FailingGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com",),
    )

    with pytest.raises(GatewayHttpError):
        service.search(request, execution_mode=ExecutionMode.PLAN)

    assert service.registry.call_count("run-1") == 1
    assert service.ledger.entries == ()


def test_malformed_gateway_body_records_usage_before_error():
    gateway = MalformedBodyGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com",),
    )

    with pytest.raises(GatewayResponseError, match="url"):
        service.search(request, execution_mode=ExecutionMode.PLAN)

    assert service.registry.call_count("run-1") == 1
    assert len(service.ledger.entries) == 1
    assert service.ledger.entries[0].gateway_request_id == "gw-search-bad"
    assert service.ledger.entries[0].cost_usd == Decimal("0.002")
    assert service.registry.search_result_urls("run-1") == frozenset()


def test_search_rejects_without_policy_trigger_before_gateway_call():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="look this up",
        reason=EvidenceReasonCode.NONE,
        policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
        allowed_domains=("docs.example.com",),
    )

    with pytest.raises(ToolCallRejected, match="no policy trigger matched"):
        service.search(request, execution_mode=ExecutionMode.PLAN)

    assert gateway.calls == []


def test_concurrent_successful_search_calls_do_not_drop_ledger_entries():
    from concurrent.futures import ThreadPoolExecutor

    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )

    def search_once(index: int) -> None:
        request = EvidenceRequest(
            run_id="run-1",
            query=f"latest pytest release {index}",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            allowed_domains=("docs.example.com",),
        )
        service.search(request, execution_mode=ExecutionMode.PLAN)

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(search_once, range(5)))

    assert service.registry.call_count("run-1") == 5
    assert len(service.ledger.entries_for_run("run-1")) == 5


def test_extract_requires_prior_search_result_and_records_separate_usage():
    gateway = FakeGatewayClient()
    registry = ToolRegistry(max_calls_per_run=10)
    registry.record_search_results(run_id="run-1", urls=("https://docs.example.com/a",))
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=registry,
        ledger=EvidenceLedger(),
    )
    request = EvidenceExtractRequest(
        run_id="run-1",
        url="https://docs.example.com/a",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
        allowed_domains=("docs.example.com",),
    )

    response, ledger = service.extract(request, execution_mode=ExecutionMode.CHAT)

    assert response.content == "Evidence text"
    assert response.trust == "untrusted"
    assert gateway.calls[0]["path"] == "/v1/tools/web/extract"
    assert gateway.calls[0]["payload"]["url"] == "https://docs.example.com/a"
    assert ledger.entries[0].tool_class is ToolClass.WEB_EXTRACT
    assert ledger.entries[0].gateway_request_id == "gw-extract-1"
    assert ledger.total_billing_units() == 1
    assert ledger.total_credits() == 1


def test_extract_rejects_unapproved_url_before_gateway_call():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceExtractRequest(
        run_id="run-1",
        url="https://docs.example.com/a",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
        allowed_domains=("docs.example.com",),
    )

    with pytest.raises(ToolCallRejected, match="URL not in approved search-result set"):
        service.extract(request, execution_mode=ExecutionMode.PLAN)

    assert gateway.calls == []


class BlockingPreToolGuard:
    def check(self, request):
        return PreToolResult(PreToolVerdict.BLOCK, "network.unexpected_egress", "blocked network egress")


def test_search_pre_tool_guard_blocks_before_gateway_transport():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        pre_tool_guard=BlockingPreToolGuard(),
    )

    with pytest.raises(ToolCallRejected, match="blocked network egress"):
        service.search(
            EvidenceRequest(
                run_id="run-1",
                query="current docs",
                reason=EvidenceReasonCode.USER_REQUESTED,
                policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
                allowed_domains=("docs.example.com",),
            ),
            execution_mode=ExecutionMode.AGENT,
        )

    assert gateway.calls == []
