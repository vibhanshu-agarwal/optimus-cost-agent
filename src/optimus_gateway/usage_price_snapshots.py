"""Immutable price snapshots through the Gateway's capture outbox (Plan 12.9; ADR-034).

A registry snapshot records the actual side: the effective registry's hash, and each model's tier, roles, list prices
and approved route (its endpoints' providers and quantizations and its routing switches), for provenance and tier attribution only (settled cost stays the provider's reported charge). A reference
snapshot records one dated reference price schedule (`optimus_model_policy.savings_references`); references are never
looked up in the registry. Both IDs are derived from content, so the same configuration is the same snapshot.

`price_snapshot_id` is set on a usage envelope only once its registry snapshot is durable in the local outbox; until
then, without accounting, or without an enforced registry it is None. A failed or slow snapshot write never refuses or
delays a request beyond the outbox's short acknowledgement wait. Process-wide like `usage_capture`.
"""

from __future__ import annotations

import functools
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from optimus_model_policy.registry import RegistrySnapshot, canonical_decimal
from optimus_model_policy.savings_references import Reference, ReferenceSet, load_references, packaged_references
from optimus_security import usage_capture_contract as uc
from optimus_security.durable_outbox import ACK_WAIT_SECONDS, OutboxWriter, Ticket

if TYPE_CHECKING:
    from optimus_gateway.model_policy import GatewayModelPolicy

_lock = threading.Lock()
_writer: OutboxWriter | None = None
_references: ReferenceSet | None = None  # an approved operator override; None: the packaged file
_payloads: dict[str, dict[str, Any] | None] = {}  # effective hash -> its snapshot payload (None: not representable)
_tickets: dict[str, Ticket] = {}  # snapshot ID -> its write


def configure(writer: OutboxWriter | None, *, references: ReferenceSet | None = None) -> None:
    global _writer, _references
    with _lock:
        _writer, _references = writer, references
        _tickets.clear()


def configured_references() -> ReferenceSet:
    """The launch-approved override when there is one, else the packaged dated reference prices."""
    return _references if _references is not None else _packaged()


@functools.cache
def _packaged() -> ReferenceSet:
    return load_references(packaged_references())  # validated by its tests; the file ships with the package


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _valid(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Only a payload the ledger will accept enters the stream: a refused record would stop the stream's delivery."""
    try:
        uc.validate_payload(payload, writer="gateway")
    except uc.ContractError:
        return None
    return payload


def registry_payload(snapshot: RegistrySnapshot) -> dict[str, Any] | None:
    policy = snapshot.policy
    roles: dict[str, list[str]] = {}
    for role, model_ids in policy.roles.items():
        for model_id in model_ids:
            roles.setdefault(model_id, []).append(str(role))
    payload: dict[str, Any] = {
        "kind": uc.REGISTRY_SNAPSHOT, "at": _now(), "registry_hash": snapshot.effective_hash,
        "price_as_of": None,  # the registry's price date is a YAML comment, not data
        "entries": [
            {"model": model_id, "tier": str(entry.tier), "roles": sorted(roles.get(model_id, [])),
             "input_usd_per_million": canonical_decimal(entry.prices.input_usd_per_million),
             "output_usd_per_million": canonical_decimal(entry.prices.output_usd_per_million),
             "route": {"providers": [e.provider for e in entry.route.endpoints],
                       "quantizations": [e.quantization for e in entry.route.endpoints],
                       "allow_fallbacks": entry.route.allow_fallbacks, "require_parameters": entry.route.require_parameters}}
            for model_id, entry in sorted(policy.models.items())
        ],
    }
    payload["snapshot_id"] = uc.snapshot_id(uc.REGISTRY_SNAPSHOT, payload)
    return _valid(payload)


def reference_payload(reference: Reference) -> dict[str, Any] | None:
    return _valid({"kind": uc.REFERENCE_SNAPSHOT, "at": _now(), "snapshot_id": reference.snapshot_id,
                   "reference": reference.model_dump(mode="json")})


def _write(writer: OutboxWriter, payload: dict[str, Any]) -> Ticket:
    """The snapshot's write, submitted again only after a failed one (caller holds `_lock`)."""
    ticket = _tickets.get(payload["snapshot_id"])
    if ticket is None or (ticket.resolved and ticket.record is None):
        ticket = _tickets[payload["snapshot_id"]] = writer.submit(payload)
    return ticket


def registry_snapshot_id(policy: GatewayModelPolicy | None) -> str | None:
    """The ID of the registry snapshot this request used, once that snapshot is durable locally; otherwise None."""
    with _lock:
        writer = _writer
        if writer is None or policy is None:
            return None
        key = policy.snapshot.effective_hash
        if key not in _payloads:
            _payloads[key] = registry_payload(policy.snapshot)
        payload = _payloads[key]
        if payload is None:
            return None
        ticket = _write(writer, payload)
    return payload["snapshot_id"] if ticket.wait(ACK_WAIT_SECONDS) else None


def stamp(usage: dict[str, Any], policy: GatewayModelPolicy | None) -> dict[str, Any]:
    """``usage`` with its ``price_snapshot_id`` once that is durable; absent, not null, until then, so a usage envelope
    without a snapshot keeps its earlier bytes."""
    snapshot_id = registry_snapshot_id(policy)
    if snapshot_id is not None:
        usage["price_snapshot_id"] = snapshot_id
    return usage


def record_references(references: ReferenceSet) -> None:
    """Capture each adopted reference schedule (at accounting start); the report reads them, never writes them."""
    with _lock:
        writer = _writer
        if writer is None:
            return
        for reference in references.references:
            payload = reference_payload(reference)
            if payload is not None:
                _write(writer, payload)
