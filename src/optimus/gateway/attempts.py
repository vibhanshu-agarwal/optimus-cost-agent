"""Provider attempts of one host model request, as the Gateway reported them (Plan 12.2 CP3; Task 1
contracts 6; Codex CP3 ruling R3-R5).

One classifier for every host call path - planning, answer and summarization - so a stage can never
settle the same Gateway outcome differently:

- a success or failure carrying ``route_attempts`` (enforced routing) is one attempt per record, in
  order. The settled usage belongs to the one completed attempt it names (its Gateway request id).
  Usage that names no single completed attempt is a Gateway contract violation, raised as
  ``AttemptIntegrityError`` rather than attributed by guess. The error carries what can still be
  recorded truthfully: the reported usage itself as one ``unattributed`` record (its reported cost is
  known, so it counts once; which attempt it settled is not, so its turn is never complete) and every
  route attempt as reported but unsettled. Callers record these, then raise (Codex CP3 correction
  ruling C1/C2). ``not_sent`` and ``rejected`` attempts
  certainly reached no model and cost exactly 0; an ``uncertain`` attempt, or one reported completed
  without the usage that would settle it, may have been billed, so it is ``uncertain`` at unknown cost;
- a proven preflight refusal - a known Gateway refusal code, ``retryable`` False, no route attempts
  (none reported, not a malformed list the client dropped) and no usage - is one ``rejected`` attempt
  costing exactly 0: the Gateway refused it before any upstream call (``PREFLIGHT_REFUSAL_CODES``,
  pinned to the Gateway's own codes by a test);
- anything else without route attempts is one attempt: ``completed`` with its reported usage, or
  ``uncertain`` with an unknown cost when no usage was reported, since the request may have run.

An empty attempt list alone never proves a refusal, and nothing here retries to resolve an uncertain
cost. The original normalized ``GatewayUsage`` is kept on the attempt that settled it, so a downstream
ledger never has to reconstruct billing facts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import GatewayDecision, GatewayResponse, GatewayRouteAttempt, GatewayUsage
from optimus_security.failure_facts import bounded, bounded_failure, exception_fact

__all__ = [
    "GATEWAY_FAILURE_CODES",
    "GATEWAY_REGISTRY_MISMATCH_CODES",
    "PREFLIGHT_REFUSAL_CODES",
    "REPLY_REFUSAL_CODES",
    "ROUTE_STOP_CODES",
    "UPSTREAM_ATTEMPT_CODES",
    "AttemptIntegrityError",
    "ProviderAttempt",
    "attempts_from_decision",
    "attempts_from_failure",
    "attempts_from_response",
    "first_error",
    "gateway_registry_mismatch_text",
    "gateway_failure_facts",
    "host_failure_facts",
    "is_gateway_registry_mismatch",
    "is_input_capacity_refusal",
    "is_preflight_refusal",
    "stops_experimental_route",
]

# Gateway model-policy refusals raised before any upstream attempt (optimus_gateway.model_policy
# admit_request/parse_route_binding and optimus_model_policy.capacity.guard_request), and the Plan 12.2
# Stage C test guard's refusals (optimus_model_policy.stage_c.StageCGuard.admit), which the Gateway returns
# under their own code before the attempt they refuse is dispatched (Codex completion review R1). Listed
# here rather than imported, so the host's call paths never load the Stage C module.
# FINISH_STATUS_UNVERIFIED and the experimental route's reply checks (EMPIRICAL_* other than
# EMPIRICAL_ROUTE_STOPPED) are raised after a completed, billed attempt and always carry its usage,
# so they are not here. A test keeps this set equal to the Gateway's codes.
PREFLIGHT_REFUSAL_CODES = frozenset(
    {
        "BINDING_MALFORMED",
        "BINDING_REQUIRED",
        "BINDING_UNSUPPORTED",
        "BINDING_VERSION_UNSUPPORTED",
        "CAPACITY_REFUSED",
        "DECISIONS_NEED_REGISTRY",
        "DECISION_DISCLOSURE_UNSUPPORTED",
        "DISCLOSURE_INVALID",
        "DISCLOSURE_REQUIRED",
        "EMPIRICAL_ROUTE_STOPPED",
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
        "STAGE_C_ATTEMPTS_EXHAUSTED",
        "STAGE_C_ATTEMPT_IN_FLIGHT",
        "STAGE_C_BUDGET_EXHAUSTED",
        "STAGE_C_HALTED",
        "STAGE_C_LEDGER_WRITE_FAILED",
        "STAGE_C_RESERVE_INVALID",
        "STAGE_C_WINDOW_EXHAUSTED",
        "UNKNOWN_MODEL",
    }
)

# Raised after a completed, billed attempt and always with its usage (optimus_gateway.model_policy's reply
# checks, status 422). On the experimental route each one also stops the route (r8 offline correction).
REPLY_REFUSAL_CODES = frozenset(
    {
        "DECISION_MODEL_MISMATCH",
        "EMPIRICAL_ESTIMATE_EXCEEDED",
        "EMPIRICAL_PROVIDER_MISMATCH",
        "EMPIRICAL_PROVIDER_MISSING",
        "EMPIRICAL_ROUTER_FALLBACK",
        "EMPIRICAL_ROUTER_METADATA_MALFORMED",
        "EMPIRICAL_ROUTER_METADATA_MISSING",
        "EMPIRICAL_ROUTER_PIPELINE",
        "FINISH_STATUS_UNVERIFIED",
    }
)
# The enforced attempt contract's failures (optimus_gateway.responses: `UPSTREAM_ATTEMPT_<outcome>`).
UPSTREAM_ATTEMPT_CODES = frozenset({"UPSTREAM_ATTEMPT_NOT_SENT", "UPSTREAM_ATTEMPT_REJECTED", "UPSTREAM_ATTEMPT_UNCERTAIN"})
# Every code the Gateway returns: the only codes a diagnostic writes. Tests keep each set equal to the Gateway's.
GATEWAY_FAILURE_CODES = PREFLIGHT_REFUSAL_CODES | REPLY_REFUSAL_CODES | UPSTREAM_ATTEMPT_CODES
# After one of these on an experimental route the Gateway admits no further request on it for the rest of its
# life (optimus_gateway.responses._stop_experimental_route), and then refuses with EMPIRICAL_ROUTE_STOPPED.
ROUTE_STOP_CODES = REPLY_REFUSAL_CODES | {"UPSTREAM_ATTEMPT_UNCERTAIN", "EMPIRICAL_ROUTE_STOPPED"}
UNRECOGNIZED_CODE = "UNRECOGNIZED"

_ZERO_COST = frozenset({"not_sent", "rejected"})
OUTCOMES = frozenset({"completed", *_ZERO_COST, "uncertain", "unattributed"})


class AttemptIntegrityError(ValueError):
    """The Gateway's report cannot be attributed truthfully, such as settled usage that names no
    completed attempt. An integrity error, never an ordinary failure: it is raised, not settled.

    `attempts` is what can still be recorded truthfully: the reported usage as one `unattributed`
    record, then the route attempts as reported but unsettled. Record them, then raise."""

    def __init__(self, message: str, *, attempts: tuple[ProviderAttempt, ...] = ()) -> None:
        super().__init__(message)
        self.attempts = attempts


def first_error(errors: Sequence[BaseException]) -> BaseException:
    """The first of the accounting errors held while every record was still offered, with each other
    one noted on it by type (content-free), so raising one never loses the rest (Fable CP3
    correction-2 review NIT-1)."""
    first = errors[0]
    for other in errors[1:]:
        note = f"accounting also failed: {type(other).__name__}"
        if other is not first and note not in getattr(first, "__notes__", ()):
            first.add_note(note)
    return first


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    """One provider attempt. ``cost_usd`` is None when unknown, never a stand-in zero.

    ``routed`` is True when the Gateway reported the attempt in ``route_attempts``; ``number`` is then
    its position there. ``gateway_usage`` is set only on the attempt whose usage settled the request,
    or on an ``unattributed`` record: reported usage that names no single completed attempt. That record
    is not a provider attempt; its ``key`` is ``usage``, never an attempt number.
    """

    number: int
    outcome: str
    cost_usd: Decimal | None
    gateway_request_id: str | None = None
    provider_request_id: str | None = None
    http_status: int | None = None
    gateway_usage: GatewayUsage | None = None
    routed: bool = False
    router_pipeline: tuple[str, ...] | None = None
    router_guardrails: Any = None  # as received; diagnostic only, re-bounded wherever it is persisted (#400)
    failure: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.number < 1 or self.outcome not in OUTCOMES:
            raise ValueError("a provider attempt needs a positive number and a known outcome")
        if self.outcome in _ZERO_COST and self.cost_usd != Decimal("0"):
            raise ValueError("an attempt that reached no model costs exactly 0")
        if self.outcome == "uncertain" and self.cost_usd is not None:
            raise ValueError("an uncertain attempt's cost is unknown")
        usage = self.gateway_usage
        if self.outcome == "unattributed" and (usage is None or self.routed):
            raise ValueError("an unattributed record is reported usage, never a route attempt")
        if usage is not None and (
            self.outcome not in {"completed", "unattributed"}
            or self.cost_usd != usage.cost_usd
            or self.gateway_request_id != usage.gateway_request_id
        ):
            raise ValueError("only the completed attempt that settled the request carries its usage")

    @property
    def key(self) -> str:
        """The record's identity within its host request: the attempt number, or `usage`."""
        return "usage" if self.outcome == "unattributed" else str(self.number)


