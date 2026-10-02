from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from optimus.gateway.errors import GatewayResponseError

if TYPE_CHECKING:
    from optimus_model_policy.binding import RouteBinding

_UNFINISHED_FINISH_REASONS = frozenset({"content_filter", "error"})


class GatewayUsage(BaseModel):
    """Wire-level usage envelope copied from an Optimus Gateway response.

    Normalized fields (service, native_unit, model, model_version,
    price_snapshot_id) are optional here. ``ProviderUsage`` persistence takes
    ``service`` and ``native_unit`` from explicit caller-supplied context
    instead of these optional wire fields; ``price_snapshot_id`` remains
    optional diagnostic metadata at both layers. ``model`` and
    ``model_version`` are copied through when present. The legacy
    per-request debit field has been removed: provider-reported
    ``cost_usd`` and ``billing_units`` are the only settled accounting
    values, and nothing here estimates any additional balance.
    """

    model_config = ConfigDict(frozen=True)

    gateway_request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_request_id: str | None = None
    cache_hit: bool = False
    billing_units: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    # Normalized gateway extensions (all optional at parse time; see class docstring).
    service: str | None = None
    native_unit: str | None = None
    model: str | None = None
    model_version: str | None = None
    price_snapshot_id: str | None = None
    resolved_provider: str | None = None
    resolved_model: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    cache_age_seconds: int | None = Field(default=None, ge=0)
    # Plan 12.2 Task 5, enforced routing only: the host request this attempt served, and which
    # attempt it was. ``gateway_request_id`` is then that attempt's own receipt identity.
    route_request_id: str | None = Field(default=None, min_length=1)
    attempt: int | None = Field(default=None, ge=1, strict=True)

    @field_validator("billing_units", mode="before")
    @classmethod
    def _billing_units_must_be_non_boolean_integer(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("billing_units must be a non-negative integer")
        return value

    @field_validator("cost_usd")
    @classmethod
    def _decimal_must_be_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("decimal values must be finite")
        return value


class GatewayRouteAttempt(BaseModel):
    """One provider attempt the Gateway made for a host request under enforced routing.

    ``outcome`` is ``completed``, ``not_sent`` (never left: nothing ran or was billed), ``rejected``
    (refused before any model ran) or ``uncertain`` (may have run and been billed; cost unknown).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt: int = Field(ge=1, strict=True)
    gateway_request_id: str = Field(min_length=1)
    outcome: Literal["completed", "not_sent", "rejected", "uncertain"]
    http_status: int | None = Field(default=None, strict=True)
    provider_request_id: str | None = None


def parse_route_attempts(raw: object) -> tuple[GatewayRouteAttempt, ...]:
    """Strictly parse a ``route_attempts`` list; raises ``ValueError`` on any malformed entry."""
    if not isinstance(raw, list):
        raise ValueError("route_attempts must be a list")
    attempts = tuple(GatewayRouteAttempt.model_validate(item) for item in raw)
    if [item.attempt for item in attempts] != list(range(1, len(attempts) + 1)):
        raise ValueError("route_attempts must be numbered 1..n in order")
    return attempts


class GatewayResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    response_id: str | None = None
    output_text: str
    gateway_usage: GatewayUsage
    raw: dict[str, Any]
    finish_reason: str | None = None
    """The provider's finish status as the Gateway reported it (``stop``, ``length``, ...), or
    ``None`` when none was reported. ``length`` means the reply hit its output limit (Plan 12.2)."""
    route_attempts: tuple[GatewayRouteAttempt, ...] = ()
    """Every provider attempt for this request under enforced routing, in order; empty otherwise."""

    @property
    def length_limited(self) -> bool:
        return self.finish_reason == "length"

    @property
    def stopped_unfinished(self) -> bool:
        """The provider stopped the reply before it finished: a content filter or a provider error.
        Such a reply is never used as a plan or shown as an answer (operator decision 2026-10-02,
        Claude and Codex concurring). A missing or other status is left to the activation contract."""
        return self.finish_reason in _UNFINISHED_FINISH_REASONS


def build_responses_payload(
    *,
    model: str,
    input_text: str,
    metadata: dict[str, Any] | None = None,
    route_binding: RouteBinding | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "input": input_text}
    if metadata:
        payload["metadata"] = metadata
    if route_binding is not None:
        payload["route_binding"] = route_binding.to_wire()
    return payload


def build_chat_completions_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    return {"model": model, "messages": messages}


def parse_gateway_usage(body: Mapping[str, Any]) -> GatewayUsage:
    """Single strict parser for a gateway_usage envelope.

    Validates and returns a GatewayUsage model from the raw dict.
    Raises GatewayResponseError on missing or invalid usage data.
    This is the canonical entry point for usage parsing—called by both
    the success-response path and the error-body path.

    Null or absent ``cost_usd`` (when billing_units is present) raises with
    ``audit_code="GATEWAY_COST_MISSING"``. Completely absent usage metrics
    raise with ``audit_code="GATEWAY_USAGE_MISSING"``.
    """
    if not isinstance(body, Mapping):
        raise GatewayResponseError("gateway_usage missing", audit_code="GATEWAY_USAGE_MISSING")

    has_billing_units = "billing_units" in body
    has_cost_usd = "cost_usd" in body
    if not has_billing_units and not has_cost_usd:
        raise GatewayResponseError(
            "gateway usage fields missing",
            audit_code="GATEWAY_USAGE_MISSING",
        )
    if has_cost_usd and body.get("cost_usd") is None:
        raise GatewayResponseError(
            "cost_usd is required and must be non-null",
            audit_code="GATEWAY_COST_MISSING",
        )
    if has_billing_units and not has_cost_usd:
        raise GatewayResponseError(
            "cost_usd is required and must be non-null",
            audit_code="GATEWAY_COST_MISSING",
        )

    try:
        return GatewayUsage.model_validate(body)
    except ValidationError as exc:
        raise GatewayResponseError(str(exc)) from exc


def parse_gateway_response(body: dict[str, Any]) -> GatewayResponse:
    usage_body = body.get("gateway_usage")
    if not isinstance(usage_body, dict):
        raise GatewayResponseError("gateway_usage missing", audit_code="GATEWAY_USAGE_MISSING")
    try:
        usage = parse_gateway_usage(usage_body)
    except GatewayResponseError:
        # Usage itself is invalid—no partial usage to preserve.
        raise

    # Usage is valid from here. Any later failure preserves it on the exception.
    output_text = body.get("output_text")
    if output_text is None:
        output_text = _extract_text_from_output(body.get("output"))
    if not isinstance(output_text, str):
        raise GatewayResponseError("output_text missing", gateway_usage=usage)

    response_id = body.get("id")
    if response_id is not None and not isinstance(response_id, str):
        raise GatewayResponseError("id must be a string when present", gateway_usage=usage)

    finish_reason = body.get("finish_reason")
    if finish_reason is not None and (not isinstance(finish_reason, str) or not finish_reason):
        raise GatewayResponseError("finish_reason must be a non-empty string when present", gateway_usage=usage)

    route_attempts: tuple[GatewayRouteAttempt, ...] = ()
    if "route_attempts" in body:
        try:
            route_attempts = parse_route_attempts(body["route_attempts"])
        except (ValueError, ValidationError) as exc:
            raise GatewayResponseError("route_attempts is malformed", gateway_usage=usage) from exc

    return GatewayResponse(
        response_id=response_id,
        output_text=output_text,
        gateway_usage=usage,
        raw=body,
        finish_reason=finish_reason.casefold() if finish_reason is not None else None,
        route_attempts=route_attempts,
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
