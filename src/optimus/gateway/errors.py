from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optimus.gateway.models import GatewayRouteAttempt, GatewayUsage


class GatewayError(Exception):
    """Base class for Optimus Gateway failures."""


class GatewayHttpError(GatewayError):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        gateway_usage: GatewayUsage | None = None,
        gateway_code: str | None = None,
        retryable: bool | None = None,
        route_attempts: tuple[GatewayRouteAttempt, ...] = (),
        route_attempts_malformed: bool = False,
    ) -> None:
        """``gateway_code``, ``retryable`` and ``route_attempts`` come from an enforced-routing error
        body (Plan 12.2 Task 5). ``retryable is False`` means the Gateway already applied the attempt
        contract, so the host must not re-send; ``None`` (today's routing) keeps status-based retries.
        ``route_attempts_malformed`` records that the body carried an attempt list the client had to
        drop, so an empty ``route_attempts`` is never mistaken for "no attempt was made"."""
        self.status_code = status_code
        self.gateway_usage = gateway_usage
        self.gateway_code = gateway_code
        self.retryable = retryable
        self.route_attempts = route_attempts
        self.route_attempts_malformed = route_attempts_malformed
        super().__init__(message)


class GatewayResponseError(GatewayError):
    """Raised when a gateway response is malformed or missing required usage."""

    def __init__(
        self,
        message: str,
        *,
        gateway_usage: GatewayUsage | None = None,
        audit_code: str | None = None,
    ) -> None:
        self.gateway_usage = gateway_usage
        self.audit_code = audit_code
        super().__init__(message)
