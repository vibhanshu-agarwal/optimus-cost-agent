"""Plan 12.11 Task 1: the request's budget reaches redis-py's real connection, pool and parser. Two local fake servers stand in
for a Redis that never answers and one that answers slowly; the real store's reconnect handling is proven in
tests/integration/memory/test_store.py."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Callable, Iterator

import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from optimus_gateway import memory_store
from optimus_security import memory_store_contract as msc


def _commands(conn: socket.socket) -> Iterator[list[bytes]]:
    """RESP arrays of bulk strings, as redis-py sends them."""
    data = b""

    def line() -> bytes:
        nonlocal data
        while b"\r\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                raise EOFError
            data += chunk
        head, data = data.split(b"\r\n", 1)
        return head

    while True:
        try:
            count = int(line()[1:])
            parts = []
            for _ in range(count):
                size = int(line()[1:])
                while len(data) < size + 2:
                    chunk = conn.recv(65536)
                    if not chunk:
                        raise EOFError
                    data += chunk
                parts.append(data[:size])
                data = data[size + 2:]
            yield parts
        except (EOFError, OSError, ValueError):
            return


_INFO = b"# Server\r\naof_enabled:1\r\nmaxmemory_policy:noeviction\r\nused_memory:1024\r\n"
_REPLIES = {
    b"INFO": b"$%d\r\n%s\r\n" % (len(_INFO), _INFO),
    b"GET": b"$25\r\noptimus-memory-store-test\r\n",
    b"INCR": b":1\r\n",
    b"INCRBY": b":1\r\n",
    b"WAITAOF": b"*2\r\n:1\r\n:0\r\n",
    b"CLIENT": b":7\r\n",
    b"DBSIZE": b":0\r\n",
    b"PING": b"+PONG\r\n",
}


class FakeRedis:
    """Accepts connections; `mode` "silent" never answers, "slow-ping" answers +OK at once and PING after two seconds."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.connections = 0
        self.logs: dict[int, list[bytes]] = {}
        self.dropped = False
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.stop = threading.Event()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        self.server.settimeout(0.2)
        while not self.stop.is_set():
            try:
                conn, _ = self.server.accept()
            except OSError:
                continue
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        self.connections += 1
        first, infos, queued = self.connections == 1, 0, None
        log = self.logs.setdefault(self.connections, [])
        with conn:
            for command in _commands(conn):
                mode = self.mode  # read per command, so a test can change it between operations
                if mode == "silent":
                    self.stop.wait(10)
                    return
                name = command[0].upper()
                log.append(name)
                reply = _REPLIES.get(name, b"+OK\r\n")
                if name == b"GET" and command[1:] != [b"omem:resource"]:
                    reply = b"$-1\r\n"
                if name == b"MULTI":
                    queued = 0
                elif queued is not None and name not in (b"EXEC", b"DISCARD"):
                    queued += 1
                    reply = b"+QUEUED\r\n"
                elif name == b"EXEC":
                    reply, queued = b"*%d\r\n" % queued + b"+OK\r\n" * queued, None
                if mode == "replace-before-set":  # the original instance is empty and unmarked, then dies before the marker
                    if command[:2] == [b"GET", b"omem:resource"]:
                        reply = b"$-1\r\n"
                    if name == b"DBSIZE":
                        reply = b":0\r\n" if not self.dropped else b":5\r\n"  # the replacement holds data
                        if not self.dropped:
                            self.dropped = True
                            conn.sendall(reply)
                            return
                    conn.sendall(reply)
                    continue
                if mode == "stall-unwatch" and name == b"UNWATCH":
                    self.stop.wait(10)
                    return
                if mode == "stall-unwatch":
                    conn.sendall(reply)
                    continue
                if mode == "drop-after-client-id" and not self.dropped and command[:2] == [b"CLIENT", b"ID"]:
                    self.dropped = True
                    conn.sendall(reply)
                    return  # the socket dies between two checkouts
                if mode == "stall-waitaof" and name == b"WAITAOF":
                    self.stop.wait(10)
                    return
                if mode in ("drop-after-client-id", "stall-waitaof"):
                    conn.sendall(reply)
                    continue
                if mode == "slow-all":  # a well-formed Redis that takes 150 ms per reply
                    self.stop.wait(0.15)
                    conn.sendall(reply)
                elif mode == "trickle":  # well-formed replies, one byte every 20 ms
                    for byte in reply:
                        if self.stop.wait(0.02):
                            return
                        conn.sendall(bytes([byte]))
                elif mode == "drop-after-info":  # the first connection dies after its second INFO, as a restart would
                    conn.sendall(reply)
                    infos += name == b"INFO"
                    if first and infos == 2:
                        return
                elif mode == "fast":
                    conn.sendall(reply)
                elif mode == "stall-info":  # verification connects and pings, then INFO never answers
                    if name == b"INFO":
                        self.stop.wait(10)
                        return
                    conn.sendall(reply)
                elif mode == "stall-get-slow-auth":  # a GET never answers, and every handshake reply takes 300 ms
                    if name == b"GET":
                        self.stop.wait(10)
                        return
                    if name in (b"AUTH", b"CLIENT", b"HELLO"):
                        self.stop.wait(0.3)
                    conn.sendall(reply)
                elif name == b"PING":
                    self.stop.wait(2)
                    conn.sendall(b"+PONG\r\n")
                else:
                    conn.sendall(b"+OK\r\n")

    def close(self) -> None:
        self.stop.set()
        self.server.close()


