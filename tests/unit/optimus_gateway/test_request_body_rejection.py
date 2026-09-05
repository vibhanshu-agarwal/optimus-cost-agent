"""P11-FU-6: bounded early POST rejection on unknown / unconfigured-tool routes.

The primary regression is deterministic and event-driven: an observer proxies the handler's request
stream and its JSON writer, and the raw loopback client releases body fragments only when the server
asks for them. On the uncorrected handler the first observed event is ``response_attempted`` with zero
body bytes consumed, which is the intended RED. No sleep is used to make any race likely.

Harness guarantees (Task 1 review corrections):
* teardown is unconditional and bounded, and lifecycle problems are reported even when the scenario
  itself failed, alongside the original failure;
* unexpected exceptions in the request handler, the serve thread or the observer are captured and
  surface in the test result (``handler_finished`` only means the handler terminated);
* legal short reads are accepted: consumption is tracked cumulatively under one fixed deadline and
  one client ``send`` is never assumed to equal one server read.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

import optimus_gateway.server as gw_server
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import OptimusGatewayHandler, serve_gateway
from optimus_gateway.upstream_client import ProviderMessageResult

REJECTED_PATHS = (
    "/v1/tools/web/search",
    "/v1/tools/web/extract",
    "/v1/tools/package/lookup",
    "/v1/tools/security/advisory",
    "/v1/unknown",
)
# Opaque, invalid JSON and invalid UTF-8: the rejection path must discard without parsing.
OPAQUE_BODY = b"{not-json\x00\xff"
CHOREOGRAPHY_DEADLINE_SECONDS = 10.0
JOIN_SECONDS = 10.0
SHARED_SECRET = "http-test-secret"  # pragma: allowlist secret - shared test fixture token, not a credential


def test_gateway_server_import_resolves_to_this_checkout() -> None:
    """Guard against the editable install pointing at another checkout."""
    repo_root = Path(__file__).resolve().parents[3]
    assert Path(gw_server.__file__).resolve().is_relative_to(repo_root / "src"), gw_server.__file__


def test_protocol_version_is_pinned_to_http_1_0() -> None:
    """The stdlib auto-answers Expect: 100-continue only from HTTP/1.1; the rejection policy relies on this pin."""
    assert OptimusGatewayHandler.protocol_version == "HTTP/1.0"


# --------------------------------------------------------------------------------------- fixtures


class _NeverCalledUpstreamClient:
    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:  # pragma: no cover - guard
        raise AssertionError("upstream client must not be invoked on a rejected route")


def _config() -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        shared_secret=SHARED_SECRET,
        provider="openrouter",
        provider_api_key="or-test",  # pragma: allowlist secret - fake provider key for the fixture
        base_url="https://openrouter.ai/api/v1",
    )


@dataclass(frozen=True)
class _Event:
    kind: str
    consumed: int
    status: int | None = None
    detail: str = ""


@dataclass
class _Observer:
    events: queue.Queue[_Event] = field(default_factory=queue.Queue)
    body_bytes_consumed: int = 0
    body_read_calls: int = 0
    handler_threads: list[threading.Thread] = field(default_factory=list)
    status_lines: list[int] = field(default_factory=list)
    background_errors: list[str] = field(default_factory=list)
    cleanup_notes: list[str] = field(default_factory=list)

    def publish(self, kind: str, *, status: int | None = None, detail: str = "") -> None:
        self.events.put(_Event(kind, self.body_bytes_consumed, status, detail))

    def record_error(self, origin: str, exc: BaseException) -> None:
        self.background_errors.append(f"{origin}: {exc!r}\n{traceback.format_exc()}")

    def next_event(self, *, expecting: str, deadline: float) -> _Event:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            return self.events.get(timeout=remaining)
        except queue.Empty:
            raise AssertionError(f"no handler event before the choreography deadline while expecting {expecting}") from None


class _ObservedReader:
    """Proxy for the handler's buffered request stream; header reads (readline) are not body reads.

    ``max_body_read`` deliberately caps every body read so short reads can be forced independently of
    the loopback stack's packetization.
    """

    def __init__(self, inner: Any, observer: _Observer, *, max_body_read: int | None = None) -> None:
        self._inner = inner
        self._observer = observer
        self._max_body_read = max_body_read

    def _body_read(self, method: str, size: int) -> bytes:
        if self._max_body_read is not None and (size < 0 or size > self._max_body_read):
            size = self._max_body_read
        self._observer.body_read_calls += 1
        self._observer.publish("body_read_requested", detail=f"{method}({size})")
        data = getattr(self._inner, method)(size)
        self._observer.body_bytes_consumed += len(data)
        return data

    def read(self, size: int = -1) -> bytes:
        return self._body_read("read", size)

    def read1(self, size: int = -1) -> bytes:
        return self._body_read("read1", size)

    def readline(self, *args: Any, **kwargs: Any) -> bytes:
        return self._inner.readline(*args, **kwargs)

    def close(self) -> None:
        self._inner.close()

    @property
    def closed(self) -> bool:
        return bool(self._inner.closed)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _install_observer(monkeypatch: pytest.MonkeyPatch, observer: _Observer, *, max_body_read: int | None = None) -> None:
    original_setup = OptimusGatewayHandler.setup
    original_handle = OptimusGatewayHandler.handle
    original_send_json = OptimusGatewayHandler._send_json
    original_finish = OptimusGatewayHandler.finish
    original_send_response_only = OptimusGatewayHandler.send_response_only

    def send_response_only(self: OptimusGatewayHandler, code: int, message: Any = None) -> None:
        observer.status_lines.append(int(code))  # every status line the server writes, interim 100 included
        original_send_response_only(self, code, message)

    monkeypatch.setattr(OptimusGatewayHandler, "send_response_only", send_response_only)

    def setup(self: OptimusGatewayHandler) -> None:
        original_setup(self)
        observer.handler_threads.append(threading.current_thread())
        self.rfile = _ObservedReader(self.rfile, observer, max_body_read=max_body_read)  # type: ignore[assignment]

    def handle(self: OptimusGatewayHandler) -> None:
        try:
            original_handle(self)
        except BaseException as exc:  # captured for the test result, then re-raised unchanged
            observer.record_error("request handler", exc)
            raise

    def _send_json(self: OptimusGatewayHandler, status: Any, body: Any, *args: Any, **kwargs: Any) -> None:
        observer.publish("response_attempted", status=int(status))
        original_send_json(self, status, body, *args, **kwargs)

    def finish(self: OptimusGatewayHandler) -> None:
        try:
            original_finish(self)
        except BaseException as exc:
            observer.record_error("handler finish", exc)
            raise
        finally:
            observer.publish("handler_finished")  # termination, not success

    monkeypatch.setattr(OptimusGatewayHandler, "setup", setup)
    monkeypatch.setattr(OptimusGatewayHandler, "handle", handle)
    monkeypatch.setattr(OptimusGatewayHandler, "_send_json", _send_json)
    monkeypatch.setattr(OptimusGatewayHandler, "finish", finish)


def _start_server(observer: _Observer) -> tuple[Any, threading.Thread, str, int]:
    server = serve_gateway(config=_config(), upstream_client=_NeverCalledUpstreamClient())

    def serve() -> None:
        try:
            server.serve_forever()
        except BaseException as exc:  # pragma: no cover - surfaced by teardown
            observer.record_error("serve thread", exc)
            raise

    thread = threading.Thread(target=serve, daemon=True, name="fu6-serve")
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def _raw_headers(path: str, *, content_length: int | None, extra: tuple[tuple[str, str], ...] = ()) -> bytes:
    lines = [
        f"POST {path} HTTP/1.1",
        "Host: 127.0.0.1",
        f"Authorization: Bearer {SHARED_SECRET}",
        "Content-Type: application/json",
    ]
    if content_length is not None:
        lines.append(f"Content-Length: {content_length}")
    lines.extend(f"{name}: {value}" for name, value in extra)
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def _read_response(client: socket.socket) -> tuple[int, Any]:
    chunks: list[bytes] = []
    while True:
        chunk = client.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    raw = b"".join(chunks)
    head, _, body = raw.partition(b"\r\n\r\n")
    status_line = head.split(b"\r\n", 1)[0].decode("iso-8859-1")
    status = int(status_line.split(" ")[1])
    text = body.decode("utf-8")
    return status, (json.loads(text) if text else None)


def _teardown(
    client: socket.socket | None,
    server: Any,
    thread: threading.Thread,
    observer: _Observer,
    *,
    join_seconds: float,
) -> list[str]:
    """Unconditional, bounded teardown. Returns lifecycle/background problems instead of raising."""
    problems: list[str] = []
    if client is not None:
        try:
            client.close()
        except OSError as exc:  # client-side cleanup only: recorded, never asserted
            observer.cleanup_notes.append(f"client close raised {exc!r}")
    shutdown_errors: list[str] = []

    def shutdown_worker() -> None:
        try:
            server.shutdown()
        except BaseException as exc:  # a raising worker is no longer alive; record it explicitly
            shutdown_errors.append(f"server.shutdown() raised {exc!r}")

    stopper = threading.Thread(target=shutdown_worker, daemon=True, name="fu6-shutdown")
    stopper.start()
    stopper.join(join_seconds)
    if stopper.is_alive():
        problems.append("server.shutdown() did not return within the bound")
    problems.extend(shutdown_errors)
    try:
        server.server_close()
    except Exception as exc:  # never let a secondary close failure replace the primary result
        problems.append(f"server_close raised {exc!r}")
    thread.join(join_seconds)
    if thread.is_alive():
        problems.append("serve thread did not exit")
    for handler_thread in observer.handler_threads:
        handler_thread.join(join_seconds)
    alive = [t.name for t in observer.handler_threads if t.is_alive()]
    if alive:
        problems.append(f"request handler thread still alive: {alive}")
    problems.extend(observer.background_errors)
    observer.cleanup_notes.append(f"serve_thread_alive={thread.is_alive()} handler_threads_alive={alive}")
    print("CLEANUP " + "; ".join(observer.cleanup_notes))
    return problems


def _run_scenario(
    observer: _Observer,
    scenario: Callable[[socket.socket | None], None],
    *,
    connect: bool = True,
    join_seconds: float = JOIN_SECONDS,
) -> None:
    """Run ``scenario`` against a fresh observed server; lifecycle checks run on every exit path."""
    server, thread, host, port = _start_server(observer)
    client: socket.socket | None = None
    try:
        if connect:
            client = socket.create_connection((host, port), timeout=CHOREOGRAPHY_DEADLINE_SECONDS)
        scenario(client)
    except BaseException as primary:
        problems = _teardown(client, server, thread, observer, join_seconds=join_seconds)
        if problems:
            raise AssertionError(f"{type(primary).__name__}: {primary}; additionally during teardown: {problems}") from primary
        raise
    problems = _teardown(client, server, thread, observer, join_seconds=join_seconds)
    assert not problems, problems
    assert observer.handler_threads, "no request handler thread was observed"


def _await_consumption(observer: _Observer, *, target: int, total: int, deadline: float) -> _Event:
    """Accept legal short reads: wait until cumulative consumption reaches ``target`` via read requests."""
    seen = -1
    while True:
        event = observer.next_event(expecting=f"body reads reaching {target} consumed", deadline=deadline)
        if event.kind == "response_attempted":
            pytest.fail(f"response attempted with {event.consumed} of {total} body bytes consumed")
        assert event.kind == "body_read_requested", event
        assert event.consumed > seen, f"consumption must increase between read requests: {event}"
        assert event.consumed <= target, f"server consumed more than the client sent: {event}"
        seen = event.consumed
        if event.consumed == target:
            return event


def _await_response(observer: _Observer, *, total: int, deadline: float) -> _Event:
    seen = -1
    while True:
        event = observer.next_event(expecting="response_attempted", deadline=deadline)
        if event.kind == "body_read_requested":
            assert seen < event.consumed <= total, f"unexpected read request: {event}"
            seen = event.consumed
            continue
        assert event.kind == "response_attempted", event
        return event


def _await_finished(observer: _Observer, *, deadline: float) -> None:
    finished = observer.next_event(expecting="handler_finished", deadline=deadline)
    assert finished.kind == "handler_finished", finished


# --------------------------------------------------------------------------------------- primary regression


@pytest.mark.parametrize("path", REJECTED_PATHS)
def test_rejected_route_consumes_declared_body_before_404(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    observer = _Observer()
    _install_observer(monkeypatch, observer)
    total = len(OPAQUE_BODY)

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + CHOREOGRAPHY_DEADLINE_SECONDS
        client.sendall(_raw_headers(path, content_length=total))

        event = observer.next_event(expecting="body_read_requested", deadline=deadline)
        if event.kind == "response_attempted":
            pytest.fail(
                f"response attempted before declared body was consumed: path={path} "
                f"status={event.status} consumed={event.consumed} of {total}"
            )
        assert event.kind == "body_read_requested", event

        client.sendall(OPAQUE_BODY[:3])
        _await_consumption(observer, target=3, total=total, deadline=deadline)

        client.sendall(OPAQUE_BODY[3:])
        event = _await_response(observer, total=total, deadline=deadline)
        assert event.consumed == total, f"response attempted with {event.consumed} of {total} body bytes consumed"
        assert event.status == 404

        status, body = _read_response(client)
        assert status == 404, path
        assert body == {"error": "not found"}
        _await_finished(observer, deadline=deadline)

    _run_scenario(observer, scenario)


def test_rejected_route_tolerates_forced_one_byte_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short-read control: every body read is capped at one byte, independent of packetization."""
    observer = _Observer()
    _install_observer(monkeypatch, observer, max_body_read=1)
    total = len(OPAQUE_BODY)
    path = "/v1/tools/web/search"

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + CHOREOGRAPHY_DEADLINE_SECONDS
        client.sendall(_raw_headers(path, content_length=total))
        event = observer.next_event(expecting="body_read_requested", deadline=deadline)
        if event.kind == "response_attempted":
            pytest.fail(
                f"response attempted before declared body was consumed: path={path} "
                f"status={event.status} consumed={event.consumed} of {total}"
            )
        client.sendall(OPAQUE_BODY)
        event = _await_response(observer, total=total, deadline=deadline)
        assert event.consumed == total, f"response attempted with {event.consumed} of {total} body bytes consumed"
        assert observer.body_read_calls == total, "one-byte reads must be requested once per body byte"
        status, body = _read_response(client)
        assert (status, body) == (404, {"error": "not found"})
        _await_finished(observer, deadline=deadline)

    _run_scenario(observer, scenario)


