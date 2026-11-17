"""Plan 12.11 Task 1: the store's commit and serving logic in the default run, against an in-memory stand-in for the commands
it uses, including WATCH conflicts. The real instance, its ACL and its persistence are proven in tests/integration/memory."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import WatchError

from context_engine import memory_contracts as engine
from optimus_gateway import memory_store
from optimus_security import memory_store_contract as msc


class Server:
    """The shared state: strings, streams, per-key versions for WATCH, and what WAITAOF answers."""

    def __init__(self) -> None:
        self.strings: dict[str, bytes] = {}
        self.streams: dict[str, list[tuple[bytes, dict[bytes, bytes]]]] = {}
        self.versions: dict[str, int] = {}
        self.sequence = 0
        self.fsync = 1
        self.used = 10 * 1024 * 1024
        self.before_exec: Callable[[], None] | None = None
        self.page_delay = 0.0
        self.waitaof_timeouts: list[int] = []

    def touch(self, key: str) -> None:
        self.versions[key] = self.versions.get(key, 0) + 1

    def get(self, key: str) -> bytes | None:
        return self.strings.get(key)

    def set(self, key: str, value: Any, px: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.strings:
            return False
        self.strings[key] = value if isinstance(value, bytes) else str(value).encode()
        self.touch(key)
        return True

    def incr(self, key: str) -> int:
        value = int(self.strings.get(key, b"0")) + 1
        self.set(key, value)
        return value

    def delete(self, key: str) -> int:
        self.touch(key)
        return int(self.strings.pop(key, None) is not None)

    def pexpire(self, key: str, _ms: int) -> bool:
        self.touch(key)
        return key in self.strings

    def xadd(self, key: str, fields: dict[str, str]) -> bytes:
        self.sequence += 1
        entry_id = f"1-{self.sequence}".encode()
        self.streams.setdefault(key, []).append((entry_id, {k.encode(): v.encode() for k, v in fields.items()}))
        self.touch(key)
        return entry_id

    def ping(self) -> bool:
        return True

    def dbsize(self) -> int:
        return len(self.strings) + len(self.streams)

    def xrange(self, key: str, min: str, max: str, count: int) -> list[Any]:
        time.sleep(self.page_delay)
        self.pages = getattr(self, "pages", 0) + 1
        low = memory_store._order(min.lstrip("("))
        high = memory_store._order(max)
        rows = [(i, f) for i, f in self.streams.get(key, []) if low < memory_store._order(i.decode()) <= high]
        return rows[:count]

    def xrevrange(self, key: str, count: int) -> list[Any]:
        return list(reversed(self.streams.get(key, [])))[:count]


class Pipeline:
    def __init__(self, client: Client, transaction: bool) -> None:
        self.client, self.server = client, client.server
        self.transaction = transaction
        self.watched: dict[str, int] = {}
        self.queued: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.buffering = not transaction

    def __enter__(self) -> Pipeline:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.reset()

    connection = None

    def reset(self) -> None:
        self.watched, self.queued = {}, []

    def watch(self, *keys: str) -> None:
        self.client.check()
        self.watched = {key: self.server.versions.get(key, 0) for key in keys}

    def unwatch(self) -> None:
        self.watched = {}

    def multi(self) -> None:
        self.buffering = True

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            if self.buffering:
                self.queued.append((name, args, kwargs))
                return self
            self.client.check()
            return getattr(self.server, name)(*args, **kwargs)
        return call

    def execute_command(self, *args: Any) -> Any:
        self.queued.append(("execute_command", args, {}))
        return self

    def execute(self) -> list[Any]:
        self.client.check()
        if self.server.before_exec is not None:
            hook, self.server.before_exec = self.server.before_exec, None
            hook()
        if any(self.server.versions.get(key, 0) != seen for key, seen in self.watched.items()):
            raise WatchError("watched key changed")
        results = [self.client.execute_command(*args) if name == "execute_command" else getattr(self.server, name)(*args, **kwargs)
                   for name, args, kwargs in self.queued]
        self.queued = []
        return results


class Client:
    def __init__(self, server: Server, connection: int = 7) -> None:
        self.server, self.connection, self.down = server, connection, False
        self.waitaof_raises: Exception | None = None

    def check(self) -> None:
        if self.down:
            raise RedisConnectionError("down")

    def pipeline(self, transaction: bool = True) -> Pipeline:
        return Pipeline(self, transaction)

    def client_id(self) -> int:
        self.check()
        return self.connection

    def info(self, _section: str) -> dict[str, Any]:
        self.check()
        return {"used_memory": self.server.used, "aof_enabled": 1, "maxmemory_policy": "noeviction"}

    def execute_command(self, *args: Any) -> Any:
        self.check()
        assert args[0] == "WAITAOF"
        if self.waitaof_raises is not None:
            error, self.waitaof_raises = self.waitaof_raises, None
            raise error
        self.server.waitaof_timeouts.append(int(args[3]))
        return [self.server.fsync, 0]

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            self.check()
            return getattr(self.server, name)(*args, **kwargs)
        return call


RESOURCE = "optimus-memory-store-test"


def store(server: Server | None = None, checks: list[int] | None = None) -> tuple[memory_store.MemoryStoreService, Server, Client]:
    """The service with the store's own verification, which marks the stand-in as its resource on first use."""
    server = server or Server()
    writer = Client(server)
    inner = memory_store.MemoryStore(Client(server, 9), writer, admission_ceiling_mb=384, cursor_key=b"k")  # type: ignore[arg-type]

    def verify(deadline: float) -> None:
        if checks is not None:
            checks.append(1)
        try:
            inner.verify(RESOURCE, deadline=deadline)
        except msc.MemoryRequestError as refusal:
            raise memory_store.MemoryStoreStartupError(refusal.code) from None

    return memory_store.MemoryStoreService(inner, verify=verify), server, writer


