"""Gateway tool route live evidence for Plan 11.2 (P11-FEAT-GATEWAY-TOOLS).

Task 4 (``requires_live_gateway``): starts the real ``serve_gateway``
``ThreadingHTTPServer`` on a loopback socket with a deterministic
server-side tool-provider bundle injected through ``GatewayToolDependencies``
(never an HTTP-layer fake).

Task 6 (``requires_gateway``): sends direct HTTP to an already-running staging
Gateway using only ``OPTIMUS_GATEWAY_URL`` and ``OPTIMUS_API_KEY``, proving
real §9D policy denials and real package/advisory success paths. No fake
server; no local unit-provider doubles.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from http.client import HTTPConnection
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from dotenv import dotenv_values

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

_SHARED_SECRET = "local-process-tools-secret"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


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


def _post_json(
    host: str,
    port: int,
    path: str,
    *,
    body: dict[str, Any],
    bearer: str | None = _SHARED_SECRET,
    timeout: float = 10,
):
    headers = {"Content-Type": "application/json"}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    connection = HTTPConnection(host, port, timeout=timeout)
    connection.request("POST", path, body=json.dumps(body), headers=headers)
    response = connection.getresponse()
    raw = response.read().decode("utf-8")
    return response.status, json.loads(raw)


def _context(**overrides: Any) -> dict[str, Any]:
    body = {"run_id": "run-local-process-1", "execution_mode": "agent"}
    body.update(overrides)
    return body


@pytest.mark.requires_live_gateway
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


@pytest.mark.requires_live_gateway
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


@pytest.mark.requires_live_gateway
def test_web_extract_rejects_url_without_prior_search_over_real_http(local_process_gateway):
    host, port = local_process_gateway

    status, body = _post_json(
        host, port, "/v1/tools/web/extract", body={"context": _context(), "urls": ["https://python.org/never-searched"]}
    )

    assert status == 403
    assert body["rule_id"] == "URL_NOT_IN_SEARCH_PROVENANCE"
    assert body["gateway_request_id"]


@pytest.mark.requires_live_gateway
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


@pytest.mark.requires_live_gateway
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


@pytest.mark.requires_live_gateway
def test_core_routes_remain_unaffected_alongside_tool_dependencies(local_process_gateway):
    host, port = local_process_gateway

    status, body = _post_json(
        host, port, "/v1/responses", body={"model": "claude-haiku", "input": "ping"}
    )

    assert status == 200
    assert body["output_text"] == "echo:ping"


@pytest.mark.requires_live_gateway
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


# --- Task 6: real staging Gateway §9D evidence (`requires_gateway`) -------------


def _load_dotenv_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = dotenv_values(path)
    return {key: value for key, value in values.items() if key and value is not None}


def _staging_credentials() -> tuple[str, int, str]:
    """Resolve host/port/bearer from the one-key agent surface only."""
    env = dict(os.environ)
    file_env = _load_dotenv_file(_PROJECT_ROOT / ".env")
    for key in ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY"):
        if not env.get(key, "").strip() and file_env.get(key, "").strip():
            env[key] = file_env[key].strip()

    gateway_url = env.get("OPTIMUS_GATEWAY_URL", "").strip()
    api_key = env.get("OPTIMUS_API_KEY", "").strip()
    if not gateway_url or not api_key:
        pytest.fail(
            "Plan 11.2 Task 6 requires OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY "
            "(agent one-key surface). Staging Gateway must already be running."
        )

    parsed = urlparse(gateway_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port, api_key


def _staging_context(**overrides: Any) -> dict[str, Any]:
    body = {"run_id": f"staging-{uuid.uuid4().hex}", "execution_mode": "agent"}
    body.update(overrides)
    return body


def _assert_gateway_request_id(body: dict[str, Any]) -> str:
    request_id = body.get("gateway_request_id") or (body.get("gateway_usage") or {}).get("gateway_request_id")
    assert isinstance(request_id, str) and request_id.startswith("gw-tool-"), body
    return request_id


def _assert_one_key_client_inputs() -> None:
    """Staging HTTP client resolves only OPTIMUS_GATEWAY_URL + OPTIMUS_API_KEY."""
    host, port, bearer = _staging_credentials()
    assert host and port and bearer


@pytest.fixture
def staging_gateway():
    _assert_one_key_client_inputs()
    return _staging_credentials()


@pytest.mark.requires_gateway
def test_staging_blocked_domain_search_is_denied(staging_gateway):
    host, port, bearer = staging_gateway
    status, body = _post_json(
        host,
        port,
        "/v1/tools/web/search",
        body={
            "context": _staging_context(run_id=f"staging-blocked-{uuid.uuid4().hex}"),
            "query": "staging blocked domain",
            "allowed_domains": ["evil.example"],
            "reason": "CURRENT_FACT",
        },
        bearer=bearer,
        timeout=30,
    )
    assert status == 403
    assert body["rule_id"] == "EMPTY_DOMAIN_INTERSECTION"
    _assert_gateway_request_id(body)


@pytest.mark.requires_gateway
def test_staging_extract_without_prior_search_is_denied(staging_gateway):
    host, port, bearer = staging_gateway
    status, body = _post_json(
        host,
        port,
        "/v1/tools/web/extract",
        body={
            "context": _staging_context(run_id=f"staging-extract-{uuid.uuid4().hex}"),
            "urls": ["https://python.org/downloads"],
        },
        bearer=bearer,
        timeout=30,
    )
    assert status == 403
    assert body["rule_id"] == "URL_NOT_IN_SEARCH_PROVENANCE"
    _assert_gateway_request_id(body)


@pytest.mark.requires_gateway
@pytest.mark.parametrize(
    ("reason", "label"),
    (
        ("PACKAGE_VERSION", "package"),
        ("SECURITY_ADVISORY", "advisory"),
    ),
)
def test_staging_web_search_rejects_package_or_advisory_reason(staging_gateway, reason: str, label: str):
    """Package/advisory intents must not authorize the web-search route.

    Package and advisory HTTP routes hardcode their policy signals; the
    Gateway-visible wrong-signal proof for those families is attempting to
    drive web search with package/advisory evidence reasons.
    """
    del label
    host, port, bearer = staging_gateway
    status, body = _post_json(
        host,
        port,
        "/v1/tools/web/search",
        body={
            "context": _staging_context(run_id=f"staging-wrong-signal-{uuid.uuid4().hex}"),
            "query": "should not authorize web search",
            "allowed_domains": ["python.org"],
            "reason": reason,
        },
        bearer=bearer,
        timeout=30,
    )
    assert status == 403
    assert body["rule_id"] == "POLICY_SIGNAL_MISMATCH"
    _assert_gateway_request_id(body)


@pytest.mark.requires_gateway
def test_staging_call_cap_overage_is_denied(staging_gateway):
    host, port, bearer = staging_gateway
    gateway_env = _load_dotenv_file(_PROJECT_ROOT / ".env.gateway")
    max_calls_raw = gateway_env.get("OPTIMUS_GATEWAY_TOOL_MAX_CALLS_PER_TOOL", "5").strip() or "5"
    max_calls = int(max_calls_raw)
    run_id = f"staging-cap-{uuid.uuid4().hex}"

    last_status = 0
    last_body: dict[str, Any] = {}
    for index in range(max_calls + 1):
        last_status, last_body = _post_json(
            host,
            port,
            "/v1/tools/package/lookup",
            body={
                "context": {"run_id": run_id, "execution_mode": "agent"},
                "package": "pytest",
                "ecosystem": "pypi",
            },
            bearer=bearer,
            timeout=60,
        )
        if last_status == 429:
            break
        assert last_status == 200, (index, last_status, last_body)

    assert last_status == 429, last_body
    assert last_body["rule_id"] == "CALL_CAP_EXCEEDED"
    _assert_gateway_request_id(last_body)


@pytest.mark.requires_gateway
def test_staging_package_lookup_success_path(staging_gateway):
    host, port, bearer = staging_gateway
    status, body = _post_json(
        host,
        port,
        "/v1/tools/package/lookup",
        body={
            "context": _staging_context(run_id=f"staging-pkg-{uuid.uuid4().hex}"),
            "package": "pytest",
            "ecosystem": "pypi",
        },
        bearer=bearer,
        timeout=60,
    )
    assert status == 200, body
    assert body["tool_class"] == "package_and_advisory_metadata"
    assert body["policy_signal"] == "DEPENDENCY_VERSION_CHECK"
    assert body["result"]["package"] == "pytest"
    assert body["result"]["ecosystem"] == "pypi"
    assert isinstance(body["result"]["latest_version"], str) and body["result"]["latest_version"]
    assert body["result"]["citations"]
    assert all(str(url).startswith("https://") for url in body["result"]["citations"])
    # Real PackageRegistryToolProvider labels usage by registry backend (pypi/npm/maven),
    # not the local-process fake's "package-registry" stand-in.
    assert body["gateway_usage"]["provider"] == "pypi"
    assert body["gateway_usage"]["cost_usd"] is not None
    assert body["gateway_usage"]["billing_units"] is not None
    _assert_gateway_request_id(body)


@pytest.mark.requires_gateway
def test_staging_security_advisory_success_path(staging_gateway):
    host, port, bearer = staging_gateway
    status, body = _post_json(
        host,
        port,
        "/v1/tools/security/advisory",
        body={
            "context": _staging_context(run_id=f"staging-adv-{uuid.uuid4().hex}"),
            "identifier": "pytest",
            "ecosystem": "pypi",
        },
        bearer=bearer,
        timeout=60,
    )
    assert status == 200, body
    assert body["tool_class"] == "package_and_advisory_metadata"
    assert body["policy_signal"] == "SECURITY_OR_CVE_CHECK"
    assert body["result"]["identifier"] == "pytest"
    assert body["result"]["ecosystem"] == "pypi"
    assert isinstance(body["result"]["advisories"], list) and body["result"]["advisories"]
    for advisory in body["result"]["advisories"]:
        assert advisory["advisory_id"]
        assert all(str(url).startswith("https://") for url in advisory.get("citations") or ())
    assert body["gateway_usage"]["provider"] == "osv"
    _assert_gateway_request_id(body)