def is_preflight_refusal(exc: BaseException) -> bool:
    """A Gateway refusal proven to precede any upstream attempt: a known preflight code, not
    retryable, no route attempts and no usage. Anything short of all four is not proof; an attempt
    list the client had to drop as malformed is not an empty one."""
    return (
        isinstance(exc, GatewayHttpError)
        and exc.gateway_code in PREFLIGHT_REFUSAL_CODES
        and exc.retryable is False
        and not exc.route_attempts
        and not exc.route_attempts_malformed
        and exc.gateway_usage is None
    )


# Preflight refusals that mean the running Gateway does not enforce this install's trusted registry: it
# enforces none (started before the upgrade) or another one. Typically a Gateway adopted with --no-auto-start or
# started by `optimus-trust run-gateway` (Plan 12.2 closure; Codex 6249427656).
GATEWAY_REGISTRY_MISMATCH_CODES = frozenset({"BINDING_UNSUPPORTED", "REGISTRY_HASH_MISMATCH"})


def is_gateway_registry_mismatch(exc: BaseException) -> bool:
    """A proven preflight refusal because the running Gateway enforces no registry or another one."""
    return is_preflight_refusal(exc) and getattr(exc, "gateway_code", None) in GATEWAY_REGISTRY_MISMATCH_CODES