def call(service: memory_store.MemoryStoreService, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    return service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 5)


def lease(service: memory_store.MemoryStoreService, owner: str = "host-1", project: str = "p-1") -> int:
    status, reply = call(service, {"op": "lease", "project": project, "owner": owner, "action": "acquire", "ttl_ms": 60_000})
    assert status == 200, reply
    return int(reply["token"])


def event(version: int = 1, item: str = "m-0123456789abcdef", **changes: Any) -> dict[str, Any]:
    base = {"event_id": f"e-{item[-4:]}-{version}", "item": item, "version": version, "action": "admit" if version == 1 else "update",
            "trust": "user-authored", "status": "active", "kind": "preference", "scope": "s-1", "title": "t",
            "statement": f"v{version}", "anchors": [], "lineage": [], "valid_from_ms": 0, "valid_until_ms": 0}
    return {**base, **changes}


def append(service: memory_store.MemoryStoreService, token: int, change: dict[str, Any], key: str | None = None) -> tuple[int, dict[str, Any]]:
    return call(service, {"op": "append", "project": "p-1", "token": token, "expected_version": change["version"] - 1,
                          "idempotency_key": key or (change["event_id"].encode().hex() * 8)[:64], "event": change})


def read(service: memory_store.MemoryStoreService, item: str = "m-0123456789abcdef") -> Any:
    return call(service, {"op": "read", "project": "p-1", "item": item})[1]["item"]


def test_a_confirmed_save_is_served_and_a_retry_appends_nothing() -> None:
    service, server, _ = store()
    token = lease(service)
    status, first = append(service, token, event(), key="a" * 64)
    assert status == 200 and (first["durable_state"], first["projection_state"]) == ("confirmed", "current")
    assert read(service)["statement"] == "v1"
    again = append(service, token, event(), key="a" * 64)[1]
    assert again["replayed"] is True and again["stream_id"] == first["stream_id"]
    assert append(service, token, event(statement="other"), key="a" * 64) == (409, msc.error_body("IDEMPOTENCY_CONFLICT"))
    assert append(service, token, event(item="m-00000000000000aa", event_id="e-cdef-1")) == (409, msc.error_body("EVENT_ID_REUSED"))
    assert append(service, token, event(version=3)) == (409, msc.error_body("VERSION_CONFLICT"))
    assert sum(len(entries) for entries in server.streams.values()) == 1