# --------------------------------------------------------------------------------------- no-body controls


@pytest.mark.parametrize("path", ("/v1/tools/web/search", "/v1/unknown"))
@pytest.mark.parametrize("content_length", (0, None), ids=("content-length-0", "no-content-length"))
def test_rejected_route_without_body_responds_immediately(monkeypatch: pytest.MonkeyPatch, path: str, content_length: int | None) -> None:
    observer = _Observer()
    _install_observer(monkeypatch, observer)

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + CHOREOGRAPHY_DEADLINE_SECONDS
        client.sendall(_raw_headers(path, content_length=content_length))
        event = observer.next_event(expecting="response_attempted", deadline=deadline)
        assert event.kind == "response_attempted", event
        assert event.consumed == 0
        assert event.status == 404
        status, body = _read_response(client)
        assert (status, body) == (404, {"error": "not found"})
        _await_finished(observer, deadline=deadline)
        assert observer.body_read_calls == 0, "a zero-length request must not trigger a body read"

    _run_scenario(observer, scenario)


# --------------------------------------------------------------------------------------- harness self-checks


def test_harness_reports_lifecycle_failure_alongside_primary_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing scenario must still run lifecycle checks, and a stuck handler thread must be reported."""
    observer = _Observer()
    _install_observer(monkeypatch, observer)
    release = threading.Event()
    stuck = threading.Thread(target=release.wait, daemon=True, name="simulated-stuck-handler")

    def scenario(client: socket.socket | None) -> None:
        stuck.start()
        observer.handler_threads.append(stuck)
        raise AssertionError("primary scenario failure")

    try:
        with pytest.raises(AssertionError) as excinfo:
            _run_scenario(observer, scenario, connect=False, join_seconds=0.2)
    finally:
        release.set()
        stuck.join(JOIN_SECONDS)
    assert not stuck.is_alive(), "the simulated stuck handler must have stopped after release"
    message = str(excinfo.value)
    assert "primary scenario failure" in message
    assert "simulated-stuck-handler" in message
    assert isinstance(excinfo.value.__cause__, AssertionError)
    assert "primary scenario failure" in str(excinfo.value.__cause__)


def test_teardown_reports_injected_shutdown_worker_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shutdown worker that raises is no longer alive; its exception must still reach the problem report."""
    observer = _Observer()
    _install_observer(monkeypatch, observer)
    server, thread, host, port = _start_server(observer)
    original_shutdown = server.shutdown

    def shutdown_then_raise() -> None:
        original_shutdown()  # real shutdown still happens, so no stray server survives this control
        raise RuntimeError("injected shutdown worker exception")

    server.shutdown = shutdown_then_raise  # type: ignore[method-assign]
    problems = _teardown(None, server, thread, observer, join_seconds=JOIN_SECONDS)
    assert any("injected shutdown worker exception" in problem for problem in problems), problems
    assert not thread.is_alive(), "serve thread must have stopped"


