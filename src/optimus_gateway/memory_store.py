"""The Gateway's memory store and handler (Plan 12.11; ADR-042), on its own dedicated Redis.

Unlike the context index (ADR-037), accepted memory cannot be rebuilt from the workspace, so the instance must persist every
acknowledged write: AOF on, `noeviction`, and `WAITAOF` answering on the serving connection. A store that cannot show all
three admits nothing. Its identity is the resource setup provisioned; an unmarked instance is adopted only while it holds no
keys, so a populated unidentified store is never initialized.

Admission is bounded, so memory traffic waits or is refused and never holds a model or capture request.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import redis
from redis.backoff import NoBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import OutOfMemoryError, RedisError, ResponseError, TimeoutError, WatchError
from redis.retry import Retry

from optimus_gateway.memory_files import Inventory, InventoryUnavailable, Residue, docker_inventory, residue
from optimus_gateway.memory_journal import JournalError, PurgeJournal, journal_key
from optimus_security import memory_store_contract as msc
from optimus_security.memory_store_config import KEYRING_SERVICE, MemoryStoreConfig

_PREFIX: Final = "omem"
_RESOURCE_KEY: Final = f"{_PREFIX}:resource"
_WAITAOF_PROBE_MS: Final = 2500  # bounds a slow disk; under appendfsync always the wait is the write's own fsync
_WAITAOF_COMMIT_MS: Final = 2500
_WATCH_ATTEMPTS: Final = 3
_FOLD_PAGE: Final = 500
_LIST_ENVELOPE_BYTES: Final = 1024  # status, cursor and framing around the items
_SOCKET_MARGIN_MS: Final = 100  # WAITAOF answers before the socket's own budget runs out
_MIN_SOCKET_SECONDS: Final = 0.05
_CONNECT_SECONDS: Final = 2.0
_FENCE_KEY: Final = f"{_PREFIX}:fence"
_PROBE_KEY: Final = f"{_PREFIX}:fsync-probe"
_MIB: Final = 1024 * 1024
_PAYLOAD_FIELDS: Final = ("title", "statement", "anchors", "lineage")
_PURGED_PAYLOAD: Final = {"title": "", "statement": "", "anchors": [], "lineage": []}
_TOMBSTONE_KEEPS: Final = ("item", "trust", "kind", "scope", "valid_from_ms", "valid_until_ms")
PURGE_COMPLETED: Final = "completed-within-declared-boundary"
# (kind, completion counter, flags that mean one is running or queued, last status, the command that starts one)
_PERSISTENCE: Final = (
    ("aof", "aof_rewrites", ("aof_rewrite_in_progress", "aof_rewrite_scheduled"), "aof_last_bgrewrite_status", ("BGREWRITEAOF",)),
    ("rdb", "rdb_saves", ("rdb_bgsave_in_progress",), "rdb_last_bgsave_status", ("BGSAVE", "SCHEDULE")),
)



_RUNBOOK = "docs/runbooks/memory-purge-pending-files.md"


def _held(why: Residue | None) -> dict[str, Any]:
    """What a purge held pending by the data directory tells the operator (Codex CP2 review 4): the reason, the entries that
    hold it (at most 16, non-printable characters shown as "?") and the runbook that says how to check and retire them."""
    if why is None:
        return {}
    shown = ["".join(c if c.isprintable() else "?" for c in entry)[:200] for entry in why.entries[:16]]
    return {"files": why.reason, "blocking": shown, "next": "inspect_data_files", "runbook": _RUNBOOK}

class MemoryStoreStartupError(RuntimeError):
    """The configured Redis is not the approved durable resource. `code` is stable and carries no secret."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MemoryStoreEndpoint:
    host: str
    port: int
    username: str
    password: str
    resource: str  # the nonsecret identity this instance was provisioned as

    def __repr__(self) -> str:
        return f"MemoryStoreEndpoint(host={self.host!r}, port={self.port}, username={self.username!r}, password='<redacted>')"


class Link:
    """One connection's bookkeeping. The connection registers itself when it is created, before any attempt to connect, so a
    budget always reaches it; every attempt to establish it, failed or not, is a new generation. redis-py's pool reconnects
    silently when it finds a closed socket at checkout; the generation is how the store sees that."""

    def __init__(self) -> None:
        self.connection: Any = None
        self.connects = 0
        self.deadline: float | None = None  # the holding request's absolute deadline, on time.monotonic()
        self.expected: int | None = None  # the verified generation while the store holds this connection; None while verifying

    def established(self, connection: Any) -> None:
        self.connects += 1  # counted before the handshake: a half-finished attempt is still another connection
        connection.on_connect()  # the handshake redis-py runs when no hook is given; refused while held, as a new generation

    def cut(self) -> None:
        """The deadline's hard stop: shut the live socket, so whatever read is blocked (a handshake, a reply arriving in
        fragments, an ordinary command) returns at once. The next use reconnects, which is a new generation."""
        self.deadline = time.monotonic()  # revoke the budget before releasing the blocked caller
        sock = getattr(self.connection, "_sock", None)  # shortcut: redis-py 8 keeps the live socket here; re-check on upgrade
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()  # on Windows only closing ends a recv blocked in another thread; shutdown alone waits out its timeout


class DeadlinePassed(RedisConnectionError):
    """Raised instead of connecting or sending once the holding request's deadline has passed. A connection error, so redis-py's
    own cleanup (a pipeline's UNWATCH after a cut, say) treats it as a dead connection rather than reconnecting."""


class Reconnected(RedisConnectionError):
    """Raised instead of sending a command on a connection established since the store last verified the resource, or one that
    would have to be established first. Nothing reaches an unverified Redis; the store verifies again before the next request."""


