"""Host-issued Contributor disclosures (Plan 12.2 Task 10; design spec 9.2; Task 1 contracts 4).

Before every new host request routed to a Contributor model, the user is shown the filed notice, and
only a confirmed delivery lets the host issue the request's disclosure authorization. That
authorization is bound to the request identity, the approved route and the exact payload digest, the
same digests the Gateway verifies before dispatch. An identical bounded retry of the same request,
payload and route shares the notice; each attempt keeps its own receipt. A new payload is a new
request and needs its own notice. This is a disclosure, never a permission dialog.
"""

from __future__ import annotations

from collections.abc import Callable

from optimus_model_policy import RegistrySnapshot
from optimus_model_policy.binding import RouteBinding, issue_disclosure, payload_digest, route_digest
from optimus_model_policy.capacity import Message

CONTRIBUTOR_NOTICE = "Muse Spark Contributor may use supplied prompts, code, tool content and completions for model training."


class ContributorDisclosure:
    """Route bindings for one trusted snapshot, noticing each new Contributor request first.

    `deliver_notice` shows the notice to the user and returns True only on a confirmed delivery."""

    def __init__(self, *, snapshot: RegistrySnapshot, key: bytes, deliver_notice: Callable[[str], bool]) -> None:
        self._snapshot = snapshot
        self._key = key
        self._deliver = deliver_notice
        self._noticed: set[tuple[str, str, str]] = set()

    def binding(self, *, model_id: str, request_id: str, input_text: str, output_cap: int) -> RouteBinding | None:
        """The request's route binding, or None when its required notice was not delivered (then
        nothing may be sent)."""
        entry = self._snapshot.policy.models.get(model_id)
        if entry is None:
            raise ValueError(f"model {model_id!r} is not in the trusted registry")
        registry_hash = self._snapshot.effective_hash
        if entry.data_use.disclosure != "contributor":
            return RouteBinding(registry_hash=registry_hash, request_id=request_id, output_cap=output_cap)
        # The Gateway's upstream request is one user message holding the final flattened input.
        messages = (Message(role="user", content=input_text),)
        payload = payload_digest(model_id, messages, output_cap, reasoning=entry.default_reasoning)
        route = route_digest(model_id, entry)
        identity = (request_id, route, payload)
        if identity not in self._noticed:
            if not self._deliver(CONTRIBUTOR_NOTICE):
                return None
            self._noticed.add(identity)
        authorization = issue_disclosure(self._key, request_id=request_id, model_id=model_id, route=route, payload=payload)
        return RouteBinding(registry_hash=registry_hash, request_id=request_id, output_cap=output_cap, disclosure=authorization)