def test_run_scenario_retains_primary_failure_when_server_close_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-OSError secondary close failure is exposed alongside, never instead of, the primary failure."""
    observer = _Observer()
    _install_observer(monkeypatch, observer)
    original_close = ThreadingHTTPServer.server_close

    def close_then_raise(self: ThreadingHTTPServer) -> None:
        original_close(self)
        raise RuntimeError("injected server_close failure")

    monkeypatch.setattr(ThreadingHTTPServer, "server_close", close_then_raise)

    def scenario(client: socket.socket | None) -> None:
        raise AssertionError("primary scenario failure")

    with pytest.raises(AssertionError) as excinfo:
        _run_scenario(observer, scenario, connect=False)
    message = str(excinfo.value)
    assert "primary scenario failure" in message
    assert "injected server_close failure" in message
    assert "primary scenario failure" in str(excinfo.value.__cause__)


def test_harness_propagates_handler_exception_after_response_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    """An exception raised after the response was observed must surface in the test result."""
    observer = _Observer()
    _install_observer(monkeypatch, observer)
    observed_send_json = OptimusGatewayHandler._send_json

    def failing_send_json(self: OptimusGatewayHandler, status: Any, body: Any, *args: Any, **kwargs: Any) -> None:
        observed_send_json(self, status, body, *args, **kwargs)
        raise RuntimeError("injected after response observation")

    monkeypatch.setattr(OptimusGatewayHandler, "_send_json", failing_send_json)

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + CHOREOGRAPHY_DEADLINE_SECONDS
        client.sendall(_raw_headers("/v1/unknown", content_length=0))
        event = observer.next_event(expecting="response_attempted", deadline=deadline)
        assert event.kind == "response_attempted", event
        status, body = _read_response(client)
        assert (status, body) == (404, {"error": "not found"})
        _await_finished(observer, deadline=deadline)

    with pytest.raises(AssertionError) as excinfo:
        _run_scenario(observer, scenario)
    assert "injected after response observation" in str(excinfo.value)
    assert "request handler" in str(excinfo.value)


# --------------------------------------------------------------------------------------- production defaults


def test_rejected_post_production_defaults_are_pinned() -> None:
    assert gw_server._REJECTED_POST_MAX_BYTES == 65_536
    assert gw_server._REJECTED_POST_BODY_SECONDS == 2.0
    assert gw_server._REJECTED_POST_WRITE_SECONDS == 2.0


# --------------------------------------------------------------------------------------- framing matrix (server-side oracles)


def _drain_events(observer: _Observer) -> list[_Event]:
    drained: list[_Event] = []
    while True:
        try:
            drained.append(observer.events.get_nowait())
        except queue.Empty:
            return drained


def _raw_request(path: str, header_lines: tuple[str, ...]) -> bytes:
    lines = [f"POST {path} HTTP/1.1", "Host: 127.0.0.1", f"Authorization: Bearer {SHARED_SECRET}", *header_lines]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


def _run_header_only_rejection(
    monkeypatch: pytest.MonkeyPatch,
    raw_request: bytes,
    *,
    expected_status: int,
    expected_error: str,
) -> None:
    """Server-side oracle: status selection, zero body reads, no dispatch, handler completion.

    The client response is read only as supplementary evidence; receipt of an error body is never
    required for a rejected request on Windows.
    """
    observer = _Observer()
    _install_observer(monkeypatch, observer)

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + CHOREOGRAPHY_DEADLINE_SECONDS
        client.sendall(raw_request)
        event = observer.next_event(expecting="response_attempted", deadline=deadline)
        assert event.kind == "response_attempted", event
        assert event.status == expected_status
        assert event.consumed == 0
        assert observer.body_read_calls == 0, "rejection must not read the body"
        try:
            status, body = _read_response(client)
        except OSError as exc:  # supplementary only
            observer.cleanup_notes.append(f"supplementary response read failed: {exc!r}")
        else:
            assert status == expected_status
            assert body == {"error": expected_error}
        _await_finished(observer, deadline=deadline)
        assert not [e for e in _drain_events(observer) if e.kind == "response_attempted"], "one response attempt only"

    _run_scenario(observer, scenario)


_INVALID_FRAMING = (400, "invalid request framing")
_TOO_LARGE = (413, "request body too large")
_ENORMOUS_DECIMAL = "9" * 400
_FRAMING_CASES: dict[str, tuple[tuple[str, ...], int, str]] = {
    "cl-and-te": (("Content-Length: 11", "Transfer-Encoding: chunked"), *_INVALID_FRAMING),
    "duplicate-cl-equal": (("Content-Length: 11", "Content-Length: 11"), *_INVALID_FRAMING),
    "duplicate-cl-different": (("Content-Length: 11", "Content-Length: 12"), *_INVALID_FRAMING),
    "cl-comma-list": (("Content-Length: 11, 11",), *_INVALID_FRAMING),
    "cl-negative": (("Content-Length: -1",), *_INVALID_FRAMING),
    "cl-plus-sign": (("Content-Length: +11",), *_INVALID_FRAMING),
    "cl-alphabetic": (("Content-Length: eleven",), *_INVALID_FRAMING),
    "cl-empty": (("Content-Length: ",), *_INVALID_FRAMING),
    "cl-non-ascii-digit": (("Content-Length: ١١",), *_INVALID_FRAMING),
    "cl-enormous-decimal": ((f"Content-Length: {_ENORMOUS_DECIMAL}",), *_TOO_LARGE),
    "cl-over-cap-by-one": (("Content-Length: 65537",), *_TOO_LARGE),
    "te-alone-chunked": (("Transfer-Encoding: chunked",), 501, "transfer encoding not supported"),
    "expect-100-continue": (("Content-Length: 11", "Expect: 100-continue"), 417, "expectation failed"),
    "expect-other": (("Content-Length: 11", "Expect: something-else"), 417, "expectation failed"),
}


@pytest.mark.parametrize("case", sorted(_FRAMING_CASES))
def test_rejected_route_framing_matrix(monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    header_lines, status, error = _FRAMING_CASES[case]
    _run_header_only_rejection(
        monkeypatch, _raw_request("/v1/tools/web/search", header_lines), expected_status=status, expected_error=error
    )


def _run_expect_case(monkeypatch: pytest.MonkeyPatch, *, inject_interim_100: bool) -> None:
    """Server-side oracle for Expect: the only status line written is 417; no body read; no dispatch."""
    observer = _Observer()
    _install_observer(monkeypatch, observer)
    if inject_interim_100:
        original_reject = OptimusGatewayHandler._reject_unhandled_post

        def reject_after_interim_100(self: OptimusGatewayHandler) -> None:
            self.send_response_only(100)
            self.end_headers()
            original_reject(self)

        monkeypatch.setattr(OptimusGatewayHandler, "_reject_unhandled_post", reject_after_interim_100)

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + CHOREOGRAPHY_DEADLINE_SECONDS
        client.sendall(_raw_request("/v1/unknown", ("Content-Length: 11", "Expect: 100-continue")))
        event = observer.next_event(expecting="response_attempted", deadline=deadline)
        assert event.kind == "response_attempted", event
        assert event.status == 417
        assert event.consumed == 0
        assert observer.body_read_calls == 0, "Expect rejection must not wait for or read the body"
        _await_finished(observer, deadline=deadline)
        assert observer.status_lines == [417], f"server wrote status lines {observer.status_lines}; no interim 100 permitted"
        try:  # supplementary only: receipt of the error body is not part of the contract
            raw = b""
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                raw += chunk
        except OSError as exc:
            observer.cleanup_notes.append(f"supplementary response read failed: {exc!r}")
        else:
            if raw:
                assert raw.startswith(b"HTTP/1.0 417 "), raw[:40]

    _run_scenario(observer, scenario)


def test_expect_header_never_receives_interim_100(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_expect_case(monkeypatch, inject_interim_100=False)


def test_expect_no_100_oracle_detects_injected_interim_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-100 oracle is load-bearing: an injected interim 100 must fail it."""
    with pytest.raises(AssertionError) as excinfo:
        _run_expect_case(monkeypatch, inject_interim_100=True)
    assert "status lines [100, 417]" in str(excinfo.value)


