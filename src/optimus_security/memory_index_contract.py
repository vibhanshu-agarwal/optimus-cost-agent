"""The context-index RPC both sides share (Plan 12.10 Task 2; ADR-037): `POST /v1/context/index`.

The Gateway owns the Redis adapter and its secret; the host owns authorization and file policy. Everything is a closed
operation with a validated shape: no command, key or filesystem path crosses this route, and no field can carry a source
body. Scopes are host-asserted: the Gateway authenticates the shared key, not the workspace, so a host holding that key
can name another scope. The trusted host binds them and the model never selects one.

Limits are agent-selected and frozen by the pilot.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
from array import array
from typing import Any, Final

PATH: Final = "/v1/context/index"
MAX_REQUEST_BYTES: Final = 1_048_576
MAX_RESPONSE_BYTES: Final = 1_048_576
MAX_RECORDS: Final = 256
MAX_QUERY_RESULTS: Final = 100
MAX_PAGE: Final = 256
MAX_TEXT_TERMS: Final = 64
DEADLINE_SECONDS: Final = 5.0
SERVING_WORKERS: Final = 2
QUEUE_DEPTH: Final = 8
MAX_LEASE_MS: Final = 60_000
MAX_DIMENSIONS: Final = 4096
NEVER_REMOVED: Final = 1 << 53

OPERATIONS: Final = frozenset({"batch", "catalogue", "cleanup", "coverage", "cursor", "generation", "lease", "query"})
KINDS: Final = frozenset({"file", "symbol", "section"})
LANGUAGES: Final = frozenset({"python", "java", "markdown", "text", "unsupported"})
QUERY_MODES: Final = frozenset({"lexical", "dense", "symbol", "path"})
CURSOR_PHASES: Final = frozenset({"idle", "catalogue", "embedding", "reconcile"})

_HEX64 = re.compile(r"[0-9a-f]{64}")
_OWNER = re.compile(r"[0-9a-f]{16,64}")
_IDENT = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_TERM = re.compile(r"[a-z0-9_]{1,64}")
_MAX_FIELD = {"symbol": 256, "signature": 2048, "description": 2048, "prose": 8192, "terms": 16384, "path": 1024}
_RECORD_KEYS = frozenset({"id", "kind", "path", "path_id", "file_hash", "language", "symbol", "signature", "description", "prose",
                          "terms", "start_line", "end_line", "modified", "vector"})
_MAX_COUNT = 1 << 53


class IndexRequestError(ValueError):
    """A refusal with a stable code. Never carries request content."""

    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def error_body(code: str) -> dict[str, str]:
    return {"status": "rejected", "error": code}


def _refuse(code: str = "REQUEST_INVALID") -> IndexRequestError:
    return IndexRequestError(code)


def _object(value: Any, allowed: frozenset[str] | set[str], required: frozenset[str] | set[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise _refuse()
    return value


def _hex64(value: Any) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise _refuse()
    return value


def _integer(value: Any, *, minimum: int = 0, maximum: int = _MAX_COUNT) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise _refuse()
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) > _MAX_FIELD[field]:
        raise _refuse()
    return value


def relative_path(value: Any) -> str:
    """A forward-slash path inside the scope: never absolute, never climbing, never a drive."""
    path = _text(value, "path")
    parts = path.split("/")
    if not path or "\\" in path or ":" in path or any(part in {"", ".", ".."} for part in parts) or any(ord(c) < 32 for c in path):
        raise _refuse()
    return path


def decode_vector(value: Any, dimensions: int) -> bytes:
    """Little-endian float32 bytes, exactly `dimensions` long and all finite."""
    if not isinstance(value, str):
        raise _refuse()
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise _refuse() from None
    if len(raw) != dimensions * 4:
        raise IndexRequestError("VECTOR_DIMENSIONS_INVALID")
    floats = array("f")
    floats.frombytes(raw)
    if not all(map(math.isfinite, floats)):
        raise _refuse()
    return raw


def encode_vector(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def query_terms(value: Any) -> list[str]:
    """The lexical query as bare terms, so nothing typed can become query syntax."""
    if not isinstance(value, list) or not 0 < len(value) <= MAX_TEXT_TERMS:
        raise _refuse()
    if not all(isinstance(term, str) and _TERM.fullmatch(term) for term in value):
        raise _refuse()
    return value


def _record(value: Any) -> dict[str, Any]:
    record = _object(value, _RECORD_KEYS, {"id", "kind", "path", "path_id", "file_hash", "language", "terms"})
    if record["kind"] not in KINDS or record["language"] not in LANGUAGES:
        raise _refuse()
    _hex64(record["id"])
    _hex64(record["path_id"])
    _hex64(record["file_hash"])
    relative_path(record["path"])
    for field in ("symbol", "signature", "description", "prose", "terms"):
        if field in record:
            _text(record[field], field)
    for field in ("start_line", "end_line", "modified"):
        if field in record:
            _integer(record[field])
    return record


def _operand(body: dict[str, Any], allowed: set[str], required: set[str] | None = None) -> dict[str, Any]:
    return _object(body, {"op", "scope", *allowed}, {"op", "scope", *(required or set())})


def parse_request(raw: bytes) -> dict[str, Any]:
    """The validated request. Vectors stay encoded here: their length depends on the scope's registered dimensions."""
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _refuse() from None
    if not isinstance(body, dict) or body.get("op") not in OPERATIONS:
        raise _refuse()
    _hex64(body.get("scope"))
    {"batch": _batch, "catalogue": _catalogue, "cleanup": _cleanup, "coverage": _coverage, "cursor": _cursor,
     "generation": _generation, "lease": _lease, "query": _query}[body["op"]](body)
    return body


