"""The Gateway's context-index store and handler (Plan 12.10 Task 2; ADR-037), on a dedicated Redis.

A scope is one line of the index: project, worktree, branch and versions, as the trusted host asserts them. Inside it,
records carry the epoch that added them and the epoch that removed them, and a reader sees exactly the records live at one
published epoch, so a publish is atomic and a half-written epoch is invisible. Writers hold a fenced lease; every write checks
the fence under WATCH, so a writer that lost its lease cannot change anything. A replayed batch rewrites the same keys.

The data is rebuildable and holds no source bodies (B1): identifiers, signatures, structural descriptions, allowed
documentation prose, paths, hashes, vectors. Admission is bounded, so index traffic waits or is refused and never holds a
model or capture request.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError, ResponseError, TimeoutError, WatchError

from optimus_security import memory_index_contract as mic
from optimus_security.memory_index_config import KEYRING_SERVICE, MemoryIndexConfig

_PREFIX: Final = "oidx"
_RECORD_PREFIX: Final = f"{_PREFIX}:rec:"
_COLD_SLOT: Final = f"{_PREFIX}:lease:cold"
_WATCH_ATTEMPTS: Final = 3
_CLEANUP_STEP: Final = 512
_SEARCH_FIELDS: Final = ("path", "path_id", "file_hash", "kind", "language", "symbol", "signature", "description", "prose",
                         "start_line", "end_line", "modified", "epoch_added")
_INT_FIELDS: Final = frozenset({"start_line", "end_line", "modified", "epoch_added"})


class IndexUnavailableError(RuntimeError):
    """Redis cannot serve the route. The model and capture routes do not depend on it."""


class IndexStartupError(RuntimeError):
    """The configured Redis is not the approved dedicated resource. `code` is stable and carries no secret."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class IndexEndpoint:
    host: str
    port: int
    username: str
    password: str
    resource: str  # the nonsecret identity this instance was provisioned as

    def __repr__(self) -> str:
        return f"IndexEndpoint(host={self.host!r}, port={self.port}, username={self.username!r}, password='<redacted>')"


def connect(endpoint: IndexEndpoint) -> redis.Redis:
    return redis.Redis(host=endpoint.host, port=endpoint.port, username=endpoint.username, password=endpoint.password,
                       socket_timeout=mic.DEADLINE_SECONDS, socket_connect_timeout=2.0, max_connections=mic.SERVING_WORKERS + 2,
                       decode_responses=False, protocol=2)


def verify_resource(client: redis.Redis, resource: str) -> None:
    """Before serving: authentication works, Search is loaded, persistence and eviction are as provisioned, and this is
    the instance setup provisioned rather than whatever now holds the port."""
    try:
        modules = {_text(module.get(b"name", b"")) for module in client.module_list()}
        persistence = client.info("persistence")
        memory = client.info("memory")
        stored = client.get(f"{_PREFIX}:resource")
    except (RedisError, OSError) as exc:
        raise IndexStartupError("INDEX_REDIS_UNREACHABLE") from exc
    if "search" not in modules:
        raise IndexStartupError("INDEX_REDIS_MODULES_MISSING")
    if not persistence.get("aof_enabled") or memory.get("maxmemory_policy") != "noeviction":
        raise IndexStartupError("INDEX_REDIS_CONFIGURATION_UNEXPECTED")
    if stored is None:
        try:
            client.set(f"{_PREFIX}:resource", resource, nx=True)
        except RedisError as exc:
            raise IndexStartupError("INDEX_REDIS_UNREACHABLE") from exc
    elif _text(stored) != resource:
        raise IndexStartupError("INDEX_REDIS_RESOURCE_MISMATCH")


def _text(value: Any) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def _escape_tag(value: str) -> str:
    return "".join(f"\\{c}" if not c.isalnum() else c for c in value)


