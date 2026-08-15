from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from optimus_security.sanitization import sanitize_for_persistence

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
AUTHENTICATION_REQUIRED = -32000
REQUEST_CANCELLED = -32800
RESOURCE_NOT_FOUND = -32002
MUTATION_FORBIDDEN = -32910
DUPLICATE_REQUEST_ID = -32911

JSON_RPC_STANDARD_ERROR_CODES = frozenset(
    {PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR}
)
ACP_PROTOCOL_ERROR_CODES = frozenset(
    {*JSON_RPC_STANDARD_ERROR_CODES, AUTHENTICATION_REQUIRED, REQUEST_CANCELLED, RESOURCE_NOT_FOUND}
)
OPTIMUS_APPLICATION_ERROR_CODES = frozenset({MUTATION_FORBIDDEN, DUPLICATE_REQUEST_ID})


@dataclass(frozen=True)
class JsonRpcError:
    code: int
    message: str
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class AcpOutboundError(Exception):
    """Raised when the ACP client rejects an agent-initiated outbound request."""

    code: int
    message: str
    data: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def success_response(request_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def sanitize_protocol_error_message(message: str) -> str:
    """Return a protocol-valid sanitized message without a raw fallback."""
    try:
        sanitized = sanitize_for_persistence(message).value
    except Exception:
        return "internal error"
    return sanitized if isinstance(sanitized, str) and sanitized else "internal error"


def sanitize_protocol_error_data(data: object) -> dict[str, Any] | None:
    """Return sanitized structured error context or drop it fail-closed."""
    try:
        sanitized = sanitize_for_persistence(data).value
    except Exception:
        return None
    return sanitized if isinstance(sanitized, dict) else None


def error_response(
    request_id: str | int | None,
    error: JsonRpcError,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": error.code,
            "message": sanitize_protocol_error_message(error.message),
        },
    }
    if error.data is not None:
        sanitized_data = sanitize_protocol_error_data(error.data)
        if sanitized_data is not None:
            payload["error"]["data"] = sanitized_data
    return payload