def test_an_unconfirmed_save_is_not_served_and_stops_new_saves_but_not_its_own_retry() -> None:
    service, server, _ = store()
    token = lease(service)
    server.fsync = 0
    status, reply = append(service, token, event(), key="b" * 64)
    assert status == 200 and (reply["durable_state"], reply["projection_state"]) == ("unconfirmed", "pending")
    assert read(service) is None
    assert call(service, {"op": "capabilities"})[1]["admitting"] is False
    assert append(service, token, event(item="m-00000000000000bb")) == (503, msc.error_body("MEMORY_NOT_ADMITTING"))
    retry = append(service, token, event(), key="b" * 64)
    assert retry[0] == 200 and retry[1]["replayed"] is True and retry[1]["durable_state"] == "unconfirmed"
    server.fsync = 1
    assert append(service, token, event(), key="b" * 64)[1]["durable_state"] == "confirmed"  # the probe clears, the retry confirms
    assert read(service)["event_id"] == "e-cdef-1"


def test_a_reconnect_between_append_and_waitaof_is_never_a_confirmation() -> None:
    service, server, writer = store()
    token = lease(service)
    server.before_exec = lambda: setattr(writer, "connection", 8)  # the append lands on another connection than the one checked
    assert append(service, token, event())[1]["durable_state"] == "unconfirmed"
    assert service._store.suspect is True


def test_saves_stop_at_the_ceiling_but_withdrawals_go_through() -> None:
    service, server, _ = store()
    token = lease(service)
    append(service, token, event())
    server.used = 384 * 1024 * 1024
    assert append(service, token, event(version=2)) == (503, msc.error_body("MEMORY_NOT_ADMITTING"))
    withdrawn = event(version=2, action="withdraw", status="withdrawn", title="", statement="")
    assert append(service, token, withdrawn)[1]["durable_state"] == "confirmed"


def test_the_fence_moves_on_and_only_the_holder_appends() -> None:
    service, _, _ = store()
    first = lease(service)
    assert call(service, {"op": "lease", "project": "p-1", "owner": "host-2", "action": "acquire", "ttl_ms": 60_000})[0] == 409
    second = lease(service)
    assert second > first and append(service, first, event()) == (409, msc.error_body("LEASE_LOST"))
    assert call(service, {"op": "lease", "project": "p-1", "owner": "host-1", "action": "renew", "ttl_ms": 60_000, "token": second})[0] == 200
    assert call(service, {"op": "lease", "project": "p-1", "owner": "host-1", "action": "release", "token": second})[0] == 200
    assert append(service, second, event()) == (409, msc.error_body("LEASE_LOST"))


def test_a_fence_that_is_not_on_disk_is_never_handed_out() -> None:
    service, server, _ = store()
    call(service, {"op": "capabilities"})  # verified while fsync still works
    server.fsync = 0
    status, reply = call(service, {"op": "lease", "project": "p-1", "owner": "host-1", "action": "acquire", "ttl_ms": 60_000})
    assert (status, reply) == (503, msc.error_body("LEASE_UNCONFIRMED"))


def test_a_head_that_keeps_moving_is_contended_not_written() -> None:
    service, server, _ = store()
    token = lease(service)
    stream = memory_store.MemoryStore._key("p-1", "events")

    def interfere() -> None:
        server.touch(stream)
        server.before_exec = interfere

    server.before_exec = interfere
    assert append(service, token, event()) == (409, msc.error_body("MEMORY_CONTENDED"))
    assert stream not in server.streams


