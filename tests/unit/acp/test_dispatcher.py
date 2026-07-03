from decimal import Decimal

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import DUPLICATE_REQUEST_ID, METHOD_NOT_FOUND, MUTATION_FORBIDDEN
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


def test_dispatcher_handles_ping():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": 1, "method": "optimus.ping"})

    assert response == {"jsonrpc": "2.0", "id": 1, "result": {"message": "pong"}}


def test_dispatcher_rejects_unknown_method():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": 2, "method": "unknown"})

    assert response["id"] == 2
    assert response["error"]["code"] == METHOD_NOT_FOUND


def test_dispatcher_rejects_duplicate_id():
    dispatcher = JsonRpcDispatcher()
    dispatcher.dispatch({"jsonrpc": "2.0", "id": "x", "method": "optimus.ping"})

    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": "x", "method": "optimus.ping"})

    assert response["id"] == "x"
    assert response["error"]["code"] == DUPLICATE_REQUEST_ID


def test_dispatcher_maps_forbidden_runtime_mutation_to_32002():
    dispatcher = JsonRpcDispatcher(
        runtime_context=RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )
    )

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "write-1",
            "method": "optimus.mutation.writeFile",
            "params": {"path": "blocked.txt", "content": "blocked"},
        }
    )

    assert response["id"] == "write-1"
    assert response["error"]["code"] == MUTATION_FORBIDDEN
    assert response["error"]["message"] == "mutation forbidden in Plan/Chat mode"


class FakeGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, object] | None = None) -> GatewayResponse:
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        return GatewayResponse(
            response_id="resp-1",
            output_text="planned",
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                cache_hit=False,
                billing_units=12,
                cost_usd=Decimal("0.0012"),
            ),
            raw={"id": "resp-1"},
        )


def test_dispatcher_routes_gateway_responses_method_to_gateway_client():
    gateway_client = FakeGatewayClient()
    dispatcher = JsonRpcDispatcher(gateway_client=gateway_client)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "gw-call-1",
            "method": "optimus.gateway.responses",
            "params": {
                "model": "glm-5.2",
                "input": "Write a plan.",
                "metadata": {"run_id": "run-1"},
            },
        }
    )

    assert response["id"] == "gw-call-1"
    assert response["result"] == {
        "response_id": "resp-1",
        "output_text": "planned",
        "gateway_usage": {
            "gateway_request_id": "gw-1",
            "provider": "glm",
            "provider_request_id": None,
            "cache_hit": False,
            "billing_units": 12,
            "cost_usd": "0.0012",
        },
    }
    assert gateway_client.calls == [
        {"model": "glm-5.2", "input_text": "Write a plan.", "metadata": {"run_id": "run-1"}}
    ]


def test_gateway_responses_are_allowed_in_plan_chat_mode_by_design():
    gateway_client = FakeGatewayClient()
    dispatcher = JsonRpcDispatcher(
        gateway_client=gateway_client,
        runtime_context=RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        ),
    )

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "gw-plan-chat-1",
            "method": "optimus.gateway.responses",
            "params": {"model": "glm-5.2", "input": "Draft an advisory answer."},
        }
    )

    assert "error" not in response
    assert response["result"]["output_text"] == "planned"
    assert gateway_client.calls == [
        {"model": "glm-5.2", "input_text": "Draft an advisory answer.", "metadata": None}
    ]


def test_dispatcher_rejects_gateway_responses_messages_shape():
    dispatcher = JsonRpcDispatcher(gateway_client=FakeGatewayClient())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "gw-call-2",
            "method": "optimus.gateway.responses",
            "params": {"model": "glm-5.2", "messages": [{"role": "user", "content": "wrong"}]},
        }
    )

    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "invalid request"


from optimus.evidence.domain_policy import EvidenceDomainRejected
from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.models import (
    EvidenceExtractResponse,
    EvidenceSearchResponse,
    EvidenceSearchResult,
)
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.tools.registry import ToolCallRejected


