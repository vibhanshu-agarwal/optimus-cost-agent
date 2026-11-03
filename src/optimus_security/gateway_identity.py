"""What makes a local Gateway compatible with a launch (#465, ADR-036).

Reachability used to count as "this launch's Gateway", so a launch approved for a stub could send its prompts to a
Gateway another launch had started with a real upstream. The ACP host and the Gateway now compose one identity from
what the launch manifest already binds, and compare it before anything is sent to that Gateway. This module is neutral
(like `launch_manifest`), so neither side imports the other's package.

Each field says what goes wrong if two launches differ on it:

- ``upstream``, ``provider``: where requests go, and how they are interpreted.
- ``upstream_credential``, ``gateway_key``: who is billed, and who may call.
- ``registry``, ``composition``: which models, providers and controls are admitted (the Auto and test compositions).
- ``stage_c``: the released test envelope, which an ordinary Gateway does not enforce.
- ``accounting``: where capture lands, and how it is read.
- ``tool_policy``: which web and package upstreams the tool routes call, with which keys and limits.

Workspace, branch, security snapshot, session, nonce and expiry stay out: they authorize a host, not shared upstream
behavior, and two projects on one Gateway are ordinary use. The OTLP endpoint stays out too: it changes where this
Gateway's traces go, not what a request calls or costs, and one launch opting into local Phoenix must not refuse another.

Every value crosses the wire as a keyed fingerprint under the approval store's key, so the reply names no URL or secret,
and is stable across sessions. Only a process holding that key can answer a fresh nonce, so an old Gateway, another
program or a replayed reply cannot pass as compatible.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

PATH = "/v1/local/identity"
HEADER = "X-Optimus-Gateway-Identity"
SCHEMA = "optimus.gateway_identity.v1"
MAX_REQUEST_BYTES = 256
READ_SECONDS = 3.0  # agent-selected: a whole exchange on loopback, so a stalled listener delays a launch this much at most

COMPOSITION_STANDARD = "standard"
COMPOSITION_AUTO = "auto"

# Gateway tool configuration, as `optimus.acp.launch_policy.GATEWAY_TOOL_CHILD_ENV_NAMES` projects it to the child.
TOOL_POLICY_NAMES = (
    "OPTIMUS_GATEWAY_MAVEN_BASE_URL",
    "OPTIMUS_GATEWAY_NPM_BASE_URL",
    "OPTIMUS_GATEWAY_OSV_API_KEY",
    "OPTIMUS_GATEWAY_OSV_BASE_URL",
    "OPTIMUS_GATEWAY_PYPI_BASE_URL",
    "OPTIMUS_GATEWAY_TAVILY_BASE_URL",
    "OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS",
    "OPTIMUS_GATEWAY_TOOL_MAX_CALLS_PER_TOOL",
    "OPTIMUS_GATEWAY_TOOL_REDIS_URL",
    "TAVILY_API_KEY",
)

# Each field and how a refusal names it to the person reading the Agent Panel.
FIELD_LABELS: Mapping[str, str] = {
    "accounting": "usage accounting",
    "composition": "composition (ordinary, Auto or test)",
    "gateway_key": "Gateway key",
    "provider": "provider",
    "registry": "model registry",
    "stage_c": "test envelope",
    "tool_policy": "tool configuration",
    "upstream": "upstream URL",
    "upstream_credential": "upstream credential",
}

_FIELD_DOMAIN = b"p465-gateway-identity-field-v1"
_DIGEST_DOMAIN = b"p465-gateway-identity-digest-v1"
_PROOF_KEY_DOMAIN = b"p465-gateway-identity-proof-key-v1"
_PROOF_DOMAIN = b"p465-gateway-identity-proof-v1"
_NONCE = re.compile(r"[0-9a-f]{32}")
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")


class IdentityReplyError(ValueError):
    """A reply that does not prove a current Gateway identity."""


@dataclass(frozen=True)
class GatewayIdentity:
    fields: Mapping[str, str]
    digest: str


def _keyed(domain: bytes, key: bytes, *parts: str) -> str:
    message = domain + b"".join(b"\x00" + part.encode("utf-8") for part in parts)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _digest(fields: Mapping[str, str], key: bytes) -> str:
    return _keyed(_DIGEST_DOMAIN, key, json.dumps(dict(fields), sort_keys=True, separators=(",", ":")))


def _normal_url(url: str | None) -> str:
    """What the upstream client itself ignores (a trailing slash), and nothing more: its path, query and fragment change
    the request it sends, and a differently spelled host is at worst a stated refusal."""
    return (url or "").strip().rstrip("/")


def _tool_policy(environ: Mapping[str, str]) -> str:
    present = {name: environ.get(name, "").strip() for name in TOOL_POLICY_NAMES}
    return json.dumps({name: value for name, value in present.items() if value}, sort_keys=True, separators=(",", ":"))


def compose_identity(
    *,
    provider: str,
    base_url: str | None,
    provider_api_key: str,
    shared_secret: str,
    composition: str,
    model_registry: str | None,
    stage_c_envelope: str | None,
    accounting: str | None,
    tool_environ: Mapping[str, str],
    hmac_key: bytes,
) -> GatewayIdentity:
    values = {
        "accounting": accounting or "",
        "composition": composition,
        "gateway_key": shared_secret,
        "provider": provider,
        "registry": model_registry or "",
        "stage_c": stage_c_envelope or "",
        "tool_policy": _tool_policy(tool_environ),
        "upstream": _normal_url(base_url),
        "upstream_credential": provider_api_key,
    }
    fields = {name: _keyed(_FIELD_DOMAIN, hmac_key, name, value) for name, value in values.items()}
    return GatewayIdentity(fields=fields, digest=_digest(fields, hmac_key))


def profile_composition(profile: str) -> str:
    return f"test:{profile}"


def new_nonce() -> str:
    return secrets.token_hex(16)


def build_request(nonce: str) -> bytes:
    return json.dumps({"nonce": nonce}, separators=(",", ":")).encode("ascii")


def parse_request(raw: bytes) -> str | None:
    """The request's nonce, or None for anything that is not exactly this contract's request."""
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict) or set(body) != {"nonce"}:
        return None
    nonce = body["nonce"]
    return nonce if isinstance(nonce, str) and _NONCE.fullmatch(nonce) else None


def proof_key(hmac_key: bytes) -> bytes:
    """What the Gateway keeps to answer: derived, so a request handler never holds the approval store's key itself."""
    return hmac.new(hmac_key, _PROOF_KEY_DOMAIN, hashlib.sha256).digest()


