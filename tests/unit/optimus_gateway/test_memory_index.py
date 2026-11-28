"""Plan 12.10 Task 2: the context-index contract and admission, without Redis. The store's behaviour is proven on the real
dedicated Redis in tests/integration/context."""

from __future__ import annotations

import http.client
import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.usage.capture_delivery import CaptureDelivery
from optimus_gateway import memory_index
from optimus_security import memory_index_contract as mic
from tests.unit.optimus_gateway.test_server import _config, _start_server
from tests.unit.usage.test_capture_delivery import _AckingStore, _capture, _fill

_SCOPE = "ab" * 32
_COVERAGE = json.dumps({"op": "coverage", "scope": _SCOPE}).encode()


class _Store:
    def __init__(self, *, release: threading.Event | None = None, error: Exception | None = None) -> None:
        self.release = release
        self.error = error
        self.calls = 0
        self.entered = threading.Condition()

    def dispatch(self, _body: dict[str, Any], *, deadline: float | None = None) -> dict[str, Any]:
        with self.entered:
            self.calls += 1
            self.entered.notify_all()
        self.deadline = deadline
        if self.release is not None:
            self.release.wait(30)  # every test that holds the store sets release; the bound only stops a hang
        if self.error is not None:
            raise self.error
        return {"status": "ok"}

    def wait_for_calls(self, count: int) -> bool:
        with self.entered:
            return self.entered.wait_for(lambda: self.calls >= count, 10)


class _Admissions:
    """Wraps a service's own waiting-slot semaphore and says when every slot is taken, so a test waits on that and not on
    a clock. Wrapping, not copying, keeps whatever the service did to its semaphore visible."""

    def __init__(self, slots: threading.BoundedSemaphore) -> None:
        self.slots = slots
        self.changed = threading.Condition()

    def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        taken = self.slots.acquire(blocking, timeout)
        with self.changed:
            self.changed.notify_all()
        return taken

    def release(self) -> None:
        self.slots.release()

    def wait_until_full(self) -> bool:
        with self.changed:
            return self.changed.wait_for(lambda: self.slots._value == 0, 10)  # type: ignore[attr-defined]


def _watch_admissions(service: Any) -> _Admissions:
    service._waiting = _Admissions(service._waiting)
    return service._waiting


def _start(target: Any, count: int, threads: list[threading.Thread]) -> None:
    for _ in range(count):
        threads.append(thread := threading.Thread(target=target))
        thread.start()


def _saturate(store: Any, admissions: _Admissions, target: Any, threads: list[threading.Thread], *, workers: int, depth: int) -> None:
    """Both workers held in the store, then every waiting slot taken; each thread joins the caller's list as it starts, so
    a failed step is still cleaned up. The waiters start only once the holders are in the store, which is after each gave
    its waiting slot back: started together, a holder between taking its worker and freeing its slot makes the last
    waiter find the queue full, and the queue never fills (#678)."""
    _start(target, workers, threads)
    assert store.wait_for_calls(workers), "both workers were not held in the store"
    _start(target, depth, threads)
    assert admissions.wait_until_full(), "the waiting requests were not all admitted"


def _service(store: _Store, **kwargs: Any) -> memory_index.IndexService:
    return memory_index.IndexService(store, **kwargs)  # type: ignore[arg-type]


def test_two_requests_serve_and_a_full_queue_is_refused_at_once() -> None:
    release = threading.Event()
    store = _Store(release=release)
    service = _service(store)
    admissions = _watch_admissions(service)
    results: list[int] = []

    def request() -> None:  # a far deadline, so the held state cannot time out while the test looks at it
        results.append(service.handle(_COVERAGE, deadline=time.monotonic() + 30)[0])

    threads: list[threading.Thread] = []
    try:
        _saturate(store, admissions, request, threads, workers=mic.SERVING_WORKERS, depth=mic.QUEUE_DEPTH)
        assert store.calls == mic.SERVING_WORKERS
        started = time.monotonic()
        refused = service.handle(_COVERAGE, deadline=time.monotonic() + 5)
        assert refused == (503, mic.error_body("INDEX_BUSY")) and time.monotonic() - started < 1
    finally:
        release.set()
        for thread in threads:
            thread.join(10)
    assert store.calls == len(threads) and results == [200] * len(threads)