class FakeEvidenceService:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []
        self.extract_calls: list[dict[str, object]] = []

    def search(self, request, *, execution_mode):
        self.search_calls.append({"request": request, "execution_mode": execution_mode})
        response = EvidenceSearchResponse(
            results=(
                EvidenceSearchResult(
                    title="Docs",
                    url="https://docs.example.com/a",
                    snippet="A",
                ),
            ),
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-search-1",
                provider="tavily",
                cache_hit=False,
                billing_units=2,
                cost_usd=Decimal("0.002"),
            ),
        )
        return response, EvidenceLedger()

    def extract(self, request, *, execution_mode):
        self.extract_calls.append({"request": request, "execution_mode": execution_mode})
        response = EvidenceExtractResponse(
            url="https://docs.example.com/a",
            title="Docs",
            content="Evidence text",
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-extract-1",
                provider="tavily",
                cache_hit=True,
                billing_units=1,
                cost_usd=Decimal("0.001"),
            ),
        )
        return response, EvidenceLedger()


def test_dispatcher_routes_evidence_search_to_service():
    evidence_service = FakeEvidenceService()
    dispatcher = JsonRpcDispatcher(evidence_service=evidence_service)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-1",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "latest pytest release",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert "error" not in response
    assert response["result"]["results"][0]["url"] == "https://docs.example.com/a"
    assert response["result"]["gateway_usage"]["gateway_request_id"] == "gw-search-1"
    assert response["result"]["ledger_run_total_cost_usd"] == "0"
    assert response["result"]["ledger_run_total_credits"] == 0
    assert evidence_service.search_calls[0]["request"].query == "latest pytest release"


def test_dispatcher_routes_evidence_extract_to_service():
    evidence_service = FakeEvidenceService()
    dispatcher = JsonRpcDispatcher(evidence_service=evidence_service)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-extract-1",
            "method": "optimus.evidence.extract",
            "params": {
                "run_id": "run-1",
                "url": "https://docs.example.com/a",
                "reason": "USER_REQUESTED",
                "policy_signal": "APPROVED_SEARCH_RESULT_PROVENANCE",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert "error" not in response
    assert response["result"]["url"] == "https://docs.example.com/a"
    assert response["result"]["content"] == "Evidence text"
    assert response["result"]["gateway_usage"]["gateway_request_id"] == "gw-extract-1"
    assert response["result"]["ledger_run_total_cost_usd"] == "0"
    assert response["result"]["ledger_run_total_credits"] == 0


def test_dispatcher_rejects_malformed_evidence_search_request():
    dispatcher = JsonRpcDispatcher(evidence_service=FakeEvidenceService())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-2",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "invalid request"


def test_dispatcher_reports_evidence_search_service_not_configured():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-missing",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "latest pytest release",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32601
    assert response["error"]["message"] == "evidence service not configured"


def test_dispatcher_reports_evidence_extract_service_not_configured():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-extract-missing",
            "method": "optimus.evidence.extract",
            "params": {
                "run_id": "run-1",
                "url": "https://docs.example.com/a",
                "reason": "USER_REQUESTED",
                "policy_signal": "APPROVED_SEARCH_RESULT_PROVENANCE",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32601
    assert response["error"]["message"] == "evidence service not configured"


class RejectedEvidenceService(FakeEvidenceService):
    def search(self, request, *, execution_mode):
        from optimus.tools.policy import PolicyDecision, ToolInvocationDecision

        raise ToolCallRejected(
            ToolInvocationDecision(
                decision=PolicyDecision.REJECT,
                reason="no policy trigger matched",
                tool_class=ToolClass.WEB_SEARCH,
                policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
                reason_code=EvidenceReasonCode.NONE,
            )
        )


def test_dispatcher_maps_tool_call_rejected_to_invalid_request():
    dispatcher = JsonRpcDispatcher(evidence_service=RejectedEvidenceService())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-rejected",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "look this up",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "no policy trigger matched"


class DomainRejectedEvidenceService(FakeEvidenceService):
    def search(self, request, *, execution_mode):
        raise EvidenceDomainRejected("allowed_domains not in configured evidence allowlist")


def test_dispatcher_maps_evidence_domain_rejected_to_invalid_request():
    dispatcher = JsonRpcDispatcher(evidence_service=DomainRejectedEvidenceService())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-domain-rejected",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "look this up",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["evil.com"],
            },
        }
    )

    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "allowed_domains not in configured evidence allowlist"


class ValueErrorEvidenceService(FakeEvidenceService):
    def search(self, request, *, execution_mode):
        raise ValueError("gateway origin not in trusted set: https://rogue.attacker.com")


def test_dispatcher_maps_gateway_trust_value_error_to_json_rpc_error():
    dispatcher = JsonRpcDispatcher(evidence_service=ValueErrorEvidenceService())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-3",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "current fact",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32603
    assert "gateway origin not in trusted set" in response["error"]["message"]
