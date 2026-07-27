"""Contract tests for the shared typed-tool models in ``optimus.gateway.tool_models``.

These models are consumed by both the local client and (in later tasks) the Gateway
server. Task 1 scope is limited to the shared Pydantic contracts and does not include
Gateway server handlers, ACP dispatcher wiring, or the package/advisory service.
"""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import GatewayUsage
from optimus.gateway.tool_models import (
    AdvisoryRecord,
    GatewayToolContext,
    GatewayToolEnvelope,
    GatewayToolProvenance,
    PackageLookupRequest,
    PackageLookupResult,
    PackageVersionRecord,
    SecurityAdvisoryRequest,
    SecurityAdvisoryResult,
    WebExtractItem,
    WebExtractRequest,
    WebExtractResultSet,
    WebSearchRequest,
    WebSearchResult,
    WebSearchResultSet,
    parse_gateway_tool_envelope,
)
from optimus.tools.policy import ToolClass, ToolPolicySignal


def _usage(**overrides) -> GatewayUsage:
    fields = {
        "gateway_request_id": "gw-tool-1",
        "provider": "tavily",
        "cache_hit": False,
        "billing_units": 1,
        "cost_usd": Decimal("0.001"),
    }
    fields.update(overrides)
    return GatewayUsage(**fields)


# --- GatewayToolContext -----------------------------------------------------


def test_gateway_tool_context_accepts_full_metadata():
    context = GatewayToolContext(
        run_id="run-1",
        session_id="session-1",
        execution_mode="AGENT",
        org_id="org-1",
        project_id="project-1",
        model="glm-5.2",
    )

    assert context.run_id == "run-1"
    assert context.execution_mode == "AGENT"


def test_gateway_tool_context_rejects_empty_run_id():
    with pytest.raises(ValidationError):
        GatewayToolContext(run_id="", session_id=None, execution_mode="AGENT")


def test_gateway_tool_context_is_frozen():
    context = GatewayToolContext(run_id="run-1", execution_mode="AGENT")
    with pytest.raises(ValidationError):
        context.run_id = "run-2"


# --- GatewayToolProvenance ---------------------------------------------------


def test_gateway_tool_provenance_defaults_untrusted():
    provenance = GatewayToolProvenance(
        search_id="search-1",
        source_urls=("https://docs.example.com/a",),
    )

    assert provenance.trust == "untrusted"
    assert provenance.source_urls[0].host == "docs.example.com"


def test_gateway_tool_provenance_rejects_non_https_source_url():
    with pytest.raises(ValidationError):
        GatewayToolProvenance(search_id="search-1", source_urls=("http://docs.example.com/a",))


# --- Web search / extract request contracts ---------------------------------


def test_web_search_request_rejects_empty_query():
    with pytest.raises(ValidationError):
        WebSearchRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            query="",
            allowed_domains=("docs.python.org",),
        )


@pytest.mark.parametrize("result_cap", [0, 11])
def test_web_search_request_rejects_result_cap_out_of_bounds(result_cap):
    with pytest.raises(ValidationError):
        WebSearchRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            query="latest pytest release",
            allowed_domains=("docs.python.org",),
            result_cap=result_cap,
        )


def test_web_search_request_accepts_bounded_result_cap():
    request = WebSearchRequest(
        context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
        query="latest pytest release",
        allowed_domains=("docs.python.org",),
        result_cap=10,
        search_depth="advanced",
    )

    assert request.result_cap == 10
    assert request.search_depth == "advanced"


def test_web_extract_request_maps_single_url_to_urls():
    request = WebExtractRequest(
        context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
        url="https://docs.example.com/a",
    )

    assert request.urls == (request.urls[0],)
    assert str(request.urls[0]) == "https://docs.example.com/a"
    assert request.max_chars_per_source == 4000


def test_web_extract_request_rejects_mixed_url_and_urls_forms():
    with pytest.raises(ValidationError):
        WebExtractRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            url="https://docs.example.com/a",
            urls=("https://docs.example.com/b",),
        )


def test_web_extract_request_rejects_when_neither_url_nor_urls_supplied():
    with pytest.raises(ValidationError):
        WebExtractRequest(context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"))


def test_web_extract_request_rejects_duplicate_urls():
    with pytest.raises(ValidationError):
        WebExtractRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            urls=(
                "https://docs.example.com/a",
                "https://docs.example.com/a",
            ),
        )


def test_web_extract_request_rejects_non_https_url():
    with pytest.raises(ValidationError):
        WebExtractRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            urls=("http://docs.example.com/a",),
        )


def test_web_extract_request_rejects_more_than_ten_urls():
    urls = tuple(f"https://docs.example.com/{i}" for i in range(11))
    with pytest.raises(ValidationError):
        WebExtractRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            urls=urls,
        )


@pytest.mark.parametrize("max_chars", [0, 20001])
def test_web_extract_request_rejects_max_chars_out_of_bounds(max_chars):
    with pytest.raises(ValidationError):
        WebExtractRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            urls=("https://docs.example.com/a",),
            max_chars_per_source=max_chars,
        )