def test_a_list_page_stays_inside_the_reply_bound() -> None:
    service, _, _ = store()
    token = lease(service)
    long = "é" * msc.MAX_STATEMENT_CHARS
    refs = [f"r-{n}" for n in range(msc.MAX_REFERENCES)]
    for n in range(100):  # a full page of maximal items is well over the bound
        append(service, token, event(item=f"m-{n:016x}", statement=long, anchors=refs, lineage=refs))
    seen: list[str] = []
    cursor: str | None = None
    while True:
        body = {"op": "list", "project": "p-1", "scope": "s-1", "limit": 100, **({"cursor": cursor} if cursor else {})}
        status, reply = call(service, body)
        assert status == 200 and len(json.dumps(reply, ensure_ascii=True)) <= msc.MAX_RESPONSE_BYTES
        seen += [entry["item"] for entry in reply["items"]]
        cursor = reply["cursor"]
        if cursor is None:
            break
    assert seen == [f"m-{n:016x}" for n in range(100)]


def test_reads_never_see_a_fold_another_request_is_advancing() -> None:
    service, _, _ = store()
    token = lease(service)
    for n in range(200):
        append(service, token, event(item=f"m-{n:016x}"))
    errors: list[tuple[int, dict[str, Any]]] = []

    def lister() -> None:
        for _ in range(30):
            reply = call(service, {"op": "list", "project": "p-1", "scope": "s-1", "limit": 100})
            if reply[0] != 200:
                errors.append(reply)

    threads = [threading.Thread(target=lister) for _ in range(2)]
    for thread in threads:
        thread.start()
    for n in range(200, 260):
        append(service, token, event(item=f"m-{n:016x}"))
    for thread in threads:
        thread.join(30)
    assert errors == []


def test_an_outage_drops_the_caches_and_a_malformed_entry_is_a_stable_code() -> None:
    service, server, writer = store()
    token = lease(service)
    append(service, token, event())
    writer.down = True
    assert append(service, token, event(version=2)) == (503, msc.error_body("MEMORY_UNAVAILABLE"))
    assert service._store._writer_folds == {} and service._store._serving_folds == {}
    writer.down = False
    stream = memory_store.MemoryStore._key("p-1", "events")
    server.streams[stream].append((b"1-999", {b"e": b"not json"}))
    server.strings[memory_store.MemoryStore._key("p-1", "durable")] = b"1-999"
    assert call(service, {"op": "read", "project": "p-1", "item": "m-0123456789abcdef"}) == (503, msc.error_body("MEMORY_STORAGE_ERROR"))


@pytest.mark.parametrize("reply", [[0, 0], [1, 0]])
def test_the_fsync_probe_writes_before_it_waits(reply: list[int]) -> None:
    server = Server()
    server.fsync = reply[0]
    client = Client(server)
    assert memory_store.fsync_probe(client, timeout_ms=10) == reply[0]  # type: ignore[arg-type]
    assert server.strings[memory_store._PROBE_KEY] == b"1"


def test_a_connection_lost_during_waitaof_never_confirms_a_save_redis_then_lost() -> None:
    checks: list[int] = []
    service, server, writer = store(checks=checks)
    token = lease(service)
    stream = memory_store.MemoryStore._key("p-1", "events")
    writer.waitaof_raises = RedisConnectionError("reset")
    reply = append(service, token, event(), key="c" * 64)[1]
    assert reply["durable_state"] == "unconfirmed" and service._store._writer_folds == {}
    server.streams[stream].clear()  # Redis lost the unconfirmed append in the outage
    other = {"type": "event", "key": "d" * 64, "digest": "0" * 64, "event": event(item="m-00000000000000dd")}
    server.xadd(stream, {"e": json.dumps(other)})  # and another Gateway appended past it
    before = len(checks)
    retry = append(service, token, event(), key="c" * 64)
    assert retry[0] == 200 and "replayed" not in retry[1] and retry[1]["durable_state"] == "confirmed"  # written again, not a phantom
    assert len(checks) == before + 1  # the resource proved itself again before that request ran
    assert [json.loads(fields[b"e"])["key"] for _id, fields in server.streams[stream]] == ["d" * 64, "c" * 64]


