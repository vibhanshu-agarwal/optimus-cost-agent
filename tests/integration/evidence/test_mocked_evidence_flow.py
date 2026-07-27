from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainPolicy
from optimus.evidence.ledger import EvidenceLedger
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus.tools.policy import ToolClass
from optimus.tools.registry import ToolRegistry

TRUSTED_GATEWAY_ORIGIN = "https://gateway.optimus.ai"


class CapturingEvidenceTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        if request.url.endswith("/v1/tools/web/search"):
            return {
                "tool_class": "web_search",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "run_id": "run-1",
                "result": {
                    "results": [
                        {
                            "title": "Docs",
                            "url": "https://docs.example.com/a",
                            "snippet": "Authoritative docs",
                        },
                    ]
                },
                "provenance": {
                    "search_id": "search-1",
                    "source_urls": ["https://docs.example.com/a"],
                    "trust": "untrusted",
                },
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
                "tool_class": "web_extract",
                "policy_signal": "APPROVED_SEARCH_RESULT_PROVENANCE",
                "run_id": "run-1",
                "result": {
                    "items": [
                        {
                            "url": "https://docs.example.com/a",
                            "title": "Docs",
                            "content": "Evidence text must be treated as untrusted text.",
                        },
                    ]
                },
                "provenance": {
                    "search_id": None,
                    "source_urls": ["https://docs.example.com/a"],
                    "trust": "untrusted",
                },
                "gateway_usage": {
                    "gateway_request_id": "gw-extract-1",
                    "provider": "tavily",
                    "cache_hit": True,
                    "billing_units": 1,
                    "cost_usd": "0.001",
                },
            }
        raise AssertionError(f"unexpected URL: {request.url}")


class MalformedSearchTransport:
    """Returns a search response with valid usage but a body that fails envelope parsing."""

    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        return {
            "tool_class": "web_search",
            "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
            "run_id": "run-1",
            # "result" and "provenance" are both missing: envelope parsing must fail.
            "gateway_usage": {
                "gateway_request_id": "gw-search-malformed",
                "provider": "tavily",
                "cache_hit": False,
                "billing_units": 2,
                "cost_usd": "0.002",
            },
        }


class UsageLessExtractTransport:
    """Search succeeds; extract returns a body with no usage fields at all."""

    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        if request.url.endswith("/v1/tools/web/search"):
            return {
                "tool_class": "web_search",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "run_id": "run-1",
                "result": {
                    "results": [
                        {
                            "title": "Docs",
                            "url": "https://docs.example.com/a",
                            "snippet": "Authoritative docs",
                        },
                    ]
                },
                "provenance": {
                    "search_id": "search-1",
                    "source_urls": ["https://docs.example.com/a"],
                    "trust": "untrusted",
                },
                "gateway_usage": {
                    "gateway_request_id": "gw-search-1",
                    "provider": "tavily",
                    "cache_hit": False,
                    "billing_units": 2,
                    "cost_usd": "0.002",
                },
            }
        if request.url.endswith("/v1/tools/web/extract"):
            # No gateway_usage key at all: the extract response is unusable and
            # must never be attributed a cost/credit.
            return {"error": "provider outage"}
        raise AssertionError(f"unexpected URL: {request.url}")


def _settings_with_only_optimus_credentials(monkeypatch) -> OptimusGatewaySettings:
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", TRUSTED_GATEWAY_ORIGIN)
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt_live_test")
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    settings = OptimusGatewaySettings.from_env()
    assert settings.validate_no_local_provider_keys() == ()
    return settings


