"""Plan 12.11 Task 1: the memory-store route, its contract, admission and start-up checks, without Redis. The checks are proven on
the real dedicated Redis in tests/integration/memory."""

from __future__ import annotations

import http.client
import json
import threading
import time
from dataclasses import replace
from typing import Any

import pytest

from optimus_gateway import memory_store
from optimus_security import memory_store_contract as msc
from optimus_security.memory_store_config import MemoryStoreConfig
from tests.unit.optimus_gateway.test_server import _config, _start_server

_CAPS = json.dumps({"op": "capabilities"}).encode()


class _Store:
    def __init__(self, *, release: threading.Event | None = None, error: Exception | None = None) -> None:
        self.release = release
        self.error = error
        self.calls = 0

    def take_suspect(self) -> bool:
        return False

    def dispatch(self, _body: dict[str, Any], *, deadline: float | None = None) -> dict[str, Any]:
        self.calls += 1
        if self.release is not None:
            self.release.wait(5)
        if self.error is not None:
            raise self.error
        return {"status": "ok"}

    def forget(self) -> None:
        self.forgotten = getattr(self, "forgotten", 0) + 1


def _service(store: _Store, **kwargs: Any) -> memory_store.MemoryStoreService:
    return memory_store.MemoryStoreService(store, **kwargs)  # type: ignore[arg-type]


class _Redis:
    """The few replies verification and capabilities read; any other command fails the test."""

    def __init__(self, *, aof: bool = True, policy: str = "noeviction", stored: bytes | None = None, keys: int = 0,
                 waitaof: Any = (1, 0), used: int = 10 * 1024 * 1024) -> None:
        self.aof, self.policy, self.stored, self.keys, self.waitaof, self.used = aof, policy, stored, keys, waitaof, used
        self.writes: list[tuple[str, str]] = []

    def info(self, section: str) -> dict[str, Any]:
        sections: dict[str, dict[str, Any]] = {"persistence": {"aof_enabled": int(self.aof)},
                                               "memory": {"maxmemory_policy": self.policy, "used_memory": self.used}}
        return sections[section]

    def get(self, key: str) -> bytes | None:
        assert key == "omem:resource"
        return self.stored

    def dbsize(self) -> int:
        return self.keys

    def set(self, key: str, value: str, nx: bool) -> None:
        assert key == "omem:resource" and nx
        self.writes.append((key, value))
        if self.stored is None:
            self.stored = value.encode()

    def execute_command(self, *args: Any) -> Any:
        assert args[:3] == ("WAITAOF", 1, 0)
        return list(self.waitaof) if isinstance(self.waitaof, tuple) else self.waitaof

    def pipeline(self, transaction: bool = True) -> _Probe:
        assert not transaction
        return _Probe(self)


class _Probe:
    """The fsync probe's one-connection pipeline: INCR of the probe key, then WAITAOF."""

    def __init__(self, client: _Redis) -> None:
        self.client, self.queued = client, []  # type: list[str]

    def incr(self, key: str) -> None:
        assert key == "omem:fsync-probe"
        self.queued.append("incr")

    def execute_command(self, *args: Any) -> None:
        assert args[:3] == ("WAITAOF", 1, 0)
        self.queued.append("waitaof")

    def execute(self) -> list[Any]:
        assert self.queued == ["incr", "waitaof"], "the probe must write before it waits"
        self.client.probes = getattr(self.client, "probes", 0) + 1
        return [1, self.client.execute_command("WAITAOF", 1, 0, 0)]


def _refusal(client: _Redis, resource: str = "optimus-memory-store-x") -> str | None:
    try:
        memory_store.verify_resource(client, resource)  # type: ignore[arg-type]
    except memory_store.MemoryStoreStartupError as exc:
        return exc.code
    return None


def test_an_empty_store_is_marked_as_the_provisioned_resource() -> None:
    client = _Redis()
    assert _refusal(client) is None
    assert client.writes == [("omem:resource", "optimus-memory-store-x")]


