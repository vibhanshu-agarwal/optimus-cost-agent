"""Trusted registry composition and the per-request route binding (Plan 12.2 Task 5).

Shared by the host, the launch gate and the Gateway, so each side computes the same digests from the
same code. Enforcement is built but inactive (operator decision 2026-10-02): ``ENFORCEMENT_ACTIVE``
stays False until a verified snapshot is approved after Task 12's measurements. While it is False,
:func:`trusted_snapshot` returns None, launch approvals and Gateway manifests carry no registry
binding and the Gateway keeps today's routing. Activation is a reviewed code change, never an
environment variable, file or caller field.

Trust flows one way. The launch gate composes the snapshot, folds :func:`approval_literal` into the
HMAC-protected approval (so the operator approves that exact effective hash) and signs it into the
Gateway child manifest; the Gateway composes its own snapshot and refuses to start unless the two
agree. A ``registry_hash`` in a request is only the caller's view, checked against that trusted
snapshot; it never grants anything.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from optimus_model_policy.capacity import Message
from optimus_model_policy.registry import ModelEntry, RegistrySnapshot, load_registry

__all__ = [
    "APPROVAL_LITERAL_NAME",
    "ENFORCEMENT_ACTIVE",
    "ROUTE_BINDING_VERSION",
    "BindingError",
    "DisclosureAuthorization",
    "RouteBinding",
    "approval_literal",
    "compose_trusted_snapshot",
    "disclosure_key",
    "issue_disclosure",
    "payload_digest",
    "route_digest",
    "trusted_approval_literal",
    "trusted_snapshot",
    "verify_disclosure",
]

ENFORCEMENT_ACTIVE: Final = False
"""Registry enforcement and the fixed medium default. Off until a verified snapshot is approved."""

APPROVAL_LITERAL_NAME: Final = "_model_registry"
"""The security-literal name under which a launch approval binds the effective registry hash."""

_APPROVAL_LITERAL_PREFIX: Final = "optimus-model-registry-v1:"
ROUTE_BINDING_VERSION: Final = 1
"""Wire version of the ``route_binding`` request field. Other versions are rejected, not ignored."""

_DISCLOSURE_KEY_DOMAIN: Final = b"plan12-contributor-disclosure-key-v1"
_DISCLOSURE_MAC_DOMAIN: Final = b"plan12-contributor-disclosure-v1"
_HEX_DIGEST_LENGTH: Final = 64


class BindingError(ValueError):
    """A trusted-composition or route-binding failure, identified by a stable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


# --- Trusted composition ---------------------------------------------------------------------------


def packaged_defaults() -> Path:
    return Path(__file__).with_name("defaults.yaml")


def compose_trusted_snapshot(defaults: Path) -> RegistrySnapshot:
    """Load the registry a launch may trust. Fixture policies never activate."""
    snapshot = load_registry(defaults, None)
    if snapshot.policy.fixture:
        raise BindingError("FIXTURE_POLICY", "a fixture registry cannot be trusted at launch")
    return snapshot


def trusted_snapshot() -> RegistrySnapshot | None:
    """The snapshot this install enforces, or None while enforcement is inactive."""
    if not ENFORCEMENT_ACTIVE:
        return None
    return compose_trusted_snapshot(packaged_defaults())


def approval_literal(snapshot: RegistrySnapshot) -> str:
    """The bounded value a launch approval and a Gateway manifest bind: schema version and hash."""
    return _APPROVAL_LITERAL_PREFIX + snapshot.effective_hash


def trusted_approval_literal() -> str | None:
    snapshot = trusted_snapshot()
    return None if snapshot is None else approval_literal(snapshot)


# --- Digests ---------------------------------------------------------------------------------------


