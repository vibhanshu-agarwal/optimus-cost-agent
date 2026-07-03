from decimal import Decimal

import pytest

from optimus.evidence.gateway_io import (
    build_web_extract_payload,
    build_web_search_payload,
    parse_web_extract_response,
    parse_web_search_response,
)
from optimus.evidence.models import EvidenceExtractResponse
from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode


def test_web_search_payload_sends_query_verbatim():
    payload = build_web_search_payload(
        query="latest pytest-asyncio release",
        reason=EvidenceReasonCode.PACKAGE_VERSION,
        allowed_domains=("pypi.org",),
        result_cap=3,
        search_depth="basic",
        metadata={"run_id": "run-1", "session_id": "session-1"},
    )

    assert payload["query"] == "latest pytest-asyncio release"
    assert payload["reason"] == "PACKAGE_VERSION"
    assert payload["allowed_domains"] == ["pypi.org"]
    assert payload["result_cap"] == 3
    assert payload["metadata"] == {"run_id": "run-1", "session_id": "session-1"}


def test_web_extract_payload_uses_url_verbatim():
    payload = build_web_extract_payload(
        url="https://docs.example.com/a",
        reason=EvidenceReasonCode.USER_REQUESTED,
        max_chars_per_source=4000,
        metadata={"run_id": "run-1"},
    )

    assert payload == {
        "url": "https://docs.example.com/a",
        "reason": "USER_REQUESTED",
        "max_chars_per_source": 4000,
        "metadata": {"run_id": "run-1"},
    }


def test_parse_web_search_response_carries_gateway_usage_and_credits():
    parsed = parse_web_search_response(
        {
            "results": [
                {"title": "Docs", "url": "https://docs.example.com/a", "snippet": "A"},
            ],
            "credits_used": 2,
            "gateway_usage": {
                "gateway_request_id": "gw-search-1",
                "provider": "tavily",
                "provider_request_id": "provider-1",
                "cache_hit": False,
                "billing_units": 2,
                "cost_usd": "0.002",
            },
        }
    )

    assert parsed.results[0].url_text == "https://docs.example.com/a"
    assert parsed.credits_used == 2
    assert parsed.gateway_usage == GatewayUsage(
        gateway_request_id="gw-search-1",
        provider="tavily",
        provider_request_id="provider-1",
        cache_hit=False,
        billing_units=2,
        cost_usd=Decimal("0.002"),
    )


def test_parse_web_extract_response_marks_content_untrusted():
    parsed = parse_web_extract_response(
        {
            "url": "https://docs.example.com/a",
            "title": "Docs",
            "content": "Extracted evidence",
            "credits_used": 1,
            "gateway_usage": {
                "gateway_request_id": "gw-extract-1",
                "provider": "tavily",
                "cache_hit": True,
                "billing_units": 1,
                "cost_usd": "0.001",
            },
        }
    )

    assert parsed == EvidenceExtractResponse(
        url="https://docs.example.com/a",
        title="Docs",
        content="Extracted evidence",
        trust="untrusted",
        gateway_usage=GatewayUsage(
            gateway_request_id="gw-extract-1",
            provider="tavily",
            cache_hit=True,
            billing_units=1,
            cost_usd=Decimal("0.001"),
        ),
        credits_used=1,
    )


def test_parse_web_search_response_wraps_malformed_result_as_gateway_response_error():
    with pytest.raises(GatewayResponseError, match="url"):
        parse_web_search_response(
            {
                "results": [{"title": "Bad", "url": "not-a-url", "snippet": "bad"}],
                "gateway_usage": {
                    "gateway_request_id": "gw-1",
                    "provider": "tavily",
                    "billing_units": 1,
                    "cost_usd": "0.01",
                },
            }
        )


def test_http_url_round_trip_preserves_provenance_string_for_path_urls():
    parsed = parse_web_search_response(
        {
            "results": [{"title": "Docs", "url": "https://docs.example.com/a", "snippet": "A"}],
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "tavily",
                "billing_units": 1,
                "cost_usd": "0.01",
            },
        }
    )

    assert parsed.results[0].url_text == "https://docs.example.com/a"


def test_parse_web_search_response_rejects_missing_results():
    with pytest.raises(GatewayResponseError, match="results missing"):
        parse_web_search_response(
            {
                "gateway_usage": {
                    "gateway_request_id": "gw-1",
                    "provider": "tavily",
                    "billing_units": 1,
                    "cost_usd": "0.01",
                }
            }
        )


def test_parse_web_search_response_rejects_missing_usage():
    with pytest.raises(GatewayResponseError, match="gateway_usage missing"):
        parse_web_search_response({"results": []})


def test_parse_web_extract_response_rejects_missing_usage():
    with pytest.raises(GatewayResponseError, match="gateway_usage missing"):
        parse_web_extract_response({"url": "https://docs.example.com/a", "content": "x"})
