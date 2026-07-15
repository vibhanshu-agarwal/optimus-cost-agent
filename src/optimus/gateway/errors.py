from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optimus.gateway.models import GatewayUsage


class GatewayError(Exception):
    """Base class for Optimus Gateway failures."""


class GatewayHttpError(GatewayError):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        gateway_usage: GatewayUsage | None = None,
    ) -> None:
        self.status_code = status_code
        self.gateway_usage = gateway_usage
        super().__init__(message)


class GatewayResponseError(GatewayError):
    """Raised when a gateway response is malformed or missing required usage."""

    def __init__(
        self,
        message: str,
        *,
        gateway_usage: GatewayUsage | None = None,
        credits_used: int | None = None,
    ) -> None:
        self.gateway_usage = gateway_usage
        self.credits_used = credits_used
        super().__init__(message)
