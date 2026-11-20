"""The memory-store RPC both sides share (Plan 12.11 Task 1; ADR-042): `POST /v1/context/memory`.

The Gateway owns the Redis adapter and its secret; the host owns authority, scans, notices and the registry. Everything is a
closed operation with a validated shape: no command, key or filesystem path crosses this route. Projects are host-asserted,
as the index's scopes are (ADR-037): the Gateway authenticates the shared key, not the workspace, so a host holding that key
can name another project. The trusted host binds them and the model never selects one.

One stream per project is authoritative: `append` (admit, update, withdraw, off) and `checkpoint` add one event under the
project's fenced lease; `read`, `list`, `history` and `checkpoints` serve only what `WAITAOF` confirmed. `purge` destroys one item's text
behind a journalled tombstone and `purge_status` reports and drives its disk step (Task 2). `export` pages a signed recovery
generation, `restore` stages one into an empty project and publishes it, and `restore_status` reports where that stands (Task 4).
Limits are agent-selected, frozen in `reports/plan12-memory-m3/targets.json`.
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
MAX_OFF_RECORDS: Final = 200  # live off records per project (targets.json admission); the overflow archive is Task 4's
MAX_OFF_BYTES: Final = 524_288
MAX_CHECKPOINTS: Final = 20
MAX_HISTORY: Final = 20  # versions per `/memory view` page (Q4)
MAX_RESTORE_BATCH: Final = 10  # ten maximal events stay well inside the request bound
MAX_VERSION: Final = 2**31 - 1
LEASE_TTL_MS: Final = (1_000, 300_000)

_OPAQUE = re.compile(r"[A-Za-z0-9._:@/-]{1,128}")
_ITEM = re.compile(r"m-[0-9a-f]{16}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_BASELINE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})?")
_PLAN_HASH = re.compile(r"(?:[0-9a-f]{64})?")
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
    """One line: no control characters (C0, DEL, C1) except tab, and no bidi overrides or isolates. Other format characters,
    such as the joiners inside emoji, are text."""
    if type(value) is not str or len(value) > limit or any(_forbidden(c) for c in value):
        raise _refuse()
    return value


def _forbidden(c: str) -> bool:
    code = ord(c)
    return (code < 32 and c != "\t") or 0x7F <= code <= 0x9F or 0x202A <= code <= 0x202E or 0x2066 <= code <= 0x2069


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
    # an off record is written off and may later be withdrawn (D10: `/forget`, or retired by switch-on); never anything else
    if (action == "off") != (trust == "off" and action != "withdraw") or (trust == "off" and statement):
        raise _refuse()
    if action == "withdraw" and (title or statement):
        raise _refuse()
    if (action == "withdraw") != (status == "withdrawn") or status == "purged":
        raise _refuse()
    if (action == "admit") != (value["version"] == 1) and action != "off":  # the engine's fold refuses anything else for good
        raise _refuse()
    return value


_CHECKPOINT_FIELDS = {"session", "sequence", "branch", "worktree", "baseline", "settled_at_ms", "outcome", "objective", "provenance",
                      "plan_hash", "pending", "amendments", "completion", "verification", "remaining"}


def checkpoint(value: Any) -> dict[str, Any]:
    """The deterministic turn checkpoint (engine `ContinuationCheckpoint`): host references only, never source text."""
    if not isinstance(value, dict) or set(value) != _CHECKPOINT_FIELDS:
        raise _refuse()
    for name in ("session", "branch", "worktree", "outcome", "objective", "provenance"):
        _opaque(value[name])
    _integer(value["sequence"], 1, MAX_VERSION)
    _integer(value["settled_at_ms"], 0, 2**53)
    _match(value["baseline"], _BASELINE)
    _match(value["plan_hash"], _PLAN_HASH)
    for name in ("pending", "amendments", "completion", "verification", "remaining"):
        _references(value[name])
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


def _history(body: dict[str, Any]) -> None:
    """One page of an item's versions, newest first, for `/memory view` (Q4): `before` is the version the page starts below."""
    _fields(body, {"op", "project", "item", "limit"}, frozenset({"before"}))
    _opaque(body["project"])
    _match(body["item"], _ITEM)
    _integer(body["limit"], 1, MAX_HISTORY)
    if "before" in body:
        _integer(body["before"], 2, MAX_VERSION)


def _checkpoint(body: dict[str, Any]) -> None:
    _fields(body, {"op", "project", "token", "checkpoint"})
    _opaque(body["project"])
    _integer(body["token"], 1, 2**63 - 1)
    checkpoint(body["checkpoint"])


def _checkpoints(body: dict[str, Any]) -> None:
    """The newest checkpoints, optionally only those on one branch, or one branch and worktree (Codex CP3 review 1, finding 5)."""
    _fields(body, {"op", "project", "limit"}, frozenset({"branch", "worktree"}))
    _opaque(body["project"])
    _integer(body["limit"], 1, MAX_CHECKPOINTS)
    if "worktree" in body and "branch" not in body:
        raise _refuse()
    for name in ("branch", "worktree"):
        if name in body:
            _opaque(body[name])


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


