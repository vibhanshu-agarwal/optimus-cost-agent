from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from optimus.gateway.models import GatewayRouteAttempt, GatewayUsage


class PreflightProof(StrEnum):
    DIRECT_REFUSAL = "direct_refusal"


class GatewayFailureReason(StrEnum):
    PREFLIGHT_REFUSED = "GATEWAY_PREFLIGHT_REFUSED"
    ACCOUNTED_FAILURE = "GATEWAY_ACCOUNTED_FAILURE"
    ATTEMPT_INTEGRITY = "GATEWAY_ATTEMPT_INTEGRITY"
    OUTCOME_UNCERTAIN = "GATEWAY_OUTCOME_UNCERTAIN"


class GatewayFailureFacts:
    """One invocation's typed fact, usable only for the very exception its owner releases."""

    def __init__(self) -> None:
        self._fact: tuple[BaseException, GatewayFailureReason] | None = None
        self._closed = False
        self._conflicted = False

    def publish(self, failure: BaseException, reason: GatewayFailureReason) -> None:
        if self._closed or self._conflicted:
            return
        if self._fact is not None:
            self._fact = None
            self._conflicted = True
            return
        self._fact = (failure, reason)

    def supply_uncertainty(self, failure: BaseException) -> None:
        if not self._closed and (self._fact is None or self._fact[0] is not failure):
            self._fact = (failure, GatewayFailureReason.OUTCOME_UNCERTAIN)

    def consume(self, failure: BaseException) -> GatewayFailureReason | None:
        fact = None if self._closed else self._fact
        self.discard()
        return fact[1] if fact is not None and fact[0] is failure else None

    def discard(self) -> None:
        self._fact = None
        self._closed = True


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
        failure: dict[str, Any] | None = None,
        error_envelope: dict[str, Any] | None = None,
        _proof: PreflightProof | None = None,
    ) -> None:
        """``gateway_code``, ``retryable`` and ``route_attempts`` come from an enforced-routing error
        body (Plan 12.2 Task 5). ``retryable is False`` means the Gateway already applied the attempt
        contract, so the host must not re-send; ``None`` (today's routing) keeps status-based retries.
        ``route_attempts_malformed`` records that the body carried an attempt list the client had to
        drop, so an empty ``route_attempts`` is never mistaken for "no attempt was made". ``failure`` is the host's
        bounded, content-free cause when the request never got a Gateway reply it could read (Plan 12.2
        diagnosability): the transport's exception class and errno, or why the reply was unreadable. ``error_envelope``
        is an HTTP error body's fixed facts: its UTF-8 validity, whether it was a JSON object and any invalid usage's
        audit code (correction plan v4, C3)."""
        self._proof = _proof
        self.status_code = status_code
        self.error_envelope = error_envelope
        self.gateway_usage = gateway_usage
        self.gateway_code = gateway_code
        self.retryable = retryable
        self.route_attempts = route_attempts
        self.route_attempts_malformed = route_attempts_malformed
        self.failure = failure
        super().__init__(message)

    @property
    def preflight_proof(self) -> PreflightProof | None:
        return self._proof


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
