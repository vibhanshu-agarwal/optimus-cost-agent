"""Integration coverage for the dedicated package-lookup/security-advisory flow
(``P11-FU-2``). Mirrors ``test_mocked_evidence_flow.py``'s transport-level fake
but exercises :class:`~optimus.evidence.package_advisory.PackageAdvisoryService`
through the ACP dispatcher, proving the package/advisory paths and tool class
are dedicated (never routed through generic web search/extract) and that
usage/cost is recorded exactly once per Gateway response.
"""

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.package_advisory import PackageAdvisoryService
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus.tools.policy import ToolClass
from optimus.tools.registry import ToolRegistry

TRUSTED_GATEWAY_ORIGIN = "https://gateway.optimus.ai"


class CapturingPackageAdvisoryTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        if request.url.endswith("/v1/tools/package/lookup"):
            return {
                "tool_class": "package_and_advisory_metadata",
                "policy_signal": "DEPENDENCY_VERSION_CHECK",
                "run_id": "run-1",
                "result": {
                    "package": "pytest-asyncio",
                    "ecosystem": "pypi",
                    "requested_version": None,
                    "latest_version": "0.24.0",
                    "versions": [],
                    "citations": ["https://pypi.org/project/pytest-asyncio/"],
                },
                "provenance": {"search_id": None, "source_urls": [], "trust": "untrusted"},
                "gateway_usage": {
                    "gateway_request_id": "gw-pkg-1",
                    "provider": "package-registry",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.0005",
                },
            }
        if request.url.endswith("/v1/tools/security/advisory"):
            return {
                "tool_class": "package_and_advisory_metadata",
                "policy_signal": "SECURITY_OR_CVE_CHECK",
                "run_id": "run-1",
                "result": {
                    "identifier": "CVE-2026-12345",
                    "ecosystem": "npm",
                    "version": "1.2.3",
                    "advisories": [
                        {
                            "advisory_id": "GHSA-xxxx-yyyy-zzzz",
                            "summary": "Untrusted summary text",
                            "severity": "high",
                            "affected_ranges": ["<1.2.4"],
                            "fixed_versions": ["1.2.4"],
                            "citations": ["https://github.com/advisories/GHSA-xxxx-yyyy-zzzz"],
                        }
                    ],
                },
                "provenance": {"search_id": None, "source_urls": [], "trust": "untrusted"},
                "gateway_usage": {
                    "gateway_request_id": "gw-adv-1",
                    "provider": "osv",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.0007",
                },
            }
        raise AssertionError(f"unexpected URL: {request.url}")


class UsageLessPackageLookupTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        # No gateway_usage key at all: the provider produced nothing billable.
        return {"error": "package registry outage"}


def _settings_with_only_optimus_credentials(monkeypatch) -> OptimusGatewaySettings:
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", TRUSTED_GATEWAY_ORIGIN)
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt_live_test")
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    settings = OptimusGatewaySettings.from_env()
    assert settings.validate_no_local_provider_keys() == ()
    return settings


