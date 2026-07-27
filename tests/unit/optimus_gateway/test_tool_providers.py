from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import urlparse

import pytest

from optimus_gateway.models import GatewayToolContext
from optimus_gateway.tool_models import (
    AdvisoryProviderResult,
    PackageLookupGatewayRequest,
    PackageProviderResult,
    SecurityAdvisoryGatewayRequest,
    WebExtractGatewayRequest,
    WebExtractProviderResult,
    WebSearchGatewayRequest,
    WebSearchProviderResult,
)
from optimus_gateway.tool_providers import (
    OsvAdvisoryToolProvider,
    PackageRegistryToolProvider,
    TavilyWebToolProvider,
    ToolProviderError,
)


class _Response:
    def __init__(self, body: object) -> None:
        self._body = json.dumps(body).encode()

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _RawResponse(_Response):
    def __init__(self, body: bytes) -> None:
        self._body = body


def _request(*, query: str = "python", depth: str = "basic", cap: int = 5) -> WebSearchGatewayRequest:
    return WebSearchGatewayRequest(
        context=GatewayToolContext(run_id="run-1", authenticated_subject="gateway-client"),
        query=query,
        allowed_domains=("python.org",),
        result_cap=cap,
        search_depth=depth,
    )


def _extract_request(*, max_chars: int = 10) -> WebExtractGatewayRequest:
    return WebExtractGatewayRequest(
        context=GatewayToolContext(run_id="run-1", authenticated_subject="gateway-client"),
        urls=("https://python.org/",),
        max_chars_per_source=max_chars,
    )


