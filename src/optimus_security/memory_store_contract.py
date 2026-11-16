"""The memory-store RPC both sides share (Plan 12.11 Task 1; ADR-042): `POST /v1/context/memory`.

The Gateway owns the Redis adapter and its secret; the host owns authority, scans, notices and the registry. Everything is a
closed operation with a validated shape: no command, key or filesystem path crosses this route. Projects are host-asserted,
as the index's scopes are (ADR-037): the Gateway authenticates the shared key, not the workspace, so a host holding that key
can name another project. The trusted host binds them and the model never selects one.

One stream per project is authoritative: `append` (admit, update, withdraw, off) and `checkpoint` add one event under the
project's fenced lease; `read`, `list` and `checkpoints` serve only what `WAITAOF` confirmed. `purge` and `purge_status` have
their shapes here and answer `MEMORY_OPERATION_UNAVAILABLE` until Task 2's journal backs them; the recovery operations join
with Task 4's export format. Limits are agent-selected, frozen in `reports/plan12-memory-m3/targets.json`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Final

PATH: Final = "/v1/context/memory"
MAX_REQUEST_BYTES: Final = 262_144
MAX_RESPONSE_BYTES: Final = 1_048_576
DEADLINE_SECONDS: Final = 5.0
SERVING_WORKERS: Final = 2
QUEUE_DEPTH: Final = 8
SCHEMA_VERSION: Final = 1

# The engine's vocabularies (context_engine.memory_contracts); a unit test keeps the two equal.
TRUST: Final = ("user-authored", "agent-derived", "legacy-import", "off")
STATUS: Final = ("active", "reverify", "conflicted", "superseded", "withdrawn", "purged")
KINDS: Final = ("fact", "preference", "decision", "constraint", "episode", "procedure", "lesson")
APPEND_ACTIONS: Final = ("admit", "update", "withdraw", "off")  # a tombstone is written only by purge
MAX_STATEMENT_CHARS: Final = 2000
MAX_TITLE_CHARS: Final = 120
MAX_REFERENCES: Final = 32
MAX_LIST: Final = 100
MAX_CHECKPOINTS: Final = 20
MAX_VERSION: Final = 2**31 - 1
LEASE_TTL_MS: Final = (1_000, 300_000)

_OPAQUE = re.compile(r"[A-Za-z0-9._:@/-]{1,128}")
_ITEM = re.compile(r"m-[0-9a-f]{16}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_BASELINE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})?")
_CURSOR = re.compile(r"[A-Za-z0-9_=-]{1,512}\.[0-9a-f]{64}")


class MemoryRequestError(ValueError):
    """A refusal with a stable code. Never carries request content."""

    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def error_body(code: str) -> dict[str, str]:
    return {"status": "rejected", "error": code}


def _refuse(code: str = "REQUEST_INVALID") -> MemoryRequestError:
    return MemoryRequestError(code)


def _fields(body: dict[str, Any], required: set[str], optional: frozenset[str] = frozenset()) -> None:
    if not required <= set(body) <= required | optional:
        raise _refuse()


def _opaque(value: Any) -> str:
    if type(value) is not str or not _OPAQUE.fullmatch(value):
        raise _refuse()
    return value


def _match(value: Any, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        raise _refuse()
    return value


def _integer(value: Any, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _refuse()
    return value


def _line(value: Any, limit: int) -> str:
    if type(value) is not str or len(value) > limit or any(ord(c) < 32 and c != "\t" for c in value):
        raise _refuse()
    return value


def _choice(value: Any, allowed: tuple[str, ...]) -> str:
    if type(value) is not str or value not in allowed:
        raise _refuse()
    return value


def _references(value: Any) -> None:
    if type(value) is not list or len(value) > MAX_REFERENCES:
        raise _refuse()
    for entry in value:
        _opaque(entry)


_EVENT_FIELDS = {"event_id", "item", "version", "action", "trust", "status", "kind", "scope", "title", "statement", "anchors",
                 "lineage", "valid_from_ms", "valid_until_ms"}


def event(value: Any) -> dict[str, Any]:
    """One event as the host proposes it. The payload rules are the engine's: an off record and a withdrawal carry no payload."""
    if not isinstance(value, dict) or set(value) != _EVENT_FIELDS:
        raise _refuse()
    _opaque(value["event_id"])
    _match(value["item"], _ITEM)
    _integer(value["version"], 1, MAX_VERSION)
    action = _choice(value["action"], APPEND_ACTIONS)
    trust = _choice(value["trust"], TRUST)
    status = _choice(value["status"], STATUS)
    _choice(value["kind"], KINDS)
    _opaque(value["scope"])
    title, statement = _line(value["title"], MAX_TITLE_CHARS), _line(value["statement"], MAX_STATEMENT_CHARS)
    _references(value["anchors"])
    _references(value["lineage"])
    start = _integer(value["valid_from_ms"], 0, 2**53)
    end = _integer(value["valid_until_ms"], 0, 2**53)  # 0: still valid
    if end and end <= start:
        raise _refuse()
    if (trust == "off") != (action == "off") or (trust == "off" and statement):
        raise _refuse()
    if action == "withdraw" and (title or statement):
        raise _refuse()
    if (action == "withdraw") != (status == "withdrawn") or status == "purged":
        raise _refuse()
    if action == "admit" and value["version"] != 1 or action == "update" and value["version"] == 1:
        raise _refuse()
    return value