def _sha256_canonical(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def route_digest(model_id: str, entry: ModelEntry) -> str:
    """Identity of one model's approved route: its endpoint allow-set and routing controls."""
    return _sha256_canonical({"model": model_id, "route": entry.route.model_dump(mode="json")})


def payload_digest(model_id: str, messages: Sequence[Message], output_cap: int) -> str:
    """Identity of the final upstream payload, after every host and Gateway transformation."""
    return _sha256_canonical(
        {"model": model_id, "messages": [[message.role, message.content] for message in messages], "output_cap": output_cap}
    )


# --- Contributor disclosure ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DisclosureAuthorization:
    """The host's binding of a Contributor notice to one request, route and payload.

    It is an integrity binding under the per-launch key the host and Gateway share, not independent
    proof: anything holding the launch's bearer secret can mint one, so the guarantee is that the host
    component delivering the notice issues it for exactly this payload. One authorization covers
    identical-payload transport retries on the same route; a changed payload, another route,
    maintenance or a fallback needs a new notice and a new authorization.
    """

    route_digest: str
    payload_digest: str
    mac: str


def disclosure_key(shared_secret: str) -> bytes:
    """Per-launch key, derived from the secret host and Gateway already share for this launch."""
    return hmac.new(shared_secret.encode("utf-8"), _DISCLOSURE_KEY_DOMAIN, hashlib.sha256).digest()


def _disclosure_mac(key: bytes, *, request_id: str, model_id: str, route: str, payload: str) -> str:
    # Each field is length-prefixed, so no request or model text can shift a field boundary.
    fields = (request_id.encode("utf-8"), model_id.encode("utf-8"), route.encode("ascii"), payload.encode("ascii"))
    message = _DISCLOSURE_MAC_DOMAIN + b"".join(len(field).to_bytes(4, "big") + field for field in fields)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def issue_disclosure(key: bytes, *, request_id: str, model_id: str, route: str, payload: str) -> DisclosureAuthorization:
    """Called by the host only after it has delivered the Contributor notice for this payload."""
    return DisclosureAuthorization(
        route_digest=route,
        payload_digest=payload,
        mac=_disclosure_mac(key, request_id=request_id, model_id=model_id, route=route, payload=payload),
    )


def verify_disclosure(
    key: bytes, authorization: DisclosureAuthorization, *, request_id: str, model_id: str, route: str, payload: str
) -> bool:
    if authorization.route_digest != route or authorization.payload_digest != payload:
        return False
    expected = _disclosure_mac(key, request_id=request_id, model_id=model_id, route=route, payload=payload)
    return hmac.compare_digest(authorization.mac, expected)


# --- Route binding (wire) --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RouteBinding:
    """The host's per-request binding: the snapshot it composed, its request identity, the output
    cap it reserved and, for a Contributor route, its disclosure authorization."""

    registry_hash: str
    request_id: str
    output_cap: int
    disclosure: DisclosureAuthorization | None = None

    def to_wire(self) -> dict[str, Any]:
        wire: dict[str, Any] = {
            "version": ROUTE_BINDING_VERSION,
            "registry_hash": self.registry_hash,
            "request_id": self.request_id,
            "output_cap": self.output_cap,
        }
        if self.disclosure is not None:
            wire["disclosure"] = {
                "route_digest": self.disclosure.route_digest,
                "payload_digest": self.disclosure.payload_digest,
                "mac": self.disclosure.mac,
            }
        return wire

    @classmethod
    def from_wire(cls, raw: object) -> RouteBinding:
        """Strict parse: unknown fields, other versions and malformed values are rejected."""
        if not isinstance(raw, Mapping):
            raise BindingError("BINDING_MALFORMED", "route_binding must be an object")
        _exact_keys(raw, required={"version", "registry_hash", "request_id", "output_cap"}, optional={"disclosure"})
        version = raw["version"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise BindingError("BINDING_MALFORMED", "version must be an integer")
        if version != ROUTE_BINDING_VERSION:
            raise BindingError("BINDING_VERSION_UNSUPPORTED", f"route_binding version {version!r}")
        output_cap = raw["output_cap"]
        if isinstance(output_cap, bool) or not isinstance(output_cap, int):
            raise BindingError("BINDING_MALFORMED", "output_cap must be an integer")
        request_id = raw["request_id"]
        if not isinstance(request_id, str) or not request_id.strip():
            raise BindingError("BINDING_MALFORMED", "request_id must be a non-empty string")
        disclosure = None
        if raw.get("disclosure") is not None:
            item = raw["disclosure"]
            if not isinstance(item, Mapping):
                raise BindingError("BINDING_MALFORMED", "disclosure must be an object")
            _exact_keys(item, required={"route_digest", "payload_digest", "mac"}, optional=set())
            disclosure = DisclosureAuthorization(
                route_digest=_hex_digest(item["route_digest"], "route_digest"),
                payload_digest=_hex_digest(item["payload_digest"], "payload_digest"),
                mac=_hex_digest(item["mac"], "mac"),
            )
        return cls(
            registry_hash=_hex_digest(raw["registry_hash"], "registry_hash"),
            request_id=request_id,
            output_cap=output_cap,
            disclosure=disclosure,
        )


def _exact_keys(raw: Mapping[Any, Any], *, required: set[str], optional: set[str]) -> None:
    keys = set(raw)
    missing = required - keys
    if missing:
        raise BindingError("BINDING_MALFORMED", f"missing {sorted(missing)}")
    unknown = keys - required - optional
    if unknown:
        raise BindingError("BINDING_MALFORMED", f"unknown fields {sorted(map(str, unknown))}")


def _hex_digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _HEX_DIGEST_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BindingError("BINDING_MALFORMED", f"{field} must be a lower-case SHA-256 hex digest")
    return value
