"""Request-scoped identity and outcomes for local ACP diagnostics."""

from __future__ import annotations

from contextvars import Context, ContextVar, copy_context
from dataclasses import dataclass, replace
from typing import Literal

from optimus_security.failure_facts import UNRECOGNIZED, host_route_id, host_session_id

RequestTransport = Literal["framed", "ndjson"]
HandlerOutcome = Literal["pending", "returned_result", "returned_error", "raised", "cancelled"]
DeliveryOutcome = Literal["not_attempted", "outside_dispatch", "pending", "flushed", "not_flushed", "failed", "cancelled"]

APPROVED_METHOD_CATEGORIES = frozenset({
    "initialize",
    "session/new",
    "session/load",
    "session/prompt",
    "session/set_mode",
    "session/set_config_option",
})

_FRAMED_METHODS = frozenset({
    "optimus.ping",
    "optimus.gateway.responses",
    "optimus.evidence.search",
    "optimus.evidence.extract",
    "optimus.evidence.package_lookup",
    "optimus.evidence.security_advisory",
    "optimus.agent.run",
    "optimus.mutation.writeFile",
})


def diagnostic_method(method: object, transport: RequestTransport) -> str:
    methods = _FRAMED_METHODS if transport == "framed" else APPROVED_METHOD_CATEGORIES
    return method if isinstance(method, str) and method in methods else "unknown"


@dataclass(frozen=True, slots=True)
class RequestCorrelation:
    operation_id: str
    transport: RequestTransport
    method: str
    session_id: str | None = None
    run_id: str | None = None

    def fields(self) -> dict[str, str]:
        fields = {"operationId": self.operation_id, "transport": self.transport, "method": self.method}
        if self.session_id is not None:
            fields["sessionId"] = self.session_id
        if self.run_id is not None:
            fields["runId"] = self.run_id
        return fields


request_correlation: ContextVar[RequestCorrelation | None] = ContextVar("acp_request_correlation", default=None)


def add_trusted_request_identity(*, session_id: str | None, run_id: str | None = None) -> None:
    current = request_correlation.get()
    if current is None:
        return
    session = host_session_id(session_id)
    run = host_route_id(run_id)
    if session is None or session == UNRECOGNIZED or current.session_id not in (None, session):
        return
    if run is None or run == UNRECOGNIZED or not run.startswith(f"{session}:"):
        run = None
    request_correlation.set(replace(current, session_id=session, run_id=current.run_id or run))


def detached_request_context() -> Context:
    """Keep ambient runtime state while clearing request-only identity."""
    context = copy_context()
    context.run(request_correlation.set, None)
    return context


@dataclass(slots=True)
class RequestObservation:
    handler: HandlerOutcome = "pending"
    delivery: DeliveryOutcome = "not_attempted"
    recovery_delivery: DeliveryOutcome | None = None
    failure_phase: Literal["handler", "delivery", "after_delivery", "recovery_delivery"] | None = None

    def returned(self, *, has_error: bool) -> None:
        self.handler = "returned_error" if has_error else "returned_result"

    def interrupted(self, *, cancelled: bool) -> None:
        delivery: DeliveryOutcome = "cancelled" if cancelled else "failed"
        if self.recovery_delivery == "pending":
            self.recovery_delivery = delivery
            self.failure_phase = self.failure_phase or "recovery_delivery"
        elif self.handler == "pending":
            self.handler = "cancelled" if cancelled else "raised"
            self.failure_phase = self.failure_phase or "handler"
        elif self.delivery == "pending":
            self.delivery = delivery
            self.failure_phase = self.failure_phase or "delivery"
        else:
            self.failure_phase = self.failure_phase or "after_delivery"