def _run_valid_body_case(monkeypatch: pytest.MonkeyPatch, raw_request: bytes, body: bytes, *, one_send: bool) -> None:
    """Valid complete bodies must be consumed, then the real client must receive the exact 404 JSON."""
    observer = _Observer()
    _install_observer(monkeypatch, observer)
    total = len(body)

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + CHOREOGRAPHY_DEADLINE_SECONDS
        if one_send:
            client.sendall(raw_request + body)
        else:
            client.sendall(raw_request)
            first = observer.next_event(expecting="body_read_requested", deadline=deadline)
            if first.kind == "response_attempted":
                pytest.fail(f"response attempted with {first.consumed} of {total} body bytes consumed")
            client.sendall(body)
        event = _await_response(observer, total=total, deadline=deadline)
        assert event.consumed == total, f"response attempted with {event.consumed} of {total} body bytes consumed"
        assert event.status == 404
        status, parsed = _read_response(client)
        assert (status, parsed) == (404, {"error": "not found"})
        _await_finished(observer, deadline=deadline)

    _run_scenario(observer, scenario)


def test_headers_and_body_delivered_together_still_consumed_before_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_valid_body_case(monkeypatch, _raw_headers("/v1/tools/web/extract", content_length=len(OPAQUE_BODY)), OPAQUE_BODY, one_send=True)


