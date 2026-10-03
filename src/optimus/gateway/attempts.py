"""Provider attempts of one host model request, as the Gateway reported them (Plan 12.2 CP3; Task 1
contracts 6; Codex CP3 ruling R3-R5).

One classifier for every host call path - planning, answer and summarization - so a stage can never
settle the same Gateway outcome differently:

- a success or failure carrying ``route_attempts`` (enforced routing) is one attempt per record, in
  order. The settled usage belongs to the final completed attempt only; ``not_sent`` and ``rejected``
  attempts certainly reached no model and cost exactly 0; an ``uncertain`` attempt may have run and
  been billed, so its cost stays unknown;
- a proven preflight refusal - a known Gateway refusal code, ``retryable`` False, no route attempts
  and no usage - is one ``rejected`` attempt costing exactly 0: the Gateway refused it before any
  upstream call (``PREFLIGHT_REFUSAL_CODES``, pinned to the Gateway's own codes by a test);
- anything else without route attempts is one attempt: ``completed`` with its reported usage, or
  ``uncertain`` with an unknown cost when no usage was reported, since the request may have run.

An empty attempt list alone never proves a refusal, and nothing here retries to resolve an uncertain
cost. The original normalized ``GatewayUsage`` is kept on the attempt that settled it, so a downstream
ledger never has to reconstruct billing facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import GatewayResponse, GatewayRouteAttempt, GatewayUsage

__all__ = [
    "PREFLIGHT_REFUSAL_CODES",
    "ProviderAttempt",
    "attempts_from_failure",
    "attempts_from_response",
    "is_preflight_refusal",
]

# Gateway model-policy refusals raised before any upstream attempt (optimus_gateway.model_policy
# admit_request/parse_route_binding and optimus_model_policy.capacity.guard_request).
# FINISH_STATUS_UNVERIFIED is raised after a completed, billed attempt and always carries its usage,
# so it is not here. A test keeps this set equal to the Gateway's codes.
PREFLIGHT_REFUSAL_CODES = frozenset(
    {
        "BINDING_MALFORMED",
        "BINDING_REQUIRED",
        "BINDING_UNSUPPORTED",
        "BINDING_VERSION_UNSUPPORTED",
        "CAPACITY_REFUSED",
        "DISCLOSURE_INVALID",
        "DISCLOSURE_REQUIRED",
        "ESTIMATOR_UNKNOWN",
        "ESTIMATOR_UNVERIFIED",
        "INPUT_EXCEEDS_CAPACITY",
        "MODEL_NOT_ELIGIBLE",
        "OUTPUT_RESERVE_EXCEEDS_ROUTE",
        "OUTPUT_RESERVE_EXCEEDS_TOTAL",
        "OUTPUT_RESERVE_INVALID",
        "REGISTRY_HASH_MISMATCH",
        "ROUTE_UNVERIFIED",
        "SNAPSHOT_NOT_APPROVED",
        "UNKNOWN_MODEL",
    }
)

_ZERO_COST = frozenset({"not_sent", "rejected"})


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    """One provider attempt. ``cost_usd`` is None when unknown, never a stand-in zero.

    ``routed`` is True when the Gateway reported the attempt in ``route_attempts``; ``number`` is then
    its position there. ``gateway_usage`` is set only on the attempt whose usage settled the request.
    """

    number: int
    outcome: str
    cost_usd: Decimal | None
    gateway_request_id: str | None = None
    provider_request_id: str | None = None
    http_status: int | None = None
    gateway_usage: GatewayUsage | None = None
    routed: bool = False

    def __post_init__(self) -> None:
        if self.number < 1 or self.outcome not in {"completed", *_ZERO_COST, "uncertain"}:
            raise ValueError("a provider attempt needs a positive number and a known outcome")
        if self.outcome in _ZERO_COST and self.cost_usd != Decimal("0"):
            raise ValueError("an attempt that reached no model costs exactly 0")
        if self.outcome == "uncertain" and self.cost_usd is not None:
            raise ValueError("an uncertain attempt's cost is unknown")
        if self.gateway_usage is not None and (self.outcome != "completed" or self.cost_usd != self.gateway_usage.cost_usd):
            raise ValueError("only the completed attempt that settled the request carries its usage")


def is_preflight_refusal(exc: BaseException) -> bool:
    """A Gateway refusal proven to precede any upstream attempt: a known preflight code, not
    retryable, no route attempts and no usage. Anything short of all four is not proof."""
    return (
        isinstance(exc, GatewayHttpError)
        and exc.gateway_code in PREFLIGHT_REFUSAL_CODES
        and exc.retryable is False
        and not exc.route_attempts
        and exc.gateway_usage is None
    )


def attempts_from_response(response: GatewayResponse) -> tuple[ProviderAttempt, ...]:
    """Every provider attempt behind a successful response."""
    return _attempts(response.route_attempts, response.gateway_usage, http_status=None)


def attempts_from_failure(exc: BaseException) -> tuple[ProviderAttempt, ...]:
    """Every provider attempt behind a failed request, known or not. Never empty."""
    if is_preflight_refusal(exc):
        assert isinstance(exc, GatewayHttpError)
        return (ProviderAttempt(number=1, outcome="rejected", cost_usd=Decimal("0"), http_status=exc.status_code),)
    if isinstance(exc, GatewayHttpError):
        return _attempts(exc.route_attempts, exc.gateway_usage, http_status=exc.status_code)
    if isinstance(exc, GatewayResponseError):
        return _attempts((), exc.gateway_usage, http_status=None)
    # Transport loss or an unexpected failure after dispatch: it may have run and been billed.
    return (ProviderAttempt(number=1, outcome="uncertain", cost_usd=None),)


def _attempts(
    route_attempts: tuple[GatewayRouteAttempt, ...], usage: GatewayUsage | None, *, http_status: int | None
) -> tuple[ProviderAttempt, ...]:
    if route_attempts:
        # The settled usage belongs to the final completed attempt only; never counted twice.
        settled = max((item.attempt for item in route_attempts if item.outcome == "completed"), default=None)
        return tuple(_routed(item, usage if usage is not None and item.attempt == settled else None) for item in route_attempts)
    if usage is not None:
        return (
            ProviderAttempt(
                number=1,
                outcome="completed",
                cost_usd=usage.cost_usd,
                gateway_request_id=usage.gateway_request_id,
                provider_request_id=usage.provider_request_id,
                http_status=http_status,
                gateway_usage=usage,
            ),
        )
    return (ProviderAttempt(number=1, outcome="uncertain", cost_usd=None, http_status=http_status),)


def _routed(item: GatewayRouteAttempt, usage: GatewayUsage | None) -> ProviderAttempt:
    if item.outcome in _ZERO_COST:
        cost: Decimal | None = Decimal("0")
    elif item.outcome == "completed" and usage is not None:
        cost = usage.cost_usd
    else:
        # Uncertain, or completed without the usage that would settle it: unknown, never zero.
        cost, usage = None, None
    return ProviderAttempt(
        number=item.attempt,
        outcome=item.outcome,
        cost_usd=cost,
        gateway_request_id=item.gateway_request_id,
        provider_request_id=item.provider_request_id,
        http_status=item.http_status,
        gateway_usage=usage,
        routed=True,
    )