def test_a_watch_error_from_a_replaced_connection_unwinds_and_waits_for_verification() -> None:
    checks: list[int] = []
    service, server, writer = store(checks=checks)
    token = lease(service)
    append(service, token, event())
    stream = memory_store.MemoryStore._key("p-1", "events")

    def reconnect() -> None:
        writer.connection = 8
        server.touch(stream)

    server.before_exec = reconnect
    assert append(service, token, event(version=2)) == (503, msc.error_body("MEMORY_UNAVAILABLE"))
    assert len(server.streams[stream]) == 1 and service._store.suspect is True
    before = len(checks)
    assert append(service, token, event(version=2))[1]["durable_state"] == "confirmed"  # verified first, then written once
    assert len(checks) == before + 1 and len(server.streams[stream]) == 2


def test_a_lease_whose_connection_was_replaced_is_not_granted() -> None:
    service, server, writer = store()
    call(service, {"op": "capabilities"})  # the first request verifies the stand-in
    lease_key = memory_store.MemoryStore._key("p-1", "lease")

    def reconnect() -> None:
        writer.connection = 8
        server.touch(lease_key)

    server.before_exec = reconnect
    status, reply = call(service, {"op": "lease", "project": "p-1", "owner": "host-1", "action": "acquire", "ttl_ms": 60_000})
    assert (status, reply) == (503, msc.error_body("MEMORY_UNAVAILABLE")) and lease_key not in server.strings


def test_a_request_queued_behind_a_lost_connection_writes_and_reads_nothing() -> None:
    service, server, _ = store()
    token = lease(service)
    service._store.connection_lost()
    stream = memory_store.MemoryStore._key("p-1", "events")
    renew = {"op": "lease", "project": "p-1", "owner": "host-1", "action": "renew", "ttl_ms": 60_000, "token": token}  # the writer alone
    body = {"op": "append", "project": "p-1", "token": token, "expected_version": 0, "idempotency_key": "9" * 64, "event": event()}
    for op in (renew, body, {"op": "read", "project": "p-1", "item": "m-0123456789abcdef"}):
        with pytest.raises(msc.MemoryRequestError) as refused:
            service._store.dispatch(op, deadline=time.monotonic() + 5)  # already past the service's verification gate
        assert refused.value.code == "MEMORY_UNAVAILABLE"
    assert stream not in server.streams


def test_a_replacement_resource_is_refused_before_anything_runs() -> None:
    service, server, _ = store()
    token = lease(service)
    service._store.connection_lost()
    server.strings["omem:resource"] = b"optimus-memory-store-someone-else"  # another instance now answers on the port
    assert append(service, token, event()) == (503, msc.error_body("MEMORY_STORE_RESOURCE_MISMATCH"))
    assert memory_store.MemoryStore._key("p-1", "events") not in server.streams


def test_a_request_whose_budget_went_on_queueing_starts_no_write() -> None:
    service, server, _ = store()
    token = lease(service)
    held = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with service._store._writing():
            held.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(5)
    started = time.monotonic()
    body = {"op": "append", "project": "p-1", "token": token, "expected_version": 0, "idempotency_key": "e" * 64, "event": event()}
    status, reply = service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 0.3)
    release.set()
    holder.join(5)
    assert (status, reply["error"]) in {(503, "MEMORY_BUSY"), (503, "MEMORY_TIMEOUT")} and time.monotonic() - started < 1.5
    assert memory_store.MemoryStore._key("p-1", "events") not in server.streams