def test_a_model_request_and_an_accepted_capture_batch_pass_a_saturated_index(tmp_path: Path) -> None:
    release = threading.Event()
    store = _Store(release=release)
    service = _service(store)
    admissions = _watch_admissions(service)
    ledger = _AckingStore()
    config = replace(_config(), memory_index=service, usage_store=ledger)
    server, thread, host, port = _start_server(config=config)
    capture = _capture(tmp_path)
    _fill(capture, 2)
    client = GatewayClient(settings=OptimusGatewaySettings(gateway_url=f"http://{host}:{port}", optimus_api_key=config.shared_secret))

    def post(path: str, body: bytes) -> tuple[int, dict[str, Any], float]:
        started = time.monotonic()
        connection = http.client.HTTPConnection(host, port, timeout=20)
        connection.request("POST", path, body, {"Authorization": f"Bearer {config.shared_secret}", "Content-Type": "application/json"})
        response = connection.getresponse()
        payload = json.loads(response.read() or b"{}")
        connection.close()
        return response.status, payload, time.monotonic() - started

    held: list[threading.Thread] = []
    try:
        _saturate(store, admissions, lambda: post(mic.PATH, _COVERAGE), held, workers=mic.SERVING_WORKERS, depth=mic.QUEUE_DEPTH)
        # refused at once: a probe admitted after the held requests' product 5 s deadline would also end INDEX_BUSY, later
        status, body, seconds = post(mic.PATH, _COVERAGE)
        assert (status, body) == (503, mic.error_body("INDEX_BUSY")) and seconds < 1
        status, _reply, seconds = post("/v1/responses", json.dumps({"model": "claude-haiku", "input": "hello"}).encode())
        assert status == 200 and seconds < 2
        started = time.monotonic()
        report = CaptureDelivery(capture, client).drain_once()
        assert report.failures == [] and report.committed == capture.writer.stats().confirmed_sequence > 0
        assert ledger.batches and time.monotonic() - started < 2
        assert admissions.slots._value == 0, "the index was still saturated when the batch was accepted"
    finally:
        capture.stop()
        release.set()
        for request in held:
            request.join(10)
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_an_expired_deadline_with_a_free_worker_never_reaches_the_store() -> None:
    store = _Store()
    assert _service(store).handle(_COVERAGE, deadline=time.monotonic() - 1) == (503, mic.error_body("INDEX_TIMEOUT"))
    assert store.calls == 0


def test_a_store_given_an_expired_deadline_does_no_work_at_all() -> None:
    store = memory_index.IndexStore(object(), cursor_key=b"c" * 32)  # type: ignore[arg-type]  # any use of this client would raise
    with pytest.raises(mic.IndexRequestError) as refused:
        store.dispatch({"op": "coverage", "scope": _SCOPE}, deadline=time.monotonic() - 1)
    assert refused.value.code == "INDEX_TIMEOUT"


def test_the_deadline_reaches_the_store() -> None:
    store = _Store()
    deadline = time.monotonic() + 5
    assert _service(store).handle(_COVERAGE, deadline=deadline)[0] == 200
    assert store.deadline == deadline


def test_a_request_past_its_deadline_is_refused_without_reaching_the_store() -> None:
    release = threading.Event()
    store = _Store(release=release)
    service = _service(store)
    holders = [threading.Thread(target=service.handle, args=(_COVERAGE,), kwargs={"deadline": time.monotonic() + 5}) for _ in range(mic.SERVING_WORKERS)]
    for holder in holders:
        holder.start()
    assert store.wait_for_calls(mic.SERVING_WORKERS)
    assert service.handle(_COVERAGE, deadline=time.monotonic() + 0.05) == (503, mic.error_body("INDEX_BUSY"))
    release.set()
    for holder in holders:
        holder.join(10)