_REGISTRY_MISMATCH_OPENINGS = {
    "CHAT_GATEWAY_REGISTRY_MISMATCH": "Chat could not answer because the running model gateway does not match this launch's model registry.",
    "PLANNING_GATEWAY_REGISTRY_MISMATCH": "Planning stopped because the running model gateway does not match this launch's model registry.",
}


def gateway_registry_mismatch_text(stop_reason: str, workspace_root: Path | None) -> str:
    """The product text for a registry-mismatch refusal (Codex's reviewed wording, #237 6250318148): it describes
    this refused dispatch only, never the whole turn, and names the launch's own workspace (double-quoted when it
    contains spaces; the ``<workspace>`` placeholder when unknown)."""
    workspace = "<workspace>" if workspace_root is None else str(workspace_root)
    if " " in workspace and workspace_root is not None:
        workspace = f'"{workspace}"'
    return (
        f"{_REGISTRY_MISMATCH_OPENINGS[stop_reason]} It refused this request before sending it to a model. This refused "
        "request incurred no provider charge. Stop and restart the gateway owned by this launch using its reviewed "
        "workspace configuration. If you manage the gateway yourself, re-approve that configuration with "
        f"`optimus-trust --workspace-root {workspace} approve --mode durable`, then use "
        f"`optimus-trust --workspace-root {workspace} run-gateway` with the same reviewed launch options. Coordinate "
        "with its owner if the gateway is shared."
    )


def is_input_capacity_refusal(exc: BaseException) -> bool:
    """A proven preflight refusal whose stated cause is that the complete input exceeds the route's
    usable capacity. Only `INPUT_EXCEEDS_CAPACITY` establishes that cause: the reasonless
    `CAPACITY_REFUSED` fallback names none, so it keeps the generic refusal (release supplement V1;
    Codex concurrence disposition, 2026-10-04)."""
    return is_preflight_refusal(exc) and getattr(exc, "gateway_code", None) == "INPUT_EXCEEDS_CAPACITY"


def gateway_failure_facts(exc: BaseException) -> dict[str, Any] | None:
    """A failed request's content-free Gateway facts, for diagnostics only (r8 offline correction): its refusal
    code when the Gateway's own, `UNRECOGNIZED` for any other code (never its text), its outer HTTP status as an
    integer, the host's own cause, a dropped-attempts flag and an error body's fixed envelope facts. None when the
    request did not fail with a Gateway HTTP error. A fact not reported stays null, and the client's 0 (no HTTP
    reply) is not a status."""
    if not isinstance(exc, GatewayHttpError):
        return None
    code = exc.gateway_code
    status = exc.status_code
    facts: dict[str, Any] = {
        "code": None if code is None else code if code in GATEWAY_FAILURE_CODES else UNRECOGNIZED_CODE,
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
    }
    failure = bounded_failure(exc.failure)
    if failure is not None:
        facts["failure"] = failure  # the host's own cause: transport class and errno, or an unreadable reply
    if exc.route_attempts_malformed:
        facts["route_attempts_malformed"] = True
    envelope = getattr(exc, "error_envelope", None)
    if isinstance(envelope, dict):  # an HTTP error body's fixed facts (correction plan v4, C3), re-bounded
        facts["error_envelope"] = {
            "error_body_encoding": bounded(envelope.get("error_body_encoding"), _ENVELOPE_ENCODINGS),
            "error_body": bounded(envelope.get("error_body"), _ENVELOPE_BODIES),
            "usage_audit_code": bounded(envelope.get("usage_audit_code"), AUDIT_CODES),
        }
    return facts


