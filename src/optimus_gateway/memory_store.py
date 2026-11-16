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


def connect(endpoint: MemoryStoreEndpoint, *, writer: bool = False) -> redis.Redis:
    """The serving pool, or with `writer` the single connection every append uses: retries off, so a dropped socket is an
    error and never a silent reconnect that `WAITAOF` would then answer for."""
    settings: dict[str, Any] = {"host": endpoint.host, "port": endpoint.port, "username": endpoint.username,
                                "password": endpoint.password, "socket_timeout": msc.DEADLINE_SECONDS,
                                "socket_connect_timeout": 2.0, "protocol": 2}
    if writer:
        pool = redis.BlockingConnectionPool(max_connections=1, timeout=msc.DEADLINE_SECONDS, retry=Retry(NoBackoff(), 0), **settings)
        return redis.Redis(connection_pool=pool)
    return redis.Redis(max_connections=msc.SERVING_WORKERS + 2, decode_responses=False, retry=Retry(NoBackoff(), 0), **settings)


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


def verify_resource(client: redis.Redis, resource: str) -> None:
    """Before serving: authentication works, persistence and eviction are as provisioned, `WAITAOF` confirms a local fsync, and
    this is the instance setup provisioned rather than whatever now holds the port."""
    try:
        persistence = client.info("persistence")
        memory = client.info("memory")
        stored = client.get(_RESOURCE_KEY)
    except (RedisError, OSError) as exc:
        raise MemoryStoreStartupError("MEMORY_STORE_UNREACHABLE") from exc
    if not persistence.get("aof_enabled") or memory.get("maxmemory_policy") != "noeviction":
        raise MemoryStoreStartupError("MEMORY_STORE_CONFIGURATION_UNEXPECTED")
    try:
        if stored is None:
            if client.dbsize() != 0:  # never adopt data nobody can vouch for
                raise MemoryStoreStartupError("MEMORY_STORE_UNIDENTIFIED_DATA")
            client.set(_RESOURCE_KEY, resource, nx=True)
            stored = client.get(_RESOURCE_KEY)  # a concurrent Gateway may have marked it first; either way it must be ours
        if stored is None or _text(stored) != resource:
            raise MemoryStoreStartupError("MEMORY_STORE_RESOURCE_MISMATCH")
        if fsync_probe(client, timeout_ms=_WAITAOF_PROBE_MS) < 1:
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
    appended; `CLIENT ID` before and after proves no reconnect came between. Reads use the pool and see only the confirmed
    watermark."""

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
        if self._remaining() <= 0:
            raise msc.MemoryRequestError("MEMORY_TIMEOUT", 503)

    def take_suspect(self) -> bool:
        """Whether a connection was lost or replaced since the last call; the service then re-verifies the resource."""
        suspect, self._suspect = self._suspect, False
        return suspect

    def _connection_lost(self) -> None:
        self.forget()
        self._suspect = True

    def _after_watch_error(self, connection: int) -> int:
        """A WatchError is either another writer or redis-py reporting a lost connection. A new connection id means the latter:
        nothing cached is trusted, and later confirmation is checked against the new connection."""
        current = int(self._writer.client_id())
        if current != connection:
            self._connection_lost()
        return current

    @staticmethod
    def _key(project: str, name: str) -> str:
        return f"{_PREFIX}:p:{hashlib.sha256(project.encode()).hexdigest()[:32]}:{name}"

    def _used(self) -> int:
        return int(self._redis.info("memory").get("used_memory", 0))

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
                        connection = self._after_watch_error(connection)
                        continue
                if not token:
                    return {"status": "ok"}
                if not self._durable(connection):
                    raise msc.MemoryRequestError("LEASE_UNCONFIRMED", 503)
                return {"status": "ok", "token": token}
            raise msc.MemoryRequestError("LEASE_CONTENDED", 409)

    @contextlib.contextmanager
    def _writing(self) -> Iterator[None]:
        self._on_time()
        if not self._write_lock.acquire(timeout=max(0.0, self._remaining())):
            raise msc.MemoryRequestError("MEMORY_BUSY", 503)
        try:
            yield
        finally:
            self._write_lock.release()

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
                        connection = self._after_watch_error(connection)
                        fold = self._writer_folds.setdefault(project, _Fold())
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
        budget = min(_WAITAOF_COMMIT_MS, int(self._remaining() * 1000))
        if budget <= 0:
            return False
        try:
            count = waitaof_local(self._writer, timeout_ms=budget)
            same = int(self._writer.client_id()) == connection
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
        self._advance_watermark(project, stream_id, connection)
        # confirmed on disk either way; "current" only once the watermark this Gateway serves from includes it
        current = _order(_text(self._redis.get(self._key(project, "durable")) or b"0-0")) >= _order(stream_id)
        return {"durable_state": "confirmed", "projection_state": "current" if current else "pending"}

    def _recheck_fsync(self) -> None:
        if self._fsync_failed and self._write_lock.acquire(timeout=msc.DEADLINE_SECONDS):
            try:
                self._fsync_failed = fsync_probe(self._writer, timeout_ms=_WAITAOF_COMMIT_MS) < 1
            except (RedisError, OSError, MemoryStoreStartupError):
                self._fsync_failed = True
            finally:
                self._write_lock.release()

    def _advance_watermark(self, project: str, stream_id: str, connection: int) -> None:
        """AOF is ordered, so a confirmed event confirms every one before it. The watermark only moves forward."""
        key = self._key(project, "durable")
        for _ in range(_WATCH_ATTEMPTS):
            with self._writer.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    current = pipe.get(key)
                    if current is not None and _order(_text(current)) >= _order(stream_id):
                        pipe.unwatch()
                        return
                    pipe.multi()
                    pipe.set(key, stream_id)
                    pipe.execute()
                    return
                except WatchError:
                    if int(self._writer.client_id()) != connection:
                        self._connection_lost()
                        return
                    continue
        # shortcut: a contended watermark stays behind until the next confirmed write moves it; nothing unconfirmed is served

    # --- serving -------------------------------------------------------------------------------------------------------

    def _served(self, project: str, answer: Callable[[_Fold], dict[str, Any]]) -> dict[str, Any]:
        """Answer from the confirmed fold while holding the read lock: another request may advance the same fold."""
        with self._read_lock:
            fold = self._serving_folds.setdefault(project, _Fold())
            watermark = _text(self._redis.get(self._key(project, "durable")) or b"0-0")
            if _order(watermark) < _order(fold.head):
                fold = self._serving_folds[project] = _Fold()
            fold.advance(self._redis, self._key(project, "events"), watermark, self._on_time)
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

    def __init__(self, store: MemoryStore, *, verify: Callable[[], None] | None = None) -> None:
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
            if not self._verified and self._verify is not None:
                try:
                    self._verify()
                except MemoryStoreStartupError as refusal:
                    return 503, msc.error_body(refusal.code)
                self._verified = True
            result = self._store.dispatch(request, deadline=deadline)
            if time.monotonic() >= deadline:  # a late answer is not a success
                return 503, msc.error_body("MEMORY_TIMEOUT")
            return 200, result
        except msc.MemoryRequestError as refusal:
            return refusal.status, msc.error_body(refusal.code)
        except (RedisConnectionError, TimeoutError, OSError):
            self._verified = self._verify is None  # whatever comes back on this port has to prove itself again
            self._store.forget()  # and nothing cached from before the outage is trusted: it may hold writes Redis lost
            return 503, msc.error_body("MEMORY_UNAVAILABLE")
        except Exception:  # noqa: BLE001 - a malformed entry or any other fault is a stable code, never a dropped connection
            self._store.forget()
            return 503, msc.error_body("MEMORY_STORAGE_ERROR")
        finally:
            if self._store.take_suspect():
                self._verified = self._verify is None  # a lost connection makes the resource prove itself before the next request
            self._workers.release()


def build_memory_store_service(config: MemoryStoreConfig, *, keyring_backend: Any, hmac_key: bytes) -> MemoryStoreService:
    """The service for the approved configuration. Nothing connects until the first request. A missing password serves a
    stable refusal, so the Agent Panel can say setup is incomplete while models keep working."""
    try:
        password = keyring_backend.get_password(KEYRING_SERVICE, config.credential_name)
    except Exception:  # noqa: BLE001 - any backend failure means the same thing here: no usable credential
        password = None
    endpoint = MemoryStoreEndpoint(config.host, config.port, config.user, password or "", config.resource)
    client = connect(endpoint)
    cursor_key = hashlib.sha256(b"optimus-memory-store-cursor-v1\0" + hmac_key).digest()

    def verify() -> None:
        if not password:
            raise MemoryStoreStartupError("MEMORY_STORE_CREDENTIAL_MISSING")
        verify_resource(client, config.resource)

    store = MemoryStore(client, connect(endpoint, writer=True), admission_ceiling_mb=config.admission_ceiling_mb, cursor_key=cursor_key)
    return MemoryStoreService(store, verify=verify)
