"""Local-process HTTP evidence for the four Gateway tool routes.

Plan 11.2 (``P11-FEAT-GATEWAY-TOOLS``), Task 4. Starts the real
``serve_gateway`` ``ThreadingHTTPServer`` bound to a real loopback socket in a
background thread, with a deterministic server-side tool-provider bundle
injected through the ``GatewayToolDependencies`` seam (never an HTTP-layer
fake). Every request in this module is a genuine HTTP round trip over a real
socket, exercising bearer auth, the four typed tool routes, and the
search-then-extract provenance sequence end to end.

This is Task 4's local-process artifact, not the real staging §9D policy
evidence reserved for Task 6 (`requires_gateway`, real credentials, real
provider revalidation against a live staging Gateway).
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.client import HTTPConnection
from typing import Any

import pytest

from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from optimus_gateway.tool_handlers import GatewayToolDependencies
from optimus_gateway.tool_models import (
    AdvisoryProviderResult,
    AdvisoryRecord,
    PackageProviderResult,
    ProviderUsage,
    WebExtractItem,
    WebExtractProviderResult,
    WebSearchProviderResult,
    WebSearchResult,
)
from optimus_gateway.tool_policy import GatewayToolPolicy
from optimus_gateway.tool_state import InMemoryGatewayToolStateStore
from optimus_gateway.upstream_client import ProviderMessageResult

pytestmark = pytest.mark.requires_live_gateway

_SHARED_SECRET = "local-process-tools-secret"


class _DeterministicUpstreamClient:
    """CORE model-route double; this module tests /v1/tools/*, not model routes."""

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        return ProviderMessageResult(message_id="msg-1", output_text=f"echo:{input_text}", input_tokens=1, output_tokens=1)


def _usage(**overrides: Any) -> ProviderUsage:
    fields: dict[str, Any] = {"provider": "tavily", "billing_units": 1, "cost_usd": "0.001", "cache_hit": False}
    fields.update(overrides)
    return ProviderUsage(**fields)


class _DeterministicWebProvider:
    """Real server-side adapter shape, deterministic upstream for local-process evidence."""

    def search(self, request):
        return WebSearchProviderResult(
            results=(
                WebSearchResult(url="https://python.org/downloads", title="Python downloads", snippet="Get Python"),
            ),
            usage=_usage(provider_request_id="tavily-req-1"),
        )

    def extract(self, request):
        return WebExtractProviderResult(
            items=tuple(
                WebExtractItem(url=url, title="Python downloads", content="Download the latest Python release.")
                for url in request.urls
            ),
            usage=_usage(provider_request_id="tavily-req-2", cache_hit=True),
        )


class _DeterministicPackageProvider:
    def lookup(self, request):
        return PackageProviderResult(
            package=request.package,
            ecosystem=request.ecosystem,
            usage=_usage(provider="package-registry"),
            requested_version=request.version,
            latest_version="1.2.3",
            citations=(f"https://pypi.org/project/{request.package}/",),
        )


class _DeterministicAdvisoryProvider:
    def lookup(self, request):
        return AdvisoryProviderResult(
            identifier=request.identifier,
            usage=_usage(provider="osv"),
            ecosystem=request.ecosystem,
            advisories=(
                AdvisoryRecord(
                    advisory_id="GHSA-local-1",
                    summary="Example locally-served advisory",
                    severity="low",
                    citations=(f"https://pypi.org/project/{request.identifier}/",),
                ),
            ),
        )


def _config() -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        shared_secret=_SHARED_SECRET,
        provider="openrouter",
        provider_api_key="or-test",
        base_url="https://openrouter.ai/api/v1",
    )


def _tool_dependencies() -> GatewayToolDependencies:
    return GatewayToolDependencies(
        web_provider=_DeterministicWebProvider(),
        package_provider=_DeterministicPackageProvider(),
        advisory_provider=_DeterministicAdvisoryProvider(),
        policy=GatewayToolPolicy(allowed_domains=("python.org", "pypi.org")),
        state_store=InMemoryGatewayToolStateStore(),
    )


@pytest.fixture
def local_process_gateway():
    server = serve_gateway(
        config=_config(), upstream_client=_DeterministicUpstreamClient(), tool_dependencies=_tool_dependencies()
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield host, port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _post_json(host: str, port: int, path: str, *, body: dict[str, Any], bearer: str | None = _SHARED_SECRET):
    headers = {"Content-Type": "application/json"}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    connection = HTTPConnection(host, port, timeout=10)
    connection.request("POST", path, body=json.dumps(body), headers=headers)
    response = connection.getresponse()
    raw = response.read().decode("utf-8")
    return response.status, json.loads(raw)


def _context(**overrides: Any) -> dict[str, Any]:
    body = {"run_id": "run-local-process-1", "execution_mode": "agent"}
    body.update(overrides)
    return body


def test_web_search_route_served_over_real_http_with_bearer_auth(local_process_gateway):
    host, port = local_process_gateway

    unauthorized_status, unauthorized_body = _post_json(
        host,
        port,
        "/v1/tools/web/search",
        body={"context": _context(), "query": "python downloads", "allowed_domains": ["python.org"], "reason": "CURRENT_FACT"},
        bearer="wrong-secret",
    )
    assert unauthorized_status == 401
    assert unauthorized_body == {"error": "unauthorized"}

    status, body = _post_json(
        host,
        port,
        "/v1/tools/web/search",
        body={"context": _context(), "query": "python downloads", "allowed_domains": ["python.org"], "reason": "CURRENT_FACT"},
    )

    assert status == 200
    assert body["tool_class"] == "web_search"
    assert body["policy_signal"] == "CURRENT_OR_LATEST_FACT"
    assert body["result"]["results"][0]["url"] == "https://python.org/downloads"
    assert body["provenance"]["search_id"]
    assert body["gateway_usage"]["gateway_request_id"].startswith("gw-tool-")
    assert body["gateway_usage"]["provider"] == "tavily"


def test_search_then_extract_provenance_sequence_over_real_http(local_process_gateway):
    host, port = local_process_gateway

    search_status, search_body = _post_json(
        host,
        port,
        "/v1/tools/web/search",
        body={"context": _context(), "query": "python downloads", "allowed_domains": ["python.org"], "reason": "CURRENT_FACT"},
    )
    assert search_status == 200
    searched_url = search_body["result"]["results"][0]["url"]

    extract_status, extract_body = _post_json(
        host, port, "/v1/tools/web/extract", body={"context": _context(), "urls": [searched_url]}
    )

    assert extract_status == 200
    assert extract_body["tool_class"] == "web_extract"
    assert extract_body["result"]["items"][0]["url"] == searched_url
    assert extract_body["gateway_usage"]["cache_hit"] is True


def test_web_extract_rejects_url_without_prior_search_over_real_http(local_process_gateway):
    host, port = local_process_gateway

    status, body = _post_json(
        host, port, "/v1/tools/web/extract", body={"context": _context(), "urls": ["https://python.org/never-searched"]}
    )

    assert status == 403
    assert body["rule_id"] == "URL_NOT_IN_SEARCH_PROVENANCE"
    assert body["gateway_request_id"]


def test_package_lookup_route_served_over_real_http(local_process_gateway):
    host, port = local_process_gateway

    status, body = _post_json(
        host,
        port,
        "/v1/tools/package/lookup",
        body={"context": _context(), "package": "pytest-asyncio", "ecosystem": "pypi"},
    )

    assert status == 200
    assert body["tool_class"] == "package_and_advisory_metadata"
    assert body["policy_signal"] == "DEPENDENCY_VERSION_CHECK"
    assert body["result"]["package"] == "pytest-asyncio"
    assert body["result"]["latest_version"] == "1.2.3"
    assert body["provenance"]["source_urls"] == ["https://pypi.org/project/pytest-asyncio/"]
    assert body["gateway_usage"]["provider"] == "package-registry"


def test_security_advisory_route_served_over_real_http(local_process_gateway):
    host, port = local_process_gateway

    status, body = _post_json(
        host,
        port,
        "/v1/tools/security/advisory",
        body={"context": _context(), "identifier": "pytest-asyncio", "ecosystem": "pypi"},
    )

    assert status == 200
    assert body["tool_class"] == "package_and_advisory_metadata"
    assert body["policy_signal"] == "SECURITY_OR_CVE_CHECK"
    assert body["result"]["advisories"][0]["advisory_id"] == "GHSA-local-1"
    assert body["gateway_usage"]["provider"] == "osv"


def test_core_routes_remain_unaffected_alongside_tool_dependencies(local_process_gateway):
    host, port = local_process_gateway

    status, body = _post_json(
        host, port, "/v1/responses", body={"model": "claude-haiku", "input": "ping"}
    )

    assert status == 200
    assert body["output_text"] == "echo:ping"


def test_unknown_route_still_returns_not_found(local_process_gateway):
    host, port = local_process_gateway

    request = urllib.request.Request(
        f"http://{host}:{port}/v1/unknown",
        data=json.dumps({"x": 1}).encode("utf-8"),
        headers={"Authorization": f"Bearer {_SHARED_SECRET}", "Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request, timeout=10)

    assert excinfo.value.code == 404