def _proof(key: bytes, nonce: str, digest: str) -> str:
    return _keyed(_PROOF_DOMAIN, key, nonce, digest)


@dataclass(frozen=True)
class ServedIdentity:
    """The identity a Gateway serves, verified at startup. Its proof key stays out of every repr."""

    identity: GatewayIdentity
    key: bytes

    def __repr__(self) -> str:
        return f"ServedIdentity(digest={self.identity.digest!r})"

    def reply(self, nonce: str) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "fields": dict(self.identity.fields),
            "digest": self.identity.digest,
            "nonce": nonce,
            "proof": _proof(self.key, nonce, self.identity.digest),
        }


def read_reply(reply: Any, *, nonce: str, hmac_key: bytes) -> GatewayIdentity:
    """The identity a reply proves for this nonce, or `IdentityReplyError`. Strict: unknown shapes are never compatible."""
    if not isinstance(reply, dict) or set(reply) != {"schema", "fields", "digest", "nonce", "proof"}:
        raise IdentityReplyError("shape")
    fields, digest, proof = reply["fields"], reply["digest"], reply["proof"]
    if reply["schema"] != SCHEMA or reply["nonce"] != nonce:
        raise IdentityReplyError("nonce")
    if not isinstance(fields, dict) or set(fields) != set(FIELD_LABELS):
        raise IdentityReplyError("fields")
    if not all(isinstance(value, str) and _HEX_DIGEST.fullmatch(value) for value in (*fields.values(), digest, proof)):
        raise IdentityReplyError("fields")
    # A digest is keyed, so an answer from another key, or with one field changed, fails here even with its own proof.
    if not hmac.compare_digest(digest, _digest(fields, hmac_key)):
        raise IdentityReplyError("digest")
    if not hmac.compare_digest(proof, _proof(proof_key(hmac_key), nonce, digest)):
        raise IdentityReplyError("proof")
    return GatewayIdentity(fields=fields, digest=digest)


def differing_fields(expected: GatewayIdentity, reported: GatewayIdentity) -> tuple[str, ...]:
    return tuple(name for name in sorted(FIELD_LABELS) if expected.fields[name] != reported.fields[name])