def test_web_extract_request_accepts_max_chars_upper_bound():
    request = WebExtractRequest(
        context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
        urls=("https://docs.example.com/a",),
        max_chars_per_source=20000,
    )

    assert request.max_chars_per_source == 20000


# --- Package lookup / security advisory request contracts -------------------


def test_package_lookup_request_rejects_empty_package():
    with pytest.raises(ValidationError):
        PackageLookupRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            package="",
            ecosystem="pypi",
        )


def test_package_lookup_request_rejects_unsupported_ecosystem():
    with pytest.raises(ValidationError):
        PackageLookupRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            package="pytest-asyncio",
            ecosystem="cargo",
        )


def test_package_lookup_request_accepts_supported_ecosystems():
    for ecosystem in ("pypi", "npm", "maven"):
        request = PackageLookupRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            package="pytest-asyncio",
            ecosystem=ecosystem,
            version="0.24.0",
        )
        assert request.ecosystem == ecosystem


def test_security_advisory_request_rejects_empty_identifier():
    with pytest.raises(ValidationError):
        SecurityAdvisoryRequest(
            context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
            identifier="",
        )


def test_security_advisory_request_accepts_optional_ecosystem_and_version():
    request = SecurityAdvisoryRequest(
        context=GatewayToolContext(run_id="run-1", execution_mode="AGENT"),
        identifier="CVE-2026-12345",
        ecosystem="npm",
        version="1.2.3",
    )

    assert request.identifier == "CVE-2026-12345"
    assert request.ecosystem == "npm"


# --- Result types -------------------------------------------------------------


def test_package_lookup_result_requires_https_citations():
    with pytest.raises(ValidationError):
        PackageLookupResult(
            package="pytest-asyncio",
            ecosystem="pypi",
            requested_version=None,
            latest_version="0.24.0",
            versions=(
                PackageVersionRecord(
                    version="0.24.0",
                    released_at="2026-01-01",
                    source_url="https://pypi.org/project/pytest-asyncio/0.24.0/",
                ),
            ),
            citations=("http://pypi.org/project/pytest-asyncio/",),
        )


def test_package_lookup_result_accepts_exact_fields():
    result = PackageLookupResult(
        package="pytest-asyncio",
        ecosystem="pypi",
        requested_version="0.23.0",
        latest_version="0.24.0",
        versions=(
            PackageVersionRecord(
                version="0.24.0",
                released_at="2026-01-01",
                source_url="https://pypi.org/project/pytest-asyncio/0.24.0/",
            ),
        ),
        citations=("https://pypi.org/project/pytest-asyncio/",),
    )

    assert result.latest_version == "0.24.0"
    assert result.versions[0].version == "0.24.0"


def test_security_advisory_result_accepts_exact_fields():
    result = SecurityAdvisoryResult(
        identifier="CVE-2026-12345",
        ecosystem="npm",
        version="1.2.3",
        advisories=(
            AdvisoryRecord(
                advisory_id="GHSA-xxxx-yyyy-zzzz",
                summary="Untrusted summary text",
                severity="high",
                affected_ranges=("<1.2.4",),
                fixed_versions=("1.2.4",),
                citations=("https://github.com/advisories/GHSA-xxxx-yyyy-zzzz",),
            ),
        ),
    )

    assert result.advisories[0].advisory_id == "GHSA-xxxx-yyyy-zzzz"


def test_advisory_record_requires_https_citations():
    with pytest.raises(ValidationError):
        AdvisoryRecord(
            advisory_id="GHSA-xxxx-yyyy-zzzz",
            summary="Untrusted summary text",
            severity="high",
            affected_ranges=("<1.2.4",),
            fixed_versions=("1.2.4",),
            citations=("http://github.com/advisories/GHSA-xxxx-yyyy-zzzz",),
        )


def test_web_search_result_set_accepts_https_results():
    result_set = WebSearchResultSet(
        results=(
            WebSearchResult(title="Docs", url="https://docs.example.com/a", snippet="text"),
        )
    )

    assert result_set.results[0].url.host == "docs.example.com"


def test_web_extract_result_set_carries_untrusted_content():
    result_set = WebExtractResultSet(
        items=(
            WebExtractItem(url="https://docs.example.com/a", title="Docs", content="page text"),
        )
    )

    assert result_set.items[0].content == "page text"


# --- GatewayToolEnvelope ------------------------------------------------------


def test_web_search_envelope_accepts_exact_success_shape():
    envelope = GatewayToolEnvelope[WebSearchResultSet](
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        run_id="run-1",
        result=WebSearchResultSet(results=()),
        provenance=GatewayToolProvenance(search_id="search-1", source_urls=()),
        gateway_usage=_usage(),
    )

    assert envelope.gateway_usage.cost_usd == Decimal("0.001")
    assert envelope.provenance.trust == "untrusted"


