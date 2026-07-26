from __future__ import annotations

from typing import Any

from optimus_gateway.models import GatewayServiceConfig, authorize_bearer
from optimus_gateway.upstream_client import UpstreamClient


def handle_chat_completions_request(
    *,
    authorization_header: str | None,
    request_body: dict[str, Any],
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
) -> tuple[int, dict[str, Any]]:
    """Provisional Chat Completions handler; Task 2 owns full wire-shape behavior."""
    del request_body, upstream_client
    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}
    return 200, {"object": "chat.completion", "choices": []}
