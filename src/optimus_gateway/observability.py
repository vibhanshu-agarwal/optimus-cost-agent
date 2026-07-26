from __future__ import annotations

import uuid
from typing import Any

from optimus_gateway.models import GatewayServiceConfig, authorize_bearer
from optimus_gateway.responses import sanitize_error_message
from optimus_gateway.upstream_client import UpstreamClient


class ObservabilityIngressError(ValueError):
    """Raised when a trace ingress envelope is structurally invalid."""


def validate_observability_envelope(request_body: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the trace ingress envelope, tolerating unknown top-level keys.

    Event contents are treated as untrusted data: only structural shape is
    checked, and no field is executed, dereferenced, or promoted to policy.
    """
    if "events" not in request_body:
        raise ObservabilityIngressError("events is required and must be an array")
    events = request_body["events"]
    if not isinstance(events, list):
        raise ObservabilityIngressError("events is required and must be an array")
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ObservabilityIngressError(f"event at index {index} must be a JSON object")
    return events


def handle_observability_traces_request(
    *,
    authorization_header: str | None,
    request_body: dict[str, Any],
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
) -> tuple[int, dict[str, Any]]:
    """Acknowledge structured trace ingress without claiming usage or cost.

    Acceptance means the Gateway accepted the structured event ingress, not that
    downstream export or cost accounting completed. Usage and cost accounting for
    observability arrive with COST-OBS, so this route never emits `gateway_usage`,
    `billing_units`, or `cost_usd` — including zero or placeholder values.
    """
    del upstream_client
    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}
    try:
        validate_observability_envelope(request_body)
    except ObservabilityIngressError as exc:
        return 400, {"error": sanitize_error_message(str(exc))}
    return 200, {
        "status": "accepted",
        "gateway_request_id": f"gw-{uuid.uuid4().hex}",
    }