def _export(body: dict[str, Any]) -> None:
    """A page of the project's recovery generation (D5); the host writes the one fixed location. `bind` is the digest of the host's
    generation metadata, which the seal binds."""
    _fields(body, {"op", "project", "limit", "bind"}, frozenset({"cursor"}))
    _opaque(body["project"])
    _integer(body["limit"], 1, MAX_LIST)
    _match(body["bind"], _DIGEST)
    if "cursor" in body:
        _match(body["cursor"], _CURSOR)


def _verify_bind(body: dict[str, Any]) -> None:
    """Whether a generation's metadata digest carries this Gateway's MAC: authenticates a manifest without restoring it."""
    _fields(body, {"op", "project", "bind", "mac"})
    _opaque(body["project"])
    _match(body["bind"], _DIGEST)
    _match(body["mac"], _DIGEST)


_ENTRY_FIELDS = {"event_id", "item", "version", "action", "trust", "status", "kind", "scope", "title", "statement", "anchors",
                 "lineage", "valid_from_ms", "valid_until_ms", "stream_id"}
_STREAM = re.compile(r"[0-9]{1,20}-[0-9]{1,20}")


def recovery_entry(value: Any) -> dict[str, Any]:
    """One item of a recovery generation: its latest event and the store's entry id. Only an active item keeps a payload; every
    other carries none (D8: active payloads only). Its HMAC is checked by the Gateway, not here."""
    if not isinstance(value, dict) or set(value) != _ENTRY_FIELDS:
        raise _refuse()
    _match(value["stream_id"], _STREAM)
    action = _choice(value["action"], (*APPEND_ACTIONS, "tombstone"))
    status = _choice(value["status"], STATUS)
    if (action == "tombstone") != (status == "purged"):
        raise _refuse()
    payload_free = status != "active" or value["trust"] == "off"
    if payload_free and (value["statement"] or (value["title"] and value["trust"] != "off") or value["anchors"]):
        raise _refuse()
    if value["trust"] == "off" and value["title"]:
        raise _refuse()  # an off record's scanned title is not exported either
    shaped = {name: value[name] for name in _ENTRY_FIELDS - {"stream_id"}}
    if action == "tombstone":
        shaped = {**shaped, "action": "withdraw", "status": "withdrawn"}  # the shape check below knows no tombstone
    event(shaped)
    return value


def _entries(value: Any) -> None:
    if type(value) is not list or not 1 <= len(value) <= MAX_RESTORE_BATCH:
        raise _refuse()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {"entry", "mac"}:
            raise _refuse()
        recovery_entry(entry["entry"])
        _match(entry["mac"], _DIGEST)


def _restore(body: dict[str, Any]) -> None:
    """One batch of a recovery generation into an empty project (D8): batches are numbered from 0 and the last says so. The last
    names the generation's head and deletion frontier, which its seal binds, and the items the host withdrew since (each can
    only remove a payload, never add one). `source`, on every batch, is the project a user-confirmed mapping restores from: the
    generation is authenticated as that project's, and published into `project` (Plan 12.11 Task 5, M21)."""
    final = body.get("final")
    if "source" in body:
        _opaque(body["source"])
    if final is True:
        _fields(body, {"op", "project", "token", "generation", "batch", "final", "entries", "head", "frontier", "withdrawn", "bind",
                       "journal", "purged"}, frozenset({"source"}))
        _match(body["head"], _STREAM)
        _match(body["bind"], _DIGEST)
        _integer(body["journal"], 0, MAX_VERSION)
        frontier = body["frontier"]
        if not isinstance(frontier, dict) or set(frontier) != {"deletions", "last"}:
            raise _refuse()
        _integer(frontier["deletions"], 0, MAX_VERSION)
        if frontier["last"] != "" and not _STREAM.fullmatch(str(frontier["last"])):
            raise _refuse()
        if type(body["withdrawn"]) is not list or len(body["withdrawn"]) > MAX_LIST * 100:
            raise _refuse()
        for name in ("withdrawn", "purged"):
            if type(body[name]) is not list or len(body[name]) > MAX_LIST * 100:
                raise _refuse()
            for item in body[name]:
                _match(item, _ITEM)
    elif final is False:
        _fields(body, {"op", "project", "token", "generation", "batch", "final", "entries"}, frozenset({"source"}))
    else:
        raise _refuse()
    _opaque(body["project"])
    _integer(body["token"], 1, 2**63 - 1)
    _match(body["generation"], _DIGEST)
    _integer(body["batch"], 0, MAX_VERSION)
    if not (final and body["entries"] == []):  # only the last batch may be empty (a generation of one full batch)
        _entries(body["entries"])


def _restore_status(body: dict[str, Any]) -> None:
    _fields(body, {"op", "project", "generation"})
    _opaque(body["project"])
    _match(body["generation"], _DIGEST)


_SHAPES: Final[dict[str, Callable[[dict[str, Any]], None]]] = {
    "capabilities": _capabilities, "lease": _lease, "append": _append, "read": _read, "list": _list, "history": _history,
    "checkpoint": _checkpoint,
    "checkpoints": _checkpoints, "purge": _purge, "purge_status": _purge_status, "export": _export, "restore": _restore,
    "restore_status": _restore_status, "verify_bind": _verify_bind,
}
OPERATIONS: Final = frozenset(_SHAPES)
UNAVAILABLE: Final[frozenset[str]] = frozenset()  # every operation is served since Task 4
