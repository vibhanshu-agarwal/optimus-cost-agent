from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidenceRequest,
    EvidenceSearchResponse,
    EvidenceSearchResult,
)
from optimus.gateway.models import GatewayUsage
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
        credits_used=2,
    )
    extract_response = EvidenceExtractResponse(
        url="https://docs.example.com/a",
        title="Docs",
        content="Evidence text",
        gateway_usage=usage,
        credits_used=1,
    )

    assert search_response.results[0].url_text == "https://docs.example.com/a"
    assert extract_response.gateway_usage.cost_usd == Decimal("0.002")
    assert extract_response.trust == "untrusted"
    assert search_response.credits_used == 2