class IndexStore:
    """One Gateway's view of the dedicated instance. Every method raises `mic.IndexRequestError` for a refusal."""

    def __init__(self, client: redis.Redis, *, cursor_key: bytes) -> None:
        self._redis = client
        self._cursor_key = cursor_key
        self._created_indexes: set[int] = set()
        self._lock = threading.Lock()

    def dispatch(self, body: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_op_{body['op']}")
        result: dict[str, Any] = handler(body["scope"], body)
        return result

    # --- line and generation -------------------------------------------------------------------------------------------

    def _line(self, scope: str) -> dict[str, str]:
        line = self._redis.hgetall(f"{_PREFIX}:line:{scope}")
        if not line:
            raise mic.IndexRequestError("SCOPE_UNKNOWN", 404)
        return {_text(key): _text(value) for key, value in line.items()}

    def _ensure_search_index(self, dimensions: int) -> None:
        with self._lock:
            if dimensions in self._created_indexes:
                return
            name = f"{_PREFIX}:idx:{dimensions}"
            try:
                self._redis.execute_command(
                    "FT.CREATE", name, "ON", "HASH", "PREFIX", "1", f"{_RECORD_PREFIX}{dimensions}:", "STOPWORDS", "0", "SCHEMA",
                    "scope", "TAG", "kind", "TAG", "path_id", "TAG", "symbol_id", "TAG",
                    "epoch_added", "NUMERIC", "epoch_removed", "NUMERIC",
                    "terms", "TEXT", "NOSTEM",
                    "vec", "VECTOR", "FLAT", "6", "TYPE", "FLOAT32", "DIM", str(dimensions), "DISTANCE_METRIC", "COSINE",
                )
            except ResponseError as exc:
                if "already exists" not in str(exc).lower():
                    raise
            self._created_indexes.add(dimensions)

    def _op_generation(self, scope: str, body: dict[str, Any]) -> dict[str, Any]:
        action = body["action"]
        if action == "open":
            return self._open(scope, body)
        if action == "begin":
            return self._fenced(scope, body["token"], lambda pipe, line: self._begin(scope, pipe, line))
        return self._publish(scope, body)

    def _open(self, scope: str, body: dict[str, Any]) -> dict[str, Any]:
        key = f"{_PREFIX}:line:{scope}"
        wanted = {"embedding": body["embedding"], "dimensions": str(body["dimensions"]), "schema_version": str(body["schema_version"])}
        self._ensure_search_index(body["dimensions"])
        for field, value in wanted.items():
            self._redis.hsetnx(key, field, value)
        self._redis.sadd(f"{_PREFIX}:lines", scope)
        line = self._line(scope)
        if any(line.get(field) != value for field, value in wanted.items()):
            raise mic.IndexRequestError("SCOPE_CONFIGURATION_MISMATCH", 409)
        return {"status": "ok", "current": self._current(scope)}

    def _begin(self, scope: str, pipe: Any, line: dict[str, str]) -> dict[str, Any]:
        building = line.get("building")
        if building:
            return {"status": "ok", "epoch": int(building)}
        raw = pipe.get(f"{_PREFIX}:current:{scope}")
        published = json.loads(raw)["epoch"] if raw else 0
        epoch = published + 1
        pipe.multi()
        pipe.hset(f"{_PREFIX}:line:{scope}", "building", str(epoch))
        return {"status": "ok", "epoch": epoch}

    def _publish(self, scope: str, body: dict[str, Any]) -> dict[str, Any]:
        def publish(pipe: Any, line: dict[str, str]) -> dict[str, Any]:
            if line.get("building") != str(body["epoch"]):
                raise mic.IndexRequestError("EPOCH_NOT_BUILDING", 409)
            current = {"epoch": body["epoch"], "revision": body["revision"], "dirty": body["dirty"], "coverage": body["coverage"]}
            pipe.multi()
            pipe.set(f"{_PREFIX}:current:{scope}", json.dumps(current, sort_keys=True))
            pipe.hdel(f"{_PREFIX}:line:{scope}", "building")
            return {"status": "ok", "current": current}

        return self._fenced(scope, body["token"], publish)

    def _current(self, scope: str) -> dict[str, Any] | None:
        raw = self._redis.get(f"{_PREFIX}:current:{scope}")
        return json.loads(raw) if raw else None

    def _op_coverage(self, scope: str, _body: dict[str, Any]) -> dict[str, Any]:
        line = self._line(scope)
        return {"status": "ok", "current": self._current(scope), "building": int(line["building"]) if "building" in line else None}

    # --- leases --------------------------------------------------------------------------------------------------------

    def _lease_key(self, scope: str, kind: str) -> str:
        return _COLD_SLOT if kind == "cold" else f"{_PREFIX}:lease:{scope}"

    def _op_lease(self, scope: str, body: dict[str, Any]) -> dict[str, Any]:
        key, owner = self._lease_key(scope, body["kind"]), body["owner"]
        if body["action"] == "acquire":
            token = self._redis.incr(f"{_PREFIX}:fence")
            if self._redis.set(key, f"{token}:{owner}", nx=True, px=body["ttl_ms"]):
                return {"status": "ok", "token": token}
            raw = self._redis.get(key)
            if raw and _text(raw).split(":", 1)[1] == owner:  # the same owner resuming takes a new fence and retires its old one
                self._redis.set(key, f"{token}:{owner}", px=body["ttl_ms"])
                return {"status": "ok", "token": token}
            raise mic.IndexRequestError("LEASE_HELD", 409)
        expected = f"{body['token']}:{owner}"
        for _ in range(_WATCH_ATTEMPTS):
            with self._redis.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    if _text(pipe.get(key) or b"") != expected:
                        pipe.unwatch()
                        raise mic.IndexRequestError("LEASE_LOST", 409)
                    pipe.multi()
                    if body["action"] == "renew":
                        pipe.pexpire(key, body["ttl_ms"])
                    else:
                        pipe.delete(key)
                    pipe.execute()
                    return {"status": "ok"}
                except WatchError:
                    continue
        raise mic.IndexRequestError("LEASE_CONTENDED", 409)

    def _fenced(self, scope: str, token: int, build: Any) -> dict[str, Any]:
        """Run `build(pipe, line)` so its writes commit only if this writer still holds the scope's lease."""
        key = self._lease_key(scope, "scope")
        for _ in range(_WATCH_ATTEMPTS):
            with self._redis.pipeline() as pipe:
                try:
                    pipe.watch(key, f"{_PREFIX}:line:{scope}")
                    held = _text(pipe.get(key) or b"")
                    if held.split(":", 1)[0] != str(token):
                        pipe.unwatch()
                        raise mic.IndexRequestError("LEASE_LOST", 409)
                    line = {_text(k): _text(v) for k, v in pipe.hgetall(f"{_PREFIX}:line:{scope}").items()}
                    if not line:
                        pipe.unwatch()
                        raise mic.IndexRequestError("SCOPE_UNKNOWN", 404)
                    result = build(pipe, line)
                    if pipe.explicit_transaction:
                        pipe.execute()
                    else:
                        pipe.unwatch()
                    return result  # type: ignore[no-any-return]
                except WatchError:
                    continue
        raise mic.IndexRequestError("LEASE_CONTENDED", 409)

    # --- writes --------------------------------------------------------------------------------------------------------

    def _op_batch(self, scope: str, body: dict[str, Any]) -> dict[str, Any]:
        epoch = body["epoch"]
        removals = body.get("removals", [])

        def write(pipe: Any, line: dict[str, str]) -> dict[str, Any]:
            if line.get("building") != str(epoch):
                raise mic.IndexRequestError("EPOCH_NOT_BUILDING", 409)
            dimensions = int(line["dimensions"])
            # Decoding before MULTI: a bad vector refuses the whole batch with nothing written.
            encoded = [(record, self._mapping(scope, dimensions, epoch, record)) for record in body["records"]]
            removed: list[str] = []
            abandoned: list[tuple[str, str]] = []
            for removal in removals:
                path_id = removal["path_id"]
                for raw in pipe.smembers(f"{_PREFIX}:members:{scope}:{path_id}"):
                    added, file_hash = pipe.hmget(_text(raw), "epoch_added", "file_hash")
                    if added is None:
                        continue
                    if int(added) < epoch:  # a reader pinned to an earlier epoch still needs it
                        removed.append(_text(raw))
                    elif _text(file_hash) != removal.get("keep_hash"):  # this epoch's own leftover: no reader ever saw it
                        abandoned.append((_text(raw), path_id))
            pipe.multi()
            for key in removed:
                pipe.hset(key, "epoch_removed", str(epoch))
            for key, path_id in abandoned:
                pipe.delete(key)
                pipe.srem(f"{_PREFIX}:members:{scope}:{path_id}", key)
            for record, mapping in encoded:
                key = self._record_key(scope, dimensions, epoch, record["id"])
                pipe.hset(key, mapping=mapping)
                pipe.sadd(f"{_PREFIX}:members:{scope}:{record['path_id']}", key)
                pipe.zadd(f"{_PREFIX}:files:{scope}", {record["path_id"]: 0})
            return {"status": "ok", "written": len(encoded), "removed": len(removed) + len(abandoned)}

        return self._fenced(scope, body["token"], write)

    @staticmethod
    def _record_key(scope: str, dimensions: int, epoch: int, record_id: str) -> str:
        return f"{_RECORD_PREFIX}{dimensions}:{scope}:{epoch}:{record_id}"

    @staticmethod
    def _mapping(scope: str, dimensions: int, epoch: int, record: dict[str, Any]) -> dict[str, Any]:
        mapping: dict[str, Any] = {key: record[key] for key in ("kind", "path", "path_id", "file_hash", "language", "terms")}
        for field in ("symbol", "signature", "description", "prose", "start_line", "end_line", "modified"):
            if field in record:
                mapping[field] = record[field]
        if "symbol" in record:
            mapping["symbol_id"] = hashlib.sha256(record["symbol"].encode("utf-8")).hexdigest()
        if "vector" in record:
            mapping["vec"] = mic.decode_vector(record["vector"], dimensions)
        mapping.update(scope=scope, epoch_added=epoch, epoch_removed=mic.NEVER_REMOVED)
        return mapping

    # --- reads ---------------------------------------------------------------------------------------------------------

    def _visible_epoch(self, scope: str, body: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
        """A reader names an epoch it is pinned to, or takes the published one. Nothing unpublished is ever the default."""
        current = self._current(scope)
        if "epoch" in body:
            return body["epoch"], current
        if current is None:
            raise mic.IndexRequestError("NOT_PUBLISHED", 404)
        return current["epoch"], current

    def _op_query(self, scope: str, body: dict[str, Any]) -> dict[str, Any]:
        line = self._line(scope)
        dimensions = int(line["dimensions"])
        epoch, current = self._visible_epoch(scope, body)
        if current is None or epoch > current["epoch"]:  # a building epoch is its writer's alone, and only through the catalogue
            raise mic.IndexRequestError("NOT_PUBLISHED", 404)
        live = f"@scope:{{{scope}}} @epoch_added:[-inf {epoch}] @epoch_removed:[({epoch} +inf]"
        kinds = body.get("kinds")
        if kinds:
            live += " @kind:{" + "|".join(kinds) + "}"
        mode, k = body["mode"], body["k"]
        name = f"{_PREFIX}:idx:{dimensions}"
        returned = [str(len(_SEARCH_FIELDS)), *_SEARCH_FIELDS]
        if mode == "dense":
            blob = mic.decode_vector(body["vector"], dimensions)
            reply = self._redis.execute_command(
                "FT.SEARCH", name, f"({live})=>[KNN {k} @vec $blob AS distance]", "PARAMS", "2", "blob", blob, "SORTBY", "distance",
                "RETURN", str(len(_SEARCH_FIELDS) + 1), *_SEARCH_FIELDS, "distance", "LIMIT", "0", str(k), "DIALECT", "2",
            )
            return self._reply(reply, epoch, current, score_field="distance")
        if mode == "lexical":
            terms = "|".join(mic.query_terms(body["terms"]))
            command = ("FT.SEARCH", name, f"{live} @terms:({terms})", "SCORER", "BM25STD", "WITHSCORES",
                       "RETURN", *returned, "LIMIT", "0", str(k), "DIALECT", "2")
            return self._reply(self._redis.execute_command(*command), epoch, current, with_scores=True)
        if mode == "symbol":
            symbol_id = hashlib.sha256(body["symbol"].encode("utf-8")).hexdigest()
            selector = f"{live} @symbol_id:{{{symbol_id}}}"
        else:
            selector = f"{live} @path_id:{{{body['path_id']}}}"
        reply = self._redis.execute_command("FT.SEARCH", name, selector, "RETURN", *returned, "LIMIT", "0", str(k), "DIALECT", "2")
        return self._reply(reply, epoch, current)

    @staticmethod
    def _reply(reply: Any, epoch: int, current: dict[str, Any] | None, *, with_scores: bool = False, score_field: str | None = None) -> dict[str, Any]:
        step = 3 if with_scores else 2
        records: list[dict[str, Any]] = []
        size = 0
        truncated = False
        for start in range(1, len(reply), step):
            fields = reply[start + step - 1]
            record: dict[str, Any] = {"id": _text(reply[start]).rsplit(":", 1)[1]}
            for name, value in zip(fields[::2], fields[1::2], strict=True):
                field = _text(name)
                record[field] = int(_text(value)) if field in _INT_FIELDS else _text(value)
            if with_scores:
                record["score"] = float(_text(reply[start + 1]))
            if score_field is not None:
                record["score"] = 1.0 - float(record.pop(score_field))
            size += len(json.dumps(record))
            if size > mic.MAX_RESPONSE_BYTES - 65_536:
                truncated = True
                break
            records.append(record)
        return {"status": "ok", "epoch": epoch, "current": current, "records": records, "truncated": truncated}

    def _seal(self, scope: str, payload: dict[str, Any]) -> str:
        data = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode("utf-8")).decode("ascii")
        tag = hmac.new(self._cursor_key, f"{scope}\n{data}".encode(), hashlib.sha256).hexdigest()
        return f"{data}.{tag}"

    def _unseal(self, scope: str, cursor: str) -> dict[str, Any]:
        data, _, tag = cursor.partition(".")
        expected = hmac.new(self._cursor_key, f"{scope}\n{data}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(tag, expected):
            raise mic.IndexRequestError("CURSOR_INVALID")
        try:
            payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(data))
        except ValueError:
            raise mic.IndexRequestError("CURSOR_INVALID") from None
        return payload

    def _op_catalogue(self, scope: str, body: dict[str, Any]) -> dict[str, Any]:
        """The file records live at one epoch, in path-id order. A cursor stays bound to its scope and epoch."""
        self._line(scope)
        start = "-"
        if "cursor" in body:
            sealed = self._unseal(scope, body["cursor"])
            if "epoch" in body and body["epoch"] != sealed["epoch"]:
                raise mic.IndexRequestError("CURSOR_INVALID")
            epoch, start, current = sealed["epoch"], f"({sealed['after']}", self._current(scope)
        else:
            epoch, current = self._visible_epoch(scope, body)
        limit = body.get("limit", mic.MAX_PAGE)
        path_ids = [_text(p) for p in self._redis.zrangebylex(f"{_PREFIX}:files:{scope}", start, "+", start=0, num=limit)]
        files: list[dict[str, Any]] = []
        for path_id in path_ids:
            found = self._live_file(scope, path_id, epoch)
            if found is not None:
                files.append(found)
        cursor = self._seal(scope, {"epoch": epoch, "after": path_ids[-1]}) if len(path_ids) == limit else None
        return {"status": "ok", "epoch": epoch, "current": current, "files": files, "cursor": cursor}

    def _live_file(self, scope: str, path_id: str, epoch: int) -> dict[str, Any] | None:
        members = [_text(raw) for raw in self._redis.smembers(f"{_PREFIX}:members:{scope}:{path_id}")]
        with self._redis.pipeline(transaction=False) as pipe:
            for key in members:
                pipe.hmget(key, "kind", "path", "file_hash", "language", "modified", "epoch_added", "epoch_removed", "description")
            rows = pipe.execute()
        for kind, path, file_hash, language, modified, added, removed, description in rows:
            if kind == b"file" and int(added) <= epoch < int(removed):
                return {"path": _text(path), "path_id": path_id, "file_hash": _text(file_hash), "language": _text(language),
                        "modified": int(modified) if modified else None, "description": _text(description) if description else None}
        return None

    # --- progress and cleanup ------------------------------------------------------------------------------------------

    def _op_cursor(self, scope: str, body: dict[str, Any]) -> dict[str, Any]:
        key = f"{_PREFIX}:progress:{scope}"
        if body["action"] == "get":
            raw = self._redis.get(key)
            return {"status": "ok", "value": json.loads(raw) if raw else None}

        def write(pipe: Any, _line: dict[str, str]) -> dict[str, Any]:
            pipe.multi()
            pipe.set(key, json.dumps(body["value"], sort_keys=True))
            return {"status": "ok"}

        return self._fenced(scope, body["token"], write)

    def _op_cleanup(self, scope: str, body: dict[str, Any]) -> dict[str, Any]:
        """One bounded step. `prune` removes what no reader can name: records retired at or before the published epoch and
        leftovers of abandoned epochs. `drop` removes the scope. The caller repeats until no cursor comes back."""
        cursor = 0
        if "cursor" in body:
            sealed = self._unseal(scope, body["cursor"])
            if sealed.get("cleanup") != body["action"]:
                raise mic.IndexRequestError("CURSOR_INVALID")
            cursor = sealed["next"]
        line = self._line(scope)
        current = self._current(scope)
        published = current["epoch"] if current else 0
        building = int(line["building"]) if "building" in line else None
        pattern = f"{_RECORD_PREFIX}{line['dimensions']}:{scope}:*"
        dropping = body["action"] == "drop"

        def step(pipe: Any, _line: dict[str, str]) -> dict[str, Any]:
            next_cursor, keys = pipe.scan(cursor=cursor, match=pattern, count=_CLEANUP_STEP)
            doomed: list[tuple[str, str]] = []
            for raw in keys:
                key = _text(raw)
                added, removed, path_id = pipe.hmget(key, "epoch_added", "epoch_removed", "path_id")
                if added is None:
                    continue
                abandoned = int(added) > published and int(added) != building
                retired = int(removed) <= published
                if dropping or abandoned or retired:
                    doomed.append((key, _text(path_id)))
            pipe.multi()
            for key, path_id in doomed:
                pipe.delete(key)
                pipe.srem(f"{_PREFIX}:members:{scope}:{path_id}", key)
            if dropping and not next_cursor:
                pipe.delete(f"{_PREFIX}:files:{scope}", f"{_PREFIX}:current:{scope}", f"{_PREFIX}:progress:{scope}",
                            f"{_PREFIX}:line:{scope}")
                pipe.srem(f"{_PREFIX}:lines", scope)
            more = self._seal(scope, {"cleanup": body["action"], "next": int(next_cursor)}) if next_cursor else None
            return {"status": "ok", "removed": len(doomed), "cursor": more}

        return self._fenced(scope, body["token"], step)


class IndexService:
    """Bounded admission in front of the store: two serving workers and a short queue. A full queue is refused at once.

    The store is checked before it first serves and again after an outage, because the Gateway may start before the container
    is up and must keep serving models meanwhile."""

    def __init__(self, store: IndexStore, *, verify: Callable[[], None] | None = None) -> None:
        self._store = store
        self._verify = verify
        self._verified = verify is None
        self._workers = threading.BoundedSemaphore(mic.SERVING_WORKERS)
        self._waiting = threading.BoundedSemaphore(mic.QUEUE_DEPTH)

    def handle(self, raw_body: bytes, *, deadline: float) -> tuple[int, dict[str, Any]]:
        if not self._waiting.acquire(blocking=False):
            return 503, mic.error_body("INDEX_BUSY")
        try:
            if not self._workers.acquire(timeout=max(0.0, deadline - time.monotonic())):
                return 503, mic.error_body("INDEX_BUSY")
        finally:
            self._waiting.release()
        try:
            request = mic.parse_request(raw_body)
            if not self._verified and self._verify is not None:
                try:
                    self._verify()
                except IndexStartupError as refusal:
                    return 503, mic.error_body(refusal.code)
                self._verified = True
            return 200, self._store.dispatch(request)
        except mic.IndexRequestError as refusal:
            return refusal.status, mic.error_body(refusal.code)
        except (RedisConnectionError, TimeoutError, OSError):
            self._verified = self._verify is None  # whatever comes back on this port has to prove itself again
            return 503, mic.error_body("INDEX_UNAVAILABLE")
        except RedisError:
            return 503, mic.error_body("INDEX_STORAGE_ERROR")
        finally:
            self._workers.release()


def build_index_service(config: MemoryIndexConfig, *, keyring_backend: Any, hmac_key: bytes) -> IndexService:
    """The service for the approved configuration. Nothing connects until the first request. A missing password serves a
    stable refusal, so the Agent Panel can say setup is incomplete while models keep working."""
    try:
        password = keyring_backend.get_password(KEYRING_SERVICE, config.credential_name)
    except Exception:  # noqa: BLE001 - any backend failure means the same thing here: no usable credential
        password = None
    client = connect(IndexEndpoint(config.host, config.port, config.user, password or "", config.resource))
    cursor_key = hashlib.sha256(b"optimus-memory-index-cursor-v1\0" + hmac_key).digest()

    def verify() -> None:
        if not password:
            raise IndexStartupError("INDEX_CREDENTIAL_MISSING")
        verify_resource(client, config.resource)

    return IndexService(IndexStore(client, cursor_key=cursor_key), verify=verify)
