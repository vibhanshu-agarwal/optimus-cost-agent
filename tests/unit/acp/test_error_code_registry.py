from __future__ import annotations

import json
from pathlib import Path

from optimus.acp.errors import (
    ACP_PROTOCOL_ERROR_CODES,
    AUTHENTICATION_REQUIRED,
    DUPLICATE_REQUEST_ID,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    JSON_RPC_STANDARD_ERROR_CODES,
    METHOD_NOT_FOUND,
    MUTATION_FORBIDDEN,
    OPTIMUS_APPLICATION_ERROR_CODES,
    PARSE_ERROR,
    REQUEST_CANCELLED,
    RESOURCE_NOT_FOUND,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ACP_SCHEMA_PATH = REPO_ROOT / "tests/fixtures/acp/acp-v1-schema.json"

RESERVED_MIN, RESERVED_MAX = -32768, -32000


def schema_error_codes() -> frozenset[int]:
    schema = json.loads(ACP_SCHEMA_PATH.read_text(encoding="utf-8"))
    return frozenset(
        item["const"]
        for item in schema["$defs"]["ErrorCode"]["anyOf"]
        if isinstance(item.get("const"), int)
    )


def test_registry_is_unique_and_protocol_aligned() -> None:
    acp_codes = schema_error_codes()
    registry_values = (
        PARSE_ERROR,
        INVALID_REQUEST,
        METHOD_NOT_FOUND,
        INVALID_PARAMS,
        INTERNAL_ERROR,
        AUTHENTICATION_REQUIRED,
        REQUEST_CANCELLED,
        RESOURCE_NOT_FOUND,
        MUTATION_FORBIDDEN,
        DUPLICATE_REQUEST_ID,
    )

    assert len(registry_values) == len(set(registry_values))
    assert JSON_RPC_STANDARD_ERROR_CODES <= ACP_PROTOCOL_ERROR_CODES
    assert ACP_PROTOCOL_ERROR_CODES == acp_codes
    assert frozenset(registry_values) == acp_codes | OPTIMUS_APPLICATION_ERROR_CODES
    assert RESOURCE_NOT_FOUND == -32002
    assert -32910 not in acp_codes
    assert -32911 not in acp_codes
    assert OPTIMUS_APPLICATION_ERROR_CODES.isdisjoint(acp_codes)
    assert all(not (RESERVED_MIN <= code <= RESERVED_MAX) for code in OPTIMUS_APPLICATION_ERROR_CODES)
    assert MUTATION_FORBIDDEN == -32910
    assert DUPLICATE_REQUEST_ID == -32911
    assert OPTIMUS_APPLICATION_ERROR_CODES == frozenset({MUTATION_FORBIDDEN, DUPLICATE_REQUEST_ID})