def test_package_lookup_envelope_accepts_exact_success_shape():
    envelope = GatewayToolEnvelope[PackageLookupResult](
        tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
        policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        run_id="run-1",
        result=PackageLookupResult(
            package="pytest-asyncio",
            ecosystem="pypi",
            requested_version=None,
            latest_version="0.24.0",
            versions=(),
            citations=("https://pypi.org/project/pytest-asyncio/",),
        ),
        provenance=GatewayToolProvenance(search_id=None, source_urls=()),
        gateway_usage=_usage(gateway_request_id="gw-pkg-1", provider="package-registry"),
    )

    assert envelope.tool_class is ToolClass.PACKAGE_AND_ADVISORY_METADATA
    assert envelope.policy_signal is ToolPolicySignal.DEPENDENCY_VERSION_CHECK


def test_security_advisory_envelope_accepts_exact_success_shape():
    envelope = GatewayToolEnvelope[SecurityAdvisoryResult](
        tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
        policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK,
        run_id="run-1",
        result=SecurityAdvisoryResult(
            identifier="CVE-2026-12345",
            ecosystem="npm",
            version="1.2.3",
            advisories=(),
        ),
        provenance=GatewayToolProvenance(search_id=None, source_urls=()),
        gateway_usage=_usage(gateway_request_id="gw-adv-1", provider="osv"),
    )

    assert envelope.result.identifier == "CVE-2026-12345"


def test_envelope_is_frozen():
    envelope = GatewayToolEnvelope[WebSearchResultSet](
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        run_id="run-1",
        result=WebSearchResultSet(results=()),
        provenance=GatewayToolProvenance(search_id=None, source_urls=()),
        gateway_usage=_usage(),
    )

    with pytest.raises(ValidationError):
        envelope.run_id = "run-2"


# --- parse_gateway_tool_envelope fail-closed behavior -------------------------


def test_parse_gateway_tool_envelope_fails_closed_on_missing_usage():
    body = {
        "tool_class": "web_search",
        "policy_signal": "CURRENT_OR_LATEST_FACT",
        "run_id": "run-1",
        "result": {"results": []},
        "provenance": {"search_id": None, "source_urls": []},
    }

    with pytest.raises(GatewayResponseError) as exc_info:
        parse_gateway_tool_envelope(body, WebSearchResultSet)

    assert exc_info.value.audit_code == "GATEWAY_USAGE_MISSING"


def test_parse_gateway_tool_envelope_fails_closed_on_null_usage():
    body = {
        "tool_class": "web_search",
        "policy_signal": "CURRENT_OR_LATEST_FACT",
        "run_id": "run-1",
        "result": {"results": []},
        "provenance": {"search_id": None, "source_urls": []},
        "gateway_usage": None,
    }

    with pytest.raises(GatewayResponseError) as exc_info:
        parse_gateway_tool_envelope(body, WebSearchResultSet)

    assert exc_info.value.audit_code == "GATEWAY_USAGE_MISSING"


def test_parse_gateway_tool_envelope_fails_closed_on_malformed_usage():
    body = {
        "tool_class": "web_search",
        "policy_signal": "CURRENT_OR_LATEST_FACT",
        "run_id": "run-1",
        "result": {"results": []},
        "provenance": {"search_id": None, "source_urls": []},
        "gateway_usage": {
            "gateway_request_id": "",
            "provider": "tavily",
            "billing_units": 1,
            "cost_usd": "0.001",
        },
    }

    with pytest.raises(GatewayResponseError):
        parse_gateway_tool_envelope(body, WebSearchResultSet)


def test_parse_gateway_tool_envelope_wraps_malformed_envelope_as_gateway_response_error():
    """Valid usage but an otherwise malformed envelope still fails closed."""
    body = {
        "tool_class": "not-a-real-tool-class",
        "policy_signal": "CURRENT_OR_LATEST_FACT",
        "run_id": "run-1",
        "result": {"results": []},
        "provenance": {"search_id": None, "source_urls": []},
        "gateway_usage": {
            "gateway_request_id": "gw-1",
            "provider": "tavily",
            "cache_hit": False,
            "billing_units": 1,
            "cost_usd": "0.001",
        },
    }

    with pytest.raises(GatewayResponseError) as exc_info:
        parse_gateway_tool_envelope(body, WebSearchResultSet)

    assert exc_info.value.gateway_usage is not None
    assert exc_info.value.gateway_usage.gateway_request_id == "gw-1"


def test_parse_gateway_tool_envelope_preserves_decimal_cost_on_success():
    body = {
        "tool_class": "package_and_advisory_metadata",
        "policy_signal": "SECURITY_OR_CVE_CHECK",
        "run_id": "run-1",
        "result": {
            "identifier": "CVE-2026-12345",
            "ecosystem": "npm",
            "version": "1.2.3",
            "advisories": [],
        },
        "provenance": {"search_id": None, "source_urls": []},
        "gateway_usage": {
            "gateway_request_id": "gw-adv-1",
            "provider": "osv",
            "cache_hit": False,
            "billing_units": 1,
            "cost_usd": "0.0007",
        },
    }

    envelope = parse_gateway_tool_envelope(body, SecurityAdvisoryResult)

    assert envelope.gateway_usage.cost_usd == Decimal("0.0007")
    assert isinstance(envelope.gateway_usage.cost_usd, Decimal)
