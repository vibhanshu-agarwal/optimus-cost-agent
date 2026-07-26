from __future__ import annotations

import uuid
from typing import Any

from optimus_gateway.models import (
    GatewayServiceConfig,
    ModelRequestValidationError,
    authorize_bearer,
    flatten_messages_to_input_text,
    validate_chat_completions_envelope,
)
from optimus_gateway.responses import run_model_completion
from optimus_gateway.upstream_client import ProviderMessageResult, UpstreamClient


def handle_chat_completions_request(
    *,
    authorization_header: str | None,
    request_body: dict[str, Any],
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
) -> tuple[int, dict[str, Any]]:
    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}

    try:
        model, messages, _metadata = validate_chat_completions_envelope(request_body)
        input_text = flatten_messages_to_input_text(messages)
    except ModelRequestValidationError as exc:
        return 400, {"error": str(exc)}

    return run_model_completion(
        model=model,
        input_text=input_text,
        config=config,
        upstream_client=upstream_client,
        build_success=_build_chat_completions_success,
    )


def _build_chat_completions_success(
    *,
    provider_result: ProviderMessageResult,
    gateway_usage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": provider_result.output_text},
                "finish_reason": "stop",
            }
        ],
        "gateway_usage": gateway_usage,
    }
