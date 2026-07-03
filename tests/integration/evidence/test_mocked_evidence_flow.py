from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainPolicy
from optimus.evidence.ledger import EvidenceLedger
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus.tools.registry import ToolRegistry


class CapturingEvidenceTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        if request.url.endswith("/v1/tools/web/search"):
            return {
                "results": [
                    {
                        "title": "Docs",
                        "url": "https://docs.example.com/a",
                        "snippet": "Authoritative docs",
                    },
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
        if request.url.endswith("/v1/tools/web/extract"):
            return {
                "url": "https://docs.example.com/a",
                "title": "Docs",
                "content": "Evidence text must be treated as untrusted text.",
                "credits_used": 1,
                "gateway_usage": {
                    "gateway_request_id": "gw-extract-1",
                    "provider": "tavily",
                    "cache_hit": True,
                    "billing_units": 1,
                    "cost_usd": "0.001",
                },
            }
        raise AssertionError(f"unexpected URL: {request.url}")


def test_mocked_search_then_extract_flow_uses_only_optimus_credentials(monkeypatch):
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt_live_test")
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)

    settings = OptimusGatewaySettings.from_env()
    assert settings.validate_no_local_provider_keys() == ()

    transport = CapturingEvidenceTransport()
    registry = ToolRegistry(max_calls_per_run=10)
    service = EvidenceAcquisitionService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        domain_policy=EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",)),
        registry=registry,
        ledger=EvidenceLedger(),
    )
    dispatcher = JsonRpcDispatcher(evidence_service=service)

    search_response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "search-1",
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
    extract_response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "extract-1",
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

    assert "error" not in search_response
    assert "error" not in extract_response
    assert search_response["result"]["gateway_usage"]["gateway_request_id"] == "gw-search-1"
    assert extract_response["result"]["gateway_usage"]["gateway_request_id"] == "gw-extract-1"
    assert extract_response["result"]["trust"] == "untrusted"
    assert extract_response["result"]["ledger_run_total_cost_usd"] == "0.003"
    assert extract_response["result"]["ledger_run_total_credits"] == 3
    assert [request.url for request in transport.requests] == [
        "https://gateway.optimus.ai/v1/tools/web/search",
        "https://gateway.optimus.ai/v1/tools/web/extract",
    ]
    assert transport.requests[0].headers["Authorization"] == "Bearer opt_live_test"
    assert transport.requests[0].payload["query"] == "latest pytest release"
    assert transport.requests[1].payload["url"] == "https://docs.example.com/a"
    assert registry.call_count("run-1") == 2
