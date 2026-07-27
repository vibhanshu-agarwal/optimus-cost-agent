from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.evidence.gateway_io import (
    build_web_extract_payload,
    build_web_search_payload,
    parse_web_extract_envelope,
    parse_web_search_envelope,
)
from optimus.evidence.models import EvidenceExtractRequest, EvidenceRequest
from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.tool_models import GatewayToolContext
from optimus.tools.policy import EvidenceReasonCode, ToolPolicySignal


def _context(**overrides) -> GatewayToolContext:
    fields = {"run_id": "run-1", "session_id": "session-1", "execution_mode": "PLAN"}
    fields.update(overrides)
    return GatewayToolContext(**fields)


def _search_request(**overrides) -> EvidenceRequest:
    fields = {
        "run_id": "run-1",
        "session_id": "session-1",
        "query": "latest pytest-asyncio release",
        "reason": EvidenceReasonCode.PACKAGE_VERSION,
        "policy_signal": ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        "allowed_domains": ("pypi.org",),
        "result_cap": 3,
        "search_depth": "basic",
    }
    fields.update(overrides)
    return EvidenceRequest(**fields)


def _extract_request(**overrides) -> EvidenceExtractRequest:
    fields = {
        "run_id": "run-1",
        "session_id": "session-1",
        "url": "https://docs.example.com/a",
        "reason": EvidenceReasonCode.USER_REQUESTED,
        "policy_signal": ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
        "allowed_domains": ("docs.example.com",),
        "max_chars_per_source": 4000,
    }
    fields.update(overrides)
    return EvidenceExtractRequest(**fields)


# --- build_web_search_payload -------------------------------------------------


def test_web_search_payload_sends_query_verbatim():
    payload = build_web_search_payload(_search_request(), _context())

    assert payload["query"] == "latest pytest-asyncio release"
    assert payload["allowed_domains"] == ["pypi.org"]
    assert payload["result_cap"] == 3
    assert payload["search_depth"] == "basic"


def test_web_search_payload_sends_reason_only_as_metadata_not_query():
    payload = build_web_search_payload(_search_request(query="what is 2+2"), _context())

    assert payload["query"] == "what is 2+2"
    assert payload["reason"] == "PACKAGE_VERSION"
    assert "PACKAGE_VERSION" not in payload["query"]


def test_web_search_payload_carries_context():
    payload = build_web_search_payload(_search_request(), _context(run_id="run-42"))

    assert payload["context"]["run_id"] == "run-42"
    assert payload["context"]["session_id"] == "session-1"
    assert payload["context"]["execution_mode"] == "PLAN"


# --- build_web_extract_payload -------------------------------------------------


def test_web_extract_payload_maps_legacy_single_url_to_urls_list():
    payload = build_web_extract_payload(_extract_request(), _context())

    assert payload["urls"] == ["https://docs.example.com/a"]
    assert "url" not in payload
    assert payload["max_chars_per_source"] == 4000


def test_web_extract_payload_sends_reason_only_as_metadata():
    payload = build_web_extract_payload(_extract_request(), _context())

    assert payload["reason"] == "USER_REQUESTED"


def test_web_extract_payload_rejects_non_https_url_via_shared_validation():
    with pytest.raises(ValidationError):
        build_web_extract_payload(_extract_request(url="http://docs.example.com/a"), _context())


# --- parse_web_search_envelope -------------------------------------------------


def _search_envelope_body(**overrides) -> dict:
    body = {
        "tool_class": "web_search",
        "policy_signal": "CURRENT_OR_LATEST_FACT",
        "run_id": "run-1",
        "result": {
            "results": [
                {"title": "Docs", "url": "https://docs.example.com/a", "snippet": "A"},
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
            "provider_request_id": "provider-1",
            "cache_hit": False,
            "billing_units": 2,
            "cost_usd": "0.002",
        },
    }
    body.update(overrides)
    return body


def test_parse_web_search_envelope_unwraps_result_and_provenance():
    envelope = parse_web_search_envelope(_search_envelope_body())

    assert envelope.result.results[0].title == "Docs"
    assert str(envelope.result.results[0].url) == "https://docs.example.com/a"
    assert envelope.provenance.search_id == "search-1"
    assert envelope.provenance.trust == "untrusted"


def test_parse_web_search_envelope_preserves_gateway_usage_fields():
    envelope = parse_web_search_envelope(_search_envelope_body())

    assert envelope.gateway_usage.gateway_request_id == "gw-search-1"
    assert envelope.gateway_usage.cache_hit is False
    assert envelope.gateway_usage.cost_usd == Decimal("0.002")


def test_parse_web_search_envelope_rejects_missing_gateway_usage():
    body = _search_envelope_body()
    del body["gateway_usage"]

    with pytest.raises(GatewayResponseError, match="gateway_usage missing"):
        parse_web_search_envelope(body)


def test_parse_web_search_envelope_wraps_malformed_result_as_gateway_response_error():
    body = _search_envelope_body(
        result={"results": [{"title": "Bad", "url": "not-a-url", "snippet": "bad"}]}
    )

    with pytest.raises(GatewayResponseError, match="url") as exc_info:
        parse_web_search_envelope(body)

    assert exc_info.value.gateway_usage is not None
    assert exc_info.value.gateway_usage.gateway_request_id == "gw-search-1"


# --- parse_web_extract_envelope ------------------------------------------------


def _extract_envelope_body(**overrides) -> dict:
    body = {
        "tool_class": "web_extract",
        "policy_signal": "APPROVED_SEARCH_RESULT_PROVENANCE",
        "run_id": "run-1",
        "result": {
            "items": [
                {"url": "https://docs.example.com/a", "title": "Docs", "content": "Extracted evidence"},
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
    body.update(overrides)
    return body


def test_parse_web_extract_envelope_preserves_untrusted_content():
    envelope = parse_web_extract_envelope(_extract_envelope_body())

    assert envelope.result.items[0].content == "Extracted evidence"
    assert envelope.provenance.trust == "untrusted"


def test_parse_web_extract_envelope_preserves_gateway_usage_fields():
    envelope = parse_web_extract_envelope(_extract_envelope_body())

    assert envelope.gateway_usage.gateway_request_id == "gw-extract-1"
    assert envelope.gateway_usage.cache_hit is True
    assert envelope.gateway_usage.billing_units == 1
    assert envelope.gateway_usage.cost_usd == Decimal("0.001")


def test_parse_web_extract_envelope_rejects_missing_gateway_usage():
    body = _extract_envelope_body()
    del body["gateway_usage"]

    with pytest.raises(GatewayResponseError, match="gateway_usage missing"):
        parse_web_extract_envelope(body)