def test_a_failed_startup_check_is_a_stable_refusal_and_is_tried_again() -> None:
    store = _Store()
    outcomes: list[Exception | None] = [memory_index.IndexStartupError("INDEX_REDIS_UNREACHABLE"), None]

    def verify() -> None:
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome

    service = _service(store, verify=verify)
    assert service.handle(_COVERAGE, deadline=time.monotonic() + 1) == (503, mic.error_body("INDEX_REDIS_UNREACHABLE"))
    assert store.calls == 0
    assert service.handle(_COVERAGE, deadline=time.monotonic() + 1) == (200, {"status": "ok"})


def test_a_missing_password_serves_a_stable_refusal() -> None:
    from optimus_security.memory_index_config import EmbeddingConfig, MemoryIndexConfig

    class Keyring:
        def get_password(self, _service: str, _name: str) -> None:
            return None

    embedding = EmbeddingConfig("m", "s", "r", "MIT", 8, 16, "0" * 64)
    config = MemoryIndexConfig("optimus-memory-x", "redis@sha256:" + "0" * 64, "c1", "v1", "127.0.0.1", 9, "u", "n", 64, "0" * 64, embedding)
    service = memory_index.build_index_service(config, keyring_backend=Keyring(), hmac_key=b"k" * 32)
    assert service.handle(_COVERAGE, deadline=time.monotonic() + 1) == (503, mic.error_body("INDEX_CREDENTIAL_MISSING"))


def test_the_endpoint_never_shows_its_password() -> None:
    endpoint = memory_index.IndexEndpoint("127.0.0.1", 1, "u", "hunter2", "r")  # pragma: allowlist secret - synthetic test fixture
    assert "hunter2" not in repr(endpoint)


@pytest.mark.parametrize("path", ["../x.py", "/abs.py", "a/../b.py", "C:/x.py", "a\\b.py", "", "a//b.py", "a/./b.py", "bad\x00.py"])
def test_a_path_cannot_leave_its_scope(path: str) -> None:
    with pytest.raises(mic.IndexRequestError):
        mic.relative_path(path)


@pytest.mark.parametrize("terms", [["ok", "a b"], ["*"], ["@scope:{x}"], ["UPPER"], [], ["a"] * (mic.MAX_TEXT_TERMS + 1), "alpha", [1]])
def test_a_lexical_query_cannot_become_query_syntax(terms: Any) -> None:
    with pytest.raises(mic.IndexRequestError):
        mic.query_terms(terms)


def test_a_non_finite_vector_is_refused() -> None:
    import struct

    with pytest.raises(mic.IndexRequestError):
        mic.decode_vector(mic.encode_vector(struct.pack("<2f", 1.0, float("nan"))), 2)
    with pytest.raises(mic.IndexRequestError):
        mic.decode_vector("not base64!!", 2)
    assert mic.decode_vector(mic.encode_vector(struct.pack("<2f", 1.0, 2.0)), 2) == struct.pack("<2f", 1.0, 2.0)


def test_an_embedding_identity_may_name_its_model_and_revision() -> None:
    """A real configured identity, which a stand-in embedder's plain name did not exercise."""
    body = {"op": "generation", "scope": _SCOPE, "action": "open", "embedding": "BAAI/bge-small-en-v1.5@aa8f8b060edb", "dimensions": 384, "schema_version": 1}
    assert mic.parse_request(json.dumps(body).encode())["embedding"] == body["embedding"]
    with pytest.raises(mic.IndexRequestError):
        mic.parse_request(json.dumps({**body, "embedding": "a b"}).encode())


def test_progress_cannot_carry_a_payload() -> None:
    body = {"op": "cursor", "scope": _SCOPE, "action": "set", "token": 1, "value": {"phase": "embedding", "source": "print('x')"}}
    with pytest.raises(mic.IndexRequestError):
        mic.parse_request(json.dumps(body).encode())


@pytest.mark.parametrize("field", ["body", "content", "text", "raw", "source"])
def test_a_record_cannot_carry_a_body_field(field: str) -> None:
    record = {"id": "0" * 64, "kind": "file", "path": "a.py", "path_id": "1" * 64, "file_hash": "2" * 64, "language": "python", "terms": "a", field: "x"}
    body = {"op": "batch", "scope": _SCOPE, "token": 1, "epoch": 1, "records": [record]}
    with pytest.raises(mic.IndexRequestError):
        mic.parse_request(json.dumps(body).encode())