def test_leading_zero_content_length_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_valid_body_case(monkeypatch, _raw_request("/v1/unknown", ("Content-Length: 00011",)), OPAQUE_BODY, one_send=False)


def test_exact_cap_body_is_consumed(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"x" * 65_536
    _run_valid_body_case(monkeypatch, _raw_headers("/v1/unknown", content_length=len(body)), body, one_send=True)


# --------------------------------------------------------------------------------------- incomplete body, stalls, deadlines


def test_incomplete_body_eof_selects_400_without_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    observer = _Observer()
    _install_observer(monkeypatch, observer)
    total = len(OPAQUE_BODY)

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + CHOREOGRAPHY_DEADLINE_SECONDS
        client.sendall(_raw_headers("/v1/tools/package/lookup", content_length=total))
        first = observer.next_event(expecting="body_read_requested", deadline=deadline)
        assert first.kind == "body_read_requested", first
        client.sendall(OPAQUE_BODY[:3])
        _await_consumption(observer, target=3, total=total, deadline=deadline)
        client.shutdown(socket.SHUT_WR)
        event = _await_response(observer, total=total, deadline=deadline)
        assert event.status == 400
        assert event.consumed == 3
        _await_finished(observer, deadline=deadline)
        assert not [e for e in _drain_events(observer) if e.kind == "response_attempted"]

    _run_scenario(observer, scenario)


def _run_stalled_client(monkeypatch: pytest.MonkeyPatch, *, deadline_seconds: float) -> None:
    observer = _Observer()
    _install_observer(monkeypatch, observer)
    total = len(OPAQUE_BODY)

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + deadline_seconds
        client.sendall(_raw_headers("/v1/tools/security/advisory", content_length=total))
        first = observer.next_event(expecting="body_read_requested", deadline=deadline)
        assert first.kind == "body_read_requested", first
        # withhold the body entirely
        event = observer.next_event(expecting="408 response_attempted", deadline=deadline)
        assert event.kind == "response_attempted", event
        assert event.status == 408
        assert event.consumed == 0
        _await_finished(observer, deadline=deadline)
        assert observer.body_read_calls == 1, "no second read after the deadline"
        assert not [e for e in _drain_events(observer) if e.kind == "response_attempted"], "exactly one response attempt"

    _run_scenario(observer, scenario)


def test_stalled_client_hits_total_deadline_with_short_test_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gw_server, "_REJECTED_POST_BODY_SECONDS", 0.3)
    _run_stalled_client(monkeypatch, deadline_seconds=CHOREOGRAPHY_DEADLINE_SECONDS)