def test_an_expired_deadline_stops_a_fold_rebuild_between_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    service, server, _ = store()
    token = lease(service)
    for n in range(6):
        append(service, token, event(item=f"m-{n:016x}"))
    monkeypatch.setattr(memory_store, "_FOLD_PAGE", 1)
    service._store.forget()
    server.page_delay, server.pages = 0.05, 0
    with pytest.raises(msc.MemoryRequestError) as stopped:
        service._store.dispatch({"op": "read", "project": "p-1", "item": "m-0000000000000000"}, deadline=time.monotonic() + 0.12)
    assert stopped.value.code == "MEMORY_TIMEOUT" and 2 <= server.pages < 6  # it started, then stopped between pages


def test_the_fsync_recheck_waits_only_for_what_is_left_of_the_request() -> None:
    service, server, _ = store()
    token = lease(service)
    service._store._fsync_failed = True
    server.fsync, server.waitaof_timeouts = 0, []
    body = {"op": "append", "project": "p-1", "token": token, "expected_version": 0, "idempotency_key": "8" * 64, "event": event()}
    started = time.monotonic()
    status, _reply = service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 0.4)
    assert status == 503 and time.monotonic() - started < 1.0
    assert server.waitaof_timeouts and max(server.waitaof_timeouts) <= 400


def test_a_read_waits_for_the_read_lock_only_inside_its_budget() -> None:
    service, _, _ = store()
    lease(service)
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with service._store._reading():
            held.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(5)
    started = time.monotonic()
    reply = service.handle(json.dumps({"op": "read", "project": "p-1", "item": "m-0123456789abcdef"}).encode(), deadline=time.monotonic() + 0.3)
    release.set()
    holder.join(5)
    assert reply == (503, msc.error_body("MEMORY_TIMEOUT")) and time.monotonic() - started < 1.0  # the wait used the whole budget


def test_replies_convert_into_the_engine_contracts() -> None:
    service, _, _ = store()
    token = lease(service)
    wire = event(anchors=["b-1:0-25"], lineage=["ev-1"], valid_from_ms=3)
    saved = append(service, token, wire)[1]
    result = engine.MemoryCommitResult(saved["event_id"], saved["item"], saved["version"], saved["durable_state"], saved["projection_state"])
    assert result.durable_state == "confirmed"
    stored = engine.StoredEvent.from_record("p-1", read(service))
    assert stored.event.lineage == ("ev-1",) and stored.stream_id == saved["stream_id"] and stored.to_record() == read(service)
    listed = call(service, {"op": "list", "project": "p-1", "scope": "s-1", "limit": 10})[1]["items"]
    assert [engine.StoredEvent.from_record("p-1", item).event.item for item in listed] == [wire["item"]]
    point = {"session": "sess-1", "sequence": 1, "branch": "main", "worktree": "wt-1", "baseline": "", "settled_at_ms": 1, "outcome": "settled",
             "objective": "obj-1", "provenance": "turn-1", "plan_hash": "", "pending": [], "amendments": [], "completion": [], "verification": [],
             "remaining": []}
    ack = call(service, {"op": "checkpoint", "project": "p-1", "token": token, "checkpoint": point})[1]
    assert engine.CheckpointResult(ack["session"], ack["sequence"], ack["stream_id"], ack["durable_state"], ack["projection_state"]).sequence == 1
    served = call(service, {"op": "checkpoints", "project": "p-1", "limit": 5})[1]["checkpoints"]
    assert engine.StoredCheckpoint.from_record("p-1", served[0]).checkpoint.provenance == "turn-1"


def test_a_retry_of_an_unconfirmed_save_is_answered_even_over_the_ceiling() -> None:
    service, server, _ = store()
    token = lease(service)
    server.fsync = 0
    append(service, token, event(), key="f" * 64)
    server.used = 384 * 1024 * 1024
    retry = append(service, token, event(), key="f" * 64)
    assert retry[0] == 200 and retry[1]["replayed"] is True
    assert append(service, token, event(item="m-00000000000000ff")) == (503, msc.error_body("MEMORY_NOT_ADMITTING"))