@pytest.fixture
def fake() -> Iterator[Callable[[str], FakeRedis]]:
    made: list[FakeRedis] = []

    def make(mode: str) -> FakeRedis:
        made.append(FakeRedis(mode))
        return made[-1]

    yield make
    for server in made:
        server.close()



def _endpoint(port: int) -> memory_store.MemoryStoreEndpoint:
    return memory_store.MemoryStoreEndpoint("127.0.0.1", port, "optimus-memory", "x" * 32, "optimus-memory-store-test")  # pragma: allowlist secret


def test_a_redis_that_never_answers_costs_a_request_only_its_budget(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("silent")
    endpoint = _endpoint(server.port)
    store = memory_store.MemoryStore(memory_store.connect(endpoint), memory_store.connect(endpoint), admission_ceiling_mb=384, cursor_key=b"k")

    def verify(deadline: float) -> None:
        try:
            store.verify(endpoint.resource, deadline=deadline)
        except msc.MemoryRequestError as refusal:
            raise memory_store.MemoryStoreStartupError(refusal.code) from None

    service = memory_store.MemoryStoreService(store, verify=verify)
    started = time.monotonic()
    status, _reply = service.handle(json.dumps({"op": "capabilities"}).encode(), deadline=time.monotonic() + 0.3)
    assert status == 503 and time.monotonic() - started < 1.0  # authentication hung; the request did not


def test_a_slow_reply_after_checkout_is_cut_at_the_budget_and_the_parser_keeps_it(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("slow-ping")
    client = memory_store.connect(_endpoint(server.port))
    assert client.set("omem:k", "v") is True  # connected with the default five-second timeouts
    memory_store.set_budget(client, 0.3)
    assert client.set("omem:k", "v") is True  # a real checkout probes the socket and restores the parser's cached timeout
    connection = client.optimus_link.connection
    assert connection.socket_timeout == 0.3 and connection._sock.gettimeout() == 0.3
    assert connection._parser._buffer.socket_timeout == 0.3  # what the checkout probe restores
    started = time.monotonic()
    with pytest.raises(RedisTimeoutError):
        client.ping()
    assert time.monotonic() - started < 1.0
    assert client.optimus_link.connects == 1


def test_the_budget_also_bounds_the_first_connection(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("silent")
    client = memory_store.connect(_endpoint(server.port))
    memory_store.set_budget(client, 0.3)
    started = time.monotonic()
    with pytest.raises(RedisTimeoutError):
        client.ping()  # the handshake itself never gets an answer
    assert time.monotonic() - started < 1.0


def test_verification_stops_between_commands_when_the_budget_runs_out(fake: Callable[[str], FakeRedis]) -> None:
    """Each reply takes 150 ms, so verification's commands need about 1.2 s; inside a 0.35 s budget it must stop part way."""
    server = fake("slow-all")
    endpoint = _endpoint(server.port)
    store = memory_store.MemoryStore(memory_store.connect(endpoint), memory_store.connect(endpoint), admission_ceiling_mb=384, cursor_key=b"k")
    started = time.monotonic()
    with pytest.raises((msc.MemoryRequestError, memory_store.MemoryStoreStartupError)) as stopped:
        store.verify(endpoint.resource, deadline=time.monotonic() + 0.35)
    assert time.monotonic() - started < 0.5, stopped.value  # the deadline plus scheduling, not the eight replies
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)  # given the time, the same server verifies
    assert store.suspect is False


def _store(server: FakeRedis) -> tuple[memory_store.MemoryStore, memory_store.MemoryStoreEndpoint]:
    endpoint = _endpoint(server.port)
    store = memory_store.MemoryStore(memory_store.connect(endpoint), memory_store.connect(endpoint), admission_ceiling_mb=384, cursor_key=b"k")
    return store, endpoint


def test_verification_refuses_a_proof_gathered_across_a_reconnect(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("drop-after-info")
    store, endpoint = _store(server)
    with pytest.raises(memory_store.MemoryStoreStartupError) as refused:
        store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    assert refused.value.code == "MEMORY_STORE_RECONNECTED" and store.suspect is False and store._verified_connects == (0, 0)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)  # later connections stay up, so the proof holds
    assert store._verified_connects == (3, 1)  # the original, the refused reconnect, then the one the proof held


def test_a_failed_first_handshake_does_not_keep_its_longer_budget(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("silent")
    store, endpoint = _store(server)
    with pytest.raises((msc.MemoryRequestError, memory_store.MemoryStoreStartupError)):
        store.verify(endpoint.resource, deadline=time.monotonic() + 1.0)
    started = time.monotonic()
    with pytest.raises((msc.MemoryRequestError, memory_store.MemoryStoreStartupError)):
        store.verify(endpoint.resource, deadline=time.monotonic() + 0.3)
    assert time.monotonic() - started < 0.5


def test_a_reply_that_trickles_in_is_cut_at_the_deadline(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("fast")
    store, endpoint = _store(server)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    server.mode = "trickle"  # INFO's reply is about 90 bytes: almost two seconds at one byte every 20 ms
    service = memory_store.MemoryStoreService(store)  # already verified above
    started = time.monotonic()
    reply = service.handle(json.dumps({"op": "capabilities"}).encode(), deadline=time.monotonic() + 0.3)
    assert time.monotonic() - started < 0.5 and reply == (503, msc.error_body("MEMORY_TIMEOUT"))


def test_a_slow_handshake_is_cut_at_the_deadline(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("slow-all")  # AUTH and the client-name replies alone take about 450 ms
    store, endpoint = _store(server)
    started = time.monotonic()
    with pytest.raises((msc.MemoryRequestError, memory_store.MemoryStoreStartupError)):
        store.verify(endpoint.resource, deadline=time.monotonic() + 0.25)
    assert time.monotonic() - started < 0.4


def test_a_stalled_verification_command_is_a_timeout_not_an_unreachable_store(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("stall-info")
    store, endpoint = _store(server)
    started = time.monotonic()
    with pytest.raises(msc.MemoryRequestError) as stopped:
        store.verify(endpoint.resource, deadline=time.monotonic() + 0.3)
    assert stopped.value.code == "MEMORY_TIMEOUT" and time.monotonic() - started < 0.5


def test_nothing_reconnects_after_the_deadline_not_even_redis_py_cleanup(fake: Callable[[str], FakeRedis]) -> None:
    """A lease's WATCH is followed by a GET that never answers; the watchdog cuts it. redis-py's cleanup would then reconnect
    (three slow handshake replies) to send UNWATCH, and the store would ask CLIENT ID: neither may happen past the deadline."""
    server = fake("fast")
    store, endpoint = _store(server)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    server.mode = "stall-get-slow-auth"
    connects = store._writer.optimus_link.connects
    started = time.monotonic()
    with pytest.raises(msc.MemoryRequestError) as stopped:
        store.dispatch({"op": "lease", "project": "p-1", "owner": "host-1", "action": "acquire", "ttl_ms": 60_000},
                       deadline=time.monotonic() + 0.5)
    assert stopped.value.code == "MEMORY_TIMEOUT" and time.monotonic() - started < 0.7
    assert store._writer.optimus_link.connects == connects  # no reconnect was attempted after the cut
    assert store.suspect is True


def test_a_watchdog_already_cutting_finishes_before_the_next_request_takes_the_connection(
        fake: Callable[[str], FakeRedis], monkeypatch: pytest.MonkeyPatch) -> None:
    server = fake("fast")
    store, endpoint = _store(server)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    started, release, order = threading.Event(), threading.Event(), []
    real_cut = memory_store.Link.cut

    def slow_cut(link: memory_store.Link) -> None:
        started.set()
        release.wait(5)  # the callback is under way while its request leaves
        real_cut(link)
        order.append("cut done")

    monkeypatch.setattr(memory_store.Link, "cut", slow_cut)

    def request_a() -> None:
        store._local.deadline = time.monotonic() + 0.05
        with store._writing():
            started.wait(5)  # the watchdog has fired
        order.append("A released")

    def request_b() -> None:
        store._local.deadline = time.monotonic() + 5
        started.wait(5)
        with store._write_lock:
            order.append("B took the lock")

    a, b = threading.Thread(target=request_a), threading.Thread(target=request_b)
    a.start()
    b.start()
    started.wait(5)
    time.sleep(0.2)  # A is now waiting in its exit for the callback, and B for the lock
    assert order == []
    release.set()
    a.join(5)
    b.join(5)
    assert order.index("cut done") < order.index("A released") and order.index("cut done") < order.index("B took the lock")


def test_a_pool_checkout_wait_is_bounded_by_the_budget(fake: Callable[[str], FakeRedis]) -> None:
    """Path 12: should anything else hold the pool's one connection, a request waits only for what is left of its budget."""
    server = fake("fast")
    store, endpoint = _store(server)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    pool = store._writer.connection_pool
    taken = pool.get_connection()  # the only connection, held outside the store
    try:
        service = memory_store.MemoryStoreService(store)
        started = time.monotonic()
        body = {"op": "lease", "project": "p-1", "owner": "host-1", "action": "acquire", "ttl_ms": 60_000}
        status, _reply = service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 0.3)
        assert status == 503 and time.monotonic() - started < 0.5
    finally:
        pool.release(taken)


def test_a_tracked_connection_neither_connects_nor_sends_after_its_deadline(fake: Callable[[str], FakeRedis]) -> None:
    """Path 16: the guard redis-py's own cleanup runs into."""
    server = fake("fast")
    client = memory_store.connect(_endpoint(server.port))
    client.ping()
    link = client.optimus_link
    link.deadline = time.monotonic() - 0.01
    with pytest.raises(memory_store.DeadlinePassed):
        link.connection.send_command("PING")
    link.connection.disconnect()
    with pytest.raises(memory_store.DeadlinePassed):
        link.connection.connect()
    assert link.connects == 1  # the refused connect never reached the handshake
    link.deadline = None
    assert client.ping() is True and link.connects == 2


_WRITES = {b"WATCH", b"GET", b"INCR", b"INCRBY", b"SET", b"MULTI", b"EXEC", b"XADD", b"PEXPIRE", b"DEL"}


def test_a_reconnect_between_checkouts_reaches_no_application_command(fake: Callable[[str], FakeRedis]) -> None:
    """The writer's socket dies right after the lease's CLIENT ID. redis-py reconnects at the next checkout; the new connection
    may authenticate, but no WATCH, GET or fence INCR reaches it."""
    server = fake("fast")
    store, endpoint = _store(server)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    before = server.connections  # the writer's existing connection is among these; anything later is a reconnect
    server.mode = "drop-after-client-id"
    service = memory_store.MemoryStoreService(store)
    body = {"op": "lease", "project": "p-1", "owner": "host-1", "action": "acquire", "ttl_ms": 60_000}
    assert service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 5) == (503, msc.error_body("MEMORY_UNAVAILABLE"))
    assert server.dropped is True
    reached = [name for number, names in server.logs.items() if number > before for name in names]
    assert not set(reached) & _WRITES, reached
    assert store.suspect is True


def test_no_command_is_sent_on_a_connection_the_store_did_not_verify(fake: Callable[[str], FakeRedis]) -> None:
    """The guard every path relies on (lease, append, replay's sync INCR, the fsync probe, the watermark, serving): a send on a
    newer generation, or one that would have to connect first, is refused before it leaves."""
    server = fake("fast")
    store, endpoint = _store(server)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    store._local.deadline = time.monotonic() + 5
    try:
        with store._writing():
            store._writer.optimus_link.connects += 1  # as if checkout had reconnected
            with pytest.raises(memory_store.Reconnected):
                store._writer.incr("omem:p:x:sync")
        store._writer.optimus_link.connects -= 1
        store._writer.optimus_link.connection.disconnect()
        with store._writing():  # a send that would reconnect first
            with pytest.raises(memory_store.Reconnected):
                store._writer.get("omem:p:x:durable")
    finally:
        store._local.deadline = None
    assert not [name for names in server.logs.values() for name in names if name == b"INCR"]


def test_connecting_takes_only_what_is_left_of_the_budget(fake: Callable[[str], FakeRedis], monkeypatch: pytest.MonkeyPatch) -> None:
    server = fake("fast")
    client = memory_store.connect(_endpoint(server.port))
    client.ping()  # the pool creates its connection on first use
    link = client.optimus_link
    link.connection.disconnect()
    seen: list[tuple[float, float]] = []
    monkeypatch.setattr(memory_store.redis.Connection, "connect_check_health",
                        lambda self, *a, **k: seen.append((self.socket_connect_timeout, self.socket_timeout)))
    link.deadline = time.monotonic() + 0.3
    time.sleep(0.2)  # a delayed checkout used most of the budget
    link.connection.connect()
    assert seen and seen[0][0] <= 0.11 and seen[0][1] <= 0.11


def test_a_pool_wait_gets_exactly_what_is_left_and_localhost_is_one_address(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("fast")
    client = memory_store.connect(_endpoint(server.port))
    memory_store.set_budget(client, 0.01)
    assert client.connection_pool.timeout == 0  # a checkout never waits: the store's locks already keep its one connection free
    local = memory_store.connect(memory_store.MemoryStoreEndpoint("localhost", server.port, "u", "p" * 32, "r"))  # pragma: allowlist secret
    assert local.connection_pool.connection_kwargs["host"] == "127.0.0.1"


def test_a_lease_whose_confirmation_stalls_is_a_timeout(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("fast")
    store, endpoint = _store(server)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    server.mode = "stall-waitaof"
    service = memory_store.MemoryStoreService(store)
    body = {"op": "lease", "project": "p-1", "owner": "host-1", "action": "acquire", "ttl_ms": 60_000}
    started = time.monotonic()
    assert service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 0.4) == (503, msc.error_body("MEMORY_TIMEOUT"))
    assert time.monotonic() - started < 0.6


def test_a_fsync_recheck_that_stalls_is_a_timeout(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("fast")
    store, endpoint = _store(server)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    store._fsync_failed = True
    server.mode = "stall-waitaof"
    service = memory_store.MemoryStoreService(store)
    event = {"event_id": "e-1", "item": "m-0123456789abcdef", "version": 1, "action": "admit", "trust": "user-authored", "status": "active",
             "kind": "fact", "scope": "s-1", "title": "t", "statement": "s", "anchors": [], "lineage": [], "valid_from_ms": 0, "valid_until_ms": 0}
    body = {"op": "append", "project": "p-1", "token": 1, "expected_version": 0, "idempotency_key": "a" * 64, "event": event}
    assert service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 0.4) == (503, msc.error_body("MEMORY_TIMEOUT"))


def test_an_unavailable_operation_never_reaches_verification(fake: Callable[[str], FakeRedis]) -> None:
    server = fake("fast")
    store, _endpoint_ = _store(server)
    checks: list[float] = []
    service = memory_store.MemoryStoreService(store, verify=checks.append)
    body = {"op": "export", "project": "p-1", "limit": 10}
    assert service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 5) == (501, msc.error_body("MEMORY_OPERATION_UNAVAILABLE"))
    assert checks == [] and server.connections == 0


def test_verification_writes_nothing_to_a_replacement_it_reconnected_to(fake: Callable[[str], FakeRedis]) -> None:
    """The original instance answers unmarked and empty, then dies right before the marker would be written; a populated,
    unmarked replacement takes the port. No SET reaches it, and verification then still refuses its unidentified data."""
    server = fake("replace-before-set")
    store, endpoint = _store(server)
    with pytest.raises(memory_store.MemoryStoreStartupError):
        store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    assert server.dropped is True
    sets = [name for names in server.logs.values() for name in names if name == b"SET"]
    assert sets == []
    with pytest.raises(memory_store.MemoryStoreStartupError) as refused:
        store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    assert refused.value.code == "MEMORY_STORE_UNIDENTIFIED_DATA"
    assert [name for names in server.logs.values() for name in names if name == b"SET"] == []


def test_pipeline_cleanup_that_times_out_finishes_inside_the_guarded_scope(fake: Callable[[str], FakeRedis]) -> None:
    """A local refusal while WATCHing leaves redis-py to send UNWATCH; its reply never comes. The cleanup ends with the budget,
    returns the connection, and leaves nothing for a finalizer to send once the guards are gone."""
    import gc

    server = fake("fast")
    store, endpoint = _store(server)
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)
    server.mode = "stall-unwatch"
    store._local.deadline = time.monotonic() + 0.4
    started = time.monotonic()
    captured = None
    try:
        with pytest.raises(RuntimeError), store._writing():
            with memory_store._pipeline(store._writer) as pipe:
                captured = pipe
                pipe.watch("omem:p:x:lease")
                raise RuntimeError("a local refusal while watching")
    finally:
        store._local.deadline = None
    assert time.monotonic() - started < 0.7
    assert captured is not None and captured.connection is None and captured.watching is False
    sent = sum(len(names) for names in server.logs.values())
    del captured, pipe
    gc.collect()
    time.sleep(0.1)
    assert sum(len(names) for names in server.logs.values()) == sent  # finalization sent nothing


def test_an_unavailable_operation_answered_after_the_deadline_is_a_timeout(fake: Callable[[str], FakeRedis],
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    server = fake("fast")
    store, _endpoint_ = _store(server)
    real_parse = msc.parse_request

    def slow_parse(raw: bytes) -> dict[str, object]:
        time.sleep(0.1)  # parsing crosses the deadline
        return real_parse(raw)

    monkeypatch.setattr(msc, "parse_request", slow_parse)
    service = memory_store.MemoryStoreService(store, verify=lambda _deadline: None)
    body = {"op": "export", "project": "p-1", "limit": 10}
    assert service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 0.05) == (503, msc.error_body("MEMORY_TIMEOUT"))
