from __future__ import annotations

import uuid
from typing import Any

from optimus_gateway.models import GatewayServiceConfig, authorize_bearer
from optimus_gateway.upstream_client import UpstreamClient


def handle_observability_traces_request(
    *,
    authorization_header: str | None,
    request_body: dict[str, Any],
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
) -> tuple[int, dict[str, Any]]:
    """Provisional observability ingress handler; Task 4 owns full validation."""
    del request_body, upstream_client
    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}
    return 200, {
        "status": "accepted",
        "gateway_request_id": f"gw-{uuid.uuid4().hex}",
    }