_CHECKPOINT_FIELDS = {"session", "sequence", "branch", "worktree", "baseline", "settled_at_ms", "outcome", "objective", "pending"}


def checkpoint(value: Any) -> dict[str, Any]:
    """The deterministic turn checkpoint (engine `ContinuationCheckpoint`): host references only, never source text."""
    if not isinstance(value, dict) or set(value) != _CHECKPOINT_FIELDS:
        raise _refuse()
    for name in ("session", "branch", "worktree", "outcome", "objective"):
        _opaque(value[name])
    _integer(value["sequence"], 1, MAX_VERSION)
    _integer(value["settled_at_ms"], 0, 2**53)
    _match(value["baseline"], _BASELINE)
    _references(value["pending"])
    return value


def parse_request(raw: bytes) -> dict[str, Any]:
    """The validated request: a JSON object naming one known operation, with exactly that operation's fields."""
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise _refuse() from None
    if not isinstance(body, dict) or body.get("op") not in _SHAPES:
        raise _refuse()
    _SHAPES[body["op"]](body)
    return body


def _capabilities(body: dict[str, Any]) -> None:
    _fields(body, {"op"})


def _lease(body: dict[str, Any]) -> None:
    action = body.get("action")
    if action == "acquire":
        _fields(body, {"op", "project", "owner", "action", "ttl_ms"})
    elif action == "renew":
        _fields(body, {"op", "project", "owner", "action", "ttl_ms", "token"})
    elif action == "release":
        _fields(body, {"op", "project", "owner", "action", "token"})
    else:
        raise _refuse()
    _opaque(body["project"])
    _opaque(body["owner"])
    if "ttl_ms" in body:
        _integer(body["ttl_ms"], *LEASE_TTL_MS)
    if "token" in body:
        _integer(body["token"], 1, 2**63 - 1)


def _append(body: dict[str, Any]) -> None:
    _fields(body, {"op", "project", "token", "expected_version", "idempotency_key", "event"})
    _opaque(body["project"])
    _integer(body["token"], 1, 2**63 - 1)
    expected = _integer(body["expected_version"], 0, MAX_VERSION - 1)
    _match(body["idempotency_key"], _DIGEST)
    if event(body["event"])["version"] != expected + 1:
        raise _refuse()


def _read(body: dict[str, Any]) -> None:
    _fields(body, {"op", "project", "item"})
    _opaque(body["project"])
    _match(body["item"], _ITEM)


def _list(body: dict[str, Any]) -> None:
    _fields(body, {"op", "project", "scope", "limit"}, frozenset({"cursor"}))
    _opaque(body["project"])
    _opaque(body["scope"])
    _integer(body["limit"], 1, MAX_LIST)
    if "cursor" in body:
        _match(body["cursor"], _CURSOR)


def _checkpoint(body: dict[str, Any]) -> None:
    _fields(body, {"op", "project", "token", "checkpoint"})
    _opaque(body["project"])
    _integer(body["token"], 1, 2**63 - 1)
    checkpoint(body["checkpoint"])


def _checkpoints(body: dict[str, Any]) -> None:
    _fields(body, {"op", "project", "limit"})
    _opaque(body["project"])
    _integer(body["limit"], 1, MAX_CHECKPOINTS)


def _purge(body: dict[str, Any]) -> None:
    _fields(body, {"op", "project", "token", "item", "idempotency_key"})
    _opaque(body["project"])
    _integer(body["token"], 1, 2**63 - 1)
    _match(body["item"], _ITEM)
    _match(body["idempotency_key"], _DIGEST)


def _purge_status(body: dict[str, Any]) -> None:
    _fields(body, {"op", "project", "item"})
    _opaque(body["project"])
    _match(body["item"], _ITEM)


_SHAPES: Final[dict[str, Callable[[dict[str, Any]], None]]] = {
    "capabilities": _capabilities, "lease": _lease, "append": _append, "read": _read, "list": _list, "checkpoint": _checkpoint,
    "checkpoints": _checkpoints, "purge": _purge, "purge_status": _purge_status,
}
OPERATIONS: Final = frozenset(_SHAPES)
UNAVAILABLE: Final = frozenset({"purge", "purge_status"})  # shapes fixed now; Task 2's journal serves them
