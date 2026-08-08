"""HTTP preamble gates for the evidence-handoff Streamable HTTP service.

CredentialValidator (via validate_authorization) sits at the auth pipeline
position formerly occupied by PreParseAuthGateStub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from evidence_handoff_runtime.auth import AuthError, CredentialValidator, validate_authorization

LEGACY_SSE_PATHS = frozenset({"/sse", "/messages", "/mcp/sse"})


def is_legacy_sse_path(path: str) -> bool:
    normalized = path.split("?", 1)[0].rstrip("/") or "/"
    if normalized in LEGACY_SSE_PATHS:
        return True
    return path.rstrip("/") in {p.rstrip("/") for p in LEGACY_SSE_PATHS} or path in LEGACY_SSE_PATHS


@dataclass(frozen=True, slots=True)
class TransportDecision:
    allowed: bool
    http_status: int
    code: str
    reached_mcp_parse: bool = False
    auth_gate_class: str | None = None


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
    credential_validator: CredentialValidator | None = None,
    ledger_instance_id: str | None = None,
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

    # In-place Task 6 replacement of PreParseAuthGateStub.
    authorization_header = normalized.get("authorization") if auth_present else None
    try:
        validate_authorization(
            authorization_header=authorization_header,
            validator=credential_validator,
            request={"ledger_instance_id": ledger_instance_id} if ledger_instance_id else {},
        )
    except AuthError as exc:
        return TransportDecision(
            allowed=False,
            http_status=401,
            code=exc.code,
            reached_mcp_parse=False,
            auth_gate_class="CredentialValidator",
        )

    return TransportDecision(
        allowed=True,
        http_status=200,
        code="ok",
        reached_mcp_parse=True,
        auth_gate_class="CredentialValidator",
    )


__all__ = [
    "LEGACY_SSE_PATHS",
    "TransportDecision",
    "evaluate_http_preamble",
    "is_legacy_sse_path",
]