def test_mocked_search_then_extract_flow_uses_only_optimus_credentials(monkeypatch):
    settings = _settings_with_only_optimus_credentials(monkeypatch)

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
    assert extract_response["result"]["ledger_run_total_credits"] == 0
    assert [request.url for request in transport.requests] == [
        f"{TRUSTED_GATEWAY_ORIGIN}/v1/tools/web/search",
        f"{TRUSTED_GATEWAY_ORIGIN}/v1/tools/web/extract",
    ]
    # No direct provider URL (e.g. a raw Tavily endpoint) is ever requested by the
    # local agent: every captured request stays on the one trusted Gateway origin.
    assert all(request.url.startswith(f"{TRUSTED_GATEWAY_ORIGIN}/v1/tools/") for request in transport.requests)
    assert transport.requests[0].headers["Authorization"] == "Bearer opt_live_test"
    assert transport.requests[1].headers["Authorization"] == "Bearer opt_live_test"
    assert transport.requests[0].payload["query"] == "latest pytest release"
    assert transport.requests[1].payload["urls"] == ["https://docs.example.com/a"]
    assert registry.call_count("run-1") == 2

    # No secret ever leaks through the request's debug representation.
    for request in transport.requests:
        assert "opt_live_test" not in repr(request)

    # The evidence ledger joins the search and extract entries by the
    # Gateway-issued gateway_request_id copied verbatim from each response's
    # gateway_usage — never a locally-generated identifier.
    assert service.ledger.gateway_request_ids(run_id="run-1") == {"gw-search-1", "gw-extract-1"}
    assert {entry.tool_class for entry in service.ledger.entries_for_run("run-1")} == {
        ToolClass.WEB_SEARCH,
        ToolClass.WEB_EXTRACT,
    }
    # Usage/cost is recorded exactly once per Gateway response, not duplicated.
    assert len(service.ledger.entries_for_run("run-1")) == 2


def test_extract_rejects_url_not_returned_by_a_prior_gateway_search(monkeypatch):
    """Extract's provenance approval must come from the Gateway's own search
    results, not a caller-supplied claim: a URL the Gateway never returned in
    ``/v1/tools/web/search`` is rejected before any extract transport call.
    """
    settings = _settings_with_only_optimus_credentials(monkeypatch)
    transport = CapturingEvidenceTransport()
    service = EvidenceAcquisitionService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        domain_policy=EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",)),
        registry=ToolRegistry(max_calls_per_run=10),
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
    assert "error" not in search_response

    unsearched_extract_response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "extract-2",
            "method": "optimus.evidence.extract",
            "params": {
                "run_id": "run-1",
                "url": "https://docs.example.com/never-searched",
                "reason": "USER_REQUESTED",
                "policy_signal": "APPROVED_SEARCH_RESULT_PROVENANCE",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert unsearched_extract_response["error"]["code"] == -32600
    # The rejection happens locally: no extract request ever reaches the transport.
    assert [request.url for request in transport.requests] == [f"{TRUSTED_GATEWAY_ORIGIN}/v1/tools/web/search"]
    # Only the search ledger entry exists; the rejected extract created no entry.
    assert len(service.ledger.entries_for_run("run-1")) == 1
    assert service.ledger.entries_for_run("run-1")[0].tool_class is ToolClass.WEB_SEARCH


def test_search_malformed_envelope_with_usage_records_ledger_entry_before_error(monkeypatch):
    """A response with valid usage but a body that fails the common-envelope
    contract (missing ``result``/``provenance``) still bills the Gateway call
    to the ledger before the error propagates — the Gateway consumed real
    resources even though the local agent could not use the result.
    """
    settings = _settings_with_only_optimus_credentials(monkeypatch)
    transport = MalformedSearchTransport()
    service = EvidenceAcquisitionService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        domain_policy=EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",)),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    dispatcher = JsonRpcDispatcher(evidence_service=service)

    response = dispatcher.dispatch(
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

    assert "error" in response
    assert len(service.ledger.entries_for_run("run-1")) == 1
    assert service.ledger.entries_for_run("run-1")[0].gateway_request_id == "gw-search-malformed"
    assert str(service.ledger.entries_for_run("run-1")[0].cost_usd) == "0.002"


def test_extract_usage_less_response_never_creates_a_false_ledger_entry(monkeypatch):
    """When extract's response carries no usable ``gateway_usage`` at all, no
    ledger entry is created — a usage-less response can never be billed.
    """
    settings = _settings_with_only_optimus_credentials(monkeypatch)
    transport = UsageLessExtractTransport()
    service = EvidenceAcquisitionService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        domain_policy=EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",)),
        registry=ToolRegistry(max_calls_per_run=10),
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
    assert "error" not in search_response

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

    assert "error" in extract_response
    # Only the successful search entry exists; the usage-less extract failure
    # never appended a false ledger entry.
    assert len(service.ledger.entries_for_run("run-1")) == 1
    assert service.ledger.entries_for_run("run-1")[0].tool_class is ToolClass.WEB_SEARCH
