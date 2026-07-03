"""Optimus Gateway client and wire models."""

from optimus.gateway.client import GatewayClient, GatewayRequest, GatewayTransport, UrllibGatewayTransport
from optimus.gateway.errors import GatewayError, GatewayHttpError, GatewayResponseError
from optimus.gateway.models import (
    GatewayResponse,
    GatewayUsage,
    build_chat_completions_payload,
    build_responses_payload,
    parse_gateway_response,
)

__all__ = [
    "GatewayClient",
    "GatewayError",
    "GatewayHttpError",
    "GatewayRequest",
    "GatewayResponse",
    "GatewayResponseError",
    "GatewayTransport",
    "GatewayUsage",
    "UrllibGatewayTransport",
    "build_chat_completions_payload",
    "build_responses_payload",
    "parse_gateway_response",
]