def test_mocked_package_lookup_and_security_advisory_use_only_optimus_credentials(monkeypatch):
    settings = _settings_with_only_optimus_credentials(monkeypatch)

    transport = CapturingPackageAdvisoryTransport()
    registry = ToolRegistry(max_calls_per_run=10)
    service = PackageAdvisoryService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        registry=registry,
        ledger=EvidenceLedger(),
    )
    dispatcher = JsonRpcDispatcher(package_advisory_service=service)

    package_response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "pkg-1",
            "method": "optimus.evidence.package_lookup",
            "params": {
                "run_id": "run-1",
                "package": "pytest-asyncio",
                "ecosystem": "pypi",
                "reason": "PACKAGE_VERSION",
                "policy_signal": "DEPENDENCY_VERSION_CHECK",
            },
        }
    )
    advisory_response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "adv-1",
            "method": "optimus.evidence.security_advisory",
            "params": {
                "run_id": "run-1",
                "identifier": "CVE-2026-12345",
                "ecosystem": "npm",
                "version": "1.2.3",
                "reason": "SECURITY_ADVISORY",
                "policy_signal": "SECURITY_OR_CVE_CHECK",
            },
        }
    )

    assert "error" not in package_response
    assert "error" not in advisory_response
    assert package_response["result"]["latest_version"] == "0.24.0"
    assert package_response["result"]["gateway_usage"]["gateway_request_id"] == "gw-pkg-1"
    assert advisory_response["result"]["advisories"][0]["advisory_id"] == "GHSA-xxxx-yyyy-zzzz"
    assert advisory_response["result"]["gateway_usage"]["gateway_request_id"] == "gw-adv-1"

    assert [request.url for request in transport.requests] == [
        f"{TRUSTED_GATEWAY_ORIGIN}/v1/tools/package/lookup",
        f"{TRUSTED_GATEWAY_ORIGIN}/v1/tools/security/advisory",
    ]
    # No direct provider URL (e.g. a raw PyPI/OSV endpoint) is ever requested by
    # the local agent: both calls stay on the one trusted Gateway origin.
    assert all(request.url.startswith(f"{TRUSTED_GATEWAY_ORIGIN}/v1/tools/") for request in transport.requests)
    for request in transport.requests:
        assert request.headers["Authorization"] == "Bearer opt_live_test"
        assert "opt_live_test" not in repr(request)

    # Both calls are authorized and recorded under the single dedicated tool
    # class — never generic web_search/web_extract — proving the P11-FU-2
    # routing is independent from the evidence web-search policy branch.
    records = registry.records("run-1")
    assert len(records) == 2
    assert {record.tool_class for record in records} == {ToolClass.PACKAGE_AND_ADVISORY_METADATA}

    # Usage/cost is recorded exactly once per Gateway response, joined by the
    # Gateway-issued gateway_request_id.
    assert len(service.ledger.entries_for_run("run-1")) == 2
    assert service.ledger.gateway_request_ids(run_id="run-1") == {"gw-pkg-1", "gw-adv-1"}
    assert {entry.tool_class for entry in service.ledger.entries_for_run("run-1")} == {
        ToolClass.PACKAGE_AND_ADVISORY_METADATA
    }
    # Citations/summary text travel through untouched (untrusted, never executed).
    assert package_response["result"]["citations"] == ["https://pypi.org/project/pytest-asyncio/"]
    assert advisory_response["result"]["advisories"][0]["summary"] == "Untrusted summary text"


def test_package_lookup_rejects_mismatched_signal_before_any_gateway_call(monkeypatch):
    """A caller cannot smuggle a package-lookup request through by supplying a
    web-search-shaped signal/reason: the dispatcher rejects the mismatch
    before the dedicated service (and therefore the transport) is ever
    reached.
    """
    settings = _settings_with_only_optimus_credentials(monkeypatch)
    transport = CapturingPackageAdvisoryTransport()
    service = PackageAdvisoryService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    dispatcher = JsonRpcDispatcher(package_advisory_service=service)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "pkg-2",
            "method": "optimus.evidence.package_lookup",
            "params": {
                "run_id": "run-1",
                "package": "pytest-asyncio",
                "ecosystem": "pypi",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
            },
        }
    )

    assert response["error"]["code"] == -32600
    assert transport.requests == []
    assert service.ledger.entries == ()


def test_package_lookup_usage_less_response_never_creates_a_false_ledger_entry(monkeypatch):
    settings = _settings_with_only_optimus_credentials(monkeypatch)
    transport = UsageLessPackageLookupTransport()
    service = PackageAdvisoryService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    dispatcher = JsonRpcDispatcher(package_advisory_service=service)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "pkg-3",
            "method": "optimus.evidence.package_lookup",
            "params": {
                "run_id": "run-1",
                "package": "pytest-asyncio",
                "ecosystem": "pypi",
                "reason": "PACKAGE_VERSION",
                "policy_signal": "DEPENDENCY_VERSION_CHECK",
            },
        }
    )

    assert "error" in response
    assert len(transport.requests) == 1
    assert service.ledger.entries == ()