WATCHDOG_SECONDS = 10.0
CHILD_KILL_COLLECT_SECONDS = 5.0
_STALLED_CHILD_SCRIPT = f"""
import importlib.util, sys, pytest
spec = importlib.util.spec_from_file_location("fu6_child", {str(Path(__file__).resolve())!r})
module = importlib.util.module_from_spec(spec)
sys.modules["fu6_child"] = module  # dataclasses resolve the defining module through sys.modules
spec.loader.exec_module(module)
mp = pytest.MonkeyPatch()
try:
    module._run_stalled_client(mp, deadline_seconds=module.CHOREOGRAPHY_DEADLINE_SECONDS)
finally:
    mp.undo()
print("STALLED-CLIENT-OK", flush=True)
"""
_HANG_CHILD_SCRIPT = "import threading; print('HANG-START', flush=True); threading.Event().wait()"


def _run_child_with_watchdog(script: str, *, timeout: float) -> tuple[int | None, str, str, bool]:
    """External process watchdog: run ``script`` in a child interpreter; kill it if ``timeout`` elapses.

    Output collection after a kill is bounded too, so a hung child can never hang the parent test.
    """
    repo_root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(repo_root / "src")}
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-c", script],
        cwd=repo_root,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        out, err = proc.communicate(timeout=CHILD_KILL_COLLECT_SECONDS)
    return proc.returncode, out, err, timed_out


