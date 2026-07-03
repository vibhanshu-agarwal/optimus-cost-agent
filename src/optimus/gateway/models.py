from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from optimus.gateway.errors import GatewayResponseError


class GatewayUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    gateway_request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_request_id: str | None = None
    cache_hit: bool = False
    billing_units: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))


class GatewayResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    response_id: str | None = None
    output_text: str
    gateway_usage: GatewayUsage
    raw: dict[str, Any]


def build_responses_payload(
    *,
    model: str,
    input_text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "input": input_text}
    if metadata:
        payload["metadata"] = metadata
    return payload


def build_chat_completions_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    return {"model": model, "messages": messages}


def parse_gateway_response(body: dict[str, Any]) -> GatewayResponse:
    usage_body = body.get("gateway_usage")
    if not isinstance(usage_body, dict):
        raise GatewayResponseError("gateway_usage missing")
    try:
        usage = GatewayUsage.model_validate(usage_body)
    except ValidationError as exc:
        raise GatewayResponseError(str(exc)) from exc

    output_text = body.get("output_text")
    if output_text is None:
        output_text = _extract_text_from_output(body.get("output"))
    if not isinstance(output_text, str):
        raise GatewayResponseError("output_text missing")

    response_id = body.get("id")
    if response_id is not None and not isinstance(response_id, str):
        raise GatewayResponseError("id must be a string when present")

    return GatewayResponse(
        response_id=response_id,
        output_text=output_text,
        gateway_usage=usage,
        raw=body,
    )


def _extract_text_from_output(output: object) -> str | None:
    if not isinstance(output, list):
        return None
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    if not chunks:
        return None
    return "".join(chunks)
