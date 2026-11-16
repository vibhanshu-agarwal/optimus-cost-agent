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
from typing import Any, Final

import redis
from redis.backoff import NoBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError, ResponseError, TimeoutError, WatchError
from redis.retry import Retry

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
    pool = redis.BlockingConnectionPool(max_connections=1, timeout=msc.DEADLINE_SECONDS, retry=Retry(NoBackoff(), 0),
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
    client.connection_pool.timeout = max(0.0, seconds)  # a checkout waits for the pool's one connection only for what is left
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


class _Fold:
    """What one project's stream says up to `head`: each item's latest event, the idempotency keys and event ids already used,
    and the checkpoints in stream order. Rebuilt from the stream alone, so it is a cache, never a source of truth."""

    def __init__(self) -> None:
        self.head = "0-0"
        self.items: dict[str, dict[str, Any]] = {}
        self.keys: dict[str, tuple[str, dict[str, Any]]] = {}
        self.event_ids: set[str] = set()
        self.checkpoints: list[dict[str, Any]] = []

    def apply(self, stream_id: str, record: dict[str, Any]) -> None:
        if record["type"] == "event":
            self.items[record["event"]["item"]] = {**record["event"], "stream_id": stream_id}
            self.event_ids.add(record["event"]["event_id"])
        else:
            self.checkpoints.append({**record["checkpoint"], "stream_id": stream_id})
        self.keys[record["key"]] = (record["digest"], _result(stream_id, record))
        self.head = stream_id

    def advance(self, reader: Any, stream: str, target: str, on_time: Callable[[], None] = lambda: None) -> None:
        while _order(self.head) < _order(target):
            on_time()
            entries = reader.xrange(stream, min=f"({self.head}", max=target, count=_FOLD_PAGE)
            if not entries:
                raise RedisError("stream shorter than its head")  # never serve a fold that skipped events
            for raw_id, fields in entries:
                self.apply(_text(raw_id), json.loads(fields[b"e"]))


def _order(stream_id: str) -> tuple[int, int]:
    ms, _, seq = stream_id.partition("-")
    return int(ms), int(seq)


def _result(stream_id: str, record: dict[str, Any]) -> dict[str, Any]:
    if record["type"] == "event":
        return {"item": record["event"]["item"], "version": record["event"]["version"], "event_id": record["event"]["event_id"],
                "stream_id": stream_id}
    return {"session": record["checkpoint"]["session"], "sequence": record["checkpoint"]["sequence"], "stream_id": stream_id}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


class MemoryStore:
    """One Gateway's view of the dedicated instance. Every method raises `msc.MemoryRequestError` for a refusal.

    Writes go through one connection, held under a lock with retries off, so `WAITAOF` answers for the very connection that
    appended; `CLIENT ID` before and after proves no reconnect came between. Reads use a second connection under their own lock
    and see only the confirmed watermark. A lost or replaced connection makes the store suspect: every operation is refused until
    `verify` shows the resource is still the provisioned one."""

    def __init__(self, client: redis.Redis, writer: redis.Redis, *, admission_ceiling_mb: int, cursor_key: bytes) -> None:
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
        if int(self._writer.client_id()) != connection:
            self._connection_lost()
            raise msc.MemoryRequestError("MEMORY_UNAVAILABLE", 503)

    @staticmethod
    def _key(project: str, name: str) -> str:
        return f"{_PREFIX}:p:{hashlib.sha256(project.encode()).hexdigest()[:32]}:{name}"

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
                with self._writer.pipeline() as pipe:
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
    def _writing(self, *, verifying: bool = False) -> Iterator[None]:
        """The writer, for the rest of the request's budget. A store under suspicion refuses, so a request queued behind the
        one that lost the connection cannot write to an unverified replacement."""
        self._on_time()
        if not self._write_lock.acquire(timeout=max(0.0, self._remaining())):
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
        record = {"type": "event", "key": body["idempotency_key"], "digest": _digest([body["expected_version"], event]),
                  "event": event}
        return self._append(body["project"], body["token"], record, expected=body["expected_version"], gated=gated)

    def _op_checkpoint(self, body: dict[str, Any]) -> dict[str, Any]:
        point = body["checkpoint"]
        record = {"type": "checkpoint", "key": f"checkpoint:{point['session']}:{point['sequence']}", "digest": _digest(point),
                  "checkpoint": point}
        return self._append(body["project"], body["token"], record, expected=None)

    def _append(self, project: str, token: int, record: dict[str, Any], *, expected: int | None, gated: bool = False) -> dict[str, Any]:
        stream, lease = self._key(project, "events"), self._key(project, "lease")
        with self._writing():
            fold = self._writer_folds.setdefault(project, _Fold())
            connection = int(self._writer.client_id())
            self._check_links()  # the baseline connection is the verified one, not one the pool re-established just now
            for _ in range(_WATCH_ATTEMPTS):
                replay_at = None
                with self._writer.pipeline() as pipe:  # a watching pipeline holds the writer's only connection until it closes
                    try:
                        pipe.watch(lease, stream)
                        if _text(pipe.get(lease) or b"").split(":", 1)[0] != str(token):
                            pipe.unwatch()
                            raise msc.MemoryRequestError("LEASE_LOST", 409)
                        newest = pipe.xrevrange(stream, count=1)
                        head = _text(newest[0][0]) if newest else "0-0"
                        if _order(head) < _order(fold.head):
                            fold = self._writer_folds[project] = _Fold()  # the stream went back: rebuild, never trust the cache
                        fold.advance(pipe, stream, head, self._on_time)
                        if record["key"] in fold.keys:
                            pipe.unwatch()
                            replay_at = head
                        elif gated and (self._fsync_failed or self._used() >= self._ceiling_bytes):
                            pipe.unwatch()
                            raise msc.MemoryRequestError("MEMORY_NOT_ADMITTING", 503)
                        else:
                            self._check(fold, record, expected)
                            self._on_time()  # past the deadline nothing is appended; once EXEC is sent the outcome may be uncertain
                            pipe.multi()
                            pipe.xadd(stream, {"e": json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)})
                            stream_id = _text(pipe.execute()[0])
                    except WatchError:
                        self._after_watch_error(connection)
                        continue
                if replay_at is not None:
                    return self._replay(project, fold, record, replay_at, connection)
                fold.apply(stream_id, record)
                return {"status": "ok", **_result(stream_id, record), **self._confirm(project, stream_id, connection)}
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

    def _replay(self, project: str, fold: _Fold, record: dict[str, Any], head: str, connection: int) -> dict[str, Any]:
        """A retry of the same change returns the first one's result once it is on disk; a different change under that key is a
        conflict. Nothing is appended twice."""
        digest, result = fold.keys[record["key"]]
        if digest != record["digest"]:
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
                with self._writer.pipeline() as pipe:
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
        """Answer from the confirmed fold while holding the read lock: another request may advance the same fold."""
        with self._reading():
            fold = self._serving_folds.setdefault(project, _Fold())
            watermark = _text(self._redis.get(self._key(project, "durable")) or b"0-0")
            if _order(watermark) < _order(fold.head):
                fold = self._serving_folds[project] = _Fold()
            fold.advance(self._redis, self._key(project, "events"), watermark, self._on_time)
            self._check_links()  # nothing read from a connection re-established since verification is served
            return answer(fold)

    def _op_read(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._served(body["project"], lambda fold: {"status": "ok", "item": fold.items.get(body["item"])})

    def _op_list(self, body: dict[str, Any]) -> dict[str, Any]:
        """Confirmed items in one scope, in item-id order, as many as fit the reply bound. A cursor is sealed to its project and scope."""
        after = self._unseal(body["project"], body["scope"], body["cursor"]) if "cursor" in body else ""

        def page(fold: _Fold) -> dict[str, Any]:
            ids = sorted(item for item, record in fold.items.items() if record["scope"] == body["scope"] and item > after)
            items: list[dict[str, Any]] = []
            size = _LIST_ENVELOPE_BYTES
            for item in ids[: body["limit"]]:
                size += len(json.dumps(fold.items[item], ensure_ascii=True)) + 1
                if items and size > msc.MAX_RESPONSE_BYTES:
                    break
                items.append(fold.items[item])
            cursor = self._seal(body["project"], body["scope"], items[-1]["item"]) if len(ids) > len(items) else None
            return {"status": "ok", "items": items, "cursor": cursor}

        return self._served(body["project"], page)

    def _op_checkpoints(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._served(body["project"], lambda fold: {"status": "ok", "checkpoints": fold.checkpoints[-body["limit"]:][::-1]})

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
                return 501, msc.error_body("MEMORY_OPERATION_UNAVAILABLE")
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


def build_memory_store_service(config: MemoryStoreConfig, *, keyring_backend: Any, hmac_key: bytes) -> MemoryStoreService:
    """The service for the approved configuration. Nothing connects until the first request. A missing password serves a
    stable refusal, so the Agent Panel can say setup is incomplete while models keep working."""
    try:
        password = keyring_backend.get_password(KEYRING_SERVICE, config.credential_name)
    except Exception:  # noqa: BLE001 - any backend failure means the same thing here: no usable credential
        password = None
    endpoint = MemoryStoreEndpoint(config.host, config.port, config.user, password or "", config.resource)
    cursor_key = hashlib.sha256(b"optimus-memory-store-cursor-v1\0" + hmac_key).digest()
    store = MemoryStore(connect(endpoint), connect(endpoint), admission_ceiling_mb=config.admission_ceiling_mb, cursor_key=cursor_key)

    def verify(deadline: float) -> None:
        if not password:
            raise MemoryStoreStartupError("MEMORY_STORE_CREDENTIAL_MISSING")
        try:
            store.verify(config.resource, deadline=deadline)
        except msc.MemoryRequestError as refusal:
            raise MemoryStoreStartupError(refusal.code) from None

    return MemoryStoreService(store, verify=verify)