def test_stalled_client_with_production_defaults_completes_under_external_watchdog() -> None:
    """Production 2 s body + 2 s write budgets in a child process under an independent 10 s watchdog."""
    returncode, out, err, timed_out = _run_child_with_watchdog(_STALLED_CHILD_SCRIPT, timeout=WATCHDOG_SECONDS)
    assert not timed_out, f"external watchdog fired and killed the child; stdout={out!r} stderr={err[-2000:]!r}"
    assert returncode == 0, (returncode, out, err[-2000:])
    assert "STALLED-CLIENT-OK" in out, out


def test_external_watchdog_fires_and_kills_hung_child() -> None:
    """Forced-hang control: the watchdog must fire, report failure and leave no owned child behind."""
    started = time.monotonic()
    returncode, out, err, timed_out = _run_child_with_watchdog(_HANG_CHILD_SCRIPT, timeout=1.0)
    elapsed = time.monotonic() - started
    assert timed_out, "watchdog did not fire for a deliberately hung child"
    assert returncode is not None, "hung child was not terminated"
    assert "HANG-START" in out, out
    assert elapsed < 1.0 + CHILD_KILL_COLLECT_SECONDS + 5.0, f"termination and output collection took {elapsed:.1f}s"


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class _FakeStream:
    """Returns one byte per read1 and advances the fake clock by ``step`` seconds each time."""

    def __init__(self, clock: _FakeClock, step: float, data: bytes) -> None:
        self.clock, self.step, self.data = clock, step, data
        self.reads = 0

    def read1(self, size: int) -> bytes:
        self.reads += 1
        self.clock.now += self.step
        chunk, self.data = self.data[:1], self.data[1:]
        return chunk