def test_search_normalizes_https_results_and_usage() -> None:
    captured: list[dict[str, object]] = []

    def fake_urlopen(request, *, timeout):
        captured.append(json.loads(request.data))
        return _Response(
            {
                "results": [
                    {"url": "https://python.org/docs", "title": "Docs", "content": "A snippet"},
                    {"url": "http://insecure.example", "title": "Drop", "content": "No"},
                ]
            }
        )

    provider = TavilyWebToolProvider(
        api_key="tavily-secret",
        base_url="https://api.tavily.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    result = provider.search(_request())

    assert isinstance(result, WebSearchProviderResult)
    assert [(item.url, item.title, item.snippet) for item in result.results] == [
        ("https://python.org/docs", "Docs", "A snippet")
    ]
    assert result.usage.provider == "tavily"
    assert result.usage.billing_units == 0
    assert result.usage.cost_usd == "0"
    assert captured[0]["query"] == "python"
    assert captured[0]["max_results"] == 5


def test_search_passes_advanced_depth_and_request_cap() -> None:
    captured: list[dict[str, object]] = []

    def fake_urlopen(request, *, timeout):
        captured.append(json.loads(request.data))
        return _Response({"results": []})

    provider = TavilyWebToolProvider(
        api_key="secret",
        base_url="https://api.tavily.example/",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    provider.search(_request(depth="advanced", cap=5))

    assert captured[0]["search_depth"] == "advanced"
    assert captured[0]["max_results"] == 5


def test_extract_normalizes_https_items_and_truncates_content() -> None:
    def fake_urlopen(request, *, timeout):
        return _Response(
            {
                "results": [
                    {
                        "url": "https://python.org/",
                        "title": "Python",
                        "raw_content": "0123456789-extra",
                    },
                    {"url": "http://insecure.example", "raw_content": "drop"},
                ]
            }
        )

    provider = TavilyWebToolProvider(
        api_key="secret",
        base_url="https://api.tavily.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    result = provider.extract(_extract_request(max_chars=10))

    assert isinstance(result, WebExtractProviderResult)
    assert [(item.url, item.title, item.content) for item in result.items] == [
        ("https://python.org/", "Python", "0123456789")
    ]


@pytest.mark.parametrize("failure", ["timeout", "http"])
def test_upstream_failures_raise_sanitized_provider_error(failure: str) -> None:
    api_key = "super-secret-tavily-key"

    def fake_urlopen(request, *, timeout):
        if failure == "timeout":
            raise TimeoutError(f"{api_key} timed out")
        raise HTTPError(request.full_url, 503, f"failure {api_key}", {}, BytesIO(b"raw secret body"))

    provider = TavilyWebToolProvider(
        api_key=api_key,
        base_url="https://api.tavily.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    with pytest.raises(ToolProviderError) as exc_info:
        provider.search(_request())

    assert api_key not in str(exc_info.value)
    assert "raw secret body" not in str(exc_info.value)


def test_malformed_body_raises_sanitized_provider_error() -> None:
    api_key = "super-secret-tavily-key"

    def fake_urlopen(request, *, timeout):
        return _Response({"unexpected": api_key})

    provider = TavilyWebToolProvider(
        api_key=api_key,
        base_url="https://api.tavily.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    with pytest.raises(ToolProviderError) as exc_info:
        provider.search(_request())

    assert api_key not in str(exc_info.value)


def _package_request(ecosystem: str, package: str, version: str | None = None) -> PackageLookupGatewayRequest:
    return PackageLookupGatewayRequest(
        context=GatewayToolContext(run_id="run-1", authenticated_subject="gateway-client"),
        package=package,
        ecosystem=ecosystem,
        version=version,
    )


def _advisory_request(
    identifier: str = "demo-package",
    ecosystem: str | None = "npm",
    version: str | None = "1.2.3",
) -> SecurityAdvisoryGatewayRequest:
    return SecurityAdvisoryGatewayRequest(
        context=GatewayToolContext(run_id="run-1", authenticated_subject="gateway-client"),
        identifier=identifier,
        ecosystem=ecosystem,
        version=version,
    )


def test_package_lookup_normalizes_pypi_metadata_and_drops_http_citations() -> None:
    def fake_urlopen(request, *, timeout):
        assert request.full_url == "https://pypi.example/pypi/demo/json"
        return _Response(
            {
                "info": {"version": "2.0.0", "project_urls": {"Docs": "https://docs.example/demo"}},
                "releases": {
                    "1.0.0": [{"upload_time_iso_8601": "2025-01-01T00:00:00Z", "url": "https://files.example/1"}],
                    "2.0.0": [
                        {"upload_time_iso_8601": "2025-02-01T00:00:00Z", "url": "http://files.example/2"},
                    ],
                },
            }
        )

    provider = PackageRegistryToolProvider(
        pypi_base_url="https://pypi.example",
        npm_base_url="https://npm.example",
        maven_base_url="https://maven.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    result = provider.lookup(_package_request("pypi", "demo", "1.0.0"))

    assert isinstance(result, PackageProviderResult)
    assert result.latest_version == "2.0.0"
    assert [record.version for record in result.versions] == ["1.0.0", "2.0.0"]
    assert all(urlparse(url).scheme == "https" for url in result.citations)
    assert result.usage.provider == "pypi"


def test_package_lookup_normalizes_npm_scoped_metadata() -> None:
    def fake_urlopen(request, *, timeout):
        assert "%40scope%2Fdemo" in request.full_url
        return _Response(
            {
                "dist-tags": {"latest": "3.0.0"},
                "versions": {"2.0.0": {}, "3.0.0": {}},
                "time": {"2.0.0": "2025-01-01T00:00:00Z", "3.0.0": "2025-03-01T00:00:00Z"},
            }
        )

    provider = PackageRegistryToolProvider(
        pypi_base_url="https://pypi.example",
        npm_base_url="https://npm.example",
        maven_base_url="https://maven.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    result = provider.lookup(_package_request("npm", "@scope/demo"))

    assert result.latest_version == "3.0.0"
    assert [record.version for record in result.versions] == ["2.0.0", "3.0.0"]
    assert result.usage.provider == "npm"


def test_package_lookup_normalizes_maven_metadata() -> None:
    def fake_urlopen(request, *, timeout):
        assert request.full_url == "https://maven.example/org/demo/maven-metadata.xml"
        return _RawResponse(
            b"""<metadata><versioning><latest>1.1.0</latest><versions>
            <version>1.0.0</version><version>1.1.0</version>
            </versions></versioning></metadata>"""
        )

    provider = PackageRegistryToolProvider(
        pypi_base_url="https://pypi.example",
        npm_base_url="https://npm.example",
        maven_base_url="https://maven.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    result = provider.lookup(_package_request("maven", "org:demo"))

    assert result.latest_version == "1.1.0"
    assert [record.version for record in result.versions] == ["1.0.0", "1.1.0"]
    assert result.usage.provider == "maven"


def test_package_lookup_rejects_malformed_pypi_metadata() -> None:
    def fake_urlopen(request, *, timeout):
        return _Response({"info": "not-an-object", "releases": {}})

    provider = PackageRegistryToolProvider(
        pypi_base_url="https://pypi.example",
        npm_base_url="https://npm.example",
        maven_base_url="https://maven.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    with pytest.raises(ToolProviderError, match="invalid"):
        provider.lookup(_package_request("pypi", "demo"))


def test_package_lookup_rejects_malformed_npm_metadata() -> None:
    def fake_urlopen(request, *, timeout):
        return _Response({"dist-tags": "not-an-object", "versions": {}})

    provider = PackageRegistryToolProvider(
        pypi_base_url="https://pypi.example",
        npm_base_url="https://npm.example",
        maven_base_url="https://maven.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    with pytest.raises(ToolProviderError, match="invalid"):
        provider.lookup(_package_request("npm", "demo"))


def test_maven_lookup_rejects_entity_expansion_payload() -> None:
    """Prove defusedxml hardening engages on untrusted Maven metadata XML."""

    billion_laughs = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<metadata>&lol3;</metadata>
"""

    def fake_urlopen(request, *, timeout):
        return _RawResponse(billion_laughs)

    provider = PackageRegistryToolProvider(
        pypi_base_url="https://pypi.example",
        npm_base_url="https://npm.example",
        maven_base_url="https://maven.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    with pytest.raises(ToolProviderError, match="invalid"):
        provider.lookup(_package_request("maven", "org:demo"))


def test_osv_lookup_posts_query_and_normalizes_https_references() -> None:
    captured: list[dict[str, object]] = []

    def fake_urlopen(request, *, timeout):
        captured.append(json.loads(request.data))
        return _Response(
            {
                "vulns": [
                    {
                        "id": "GHSA-xxxx-yyyy-zzzz",
                        "summary": "Untrusted advisory text",
                        "severity": [{"type": "CVSS_V3", "score": "9.8"}],
                        "affected": [
                            {
                                "ranges": [{"events": [{"introduced": "0"}, {"fixed": "1.2.4"}]}],
                            }
                        ],
                        "references": [
                            {"url": "https://github.com/advisories/GHSA-xxxx-yyyy-zzzz"},
                            {"url": "http://insecure.example/advisory"},
                        ],
                    }
                ]
            }
        )

    provider = OsvAdvisoryToolProvider(
        base_url="https://osv.example",
        api_key="osv-secret",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    result = provider.lookup(_advisory_request())

    assert isinstance(result, AdvisoryProviderResult)
    assert captured == [{"package": {"name": "demo-package", "ecosystem": "npm"}, "version": "1.2.3"}]
    assert result.advisories[0].fixed_versions == ("1.2.4",)
    assert result.advisories[0].citations == ("https://github.com/advisories/GHSA-xxxx-yyyy-zzzz",)
    assert result.usage.provider == "osv"


@pytest.mark.parametrize(
    ("wire_ecosystem", "osv_ecosystem"),
    (
        ("pypi", "PyPI"),
        ("npm", "npm"),
        ("maven", "Maven"),
    ),
)
def test_osv_query_maps_ecosystem_casing_for_outgoing_payload_only(
    wire_ecosystem: str,
    osv_ecosystem: str,
) -> None:
    """OSV /v1/query needs mixed-case ecosystems; the wire/result contract stays lowercase."""
    captured: list[dict[str, object]] = []

    def fake_urlopen(request, *, timeout):
        assert request.get_method() == "POST"
        assert request.full_url.endswith("/v1/query")
        captured.append(json.loads(request.data))
        return _Response({"vulns": []})

    provider = OsvAdvisoryToolProvider(
        base_url="https://osv.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    result = provider.lookup(_advisory_request(ecosystem=wire_ecosystem))

    assert captured == [
        {"package": {"name": "demo-package", "ecosystem": osv_ecosystem}, "version": "1.2.3"}
    ]
    assert result.ecosystem == wire_ecosystem


def test_osv_vuln_id_lookup_does_not_send_ecosystem_field() -> None:
    captured_urls: list[str] = []

    def fake_urlopen(request, *, timeout):
        captured_urls.append(request.full_url)
        assert request.data is None
        return _Response({"id": "GHSA-xxxx-yyyy-zzzz", "summary": "id path", "affected": [], "references": []})

    provider = OsvAdvisoryToolProvider(
        base_url="https://osv.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    result = provider.lookup(_advisory_request(identifier="GHSA-xxxx-yyyy-zzzz", ecosystem="pypi"))

    assert captured_urls == ["https://osv.example/vulns/GHSA-xxxx-yyyy-zzzz"]
    assert result.ecosystem == "pypi"


def test_osv_lookup_rejects_null_affected_and_references() -> None:
    def fake_urlopen(request, *, timeout):
        return _Response(
            {
                "vulns": [
                    {
                        "id": "GHSA-xxxx-yyyy-zzzz",
                        "summary": "Broken nested fields",
                        "affected": None,
                        "references": None,
                    }
                ]
            }
        )

    provider = OsvAdvisoryToolProvider(
        base_url="https://osv.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    with pytest.raises(ToolProviderError, match="invalid"):
        provider.lookup(_advisory_request())


def test_osv_lookup_rejects_non_object_advisory_entries() -> None:
    def fake_urlopen(request, *, timeout):
        return _Response({"vulns": ["not-an-object"]})

    provider = OsvAdvisoryToolProvider(
        base_url="https://osv.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    with pytest.raises(ToolProviderError, match="invalid"):
        provider.lookup(_advisory_request())


def test_maven_citations_are_url_encoded() -> None:
    def fake_urlopen(request, *, timeout):
        return _RawResponse(
            b"""<metadata><versioning><latest>1.0.0</latest><versions>
            <version>1.0.0</version>
            </versions></versioning></metadata>"""
        )

    provider = PackageRegistryToolProvider(
        pypi_base_url="https://pypi.example",
        npm_base_url="https://npm.example",
        maven_base_url="https://maven.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )
    result = provider.lookup(_package_request("maven", "com.example:demo artifact"))

    assert result.citations == ("https://central.sonatype.com/artifact/com.example/demo%20artifact",)
    assert result.versions[0].source_url == (
        "https://central.sonatype.com/artifact/com.example/demo%20artifact/1.0.0"
    )


@pytest.mark.parametrize("failure", ["timeout", "http_transient", "http_permanent", "os_error"])
def test_maven_request_bytes_upstream_failures_raise_sanitized_provider_error(failure: str) -> None:
    """Maven metadata uses request_bytes; prove the same sanitization as request_json paths."""
    secret = "maven-super-secret-token"

    def fake_urlopen(request, *, timeout):
        del timeout
        assert "maven-metadata.xml" in request.full_url
        if failure == "timeout":
            raise TimeoutError(f"{secret} timed out")
        if failure == "os_error":
            raise OSError(f"socket blowup {secret}")
        status = 503 if failure == "http_transient" else 404
        raise HTTPError(
            request.full_url,
            status,
            f"failure {secret}",
            {},
            BytesIO(f"raw body {secret}".encode()),
        )

    provider = PackageRegistryToolProvider(
        pypi_base_url="https://pypi.example",
        npm_base_url="https://npm.example",
        maven_base_url="https://maven.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    with pytest.raises(ToolProviderError) as exc_info:
        provider.lookup(_package_request("maven", "com.example:demo"))

    message = str(exc_info.value)
    assert message == "Maven lookup failed"
    assert secret not in message
    assert "raw body" not in message
    assert "socket blowup" not in message


@pytest.mark.parametrize("provider_kind", ["registry", "osv"])
def test_provider_upstream_faults_are_sanitized(provider_kind: str) -> None:
    secret = "provider-super-secret"

    def fake_urlopen(request, *, timeout):
        raise HTTPError(request.full_url, 503, secret, {}, BytesIO(secret.encode()))

    if provider_kind == "registry":
        provider = PackageRegistryToolProvider(
            pypi_base_url="https://pypi.example",
            npm_base_url="https://npm.example",
            maven_base_url="https://maven.example",
            urlopen=fake_urlopen,
            sleep=lambda _: None,
        )
        def operation():
            return provider.lookup(_package_request("pypi", "demo"))
    else:
        provider = OsvAdvisoryToolProvider(
            base_url="https://osv.example",
            api_key=secret,
            urlopen=fake_urlopen,
            sleep=lambda _: None,
        )
        def operation():
            return provider.lookup(_advisory_request())

    with pytest.raises(ToolProviderError) as exc_info:
        operation()

    assert secret not in str(exc_info.value)
    assert "provider-super-secret" not in str(exc_info.value)
