from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidencePackageLookupRequest,
    EvidencePackageLookupResponse,
    EvidenceRequest,
    EvidenceSearchResponse,
    EvidenceSearchResult,
    EvidenceSecurityAdvisoryRequest,
    EvidenceSecurityAdvisoryResponse,
)
from optimus.gateway.models import GatewayUsage
from optimus.gateway.tool_models import PackageLookupResult, SecurityAdvisoryResult
from optimus.tools.policy import EvidenceReasonCode, ToolPolicySignal


def test_evidence_request_preserves_query_verbatim():
    request = EvidenceRequest(
        run_id="run-1",
        session_id="session-1",
        query="latest pytest-asyncio release",
        reason=EvidenceReasonCode.PACKAGE_VERSION,
        policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        allowed_domains=("pypi.org",),
    )

    assert request.query == "latest pytest-asyncio release"
    assert request.session_id == "session-1"


def test_evidence_request_rejects_empty_query():
    with pytest.raises(ValidationError):
        EvidenceRequest(
            run_id="run-1",
            query="",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            allowed_domains=("example.com",),
        )


def test_extract_request_rejects_zero_max_chars():
    with pytest.raises(ValidationError):
        EvidenceExtractRequest(
            run_id="run-1",
            url="https://docs.example.com/a",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
            allowed_domains=("docs.example.com",),
            max_chars_per_source=0,
        )


def test_extract_request_default_max_chars_per_source_is_4000():
    """Aligns the ACP-facing default with the Plan 11.2 design's 4,000-char default."""
    request = EvidenceExtractRequest(
        run_id="run-1",
        url="https://docs.example.com/a",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
        allowed_domains=("docs.example.com",),
    )

    assert request.max_chars_per_source == 4000


def test_search_and_extract_responses_carry_gateway_usage():
    usage = GatewayUsage(
        gateway_request_id="gw-search-1",
        provider="tavily",
        provider_request_id="provider-1",
        cache_hit=False,
        billing_units=2,
        cost_usd=Decimal("0.002"),
    )
    search_response = EvidenceSearchResponse(
        results=(
            EvidenceSearchResult(
                title="Docs",
                url="https://docs.example.com/a",
                snippet="Authoritative docs",
            ),
        ),
        gateway_usage=usage,
    )
    extract_response = EvidenceExtractResponse(
        url="https://docs.example.com/a",
        title="Docs",
        content="Evidence text",
        gateway_usage=usage,
    )

    assert search_response.results[0].url_text == "https://docs.example.com/a"
    assert extract_response.gateway_usage.cost_usd == Decimal("0.002")
    assert extract_response.trust == "untrusted"
    assert not hasattr(search_response, "credits_used")
    assert not hasattr(extract_response, "credits_used")


# --- Package lookup / security advisory ACP-facing models (P11-FU-2) --------


def test_package_lookup_request_rejects_empty_package():
    with pytest.raises(ValidationError):
        EvidencePackageLookupRequest(
            run_id="run-1",
            package="",
            ecosystem="pypi",
            reason=EvidenceReasonCode.PACKAGE_VERSION,
            policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        )


def test_package_lookup_request_rejects_unsupported_ecosystem():
    with pytest.raises(ValidationError):
        EvidencePackageLookupRequest(
            run_id="run-1",
            package="pytest-asyncio",
            ecosystem="cargo",
            reason=EvidenceReasonCode.PACKAGE_VERSION,
            policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        )


def test_package_lookup_request_preserves_package_and_version_verbatim():
    request = EvidencePackageLookupRequest(
        run_id="run-1",
        session_id="session-1",
        package="pytest-asyncio",
        ecosystem="pypi",
        version="0.23.0",
        reason=EvidenceReasonCode.PACKAGE_VERSION,
        policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
    )

    assert request.package == "pytest-asyncio"
    assert request.version == "0.23.0"


def test_security_advisory_request_rejects_empty_identifier():
    with pytest.raises(ValidationError):
        EvidenceSecurityAdvisoryRequest(
            run_id="run-1",
            identifier="",
            reason=EvidenceReasonCode.SECURITY_ADVISORY,
            policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK,
        )


def test_security_advisory_request_accepts_optional_ecosystem_and_version():
    request = EvidenceSecurityAdvisoryRequest(
        run_id="run-1",
        identifier="CVE-2026-12345",
        ecosystem="npm",
        version="1.2.3",
        reason=EvidenceReasonCode.SECURITY_ADVISORY,
        policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK,
    )

    assert request.identifier == "CVE-2026-12345"
    assert request.ecosystem == "npm"


def test_package_lookup_response_carries_gateway_usage_and_untrusted_result():
    usage = GatewayUsage(
        gateway_request_id="gw-pkg-1",
        provider="package-registry",
        cache_hit=False,
        billing_units=1,
        cost_usd=Decimal("0.0005"),
    )
    response = EvidencePackageLookupResponse(
        result=PackageLookupResult(
            package="pytest-asyncio",
            ecosystem="pypi",
            requested_version=None,
            latest_version="0.24.0",
            versions=(),
            citations=("https://pypi.org/project/pytest-asyncio/",),
        ),
        gateway_usage=usage,
    )

    assert response.result.latest_version == "0.24.0"
    assert response.gateway_usage.cost_usd == Decimal("0.0005")


def test_security_advisory_response_carries_gateway_usage_and_untrusted_result():
    usage = GatewayUsage(
        gateway_request_id="gw-adv-1",
        provider="osv",
        cache_hit=False,
        billing_units=1,
        cost_usd=Decimal("0.0007"),
    )
    response = EvidenceSecurityAdvisoryResponse(
        result=SecurityAdvisoryResult(
            identifier="CVE-2026-12345",
            ecosystem="npm",
            version="1.2.3",
            advisories=(),
        ),
        gateway_usage=usage,
    )

    assert response.result.identifier == "CVE-2026-12345"
    assert response.gateway_usage.cost_usd == Decimal("0.0007")