def test_a_store_already_marked_as_ours_is_served_without_writing() -> None:
    client = _Redis(stored=b"optimus-memory-store-x", keys=5)
    assert _refusal(client) is None and client.writes == []


@pytest.mark.parametrize(
    ("client", "code"),
    [(_Redis(aof=False), "MEMORY_STORE_CONFIGURATION_UNEXPECTED"),
     (_Redis(policy="allkeys-lru"), "MEMORY_STORE_CONFIGURATION_UNEXPECTED"),
     (_Redis(keys=3), "MEMORY_STORE_UNIDENTIFIED_DATA"),
     (_Redis(stored=b"optimus-memory-store-other"), "MEMORY_STORE_RESOURCE_MISMATCH"),
     (_Redis(waitaof=(0, 0)), "MEMORY_STORE_FSYNC_UNCONFIRMED"),
     (_Redis(waitaof="OK"), "MEMORY_STORE_WAITAOF_UNEXPECTED")],
    ids=["aof-off", "evicting", "populated-unmarked", "another-resource", "no-fsync", "odd-waitaof"],
)
def test_a_store_that_cannot_keep_acknowledged_writes_is_refused(client: _Redis, code: str) -> None:
    assert _refusal(client) == code


def test_populated_unidentified_data_is_never_marked() -> None:
    client = _Redis(keys=3)
    _refusal(client)
    assert client.writes == []


def test_capabilities_reports_only_counts_and_flags() -> None:
    store = memory_store.MemoryStore(_Redis(used=100 * 1024 * 1024), _Redis(), admission_ceiling_mb=384, cursor_key=b"k")  # type: ignore[arg-type]
    reply = store.dispatch(msc.parse_request(_CAPS))
    assert reply == {"status": "ok", "schema_version": 1, "durable": True, "admitting": True, "used_mb": 100, "admission_ceiling_mb": 384}
    full = memory_store.MemoryStore(_Redis(used=384 * 1024 * 1024), _Redis(), admission_ceiling_mb=384, cursor_key=b"k")  # type: ignore[arg-type]
    assert full.dispatch(msc.parse_request(_CAPS))["admitting"] is False


@pytest.mark.parametrize("body", [b"", b"[]", b"not json", b'{"op": "flushall"}', b'{"op": "capabilities", "key": "omem:*"}', b"\xff"])
def test_only_closed_operations_with_exact_fields_are_accepted(body: bytes) -> None:
    with pytest.raises(msc.MemoryRequestError):
        msc.parse_request(body)


def test_two_requests_serve_and_a_full_queue_is_refused_at_once() -> None:
    release = threading.Event()
    store = _Store(release=release)
    service = _service(store)
    threads = [threading.Thread(target=service.handle, args=(_CAPS,), kwargs={"deadline": time.monotonic() + 5})
               for _ in range(msc.SERVING_WORKERS + msc.QUEUE_DEPTH)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 5
    while store.calls < msc.SERVING_WORKERS and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.05)
    started = time.monotonic()
    assert service.handle(_CAPS, deadline=time.monotonic() + 5) == (503, msc.error_body("MEMORY_BUSY"))
    assert time.monotonic() - started < 1
    release.set()
    for thread in threads:
        thread.join(10)
    assert store.calls == len(threads)


def test_an_expired_deadline_never_reaches_the_store() -> None:
    store = _Store()
    assert _service(store).handle(_CAPS, deadline=time.monotonic() - 1) == (503, msc.error_body("MEMORY_TIMEOUT"))
    assert store.calls == 0


def test_a_failed_startup_check_is_a_stable_refusal_and_is_tried_again() -> None:
    store = _Store()
    outcomes: list[Exception | None] = [memory_store.MemoryStoreStartupError("MEMORY_STORE_UNREACHABLE"), None]

    def verify() -> None:
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome

    service = _service(store, verify=verify)
    assert service.handle(_CAPS, deadline=time.monotonic() + 1) == (503, msc.error_body("MEMORY_STORE_UNREACHABLE"))
    assert store.calls == 0
    assert service.handle(_CAPS, deadline=time.monotonic() + 1) == (200, {"status": "ok"})


