"""Trusted route identity and per-turn request binding (Plan 12.2 CP3; Task 1 contracts 4 and 6;
Codex CP3 ruling R4 and R5).

`RouteIdentity` is what a request is bound to: the exact registry model, its role, its approved
endpoints, reasoning setting and quantizations, and the trusted snapshot they come from. It is read
from the snapshot, never from a caller's claim, and every receipt of the request carries it.

`RoutePolicy` is the injected trusted policy for the planning/answer route: the launch snapshot, the
per-launch disclosure key, the exact model and role and an explicit output cap. Nothing ships one:
attaching it at startup, choosing the numeric cap and qualifying the route stay held (activation
hold). Without a policy no binding is sent, as today (registry enforcement inactive).

A turn captures its `TurnRouteBinder` before any await, so a later setter cannot change what its
requests are bound to. Each new payload is a new request: it gets its own request identity and, on a
Contributor route, its own notice before its disclosure is issued; an undelivered notice binds
nothing, so nothing is sent. An identical bounded transport retry of the same payload reuses its
binding, with its own attempt identity.
"""

from __future__ import annotations

import itertools
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from optimus.gateway.disclosure import ContributorDisclosure
from optimus_model_policy import Message, PackedModelRequest, RegistrySnapshot, guard_request
from optimus_model_policy.binding import RouteBinding

__all__ = [
    "BoundRequest",
    "RequestReading",
    "RouteIdentity",
    "RouteIdentityError",
    "RoutePolicy",
    "TurnRouteBinder",
    "registry_route_identity",
]


class RouteIdentityError(ValueError):
    """A route identity that does not match the trusted snapshot or the route actually bound."""


@dataclass(frozen=True, slots=True)
class RouteIdentity:
    model_id: str
    role: str
    route: tuple[str, ...]
    reasoning: str | None
    quantizations: tuple[str | None, ...]
    registry_hash: str


def registry_route_identity(snapshot: RegistrySnapshot, *, model_id: str, role: str) -> RouteIdentity:
    """The identity the trusted snapshot gives `model_id` in `role`."""
    entry = snapshot.policy.models.get(model_id)
    if entry is None:
        raise RouteIdentityError(f"model {model_id!r} is not in the trusted registry")
    if not role:
        raise RouteIdentityError("a route identity needs its role")
    endpoints = entry.route.endpoints
    return RouteIdentity(
        model_id=model_id,
        role=role,
        route=tuple(endpoint.provider for endpoint in endpoints),
        reasoning=entry.default_reasoning,
        quantizations=tuple(endpoint.quantization for endpoint in endpoints),
        registry_hash=snapshot.effective_hash,
    )


@dataclass(frozen=True, slots=True)
class RequestReading:
    """One planning/answer request actually sent without an attached engine: its complete-input
    estimate and that request's usable input capacity, as the Gateway's final guard computes them."""

    tokens: int
    capacity: int

    @property
    def fraction(self) -> float:
        return self.tokens / self.capacity


@dataclass(frozen=True, slots=True)
class BoundRequest:
    """One host request's binding and the identity it binds."""

    request_id: str
    binding: RouteBinding
    identity: RouteIdentity


class RoutePolicy:
    """The trusted planning/answer route policy (see the module docstring)."""

    def __init__(self, *, snapshot: RegistrySnapshot, disclosure_key: bytes, model_id: str, role: str, output_cap: int) -> None:
        if isinstance(output_cap, bool) or not isinstance(output_cap, int) or output_cap <= 0:
            raise RouteIdentityError("the route's output cap must be an explicit positive integer")
        if not disclosure_key:
            raise RouteIdentityError("a bound route needs the launch disclosure key")
        self._snapshot = snapshot
        self._key = disclosure_key
        self.identity = registry_route_identity(snapshot, model_id=model_id, role=role)
        self.output_cap = output_cap

    def capture(self, *, session_id: str, turn_seq: int, deliver_notice: Callable[[str], bool]) -> TurnRouteBinder:
        """This turn's binder; call it before any await."""
        disclosure = ContributorDisclosure(snapshot=self._snapshot, key=self._key, deliver_notice=deliver_notice)
        return TurnRouteBinder(
            identity=self.identity,
            output_cap=self.output_cap,
            disclosure=disclosure,
            session_id=session_id,
            turn_seq=turn_seq,
            snapshot=self._snapshot,
        )


class TurnRouteBinder:
    """One turn's request binder: its captured identity and the turn's notice channel."""

    def __init__(
        self,
        *,
        identity: RouteIdentity,
        output_cap: int,
        disclosure: ContributorDisclosure,
        session_id: str,
        turn_seq: int,
        snapshot: RegistrySnapshot | None = None,
    ) -> None:
        self.identity = identity
        self.output_cap = output_cap
        self._disclosure = disclosure
        self._snapshot = snapshot
        self._prefix = f"{session_id}:{turn_seq}"
        self._ordinal = itertools.count(1)
        self._lock = threading.Lock()
        self._readings: list[RequestReading] = []

    def record_dispatch(self, input_text: str) -> None:
        """The runner is sending `input_text` as one complete planning/answer request now (no attached
        engine). Its reading uses the same packed input, verified estimator and usable capacity as the
        Gateway's final guard (release supplement V1). A request that guard would refuse records nothing:
        its capacity refusal is shown instead, never a successful reading."""
        if self._snapshot is None:
            return
        packed = PackedModelRequest(
            model_id=self.identity.model_id, messages=(Message(role="user", content=input_text),), tools_json="", output_cap=self.output_cap
        )
        decision = guard_request(packed, self._snapshot, self._snapshot.effective_hash)
        if decision.allowed:
            with self._lock:
                self._readings.append(RequestReading(tokens=decision.input_tokens, capacity=decision.usable_input))

    def largest_dispatch(self) -> RequestReading | None:
        """The turn's meter reading: the largest request sent, the smaller capacity on a tie; None when
        nothing was sent."""
        with self._lock:
            readings = list(self._readings)
        if not readings:
            return None
        return max(readings, key=lambda reading: (reading.tokens, -reading.capacity))

    def bind(self, *, stage: str, input_text: str) -> BoundRequest | None:
        """A new request for the complete final `input_text`, or None when its required notice was
        not delivered (then nothing may be sent)."""
        with self._lock:
            ordinal = next(self._ordinal)
        request_id = f"{self._prefix}:{stage}:{ordinal}:{uuid.uuid4().hex}"
        binding = self._disclosure.binding(
            model_id=self.identity.model_id, request_id=request_id, input_text=input_text, output_cap=self.output_cap
        )
        if binding is None:
            return None
        return BoundRequest(request_id=request_id, binding=binding, identity=self.identity)