def _batch(body: dict[str, Any]) -> None:
    _operand(body, {"token", "epoch", "records", "removals"}, {"token", "epoch", "records"})
    _integer(body["token"], minimum=1)
    _integer(body["epoch"], minimum=1)
    records, removals = body["records"], body.get("removals", [])
    if not isinstance(records, list) or not isinstance(removals, list):
        raise _refuse()
    if len(records) > MAX_RECORDS or len(removals) > MAX_RECORDS:
        raise IndexRequestError("BATCH_TOO_LARGE")
    for record in records:
        _record(record)
    for path_id in removals:
        _hex64(path_id)


def _catalogue(body: dict[str, Any]) -> None:
    _operand(body, {"epoch", "cursor", "limit"})
    if "epoch" in body:
        _integer(body["epoch"], minimum=1)
    if "cursor" in body and not isinstance(body["cursor"], str):
        raise _refuse()
    if "limit" in body:
        _integer(body["limit"], minimum=1, maximum=MAX_PAGE)


def _cleanup(body: dict[str, Any]) -> None:
    _operand(body, {"token", "action", "cursor"}, {"token", "action"})
    _integer(body["token"], minimum=1)
    if body["action"] not in {"prune", "drop"} or ("cursor" in body and not isinstance(body["cursor"], str)):
        raise _refuse()


def _coverage(body: dict[str, Any]) -> None:
    _operand(body, set())


def _cursor(body: dict[str, Any]) -> None:
    _operand(body, {"action", "token", "value"}, {"action"})
    if body["action"] == "get":
        if set(body) - {"op", "scope", "action"}:
            raise _refuse()
        return
    if body["action"] != "set":
        raise _refuse()
    _integer(body.get("token"), minimum=1)
    value = _object(body.get("value"), {"phase", "next_path_id", "counts"}, {"phase"})
    if value["phase"] not in CURSOR_PHASES:
        raise _refuse()
    if "next_path_id" in value:
        _hex64(value["next_path_id"])
    counts = value.get("counts", {})
    if not isinstance(counts, dict) or len(counts) > 32:
        raise _refuse()
    for key, count in counts.items():
        if not isinstance(key, str) or not _IDENT.fullmatch(key):
            raise _refuse()
        _integer(count)


def _coverage_report(value: Any) -> None:
    report = _object(value, {"complete", "files_indexed", "files_total", "records", "unsupported", "excluded", "parsed_loc"},
                     {"complete", "files_indexed", "files_total"})
    if not isinstance(report["complete"], bool):
        raise _refuse()
    for field in ("files_indexed", "files_total", "records", "unsupported", "excluded"):
        if field in report:
            _integer(report[field])
    locs = report.get("parsed_loc", {})
    if not isinstance(locs, dict) or set(locs) - LANGUAGES:
        raise _refuse()
    for count in locs.values():
        _integer(count)


def _generation(body: dict[str, Any]) -> None:
    action = body.get("action")
    if action == "open":
        _operand(body, {"action", "embedding", "dimensions", "schema_version"}, {"action", "embedding", "dimensions", "schema_version"})
        if not isinstance(body["embedding"], str) or not _IDENT.fullmatch(body["embedding"]):
            raise _refuse()
        _integer(body["dimensions"], minimum=1, maximum=MAX_DIMENSIONS)
        _integer(body["schema_version"], minimum=1, maximum=1 << 16)
    elif action == "begin":
        _operand(body, {"action", "token"}, {"action", "token"})
        _integer(body["token"], minimum=1)
    elif action == "publish":
        _operand(body, {"action", "token", "epoch", "revision", "dirty", "coverage"}, {"action", "token", "epoch", "revision", "dirty", "coverage"})
        _integer(body["token"], minimum=1)
        _integer(body["epoch"], minimum=1)
        _hex64(body["revision"])
        if not isinstance(body["dirty"], bool):
            raise _refuse()
        _coverage_report(body["coverage"])
    else:
        raise _refuse()


def _lease(body: dict[str, Any]) -> None:
    action = body.get("action")
    if action == "acquire":
        _operand(body, {"action", "owner", "ttl_ms", "kind"}, {"action", "owner", "ttl_ms", "kind"})
    elif action == "renew":
        _operand(body, {"action", "owner", "ttl_ms", "kind", "token"}, {"action", "owner", "ttl_ms", "kind", "token"})
        _integer(body["token"], minimum=1)
    elif action == "release":
        _operand(body, {"action", "owner", "kind", "token"}, {"action", "owner", "kind", "token"})
        _integer(body["token"], minimum=1)
    else:
        raise _refuse()
    if not isinstance(body["owner"], str) or not _OWNER.fullmatch(body["owner"]) or body["kind"] not in {"scope", "cold"}:
        raise _refuse()
    if "ttl_ms" in body:
        _integer(body["ttl_ms"], minimum=1000, maximum=MAX_LEASE_MS)


def _query(body: dict[str, Any]) -> None:
    _operand(body, {"mode", "epoch", "terms", "vector", "symbol", "path_id", "k", "kinds"}, {"mode", "k"})
    if body["mode"] not in QUERY_MODES:
        raise _refuse()
    if "epoch" in body:
        _integer(body["epoch"], minimum=1)
    _integer(body["k"], minimum=1, maximum=MAX_QUERY_RESULTS)
    kinds = body.get("kinds", [])
    if not isinstance(kinds, list) or not set(kinds) <= KINDS:
        raise _refuse()
    required = {"lexical": "terms", "dense": "vector", "symbol": "symbol", "path": "path_id"}[body["mode"]]
    if required not in body:
        raise _refuse()
    if body["mode"] == "lexical":
        query_terms(body["terms"])
    elif body["mode"] == "symbol":
        _text(body["symbol"], "symbol")
    elif body["mode"] == "path":
        _hex64(body["path_id"])