_ENVELOPE_ENCODINGS = frozenset({"ok", "invalid_utf8"})
_ENVELOPE_BODIES = frozenset({"ok", "invalid_json", "non_object"})


# Every audit code a host response-contract failure carries (optimus.gateway.models, tool_models).
AUDIT_CODES = frozenset(
    {
        "GATEWAY_USAGE_MISSING",
        "GATEWAY_USAGE_INVALID",
        "OUTPUT_TEXT_MISSING",
        "RESPONSE_ID_INVALID",
        "FINISH_REASON_INVALID",
        "GATEWAY_COST_MISSING",
        "ROUTE_ATTEMPTS_MALFORMED",
    }
)


def host_failure_facts(exc: BaseException) -> dict[str, Any] | None:
    """A failed request's content-free host cause when the Gateway facts cannot carry it (Plan 12.2 diagnosability;
    Codex round 13 finding 2): a response-contract failure's allowlisted audit code, or any other exception's class,
    first cause and errno. Never its text. None for a Gateway HTTP error, whose facts already carry its cause."""
    if isinstance(exc, GatewayHttpError):
        return None
    if isinstance(exc, GatewayResponseError):
        return {"audit_code": bounded(exc.audit_code, AUDIT_CODES)}
    return {"exception": exception_fact(exc)}


def stops_experimental_route(exc: BaseException, *, experimental: bool) -> bool:
    """Whether this failure proves the request's experimental route is stopped: the Gateway's refusal of a stopped
    route, or a stop-tripping code on a route the host's trusted snapshot names experimental."""
    if not isinstance(exc, GatewayHttpError) or exc.gateway_code not in ROUTE_STOP_CODES:
        return False
    return exc.gateway_code == "EMPIRICAL_ROUTE_STOPPED" or experimental


# The closing sentence of every stopped-route text, Chat's and Agent mode's (r8 offline correction; #400).
ROUTE_STOPPED_NO_RETRY = "No further request on this route will be sent while this agent runs, so retrying will not help."


def attempts_from_response(response: GatewayResponse) -> tuple[ProviderAttempt, ...]:
    """Every provider attempt behind a successful response."""
    return _attempts(response.route_attempts, response.gateway_usage, http_status=None)


def attempts_from_decision(decision: GatewayDecision) -> tuple[ProviderAttempt, ...]:
    """Every provider attempt behind a 200 decision reply (Plan 12.4 Task 5), attributed as for a model reply."""
    return _attempts(decision.route_attempts, decision.gateway_usage, http_status=None)


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
        # The settled usage belongs to the completed attempt it names, and only to it: never counted
        # twice, never attributed by position.
        settled = None
        if usage is not None:
            named = [item.attempt for item in route_attempts if item.outcome == "completed" and item.gateway_request_id == usage.gateway_request_id]
            if len(named) != 1:
                # Keep the reported charge (known, counted once) without guessing which attempt it
                # settled; the route attempts stay as reported, unsettled.
                unattributed = ProviderAttempt(
                    number=1,
                    outcome="unattributed",
                    cost_usd=usage.cost_usd,
                    gateway_request_id=usage.gateway_request_id,
                    provider_request_id=usage.provider_request_id,
                    http_status=http_status,
                    gateway_usage=usage,
                )
                raise AttemptIntegrityError(
                    "the Gateway's settled usage names no single completed route attempt",
                    attempts=(unattributed, *(_routed(item, None) for item in route_attempts)),
                )
            settled = named[0]
        return tuple(_routed(item, usage if item.attempt == settled else None) for item in route_attempts)
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
    outcome = item.outcome
    if outcome in _ZERO_COST:
        cost: Decimal | None = Decimal("0")
    elif outcome == "completed" and usage is not None:
        cost = usage.cost_usd
    else:
        # Uncertain, or completed without the usage that would settle it: it may have been billed and
        # nothing settles it, so it is uncertain at unknown cost (as the Gateway itself reports it).
        outcome, cost, usage = "uncertain", None, None
    return ProviderAttempt(
        number=item.attempt,
        outcome=outcome,
        cost_usd=cost,
        gateway_request_id=item.gateway_request_id,
        provider_request_id=item.provider_request_id,
        http_status=item.http_status,
        gateway_usage=usage,
        routed=True,
        router_pipeline=item.router_pipeline,
        router_guardrails=item.router_guardrails,
        failure=item.failure,
    )