class _TrackedConnection(redis.Connection):
    """A redis-py connection that hands itself to its `Link` as soon as it exists, and refuses to connect or send after the
    holding request's deadline, so nothing, redis-py's own cleanup included, reconnects or talks past it."""

    def __init__(self, *args: Any, optimus_link: Link, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._optimus_link = optimus_link
        optimus_link.connection = self

    def _within_deadline(self) -> None:
        deadline = self._optimus_link.deadline
        if deadline is not None and time.monotonic() >= deadline:
            raise DeadlinePassed("the memory request's deadline has passed")

    def connect_check_health(self, *args: Any, **kwargs: Any) -> None:
        """Where redis-py really connects (a pool checkout, or a send on a closed connection): only inside the deadline, and with
        what is left of it as the TCP and handshake timeouts."""
        self._within_deadline()
        deadline = self._optimus_link.deadline
        if deadline is not None:
            remaining = max(0.001, deadline - time.monotonic())
            self.socket_connect_timeout = min(_CONNECT_SECONDS, remaining)
            self.socket_timeout = remaining
        super().connect_check_health(*args, **kwargs)

    def _connect(self) -> socket.socket:
        self._within_deadline()
        return super()._connect()

    def send_packed_command(self, *args: Any, **kwargs: Any) -> None:
        self._within_deadline()
        link = self._optimus_link
        if link.expected is not None and (self._sock is None or link.connects != link.expected):
            raise Reconnected("this connection is not the one the store verified")
        super().send_packed_command(*args, **kwargs)


def connect(endpoint: MemoryStoreEndpoint) -> redis.Redis:
    """One connection with retries off, so a dropped socket is an error, never a retried command that `WAITAOF` would then answer
    for; a reconnect at checkout is counted by its `Link` (on the client as `optimus_link`). The store keeps two, one for writes
    and one for reads, each used under its own lock."""
    link = Link()
    host = "127.0.0.1" if endpoint.host == "localhost" else endpoint.host  # one literal address: no resolver, no address fallback
    pool = redis.BlockingConnectionPool(max_connections=1, timeout=0, retry=Retry(NoBackoff(), 0),
                                        connection_class=_TrackedConnection, optimus_link=link,
                                        host=host, port=endpoint.port, username=endpoint.username, password=endpoint.password,
                                        socket_timeout=msc.DEADLINE_SECONDS, socket_connect_timeout=_CONNECT_SECONDS, protocol=2,
                                        redis_connect_func=link.established)
    client = redis.Redis(connection_pool=pool)
    client.optimus_link = link  # type: ignore[attr-defined]
    return client


def set_budget(client: Any, seconds: float) -> None:
    """Bound every wait on this client's one connection to `seconds`: connecting and authenticating, each socket read, and the
    timeout redis-py's parser restores after its checkout probe. It touches the recorded connection object, never the pool, so it
    is safe while a watching pipeline holds the connection."""
    link = getattr(client, "optimus_link", None)
    if not isinstance(link, Link):  # an in-memory stand-in
        return
    seconds = max(_MIN_SOCKET_SECONDS, seconds)
    client.connection_pool.connection_kwargs.update(socket_timeout=seconds, socket_connect_timeout=min(_CONNECT_SECONDS, seconds))
    connection = link.connection
    if connection is None:  # not connected yet: the pool's settings above apply to the first connection
        return
    connection.socket_timeout = seconds
    connection.socket_connect_timeout = min(_CONNECT_SECONDS, seconds)
    # shortcut: redis-py 8 keeps the live socket and the parser's cached timeout in private fields; re-check them on upgrade
    sock = getattr(connection, "_sock", None)
    if sock is not None:
        try:
            sock.settimeout(seconds)
        except OSError:
            pass  # cut at a deadline: the next use reconnects, a new generation that must be verified
    buffer = getattr(getattr(connection, "_parser", None), "_buffer", None)
    if buffer is not None:
        buffer.socket_timeout = seconds


@contextlib.contextmanager
def _pipeline(client: Any) -> Iterator[Any]:
    """A transaction pipeline whose cleanup finishes here, inside the holding request's guards. redis-py's own reset sends
    UNWATCH and catches only connection errors: a timeout while it waits for the reply would leave the WATCH state and the
    checked-out connection for a later finalizer, which would run after the guards are gone. Any cleanup failure disconnects,
    returns the connection to the pool and clears the pipeline, so finalization has nothing left to send."""
    pipe = client.pipeline()
    try:
        yield pipe
    finally:
        try:
            pipe.reset()
        except Exception:  # noqa: BLE001 - whatever stopped the UNWATCH, the connection is no longer trustworthy
            connection = getattr(pipe, "connection", None)
            if connection is not None:
                try:
                    connection.disconnect()
                finally:
                    pipe.connection_pool.release(connection)
            pipe.connection = None
            pipe.watching = False
            pipe.command_stack = []


def _connects(client: Any) -> int:
    link = getattr(client, "optimus_link", None)
    return int(link.connects) if isinstance(link, Link) else 0


def _text(value: Any) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def waitaof_local(client: redis.Redis, *, timeout_ms: int) -> int:
    """How many local fsyncs `WAITAOF 1 0` confirms on one connection: 1 once preceding writes are on disk, 0 otherwise."""
    try:
        reply = client.execute_command("WAITAOF", 1, 0, timeout_ms)
    except ResponseError as exc:
        raise MemoryStoreStartupError("MEMORY_STORE_FSYNC_UNCONFIRMED") from exc
    return _local_count(reply)


def _local_count(reply: Any) -> int:
    if not isinstance(reply, list) or len(reply) != 2 or not all(isinstance(count, int) for count in reply):
        raise MemoryStoreStartupError("MEMORY_STORE_WAITAOF_UNEXPECTED")
    return int(reply[0])


def verify_resource(client: redis.Redis, resource: str, *, probe_ms: int = _WAITAOF_PROBE_MS,
                    step: Callable[[], None] = lambda: None) -> None:
    """Before serving: authentication works, persistence and eviction are as provisioned, `WAITAOF` confirms a local fsync, and
    this is the instance setup provisioned rather than whatever now holds the port. `step` runs before each command, so a caller
    can stop on its deadline and shrink the socket's budget between commands."""
    try:
        step()
        persistence = client.info("persistence")
        step()
        memory = client.info("memory")
        step()
        stored = client.get(_RESOURCE_KEY)
    except (RedisError, OSError) as exc:
        raise MemoryStoreStartupError("MEMORY_STORE_UNREACHABLE") from exc
    if not persistence.get("aof_enabled") or memory.get("maxmemory_policy") != "noeviction":
        raise MemoryStoreStartupError("MEMORY_STORE_CONFIGURATION_UNEXPECTED")
    try:
        if stored is None:
            step()
            if client.dbsize() != 0:  # never adopt data nobody can vouch for
                raise MemoryStoreStartupError("MEMORY_STORE_UNIDENTIFIED_DATA")
            step()
            client.set(_RESOURCE_KEY, resource, nx=True)
            step()
            stored = client.get(_RESOURCE_KEY)  # a concurrent Gateway may have marked it first; either way it must be ours
        if stored is None or _text(stored) != resource:
            raise MemoryStoreStartupError("MEMORY_STORE_RESOURCE_MISMATCH")
        step()
        if fsync_probe(client, timeout_ms=probe_ms) < 1:
            raise MemoryStoreStartupError("MEMORY_STORE_FSYNC_UNCONFIRMED")
    except MemoryStoreStartupError:
        raise
    except (RedisError, OSError) as exc:
        raise MemoryStoreStartupError("MEMORY_STORE_UNREACHABLE") from exc


def fsync_probe(client: redis.Redis, *, timeout_ms: int) -> int:
    """Write the probe key and wait for its fsync on one connection: a WAITAOF after no write answers at once and proves nothing."""
    pipe = client.pipeline(transaction=False)
    pipe.incr(_PROBE_KEY)
    pipe.execute_command("WAITAOF", 1, 0, timeout_ms)
    try:
        replies = pipe.execute()
    except ResponseError as exc:
        raise MemoryStoreStartupError("MEMORY_STORE_FSYNC_UNCONFIRMED") from exc
    return _local_count(replies[1])


def _split(event: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """An event's stream entry and its payload. The stream keeps only ids, state and validity: Redis XDEL leaves a stream entry's
    bytes in the snapshot, so anything a purge must destroy lives in the project's payload hash, where HDEL really removes it."""
    return ({name: value for name, value in event.items() if name not in _PAYLOAD_FIELDS},
            {name: event[name] for name in _PAYLOAD_FIELDS})


class _Fold:
    """What one project's stream says up to `head`: each item's latest event, the idempotency keys and event ids already used,
    every event id of each item (a purge removes all their payloads) and the checkpoints in stream order. Rebuilt from the
    stream and the payload hash, so it is a cache, never a source of truth. A purged item keeps only its tombstone."""

    def __init__(self) -> None:
        self.head = "0-0"
        self.items: dict[str, dict[str, Any]] = {}
        self.keys: dict[str, tuple[str | None, dict[str, Any]]] = {}
        self.event_ids: set[str] = set()
        self.history: dict[str, list[str]] = {}
        self.versions: dict[str, list[dict[str, Any]]] = {}  # each item's stream entries, oldest first, payload-free (Q4)
        self.checkpoints: list[dict[str, Any]] = []
        self.off: dict[str, int] = {}  # live off records and the bytes each holds: the cap counts these

    def apply(self, stream_id: str, record: dict[str, Any], payload: dict[str, Any] | None = None) -> None:
        digest = record.get("digest")
        if record["type"] == "event":
            event = record["event"]
            item = event["item"]
            if event["action"] == "tombstone":
                self.items[item] = {**event, **_PURGED_PAYLOAD, "stream_id": stream_id}
                for key, (_digest_value, result) in list(self.keys.items()):
                    if result.get("item") == item:
                        self.keys[key] = (None, result)  # nothing derived from the purged text stays, not even its digest
            else:
                digest = payload.pop("digest", None) if payload is not None else None
                self.items[item] = {**event, **(payload or {}), "stream_id": stream_id}  # no payload: refused when served
                self.history.setdefault(item, []).append(event["event_id"])
            self.event_ids.add(event["event_id"])
            self.versions.setdefault(item, []).append({**event, "stream_id": stream_id})
            if event["trust"] == "off" and event["status"] == "active":
                self.off[item] = len(_json(self.items[item]))
            else:
                self.off.pop(item, None)
        else:
            self.checkpoints.append({**record["checkpoint"], "stream_id": stream_id})
        self.keys[record["key"]] = (digest, _result(stream_id, record))
        self.head = stream_id

    def advance(self, reader: Any, stream: str, payloads: str, target: str, on_time: Callable[[], None] = lambda: None) -> None:
        while _order(self.head) < _order(target):
            on_time()
            entries = reader.xrange(stream, min=f"({self.head}", max=target, count=_FOLD_PAGE)
            if not entries:
                raise RedisError("stream shorter than its head")  # never serve a fold that skipped events
            records = [(_text(raw_id), json.loads(fields[b"e"])) for raw_id, fields in entries]
            wanted = [record["event"]["event_id"] for _, record in records
                      if record["type"] == "event" and record["event"]["action"] != "tombstone"]
            on_time()
            found = dict(zip(wanted, reader.hmget(payloads, wanted), strict=True)) if wanted else {}
            for stream_id, record in records:
                raw = found.get(record["event"]["event_id"]) if record["type"] == "event" else None
                self.apply(stream_id, record, json.loads(raw) if raw is not None else None)


def _archived(fold: _Fold) -> tuple[dict[str, Any], dict[str, Any]]:
    """The oldest live off record's next version, archived: still off, now `superseded`, so it is unserved and no longer counts
    against the cap, with its scanned title and source locator kept and marked `archived:overflow`. Nothing is deleted; the user
    can still list, forget or re-remember it. Returned as (stream record, payload)."""
    oldest = next(iter(fold.off))
    current = fold.items[oldest]
    lineage = [*current["lineage"], "archived:overflow"][-msc.MAX_REFERENCES:]
    event = {"event_id": f"archive-{oldest}-{current['version'] + 1}", "item": oldest, "version": current["version"] + 1,
             "action": "off", "trust": "off", "status": "superseded", "kind": current["kind"], "scope": current["scope"],
             "title": current["title"], "statement": "", "anchors": list(current["anchors"]), "lineage": lineage,
             "valid_from_ms": current["valid_from_ms"], "valid_until_ms": current["valid_until_ms"]}
    entry, payload = _split(event)
    payload["digest"] = _digest([current["version"], event])
    key = hashlib.sha256(f"omem/archive/v1\0{oldest}\0{current['version']}".encode()).hexdigest()
    return {"type": "event", "key": key, "event": entry}, payload


def recovery_key(password: str) -> bytes:
    """The recovery generations' HMAC key: domain-separated from the journal's, derived from the Gateway's generated ACL password,
    so no new secret exists and a host without the store's credential cannot forge or alter a generation."""
    return hashlib.sha256(b"optimus-memory-recovery-v1\0" + password.encode("utf-8")).digest()


def _exported(record: dict[str, Any]) -> dict[str, Any]:
    """One item as a recovery generation keeps it (D8): an active vouched-for item whole; any other only its payload-free
    lifecycle, with no title, statement, anchors or lineage (an off record's scanned title included)."""
    keep = record["status"] == "active" and record["trust"] != "off"
    entry = {name: record[name] for name in ("event_id", "item", "version", "action", "trust", "status", "kind", "scope",
                                             "valid_from_ms", "valid_until_ms", "stream_id")}
    if keep:
        return {**entry, "title": record["title"], "statement": record["statement"], "anchors": list(record["anchors"]),
                "lineage": list(record["lineage"])}
    return {**entry, "title": "", "statement": "", "anchors": [], "lineage": []}


def _frontier(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """How far deletion had gone in a generation: how many items it holds withdrawn or purged, and the newest such entry."""
    gone = [entry for entry in entries if entry["status"] in ("withdrawn", "purged")]
    return {"deletions": len(gone), "last": max((entry["stream_id"] for entry in gone), key=_order, default="")}


def _order(stream_id: str) -> tuple[int, int]:
    ms, _, seq = stream_id.partition("-")
    return int(ms), int(seq)


def _result(stream_id: str, record: dict[str, Any]) -> dict[str, Any]:
    if record["type"] == "event":
        return {"item": record["event"]["item"], "version": record["event"]["version"], "event_id": record["event"]["event_id"],
                "stream_id": stream_id}
    return {"session": record["checkpoint"]["session"], "sequence": record["checkpoint"]["sequence"], "stream_id": stream_id}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


class MemoryStore:
    """One Gateway's view of the dedicated instance. Every method raises `msc.MemoryRequestError` for a refusal.

    Writes go through one connection, held under a lock with retries off, so `WAITAOF` answers for the very connection that
    appended; `CLIENT ID` before and after proves no reconnect came between. Reads use a second connection under their own lock
    and see only the confirmed watermark. A lost or replaced connection makes the store suspect: every operation is refused until
    `verify` shows the resource is still the provisioned one."""

    def __init__(self, client: redis.Redis, writer: redis.Redis, *, admission_ceiling_mb: int, cursor_key: bytes,
                 journal: PurgeJournal | None = None, inventory: Callable[[float], Inventory] | None = None,
                 recovery_key: bytes | None = None) -> None:
        self._purge_journal = journal
        self._recovery_key = recovery_key  # HMAC key for recovery generations, derived from the ACL password; None refuses them
        self._inventory = inventory  # lists the data directory; without one no purge's disk step is ever shown complete
        self._redis = client
        self._writer = writer
        self._write_lock = threading.Lock()
        self._read_lock = threading.Lock()
        self._ceiling_bytes = admission_ceiling_mb * _MIB
        self._admission_ceiling_mb = admission_ceiling_mb
        self._cursor_key = cursor_key
        self._fsync_failed = False
        self._suspect = False
        self._verified_connects = (_connects(writer), _connects(client))
        self._local = threading.local()
        self._writer_folds: dict[str, _Fold] = {}
        self._serving_folds: dict[str, _Fold] = {}

    def dispatch(self, body: dict[str, Any], *, deadline: float | None = None) -> dict[str, Any]:
        """Run one operation inside the request's deadline: no lock wait, fold page or append starts once it has passed."""
        if body["op"] in msc.UNAVAILABLE:
            raise msc.MemoryRequestError("MEMORY_OPERATION_UNAVAILABLE", 501)
        self._local.deadline = deadline
        try:
            handler = getattr(self, f"_op_{body['op']}")
            result: dict[str, Any] = handler(body)
            return result
        finally:
            self._local.deadline = None

    def _remaining(self) -> float:
        deadline = getattr(self._local, "deadline", None)
        return msc.DEADLINE_SECONDS if deadline is None else deadline - time.monotonic()

    def _on_time(self) -> None:
        """Between blocking steps: stop once the deadline has passed, stop if either connection was re-established since the
        resource was verified, and give the held connection only what is left of the budget."""
        if self._remaining() <= 0:
            raise msc.MemoryRequestError("MEMORY_TIMEOUT", 503)
        self._check_links()
        self._rebudget()

    def _check_links(self) -> None:
        if getattr(self._local, "verifying", False):
            return
        if (_connects(self._writer), _connects(self._redis)) != self._verified_connects:
            self.connection_lost()
            raise msc.MemoryRequestError("MEMORY_UNAVAILABLE", 503)

    def _rebudget(self) -> None:
        """Shrink the held connections' budgets to what is left of the request's."""
        for client in getattr(self._local, "held", ()):
            set_budget(client, self._remaining())

    @contextlib.contextmanager
    def _holding(self, client: Any) -> Iterator[None]:
        """Use one connection inside the request's budget: its timeouts shrink as the budget does, and a watchdog cuts its
        socket at the absolute deadline, so no sequence of reads, however fragmented, outlasts the request."""
        held = getattr(self._local, "held", ())
        self._local.held = (*held, client)
        set_budget(client, self._remaining())
        link = getattr(client, "optimus_link", None)
        watchdog = None
        if isinstance(link, Link):
            link.deadline = time.monotonic() + self._remaining()
            verifying = getattr(self._local, "verifying", False)
            link.expected = None if verifying else self._verified_connects[0 if client is self._writer else 1]
            watchdog = threading.Timer(max(0.0, self._remaining()), link.cut)
            watchdog.daemon = True
            watchdog.start()
        try:
            yield
        finally:
            if watchdog is not None and isinstance(link, Link):
                watchdog.cancel()
                watchdog.join()  # a cut already under way finishes on this request's connection, before the lock is released
                link.deadline = None
                link.expected = None
            self._local.held = held
            set_budget(client, msc.DEADLINE_SECONDS)

    @property
    def suspect(self) -> bool:
        """A connection was lost or replaced: nothing runs until `verify` succeeds."""
        return self._suspect

    def verify(self, resource: str, *, deadline: float | None = None) -> None:
        """Prove the resource on both connections, inside the request's budget, and clear suspicion only when it holds.

        Both connections are established first and their generations fixed; the proof is refused if either changes while it is
        collected, so persistence, eviction, the resource marker and the fsync probe all come from the same two connections.
        Those generations are the ones every later operation must still see."""
        self._local.deadline = deadline
        self._local.verifying = True
        try:
            self._prove(resource)
        except (RedisError, OSError, MemoryStoreStartupError) as exc:  # a cut at the deadline included, however it was wrapped
            if self._remaining() <= 0:
                raise msc.MemoryRequestError("MEMORY_TIMEOUT", 503) from None
            if isinstance(exc, Reconnected) or isinstance(exc.__cause__, Reconnected):  # refused at the send, before writing
                raise MemoryStoreStartupError("MEMORY_STORE_RECONNECTED") from exc
            if isinstance(exc, MemoryStoreStartupError):
                raise
            raise MemoryStoreStartupError("MEMORY_STORE_UNREACHABLE") from exc
        finally:
            self._local.deadline = None
            self._local.verifying = False

    def _prove(self, resource: str) -> None:
        with self._writing(verifying=True), self._reading(verifying=True):
            self._writer.ping()
            self._redis.ping()
            generations = (_connects(self._writer), _connects(self._redis))
            for client, generation in ((self._writer, generations[0]), (self._redis, generations[1])):
                link = getattr(client, "optimus_link", None)
                if isinstance(link, Link):
                    link.expected = generation  # nothing in the proof, the marker write included, reaches a reconnected server

            def step() -> None:
                self._on_time()
                if (_connects(self._writer), _connects(self._redis)) != generations:
                    raise MemoryStoreStartupError("MEMORY_STORE_RECONNECTED")

            probe_ms = min(_WAITAOF_PROBE_MS, int(self._remaining() * 1000) - _SOCKET_MARGIN_MS)
            if probe_ms <= 0:
                raise msc.MemoryRequestError("MEMORY_TIMEOUT", 503)
            verify_resource(self._writer, resource, probe_ms=probe_ms, step=step)
            step()
            if _text(self._redis.get(_RESOURCE_KEY) or b"") != resource:  # the reader reaches the same instance
                raise MemoryStoreStartupError("MEMORY_STORE_RESOURCE_MISMATCH")
            step()
            self.forget()
            self._verified_connects = generations
            self._suspect = False

    def connection_lost(self) -> None:
        """Drop every cache and refuse everything until the resource is verified again."""
        self.forget()
        self._suspect = True

    _connection_lost = connection_lost

    def _after_watch_error(self, connection: int) -> None:
        """A WatchError is either another writer, which is retried, or redis-py reporting a lost connection. A new connection id
        means the latter: nothing cached is trusted and nothing more runs until the resource is verified again. Whether a
        transaction already sent took effect is uncertain; a retry under the same key reconciles it."""
        if self._remaining() <= 0:  # past the deadline nothing reconnects, not even to ask which connection this is
            self._connection_lost()
            raise msc.MemoryRequestError("MEMORY_TIMEOUT", 503)
        try:
            same_connection = int(self._writer.client_id()) == connection
        except (RedisConnectionError, TimeoutError, OSError) as exc:
            self._connection_lost()
            expired = isinstance(exc, DeadlinePassed) or self._remaining() <= 0
            raise msc.MemoryRequestError("MEMORY_TIMEOUT" if expired else "MEMORY_UNAVAILABLE", 503) from None
        if not same_connection:
            self._connection_lost()
            raise msc.MemoryRequestError("MEMORY_UNAVAILABLE", 503)

    @staticmethod
    def _project_hash(project: str) -> str:
        return hashlib.sha256(project.encode()).hexdigest()[:32]

    @classmethod
    def _key(cls, project: str, name: str) -> str:
        return f"{_PREFIX}:p:{cls._project_hash(project)}:{name}"

    def _used(self) -> int:
        with self._reading():
            used = int(self._redis.info("memory").get("used_memory", 0))
            self._check_links()  # a reply from a connection re-established since verification is not reported
            return used

    def _op_capabilities(self, _body: dict[str, Any]) -> dict[str, Any]:
        used = self._used()
        return {
            "status": "ok",
            "schema_version": msc.SCHEMA_VERSION,
            "durable": not self._fsync_failed,
            "admitting": used < self._ceiling_bytes and not self._fsync_failed,
            "used_mb": used // _MIB,
            "admission_ceiling_mb": self._admission_ceiling_mb,
        }

    # --- leases --------------------------------------------------------------------------------------------------------

    def _op_lease(self, body: dict[str, Any]) -> dict[str, Any]:
        """One writer per project. A new holder always takes a higher fence, and gets it only once the fence is on disk, so a
        crash cannot hand the same token out twice and a writer that lost its lease cannot append."""
        key, owner = self._key(body["project"], "lease"), body["owner"]
        with self._writing():
            connection = int(self._writer.client_id())
            self._check_links()
            for _ in range(_WATCH_ATTEMPTS):
                token = 0
                with _pipeline(self._writer) as pipe:
                    try:
                        pipe.watch(key)
                        held = _text(pipe.get(key) or b"")
                        if body["action"] == "acquire":
                            if held and held.split(":", 1)[1] != owner:
                                pipe.unwatch()
                                raise msc.MemoryRequestError("LEASE_HELD", 409)
                            token = int(pipe.incr(_FENCE_KEY))
                            pipe.multi()
                            pipe.set(key, f"{token}:{owner}", px=body["ttl_ms"])
                        else:
                            if held != f"{body['token']}:{owner}":
                                pipe.unwatch()
                                raise msc.MemoryRequestError("LEASE_LOST", 409)
                            pipe.multi()
                            if body["action"] == "renew":
                                pipe.pexpire(key, body["ttl_ms"])
                            else:
                                pipe.delete(key)
                        self._on_time()
                        pipe.execute()
                    except WatchError:
                        self._after_watch_error(connection)
                        continue
                if not token:
                    return {"status": "ok"}
                if not self._durable(connection):
                    raise msc.MemoryRequestError("LEASE_UNCONFIRMED", 503)
                return {"status": "ok", "token": token}
            raise msc.MemoryRequestError("LEASE_CONTENDED", 409)

    @contextlib.contextmanager
    def _writing(self, *, verifying: bool = False, share: float = 1.0) -> Iterator[None]:
        """The writer, for the rest of the request's budget (`share` of it for the wait). A store under suspicion refuses, so a
        request queued behind the one that lost the connection cannot write to an unverified replacement."""
        self._on_time()
        if not self._write_lock.acquire(timeout=max(0.0, self._remaining() * share)):
            raise msc.MemoryRequestError("MEMORY_BUSY", 503)
        try:
            self._on_time()  # the wait for the lock may have used up the budget
            if self._suspect and not verifying:
                raise msc.MemoryRequestError("MEMORY_UNAVAILABLE", 503)
            self._check_links()
            with self._holding(self._writer):
                yield
        finally:
            self._write_lock.release()

    @contextlib.contextmanager
    def _reading(self, *, verifying: bool = False) -> Iterator[None]:
        self._on_time()
        if not self._read_lock.acquire(timeout=max(0.0, self._remaining())):
            raise msc.MemoryRequestError("MEMORY_BUSY", 503)
        try:
            self._on_time()
            if self._suspect and not verifying:
                raise msc.MemoryRequestError("MEMORY_UNAVAILABLE", 503)
            self._check_links()
            with self._holding(self._redis):
                yield
        finally:
            self._read_lock.release()

    def forget(self) -> None:
        """Drop every cached fold after an outage or an unexpected error; the next use rebuilds from the stream."""
        self._writer_folds = {}
        self._serving_folds = {}

    # --- the one append ------------------------------------------------------------------------------------------------

    def _op_append(self, body: dict[str, Any]) -> dict[str, Any]:
        event = body["event"]
        gated = event["action"] in ("admit", "update")  # withdrawals and off records still go through when saves are refused
        if gated and self._fsync_failed:
            self._recheck_fsync()
        entry, payload = _split(event)
        record = {"type": "event", "key": body["idempotency_key"], "event": entry}
        payload["digest"] = _digest([body["expected_version"], event])  # the retry check, purged with the payload
        return self._append(body["project"], body["token"], record, payload, expected=body["expected_version"], gated=gated)

    def _op_checkpoint(self, body: dict[str, Any]) -> dict[str, Any]:
        point = body["checkpoint"]  # host references only, never source text: it stays in the stream
        record = {"type": "checkpoint", "key": f"checkpoint:{point['session']}:{point['sequence']}", "digest": _digest(point),
                  "checkpoint": point}
        return self._append(body["project"], body["token"], record, None, expected=None)

    def _writer_fold(self, pipe: Any, project: str, token: int) -> tuple[_Fold, str]:
        """Inside a watching pipeline: the lease still names this holder, and the writer's fold is advanced to the stream's head."""
        stream, lease = self._key(project, "events"), self._key(project, "lease")
        pipe.watch(lease, stream)
        if _text(pipe.get(lease) or b"").split(":", 1)[0] != str(token):
            pipe.unwatch()
            raise msc.MemoryRequestError("LEASE_LOST", 409)
        newest = pipe.xrevrange(stream, count=1)
        head = _text(newest[0][0]) if newest else "0-0"
        fold = self._writer_folds.setdefault(project, _Fold())
        if _order(head) < _order(fold.head):
            fold = self._writer_folds[project] = _Fold()  # the stream went back: rebuild, never trust the cache
        fold.advance(pipe, stream, self._key(project, "payloads"), head, self._on_time)
        return fold, head

    @staticmethod
    def _execute(pipe: Any) -> list[Any]:
        """EXEC, with a store at its memory limit reported as such rather than as a storage fault."""
        try:
            return list(pipe.execute())
        except OutOfMemoryError:  # noeviction at maxmemory refused the queued XADD; its message quotes the command, never logged
            raise msc.MemoryRequestError("MEMORY_FULL", 507) from None

    def _append(self, project: str, token: int, record: dict[str, Any], payload: dict[str, Any] | None, *, expected: int | None,
                gated: bool = False) -> dict[str, Any]:
        stream, payloads = self._key(project, "events"), self._key(project, "payloads")
        with self._writing():
            connection = int(self._writer.client_id())
            self._check_links()  # the baseline connection is the verified one, not one the pool re-established just now
            for _ in range(_WATCH_ATTEMPTS):
                replay_at = archive = None
                with _pipeline(self._writer) as pipe:  # a watching pipeline holds the writer's only connection until it closes
                    try:
                        fold, head = self._writer_fold(pipe, project, token)
                        if record["key"] in fold.keys:
                            pipe.unwatch()
                            replay_at = head
                        elif gated and (self._fsync_failed or self._used() >= self._ceiling_bytes):
                            pipe.unwatch()
                            raise msc.MemoryRequestError("MEMORY_NOT_ADMITTING", 503)
                        else:
                            self._check(fold, record, expected)
                            if record.get("event", {}).get("trust") == "off" and record["event"]["action"] == "off" and (
                                    len(fold.off) >= msc.MAX_OFF_RECORDS or sum(fold.off.values()) >= msc.MAX_OFF_BYTES):
                                if self._used() >= self._ceiling_bytes:  # the archive grows only below the ceiling (Fable CP2 M5)
                                    pipe.unwatch()
                                    raise msc.MemoryRequestError("OFF_RECORDS_FULL", 507)
                                archive = _archived(fold)  # the oldest live off record moves to the unserved archive first
                            self._on_time()  # past the deadline nothing is appended; once EXEC is sent the outcome may be uncertain
                            pipe.multi()
                            if archive is not None:
                                pipe.xadd(stream, {"e": _json(archive[0])})
                                pipe.hset(payloads, archive[0]["event"]["event_id"], _json(archive[1]))
                            pipe.xadd(stream, {"e": _json(record)})
                            if payload is not None:
                                pipe.hset(payloads, record["event"]["event_id"], _json(payload))
                            replies = self._execute(pipe)
                            stream_id = _text(replies[2 if archive is not None else 0])
                            if archive is not None:
                                fold.apply(_text(replies[0]), archive[0], dict(archive[1]))
                    except WatchError:
                        self._after_watch_error(connection)
                        continue
                if replay_at is not None:
                    return self._replay(project, fold, record, payload, replay_at, connection)
                fold.apply(stream_id, record, None if payload is None else dict(payload))
                archived = {"archived": archive[0]["event"]["item"]} if archive is not None else {}  # growth stays visible
                return {"status": "ok", **_result(stream_id, record), **archived, **self._confirm(project, stream_id, connection)}
            raise msc.MemoryRequestError("MEMORY_CONTENDED", 409)

    @staticmethod
    def _check(fold: _Fold, record: dict[str, Any], expected: int | None) -> None:
        if record["type"] != "event":
            return
        event = record["event"]
        current = fold.items.get(event["item"])
        if (current["version"] if current else 0) != expected:
            raise msc.MemoryRequestError("VERSION_CONFLICT", 409)
        if current and current["status"] == "purged":
            raise msc.MemoryRequestError("ITEM_PURGED", 409)
        if event["event_id"] in fold.event_ids:
            raise msc.MemoryRequestError("EVENT_ID_REUSED", 409)

    def _replay(self, project: str, fold: _Fold, record: dict[str, Any], payload: dict[str, Any] | None, head: str,
                connection: int) -> dict[str, Any]:
        """A retry of the same change returns the first one's result once it is on disk; a different change under that key is a
        conflict, and a change whose item has since been purged is refused. Nothing is appended twice."""
        digest, result = fold.keys[record["key"]]
        if digest is None:
            raise msc.MemoryRequestError("ITEM_PURGED", 409)
        if digest != (payload["digest"] if payload is not None else record["digest"]):
            raise msc.MemoryRequestError("IDEMPOTENCY_CONFLICT", 409)
        self._writer.incr(self._key(project, "sync"))  # puts this connection's offset past the earlier append, wherever it came from
        return {"status": "ok", **result, "replayed": True, **self._confirm(project, head, connection)}

    def _durable(self, connection: int) -> bool:
        """Whether this connection's writes are on disk: `WAITAOF` on the writer, and the same connection before and after.

        Three ways to fail, kept apart. A lost or replaced connection drops every cache and re-verifies the resource, since Redis
        may have lost writes the caches hold. A full-length wait that confirms nothing stops new saves until a probe succeeds. A
        wait cut short by the request's deadline only leaves this write unconfirmed."""
        budget = min(_WAITAOF_COMMIT_MS, int(self._remaining() * 1000) - _SOCKET_MARGIN_MS)
        if budget <= 0:
            return False
        self._rebudget()
        try:
            count = waitaof_local(self._writer, timeout_ms=budget)
            same = int(self._writer.client_id()) == connection and _connects(self._writer) == self._verified_connects[0]
        except (RedisConnectionError, TimeoutError, OSError):
            count, same = 0, False
        except (RedisError, MemoryStoreStartupError):
            count, same = 0, True
        if not same:
            self._connection_lost()
            return False
        if count < 1 and budget == _WAITAOF_COMMIT_MS:
            self._fsync_failed = True
        return count >= 1

    def _confirm(self, project: str, stream_id: str, connection: int) -> dict[str, str]:
        if not self._durable(connection):
            return {"durable_state": "unconfirmed", "projection_state": "pending"}
        current = self._advance_watermark(project, stream_id, connection)
        # confirmed on disk either way; "current" only once the watermark this Gateway serves from includes it
        return {"durable_state": "confirmed", "projection_state": "current" if current else "pending"}

    def _recheck_fsync(self) -> None:
        """A new fsync probe inside the request's budget; only a full-length probe that confirms nothing keeps saves stopped."""
        with self._writing():
            budget = min(_WAITAOF_COMMIT_MS, int(self._remaining() * 1000) - _SOCKET_MARGIN_MS)
            if budget <= 0:
                return
            try:
                confirmed = fsync_probe(self._writer, timeout_ms=budget) >= 1
            except (RedisConnectionError, TimeoutError, OSError):
                self._connection_lost()
                raise msc.MemoryRequestError("MEMORY_UNAVAILABLE", 503) from None
            except (RedisError, MemoryStoreStartupError):
                confirmed = False
            if confirmed or budget == _WAITAOF_COMMIT_MS:
                self._fsync_failed = not confirmed

    def _advance_watermark(self, project: str, stream_id: str, connection: int) -> bool:
        """AOF is ordered, so a confirmed event confirms every one before it. The watermark only moves forward. True when it now
        covers `stream_id`; false when that could not be established, which leaves the save confirmed but its projection pending."""
        key = self._key(project, "durable")
        try:
            for _ in range(_WATCH_ATTEMPTS):
                with _pipeline(self._writer) as pipe:
                    try:
                        pipe.watch(key)
                        current = pipe.get(key)
                        if current is not None and _order(_text(current)) >= _order(stream_id):
                            pipe.unwatch()
                            return True
                        self._on_time()
                        pipe.multi()
                        pipe.set(key, stream_id)
                        pipe.execute()
                        return True
                    except WatchError:
                        if int(self._writer.client_id()) != connection:
                            self._connection_lost()
                            return False
                        continue
        except msc.MemoryRequestError:
            return False  # the budget ran out after the save was confirmed
        except (RedisConnectionError, TimeoutError, OSError):
            self._connection_lost()
            return False
        return False  # shortcut: a contended watermark stays behind until the next confirmed write moves it

    # --- serving -------------------------------------------------------------------------------------------------------

    def _served(self, project: str, answer: Callable[[_Fold], dict[str, Any]]) -> dict[str, Any]:
        """Answer from the confirmed fold while holding the read lock: another request may advance the same fold. A watermark
        behind the stream's head (a save confirmed just before a crash, or one whose proof was cut) is reconciled once first."""
        for reconciled in (False, True):
            with self._reading():
                watermark = _text(self._redis.get(self._key(project, "durable")) or b"0-0")
                newest = self._redis.xrevrange(self._key(project, "events"), count=1)
                head = _text(newest[0][0]) if newest else "0-0"
                if reconciled or _order(watermark) >= _order(head):
                    fold = self._serving_folds.setdefault(project, _Fold())
                    if _order(watermark) < _order(fold.head):
                        fold = self._serving_folds[project] = _Fold()
                    fold.advance(self._redis, self._key(project, "events"), self._key(project, "payloads"), watermark, self._on_time)
                    self._check_links()  # nothing read from a connection re-established since verification is served
                    return answer(fold)
            try:
                self._reconcile(project, head)  # outside the read lock: writers take it while they hold the write lock
            except msc.MemoryRequestError:
                pass  # the writer is busy or out of time: serve what the watermark already proves
        raise AssertionError("unreachable")

    def _reconcile(self, project: str, head: str) -> None:
        """Prove the stream's tail is on disk and move the watermark over it: one write on the writer's own connection after the
        tail, then WAITAOF there. The AOF is ordered, so that fsync covers every entry before it. If it cannot be proven, reads
        stay at the watermark and the tail's projection stays pending. It waits for the writer at most half the budget, so the
        read can still be served."""
        with self._writing(share=0.5):
            connection = int(self._writer.client_id())
            self._check_links()
            self._writer.incr(self._key(project, "sync"))
            if self._durable(connection):
                self._advance_watermark(project, head, connection)

    @staticmethod
    def _whole(record: Any) -> Any:
        """A live item whose payload is missing is damage, never an empty memory."""
        if record is not None and "statement" not in record:
            raise RedisError("an event's payload is missing")
        return record

    def _op_read(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._served(body["project"], lambda fold: {"status": "ok", "item": self._whole(fold.items.get(body["item"]))})

    def _op_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """Confirmed items in one scope, in item-id order, as many as fit the reply bound. A cursor is sealed to its project and scope."""
        after = self._unseal(body["project"], body["scope"], body["cursor"]) if "cursor" in body else ""

        def page(fold: _Fold) -> dict[str, Any]:
            ids = sorted(item for item, record in fold.items.items() if record["scope"] == body["scope"] and item > after)
            items: list[dict[str, Any]] = []
            size = _LIST_ENVELOPE_BYTES
            for item in ids[: body["limit"]]:
                record = self._whole(fold.items[item])
                size += len(json.dumps(record, ensure_ascii=True)) + 1
                if items and size > msc.MAX_RESPONSE_BYTES:
                    break
                items.append(record)
            cursor = self._seal(body["project"], body["scope"], items[-1]["item"]) if len(ids) > len(items) else None
            return {"status": "ok", "items": items, "cursor": cursor}

        return self._served(body["project"], page)

    def _op_history(self, body: dict[str, Any]) -> dict[str, Any]:
        """One page of an item's versions, newest first (Q4). Each version's text is read from the payload hash, so a withdrawal
        keeps the earlier versions and a purge, which removes every payload the item had, leaves only payload-free entries."""
        project = body["project"]

        def page(fold: _Fold) -> dict[str, Any]:
            before = body.get("before", msc.MAX_VERSION + 1)
            older = [entry for entry in reversed(fold.versions.get(body["item"], [])) if entry["version"] < before]
            shown = older[: body["limit"]]
            ids = [entry["event_id"] for entry in shown]
            found = dict(zip(ids, self._redis.hmget(self._key(project, "payloads"), ids), strict=True)) if ids else {}
            versions = []
            for entry in shown:
                raw = found.get(entry["event_id"])
                text = json.loads(raw) if raw is not None else None
                versions.append({name: entry[name] for name in ("event_id", "version", "action", "status", "trust", "kind", "stream_id")}
                                | {"title": text["title"] if text else "", "statement": text["statement"] if text else "",
                                   "text": "kept" if text else "none"})
            return {"status": "ok", "versions": versions, "more": len(older) > len(shown)}

        return self._served(project, page)

    def _op_checkpoints(self, body: dict[str, Any]) -> dict[str, Any]:
        def page(fold: _Fold) -> dict[str, Any]:
            chosen = [point for point in fold.checkpoints if all(point[name] == body[name] for name in ("branch", "worktree") if name in body)]
            return {"status": "ok", "checkpoints": chosen[-body["limit"]:][::-1]}

        return self._served(body["project"], page)

    # --- the recovery copy (D5, D8) --------------------------------------------------------------------------------------

    def _need_recovery(self) -> bytes:
        if self._recovery_key is None:
            raise msc.MemoryRequestError("MEMORY_RECOVERY_UNAVAILABLE", 503)
        return self._recovery_key

    def _entry_mac(self, key: bytes, project: str, entry: dict[str, Any]) -> str:
        return hmac.new(key, b"omem/recovery-entry/v1\0" + project.encode() + b"\0" + _json(entry).encode(), hashlib.sha256).hexdigest()

    def _generation_seal(self, key: bytes, project: str, head: str, macs: list[tuple[str, str]], frontier: dict[str, Any], bind: str,
                         journal: int) -> str:
        """The seal over a whole generation: its head, every entry's MAC, its deletion frontier, the host's metadata digest (format,
        registry mapping, layout files; Codex CP3 review 1) and how many deletion-journal records the project had."""
        body = _json({"project": project, "head": head, "entries": sorted(macs), "frontier": frontier, "bind": bind, "journal": journal})
        return hmac.new(key, b"omem/recovery-generation/v2\0" + body.encode(), hashlib.sha256).hexdigest()

    def _bind_mac(self, key: bytes, project: str, bind: str) -> str:
        return hmac.new(key, b"omem/recovery-bind/v1\0" + project.encode() + b"\0" + bind.encode(), hashlib.sha256).hexdigest()

    def _journal_count(self, project: str) -> int:
        journal = self._need_journal()
        try:
            return len(journal.project_entries(self._project_hash(project)))
        except JournalError as refusal:
            raise msc.MemoryRequestError(refusal.code, 503) from None

    def _op_verify_bind(self, body: dict[str, Any]) -> dict[str, Any]:
        key = self._need_recovery()
        return {"status": "ok", "valid": hmac.compare_digest(body["mac"], self._bind_mac(key, body["project"], body["bind"]))}

    def _op_export(self, body: dict[str, Any]) -> dict[str, Any]:
        """One page of the project's recovery generation at the confirmed head, every item in id order, each with its HMAC. The
        last page also carries the head, the deletion frontier and the seal over all of it, so a restore can tell a whole,
        unaltered generation this Gateway wrote. Pages read at different heads do not seal: the host starts again."""
        key = self._need_recovery()
        project = body["project"]
        after = self._unseal(project, "recovery", body["cursor"]) if "cursor" in body else ""
        journal = self._journal_count(project)  # how many deletion-journal records the seal binds

        def page(fold: _Fold) -> dict[str, Any]:
            ids = sorted(item for item in fold.items if item > after)
            entries: list[dict[str, Any]] = []
            size = _LIST_ENVELOPE_BYTES
            for item in ids[: body["limit"]]:
                entry = _exported(self._whole(fold.items[item]))
                shaped = {"entry": entry, "mac": self._entry_mac(key, project, entry)}
                size += len(_json(shaped)) + 1
                if entries and size > msc.MAX_RESPONSE_BYTES - 4096:
                    break
                entries.append(shaped)
            more = len(ids) > len(entries)
            reply: dict[str, Any] = {"status": "ok", "head": fold.head, "entries": entries,
                                     "cursor": self._seal(project, "recovery", entries[-1]["entry"]["item"]) if more else None}
            if not more:
                every = [_exported(self._whole(record)) for record in fold.items.values()]
                frontier = _frontier(every)
                macs = [(entry["item"], self._entry_mac(key, project, entry)) for entry in every]
                reply |= {"frontier": frontier, "journal": journal, "bind_mac": self._bind_mac(key, project, body["bind"]),
                          "seal": self._generation_seal(key, project, fold.head, macs, frontier, body["bind"], journal)}
            return reply

        return self._served(project, page)

    def _restore_keys(self, project: str, generation: str) -> tuple[str, str]:
        return self._key(project, f"restore:{generation}"), self._key(project, f"restore:{generation}:next")

    def _op_restore(self, body: dict[str, Any]) -> dict[str, Any]:
        """Stage one verified batch of a generation, unserved; on the last, verify the whole generation's seal and publish it
        into the empty project in one fenced transaction. Never into a project holding anything (`RESTORE_TARGET_NOT_EMPTY`,
        before any live event or idempotency record is touched); never over an uncertain deletion. The deletion journal and
        the host's own later withdrawals apply whatever the generation's age: they only take payloads away. With `source` (a
        user-confirmed mapping), the generation is authenticated as that project's and published into this one."""
        key = self._need_recovery()
        project, generation, batch = body["project"], body["generation"], body["batch"]
        source = body.get("source", project)
        staged, cursor_key = self._restore_keys(project, generation)
        stream, payloads, lease = self._key(project, "events"), self._key(project, "payloads"), self._key(project, "lease")
        for shaped in body["entries"]:
            if not hmac.compare_digest(shaped["mac"], self._entry_mac(key, source, shaped["entry"])):
                raise msc.MemoryRequestError("RESTORE_ENTRY_INVALID", 422)
        with self._writing():
            connection = int(self._writer.client_id())
            self._check_links()
            if _text(self._writer.get(lease) or b"").split(":", 1)[0] != str(body["token"]):
                raise msc.MemoryRequestError("LEASE_LOST", 409)
            if int(self._writer.xlen(stream)):
                raise msc.MemoryRequestError("RESTORE_TARGET_NOT_EMPTY", 409)
            expected = int(self._writer.get(cursor_key) or 0)
            if batch > expected:
                raise msc.MemoryRequestError("RESTORE_BATCH_OUT_OF_ORDER", 409)
            if batch == 0 and expected:
                self._writer.delete(staged, cursor_key)  # a new attempt at this generation discards the interrupted one
                expected = 0
            if batch == expected:
                self._on_time()
                with _pipeline(self._writer) as pipe:
                    pipe.multi()
                    for shaped in body["entries"]:
                        pipe.hset(staged, shaped["entry"]["item"], _json(shaped))
                    pipe.set(cursor_key, batch + 1)
                    self._execute(pipe)
            if not body["final"]:
                return {"status": "ok", "state": "staged", "next_batch": max(expected, batch + 1)}
            return self._publish_restore(key, body, staged, cursor_key, stream, payloads, lease, connection)

    def _publish_restore(self, key: bytes, body: dict[str, Any], staged: str, cursor_key: str, stream: str, payloads: str, lease: str,
                         connection: int) -> dict[str, Any]:
        project = body["project"]
        source = body.get("source", project)
        raw = self._writer.hgetall(staged)
        entries = [json.loads(value)["entry"] for value in raw.values()]
        macs = [(entry["item"], self._entry_mac(key, source, entry)) for entry in entries]
        seal = self._generation_seal(key, source, body["head"], macs, body["frontier"], body["bind"], body["journal"])
        if not hmac.compare_digest(body["generation"], seal) or body["frontier"] != _frontier(entries):
            raise msc.MemoryRequestError("RESTORE_GENERATION_INVALID", 422)  # a missing, extra or altered entry, or another head
        if source == project:
            purged = self._journalled_purges(project, body["journal"], body["purged"])
        else:  # a mapping: the source's journal as the generation knew it, and every purge since in the project it maps to
            purged = self._journalled_purges(source, body["journal"], []) | self._journalled_purges(project, 0, body["purged"])
        withdrawn = set(body["withdrawn"])
        records: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
        for entry in sorted(entries, key=lambda value: _order(value["stream_id"])):
            event = {name: value for name, value in entry.items() if name != "stream_id"}
            # a later deletion is the item's next version, as it was in the lost store, with nothing of its payload
            gone = {"version": event["version"] + 1, "event_id": f"restored-{event['item']}-{event['version'] + 1}", "title": "",
                    "statement": "", "anchors": [], "lineage": []}
            if event["item"] in purged and event["status"] != "purged":
                event = {**event, **gone, "action": "tombstone", "status": "purged"}
            elif event["item"] in withdrawn and event["status"] == "active":
                event = {**event, **gone, "action": "withdraw", "status": "withdrawn"}
            restore_key = hashlib.sha256(f"omem/restored/v1\0{event['event_id']}".encode()).hexdigest()
            if event["action"] == "tombstone":
                records.append(({"type": "event", "key": restore_key, "digest": _digest(["purge", event["item"]]), "event": event}, None))
                continue
            entry_part, payload = _split(event)
            payload["digest"] = _digest([event["version"] - 1, event])
            records.append(({"type": "event", "key": restore_key, "event": entry_part}, payload))
        with _pipeline(self._writer) as pipe:
            try:
                pipe.watch(lease, stream)
                if _text(pipe.get(lease) or b"").split(":", 1)[0] != str(body["token"]):
                    raise msc.MemoryRequestError("LEASE_LOST", 409)
                if int(pipe.xlen(stream)):
                    raise msc.MemoryRequestError("RESTORE_TARGET_NOT_EMPTY", 409)  # a write landed meanwhile: nothing is merged
                self._on_time()
                pipe.multi()
                for record, kept in records:
                    pipe.xadd(stream, {"e": _json(record)})
                    if kept is not None:
                        pipe.hset(payloads, record["event"]["event_id"], _json(kept))
                pipe.delete(staged, cursor_key)
                pipe.set(self._key(project, "restored"), body["generation"])
                replies = self._execute(pipe)
            except WatchError:
                raise msc.MemoryRequestError("RESTORE_TARGET_NOT_EMPTY", 409) from None
        del replies
        newest = self._writer.xrevrange(stream, count=1)
        head = _text(newest[0][0]) if newest else "0-0"
        self._writer_folds.pop(project, None)
        self._serving_folds.pop(project, None)
        confirmed = self._confirm(project, head, connection) if records else {"durable_state": "confirmed", "projection_state": "current"}
        return {"status": "ok", "state": "published", "restored": len(records), "purged": sorted(purged & {r[0]["event"]["item"] for r in records}),
                **confirmed}

    def _journalled_purges(self, project: str, expected: int, known: list[str]) -> set[str]:
        """Items the deletion journal says were purged in this project. An intent with no later step is uncertain: the
        generation may hold text a purge was destroying, so nothing is published until that purge is retried."""
        journal = self._need_journal()
        try:
            records = journal.project_entries(self._project_hash(project))
        except JournalError as refusal:
            raise msc.MemoryRequestError("RESTORE_DELETION_UNKNOWN" if refusal.code == "MEMORY_JOURNAL_DAMAGED" else refusal.code, 409) from None
        if len(records) < expected:  # fewer records than when the generation was written: the journal was lost or cut
            raise msc.MemoryRequestError("RESTORE_DELETION_UNKNOWN", 409)
        phases: dict[str, set[str]] = {}
        for record in records:
            phases.setdefault(record["item"], set()).add(record["phase"])
        if any(found == {"intent"} for found in phases.values()):
            raise msc.MemoryRequestError("RESTORE_DELETION_UNCERTAIN", 409)
        purged = {item for item, found in phases.items() if found & {"tombstoned", "physical", "completed"}}
        if not set(known) <= purged:  # the host saw a purge the journal no longer shows: it was lost (Codex CP3 review 1, finding 1)
            raise msc.MemoryRequestError("RESTORE_DELETION_UNKNOWN", 409)
        return purged

    def _op_restore_status(self, body: dict[str, Any]) -> dict[str, Any]:
        project, generation = body["project"], body["generation"]
        staged, cursor_key = self._restore_keys(project, generation)
        with self._writing():
            self._check_links()
            restored = _text(self._writer.get(self._key(project, "restored")) or b"")
            if restored == generation:
                return {"status": "ok", "state": "published"}
            next_batch = int(self._writer.get(cursor_key) or 0)
            empty = not int(self._writer.xlen(self._key(project, "events")))
        if next_batch:
            return {"status": "ok", "state": "staged", "next_batch": next_batch, "target_empty": empty}
        return {"status": "ok", "state": "none", "target_empty": empty}

    # --- purge ---------------------------------------------------------------------------------------------------------

    def _op_purge(self, body: dict[str, Any]) -> dict[str, Any]:
        """Destroy one item's text. The intent is journalled (fsynced, payload-free) before anything is sent; the tombstone and
        the HDEL of every payload the item ever had go in one transaction, so the text is never gone without its tombstone and
        never outlives it; once WAITAOF confirms that, the AOF rewrite and the snapshot that drop the text from disk are started.
        A retry under the same key finishes whatever an interruption left."""
        journal = self._need_journal()
        project, item, key = body["project"], body["item"], body["idempotency_key"]
        name, digest = self._project_hash(project), _digest(["purge", item])
        stream, payloads = self._key(project, "events"), self._key(project, "payloads")
        outcome: dict[str, Any]
        with self._writing():
            connection = int(self._writer.client_id())
            self._check_links()
            for _ in range(_WATCH_ATTEMPTS):
                replay_at = already = None
                with _pipeline(self._writer) as pipe:
                    try:
                        fold, head = self._writer_fold(pipe, project, body["token"])
                        current = fold.items.get(item)
                        if key in fold.keys:
                            pipe.unwatch()
                            replay_at = head
                        elif current is None:
                            pipe.unwatch()
                            raise msc.MemoryRequestError("ITEM_UNKNOWN", 404)
                        elif current["status"] == "purged":
                            pipe.unwatch()
                            already = current  # purged under another key: finish what it left, never refuse it
                        else:
                            tombstone = {**{field: current[field] for field in _TOMBSTONE_KEEPS}, "event_id": f"purge-{key}",
                                         "version": current["version"] + 1, "action": "tombstone", "status": "purged"}
                            record = {"type": "event", "key": key, "digest": digest, "event": tombstone}
                            self._journal(journal, name, item, "intent", version=tombstone["version"], key=key)
                            self._on_time()
                            pipe.multi()
                            pipe.xadd(stream, {"e": _json(record)})
                            if fold.history.get(item):
                                pipe.hdel(payloads, *fold.history[item])
                            stream_id = _text(self._execute(pipe)[0])
                    except WatchError:
                        self._after_watch_error(connection)
                        continue
                if already is not None:
                    self._writer.incr(self._key(project, "sync"))
                    result = {"item": item, "version": already["version"], "event_id": already["event_id"], "stream_id": already["stream_id"]}
                    outcome = {"already_purged": True, **self._confirm(project, head, connection)}
                elif replay_at is not None:
                    seen, result = fold.keys[key]
                    if seen != digest:
                        raise msc.MemoryRequestError("IDEMPOTENCY_CONFLICT", 409)
                    self._writer.incr(self._key(project, "sync"))  # this connection's offset past the tombstone, wherever it came from
                    outcome = {"replayed": True, **self._confirm(project, replay_at, connection)}
                else:
                    fold.apply(stream_id, record)
                    result = _result(stream_id, record)
                    outcome = self._confirm(project, stream_id, connection)
                state, why = "pending", None
                if outcome["durable_state"] == "confirmed":
                    state, why = self._settle(journal, name, item, result["stream_id"])
                return {"status": "ok", **result, **outcome, "purge_state": state, **_held(why)}
            raise msc.MemoryRequestError("MEMORY_CONTENDED", 409)

    def _op_purge_status(self, body: dict[str, Any]) -> dict[str, Any]:
        """Where a purge stands, moving it on when it can. Redis is the record of whether the tombstone landed, so a journal
        missing a step never makes a purge read "none": a tombstone in the stream is proven on disk (a write and WAITAOF on
        the writer's connection) and its disk step driven. "none": no tombstone and nothing journalled. "pending": a journalled
        intent whose tombstone never landed (the host retries the purge), a tombstone not yet proven, or a rewrite and
        snapshot not both completed after the deletion. The declared boundary is this store's live data and its AOF and RDB
        files."""
        journal = self._need_journal()
        project, item = body["project"], body["item"]
        name = self._project_hash(project)
        with self._writing():
            connection = int(self._writer.client_id())
            self._check_links()
            current = self._fold_at_head(project).items.get(item)
            if current is None or current["status"] != "purged":
                if self._entries(journal, name, item):
                    return {"status": "ok", "item": item, "purge_state": "pending", "next": "retry_purge"}
                return {"status": "ok", "item": item, "purge_state": "none"}
            self._writer.incr(self._key(project, "sync"))
            if not self._durable(connection):
                return {"status": "ok", "item": item, "purge_state": "pending"}
            self._advance_watermark(project, current["stream_id"], connection)
            state, why = self._settle(journal, name, item, current["stream_id"])
            return {"status": "ok", "item": item, "purge_state": state, **_held(why)}

    def _fold_at_head(self, project: str) -> _Fold:
        """The writer's fold advanced to the stream's head, read only (no lease, no WATCH), while the write lock is held."""
        stream = self._key(project, "events")
        newest = self._writer.xrevrange(stream, count=1)
        head = _text(newest[0][0]) if newest else "0-0"
        fold = self._writer_folds.setdefault(project, _Fold())
        if _order(head) < _order(fold.head):
            fold = self._writer_folds[project] = _Fold()
        fold.advance(self._writer, stream, self._key(project, "payloads"), head, self._on_time)
        return fold

    def _settle(self, journal: PurgeJournal, name: str, item: str, tombstone: str) -> tuple[str, Residue | None]:
        """Drive the disk step of a confirmed purge. Each of the AOF rewrite and the RDB snapshot is complete only when one that
        started after the deletion has finished well: so nothing is counted while one is already running (it may predate the
        deletion); an idle store gets a fresh one, whose target is the counter read while idle plus one. A restarted Redis
        (another run id) starts over, since it may have loaded files that still hold the text. Then the data directory must
        hold nothing but the current files. Returns the state and, while pending after both ran, why."""
        entries = self._entries(journal, name, item)
        if any(entry["phase"] == "completed" for entry in entries):
            return PURGE_COMPLETED, None
        if not any(entry["phase"] == "tombstoned" for entry in entries):
            self._journal(journal, name, item, "tombstoned", stream_id=tombstone)
        self._on_time()
        run_id = _text(self._writer.info("server")["run_id"])
        last = next((entry for entry in reversed(entries) if entry["phase"] == "physical" and entry["run_id"] == run_id), {})
        targets: dict[str, int | None] = {kind: last.get(f"{kind}_target") for kind, *_ in _PERSISTENCE}
        before, done = dict(targets), []
        for kind, counter, busy, status, command in _PERSISTENCE:
            self._on_time()
            info = self._writer.info("persistence")
            target = targets[kind]
            if any(info.get(flag) for flag in busy):
                done.append(False)
                continue
            if target is not None and int(info[counter]) >= target and info.get(status) == "ok":
                done.append(True)
                continue
            targets[kind] = int(info[counter]) + 1
            self._on_time()
            try:
                self._writer.execute_command(*command)
            except ResponseError as exc:
                if "in progress" not in str(exc):  # another Gateway started one just now, after this deletion: it counts
                    raise
            done.append(False)
        if targets != before:
            self._journal(journal, name, item, "physical", run_id=run_id, **{f"{kind}_target": value for kind, value in targets.items()})
        if not all(done):
            return "pending", None
        why = self._residue()
        if why is not None:
            return "pending", why  # both ran, but a file outside the current set may still hold the text
        self._journal(journal, name, item, "completed", run_id=run_id)
        return PURGE_COMPLETED, None

    def _residue(self) -> Residue | None:
        """Why the data directory may still hold deleted text, read after the rewrite and the snapshot have both finished;
        None only when it holds the current snapshot and AOF set alone (Codex CP2 review 1, finding 2)."""
        if self._inventory is None:
            return Residue("file_inventory_unavailable", ())
        self._on_time()
        try:
            return residue(self._inventory(max(1.0, min(10.0, self._remaining()))))
        except InventoryUnavailable:
            return Residue("file_inventory_unavailable", ())

    def _need_journal(self) -> PurgeJournal:
        if self._purge_journal is None:
            raise msc.MemoryRequestError("MEMORY_JOURNAL_UNAVAILABLE", 503)
        return self._purge_journal

    @staticmethod
    def _journal(journal: PurgeJournal, name: str, item: str, phase: str, **facts: Any) -> None:
        try:
            journal.record(name, item, phase, **facts)
        except JournalError as refusal:
            raise msc.MemoryRequestError(refusal.code, 503) from None

    @staticmethod
    def _entries(journal: PurgeJournal, name: str, item: str) -> list[dict[str, Any]]:
        try:
            return journal.entries(name, item)
        except JournalError as refusal:
            raise msc.MemoryRequestError(refusal.code, 503) from None

    def _seal(self, project: str, scope: str, after: str) -> str:
        data = base64.urlsafe_b64encode(after.encode()).decode()
        tag = hmac.new(self._cursor_key, f"{project}\n{scope}\n{data}".encode(), hashlib.sha256).hexdigest()
        return f"{data}.{tag}"

    def _unseal(self, project: str, scope: str, cursor: str) -> str:
        data, _, tag = cursor.partition(".")
        expected = hmac.new(self._cursor_key, f"{project}\n{scope}\n{data}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(tag, expected):
            raise msc.MemoryRequestError("CURSOR_INVALID")
        return base64.urlsafe_b64decode(data.encode()).decode()


class MemoryStoreService:
    """Bounded admission in front of the store: two serving workers and a short queue. A full queue is refused at once.

    The store is checked before it first serves and again after an outage, because the Gateway may start before the container
    is up and must keep serving models meanwhile."""

    @staticmethod
    def _late(deadline: float) -> tuple[int, dict[str, str]] | None:
        """After the deadline every outcome is a timeout, whatever the operation made of the failure: the caller must treat
        anything it sent as uncertain."""
        return (503, msc.error_body("MEMORY_TIMEOUT")) if time.monotonic() >= deadline else None

    def __init__(self, store: MemoryStore, *, verify: Callable[[float], None] | None = None) -> None:
        self._store = store
        self._verify = verify
        self._verified = verify is None
        self._workers = threading.BoundedSemaphore(msc.SERVING_WORKERS)
        self._waiting = threading.BoundedSemaphore(msc.QUEUE_DEPTH)

    def handle(self, raw_body: bytes, *, deadline: float) -> tuple[int, dict[str, Any]]:
        if not self._waiting.acquire(blocking=False):
            return 503, msc.error_body("MEMORY_BUSY")
        try:
            if not self._workers.acquire(timeout=max(0.0, deadline - time.monotonic())):
                return 503, msc.error_body("MEMORY_BUSY")
        finally:
            self._waiting.release()
        try:
            if time.monotonic() >= deadline:
                return 503, msc.error_body("MEMORY_TIMEOUT")
            request = msc.parse_request(raw_body)
            if request["op"] in msc.UNAVAILABLE:  # answered before verification, which would connect and write
                return self._late(deadline) or (501, msc.error_body("MEMORY_OPERATION_UNAVAILABLE"))
            if not self._verified or self._store.suspect:
                if self._verify is None:
                    raise msc.MemoryRequestError("MEMORY_UNAVAILABLE", 503)
                try:
                    self._verify(deadline)
                except MemoryStoreStartupError as refusal:
                    return self._late(deadline) or (503, msc.error_body(refusal.code))
                self._verified = True
            result = self._store.dispatch(request, deadline=deadline)
            if time.monotonic() >= deadline:  # a late answer is not a success
                return 503, msc.error_body("MEMORY_TIMEOUT")
            return 200, result
        except msc.MemoryRequestError as refusal:
            return self._late(deadline) or (refusal.status, msc.error_body(refusal.code))
        except (RedisConnectionError, TimeoutError, OSError):
            self._verified = self._verify is None  # whatever comes back on this port has to prove itself again
            self._store.connection_lost()  # and nothing cached from before the outage is trusted: it may hold writes Redis lost
            return self._late(deadline) or (503, msc.error_body("MEMORY_UNAVAILABLE"))
        except Exception:  # noqa: BLE001 - a malformed entry or any other fault is a stable code, never a dropped connection
            self._store.forget()
            return self._late(deadline) or (503, msc.error_body("MEMORY_STORAGE_ERROR"))
        finally:
            self._workers.release()


def build_memory_store_service(config: MemoryStoreConfig, *, keyring_backend: Any, hmac_key: bytes,
                               journal_root: Path | None = None,
                               inventory: Callable[[float], Inventory] | None = None) -> MemoryStoreService:
    """The service for the approved configuration. Nothing connects until the first request. A missing password serves a
    stable refusal, so the Agent Panel can say setup is incomplete while models keep working. The purge journal lives under
    `journal_root`, outside the Redis volume; without one (or without a password) purge is refused. A purge's disk step ends
    only once `inventory` (by default, the provisioned container's data directory read through Docker) shows no old file."""
    try:
        password = keyring_backend.get_password(KEYRING_SERVICE, config.credential_name)
    except Exception:  # noqa: BLE001 - any backend failure means the same thing here: no usable credential
        password = None
    endpoint = MemoryStoreEndpoint(config.host, config.port, config.user, password or "", config.resource)
    cursor_key = hashlib.sha256(b"optimus-memory-store-cursor-v1\0" + hmac_key).digest()
    journal = PurgeJournal(journal_root, journal_key(password)) if journal_root is not None and password else None
    store = MemoryStore(connect(endpoint), connect(endpoint), admission_ceiling_mb=config.admission_ceiling_mb, cursor_key=cursor_key,
                        journal=journal, inventory=inventory or docker_inventory(config),
                        recovery_key=recovery_key(password) if password else None)

    def verify(deadline: float) -> None:
        if not password:
            raise MemoryStoreStartupError("MEMORY_STORE_CREDENTIAL_MISSING")
        try:
            store.verify(config.resource, deadline=deadline)
        except msc.MemoryRequestError as refusal:
            raise MemoryStoreStartupError(refusal.code) from None

    return MemoryStoreService(store, verify=verify)