class _FakeConnection:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)


def test_discard_enforces_total_deadline_not_per_chunk_inactivity(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(gw_server, "_monotonic", clock)
    stream = _FakeStream(clock, step=0.7, data=b"abcde")
    connection = _FakeConnection()
    with pytest.raises(gw_server._RejectedPostError) as excinfo:
        gw_server._discard_rejected_post_body(stream, connection, 5, clock.now + 2.0)
    assert excinfo.value.status == 408
    assert excinfo.value.error == "request body timeout"
    assert stream.reads == 3, "the third short interval crosses the 2 s total budget"
    assert connection.timeouts == pytest.approx([2.0, 1.3, 0.6]), "remaining budget shrinks; never reset per chunk"


def test_discard_completes_within_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(gw_server, "_monotonic", clock)
    stream = _FakeStream(clock, step=0.1, data=b"abcde")
    gw_server._discard_rejected_post_body(stream, _FakeConnection(), 5, clock.now + 2.0)
    assert stream.reads == 5


def test_discard_treats_eof_as_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(gw_server, "_monotonic", clock)
    stream = _FakeStream(clock, step=0.1, data=b"ab")  # declares 5, delivers 2 then EOF
    with pytest.raises(gw_server._RejectedPostError) as excinfo:
        gw_server._discard_rejected_post_body(stream, _FakeConnection(), 5, clock.now + 2.0)
    assert (excinfo.value.status, excinfo.value.error) == (400, "incomplete request body")


def test_response_write_budget_is_shared_between_headers_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(gw_server, "_monotonic", clock)

    class _Recorder:
        def __init__(self, headers_cost: float) -> None:
            self.connection = _FakeConnection()
            self.writes: list[bytes] = []
            self.wfile = self
            self.headers_cost = headers_cost

        def write(self, payload: bytes) -> None:
            self.writes.append(payload)

        def send_response(self, code: int) -> None:
            pass

        def send_header(self, name: str, value: str) -> None:
            pass

        def end_headers(self) -> None:
            clock.now += self.headers_cost

        _arm_write_deadline = OptimusGatewayHandler._arm_write_deadline

    recorder = _Recorder(headers_cost=1.5)
    OptimusGatewayHandler._send_json(recorder, 404, {"error": "not found"}, write_deadline=clock.now + 2.0)
    assert recorder.connection.timeouts == pytest.approx([2.0, 0.5]), "body write receives only the remainder"
    assert recorder.writes == [b'{"error":"not found"}']

    expired = _Recorder(headers_cost=2.5)
    with pytest.raises(TimeoutError):
        OptimusGatewayHandler._send_json(expired, 404, {"error": "not found"}, write_deadline=clock.now + 2.0)
    assert expired.writes == [], "an expired response budget must not write the body"


def test_injected_response_write_error_is_not_reported_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import socketserver

    observer = _Observer()
    _install_observer(monkeypatch, observer)

    def failing_write(self: Any, payload: bytes) -> int:
        raise OSError("injected response write failure")

    monkeypatch.setattr(socketserver._SocketWriter, "write", failing_write)

    def scenario(client: socket.socket | None) -> None:
        assert client is not None
        deadline = time.monotonic() + CHOREOGRAPHY_DEADLINE_SECONDS
        client.sendall(_raw_headers("/v1/unknown", content_length=0))
        event = observer.next_event(expecting="response_attempted", deadline=deadline)
        assert event.status == 404
        _await_finished(observer, deadline=deadline)

    with pytest.raises(AssertionError) as excinfo:
        _run_scenario(observer, scenario)
    assert "injected response write failure" in str(excinfo.value)
    assert not [t for t in observer.handler_threads if t.is_alive()], "cleanup must still complete"
