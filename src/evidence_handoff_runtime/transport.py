"""HTTP preamble gates for the evidence-handoff Streamable HTTP service.

PreParseAuthGateStub sits at the exact pipeline position Task 6's CredentialValidator
will replace in place. It is intentionally NOT real authentication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

LEGACY_SSE_PATHS = frozenset({"/sse", "/messages", "/mcp/sse"})


def is_legacy_sse_path(path: str) -> bool:
    normalized = path.split("?", 1)[0].rstrip("/") or "/"
    if normalized in LEGACY_SSE_PATHS:
        return True
    # Keep exact legacy markers even when trailing slash was stripped oddly.
    return path.rstrip("/") in {p.rstrip("/") for p in LEGACY_SSE_PATHS} or path in LEGACY_SSE_PATHS


@dataclass(frozen=True, slots=True)
class TransportDecision:
    allowed: bool
    http_status: int
    code: str
    reached_mcp_parse: bool = False
    auth_gate_class: str | None = None


class PreParseAuthGateStub:
    """STUB auth gate — Task 6 replaces this class in place with CredentialValidator.

    This stub only checks that an Authorization material is present so that an absent
    Origin header cannot by itself bypass the authentication position in the pipeline.
    It does NOT validate issuer, audience, expiry, signature, or session binding.
    Tokens are never forwarded to PostgreSQL from this stub.
    """

    def evaluate(self, *, auth_present: bool) -> TransportDecision | None:
        if auth_present:
            return None
        return TransportDecision(
            allowed=False,
            http_status=401,
            code="auth_gate_rejected",
            reached_mcp_parse=False,
            auth_gate_class=self.__class__.__name__,
        )


def evaluate_http_preamble(
    *,
    bind_host: str,
    bind_port: int,
    allowed_origins: frozenset[str],
    headers: Mapping[str, str],
    content_length: int,
    max_body_bytes: int,
    auth_present: bool,
    allowed_protocol_versions: frozenset[str] | None = None,
) -> TransportDecision:
    """Evaluate Host/Origin/limits/protocol/auth gates before any MCP body parse."""
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    expected_host = f"{bind_host}:{bind_port}"
    host = normalized.get("host", "")
    if host != expected_host and host != bind_host:
        return TransportDecision(
            allowed=False,
            http_status=403,
            code="host_header_rejected",
            reached_mcp_parse=False,
        )

    origin = normalized.get("origin")
    if origin is not None and origin not in allowed_origins:
        return TransportDecision(
            allowed=False,
            http_status=403,
            code="origin_rejected",
            reached_mcp_parse=False,
        )

    if content_length > max_body_bytes:
        return TransportDecision(
            allowed=False,
            http_status=413,
            code="request_too_large",
            reached_mcp_parse=False,
        )

    if allowed_protocol_versions is not None:
        version = normalized.get("mcp-protocol-version")
        if version is not None and version not in allowed_protocol_versions:
            return TransportDecision(
                allowed=False,
                http_status=400,
                code="unsupported_protocol_version",
                reached_mcp_parse=False,
            )

    # Task 6 replacement point: PreParseAuthGateStub -> CredentialValidator
    auth_decision = PreParseAuthGateStub().evaluate(auth_present=auth_present)
    if auth_decision is not None:
        return auth_decision

    return TransportDecision(
        allowed=True,
        http_status=200,
        code="ok",
        reached_mcp_parse=True,
        auth_gate_class="PreParseAuthGateStub",
    )


__all__ = [
    "LEGACY_SSE_PATHS",
    "PreParseAuthGateStub",
    "TransportDecision",
    "evaluate_http_preamble",
    "is_legacy_sse_path",
]
