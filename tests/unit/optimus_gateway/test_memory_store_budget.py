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
}


class FakeRedis:
    """Accepts connections; `mode` "silent" never answers, "slow-ping" answers +OK at once and PING after two seconds."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
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
        with conn:
            for command in _commands(conn):
                if self.mode == "silent":
                    self.stop.wait(10)
                    return
                name = command[0].upper()
                if self.mode == "slow-all":  # a well-formed Redis that takes 150 ms per reply
                    self.stop.wait(0.15)
                    conn.sendall(_REPLIES.get(name, b"+OK\r\n"))
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
    assert time.monotonic() - started < 0.8, stopped.value
    store.verify(endpoint.resource, deadline=time.monotonic() + 5)  # given the time, the same server verifies
    assert store.suspect is False