def test_an_outage_makes_the_store_prove_itself_again() -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    store = _Store(error=RedisConnectionError("gone"))
    checks: list[int] = []
    service = _service(store, verify=lambda: checks.append(1))
    assert service.handle(_CAPS, deadline=time.monotonic() + 1) == (503, msc.error_body("MEMORY_UNAVAILABLE"))
    store.error = None
    assert service.handle(_CAPS, deadline=time.monotonic() + 1)[0] == 200
    assert len(checks) == 2


def _config_for(port: int = 9) -> MemoryStoreConfig:
    return MemoryStoreConfig("optimus-memory-store-x", "redis@sha256:" + "0" * 64, "c1", "v1", "127.0.0.1", port, "u", "n", 512, 384, "0" * 64)


def test_a_missing_password_serves_a_stable_refusal() -> None:
    class Keyring:
        def get_password(self, _service: str, _name: str) -> None:
            return None

    service = memory_store.build_memory_store_service(_config_for(), keyring_backend=Keyring(), hmac_key=b"k" * 32)
    assert service.handle(_CAPS, deadline=time.monotonic() + 1) == (503, msc.error_body("MEMORY_STORE_CREDENTIAL_MISSING"))


def test_the_endpoint_never_shows_its_password() -> None:
    endpoint = memory_store.MemoryStoreEndpoint("127.0.0.1", 1, "u", "hunter2", "r")  # pragma: allowlist secret - synthetic test fixture
    assert "hunter2" not in repr(endpoint)


def _post(host: str, port: int, body: bytes, *, token: str | None, path: str = msc.PATH) -> tuple[int, dict[str, Any]]:
    connection = http.client.HTTPConnection(host, port, timeout=10)
    headers = {"Content-Type": "application/json", **({} if token is None else {"Authorization": f"Bearer {token}"})}
    connection.request("POST", path, body, headers)
    response = connection.getresponse()
    payload = json.loads(response.read() or b"{}")
    connection.close()
    return response.status, payload


def _declared_only(host: str, port: int, length: int, *, token: str) -> tuple[int, dict[str, Any]]:
    """Send only the request head: the route refuses an oversized body before reading it, so sending one races the reset."""
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.putrequest("POST", msc.PATH)
    for name, value in {"Content-Type": "application/json", "Content-Length": str(length), "Authorization": f"Bearer {token}"}.items():
        connection.putheader(name, value)
    connection.endheaders()
    response = connection.getresponse()
    payload = json.loads(response.read() or b"{}")
    connection.close()
    return response.status, payload


def test_the_route_authenticates_first_and_serves_the_closed_operation() -> None:
    store = _Store()
    config = replace(_config(), memory_store=_service(store))
    server, thread, host, port = _start_server(config=config)
    try:
        assert _post(host, port, _CAPS, token=None) == (401, msc.error_body("UNAUTHORIZED"))
        assert _post(host, port, _CAPS, token="wrong") == (401, msc.error_body("UNAUTHORIZED"))
        assert store.calls == 0
        assert _post(host, port, b'{"op": "nope"}', token=config.shared_secret) == (400, msc.error_body("REQUEST_INVALID"))
        assert _declared_only(host, port, msc.MAX_REQUEST_BYTES + 1, token=config.shared_secret) == (413, msc.error_body("REQUEST_TOO_LARGE"))
        assert _post(host, port, _CAPS, token=config.shared_secret) == (200, {"status": "ok"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_without_a_configured_store_the_route_does_not_exist() -> None:
    server, thread, host, port = _start_server(config=_config())
    try:
        status, _body = _post(host, port, _CAPS, token=_config().shared_secret)
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
