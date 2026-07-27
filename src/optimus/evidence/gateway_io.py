from __future__ import annotations

from typing import Any, Mapping

from optimus.evidence.models import EvidenceExtractRequest, EvidenceRequest
from optimus.gateway.tool_models import (
    GatewayToolContext,
    GatewayToolEnvelope,
    WebExtractRequest,
    WebExtractResultSet,
    WebSearchRequest,
    WebSearchResultSet,
    parse_gateway_tool_envelope,
)


def build_web_search_payload(request: EvidenceRequest, context: GatewayToolContext) -> dict[str, Any]:
    """Build the shared Gateway-facing ``/v1/tools/web/search`` payload.

    ``query`` is sent verbatim; ``reason`` travels as metadata only and is
    never merged into the query text.
    """
    shared_request = WebSearchRequest(
        context=context,
        query=request.query,
        allowed_domains=request.allowed_domains,
        result_cap=request.result_cap,
        search_depth=request.search_depth,
    )
    payload = shared_request.model_dump(mode="json")
    payload["reason"] = request.reason.value
    return payload


def build_web_extract_payload(request: EvidenceExtractRequest, context: GatewayToolContext) -> dict[str, Any]:
    """Build the shared Gateway-facing ``/v1/tools/web/extract`` payload.

    Maps the ACP-facing legacy single ``url`` to the shared ``urls`` list via
    :class:`~optimus.gateway.tool_models.WebExtractRequest`, which also
    enforces the HTTPS/duplicate/bounds validation shared with the Gateway.
    """
    shared_request = WebExtractRequest(
        context=context,
        url=request.url_text,
        max_chars_per_source=request.max_chars_per_source,
    )
    payload = shared_request.model_dump(mode="json")
    payload["reason"] = request.reason.value
    return payload


def parse_web_search_envelope(body: Mapping[str, Any]) -> GatewayToolEnvelope[WebSearchResultSet]:
    """Parse a ``/v1/tools/web/search`` response into the shared typed envelope."""
    return parse_gateway_tool_envelope(body, WebSearchResultSet)


def parse_web_extract_envelope(body: Mapping[str, Any]) -> GatewayToolEnvelope[WebExtractResultSet]:
    """Parse a ``/v1/tools/web/extract`` response into the shared typed envelope."""
    return parse_gateway_tool_envelope(body, WebExtractResultSet)
