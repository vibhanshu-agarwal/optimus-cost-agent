from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from optimus.evidence.models import (
    EvidenceExtractResponse,
    EvidenceSearchResponse,
    EvidenceSearchResult,
)
from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode


def build_web_search_payload(
    *,
    query: str,
    reason: EvidenceReasonCode,
    allowed_domains: tuple[str, ...],
    result_cap: int,
    search_depth: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": query,
        "reason": reason.value,
        "allowed_domains": list(allowed_domains),
        "result_cap": result_cap,
        "search_depth": search_depth,
    }
    if metadata:
        payload["metadata"] = metadata
    return payload


def build_web_extract_payload(
    *,
    url: str,
    reason: EvidenceReasonCode,
    max_chars_per_source: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": url,
        "reason": reason.value,
        "max_chars_per_source": max_chars_per_source,
    }
    if metadata:
        payload["metadata"] = metadata
    return payload


def parse_web_search_response(body: dict[str, Any]) -> EvidenceSearchResponse:
    usage = _parse_gateway_usage(body)
    results_body = body.get("results")
    if not isinstance(results_body, list):
        raise GatewayResponseError("results missing")
    try:
        return EvidenceSearchResponse(
            results=tuple(EvidenceSearchResult.model_validate(item) for item in results_body),
            gateway_usage=usage,
            credits_used=int(body.get("credits_used", 0)),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise GatewayResponseError(str(exc)) from exc


def parse_web_extract_response(body: dict[str, Any]) -> EvidenceExtractResponse:
    usage = _parse_gateway_usage(body)
    try:
        return EvidenceExtractResponse(
            url=body["url"],
            title=str(body.get("title", "")),
            content=body["content"],
            trust="untrusted",
            gateway_usage=usage,
            credits_used=int(body.get("credits_used", 0)),
        )
    except KeyError as exc:
        raise GatewayResponseError(f"{exc.args[0]} missing") from exc
    except (TypeError, ValueError, ValidationError) as exc:
        raise GatewayResponseError(str(exc)) from exc


def _parse_gateway_usage(body: dict[str, Any]) -> GatewayUsage:
    usage_body = body.get("gateway_usage")
    if not isinstance(usage_body, dict):
        raise GatewayResponseError("gateway_usage missing")
    try:
        return GatewayUsage.model_validate(usage_body)
    except ValidationError as exc:
        raise GatewayResponseError(str(exc)) from exc
