"""Plan 12.8 Task 2: the Gateway's minimal capture stream (one intent and one outcome per physical upstream attempt), on
a real outbox under a temporary root, through the real legacy retry loop. Every record is validated against its kind's
contract schema."""

from __future__ import annotations

import io
from pathlib import Path
from urllib.error import HTTPError

import pytest

from optimus_gateway import usage_capture
from optimus_gateway.upstream_client import UrllibOpenAICompatibleClient
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc


class _Reply:
    def __init__(self, payload: bytes) -> None:
        self._payload, self.headers = payload, {}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _Reply:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


_OK = (
    b'{"id":"chatcmpl-ok","choices":[{"message":{"role":"assistant","content":"ok"}}],'
    b'"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"cost":"0.00001"}}'
)


def _http_error(code: int) -> HTTPError:
    return HTTPError(url="https://openrouter.ai/api/v1/chat/completions", code=code, msg="error", hdrs=None, fp=io.BytesIO(b"x"))  # type: ignore[arg-type]


@pytest.fixture
def capture(tmp_path: Path):
    writer = ob.OutboxWriter(tmp_path / "accounting" / "outbox" / "gateway")
    usage_capture.configure(writer, ack_wait=5.0)
    yield writer
    usage_capture.configure(None)
    usage_capture.end()
    writer.close()


def _records(writer: ob.OutboxWriter) -> list[dict]:
    writer.close()
    payloads = [dict(r.payload) for r in ob.scan_stream(writer.directory).records]
    for payload in payloads:
        uc.validate_payload(payload, writer="gateway")
    return payloads


def test_unconfigured_capture_is_a_no_op(tmp_path):
    usage_capture.configure(None)
    usage_capture.begin("s:1:planning:1:1")
    usage_capture.set_request("gw-1")
    with usage_capture.physical_attempt():
        pass
    usage_capture.end()

    assert not (tmp_path / "accounting").exists()


def test_legacy_internal_retries_are_each_recorded_under_the_one_request(capture, monkeypatch):
    calls: list[int] = []

    def fake_urlopen(request: object, timeout: float = 0):
        calls.append(1)
        if len(calls) < 3:
            raise _http_error(503)
        return _Reply(_OK)

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(api_key="or-test", base_url="https://openrouter.ai/api/v1", sleep=lambda _s: None)  # pragma: allowlist secret
    usage_capture.begin("s:1:planning:1:1")
    usage_capture.set_request("gw-legacy")

    assert client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi").output_text == "ok"
    records = _records(capture)

    assert [(r["kind"], r["attempt"]) for r in records] == [
        (uc.GATEWAY_ATTEMPT_INTENT, 1), (uc.GATEWAY_ATTEMPT_OUTCOME, 1),
        (uc.GATEWAY_ATTEMPT_INTENT, 2), (uc.GATEWAY_ATTEMPT_OUTCOME, 2),
        (uc.GATEWAY_ATTEMPT_INTENT, 3), (uc.GATEWAY_ATTEMPT_OUTCOME, 3),
    ]
    assert {r["gateway_request_id"] for r in records} == {"gw-legacy"}
    assert all(r["host_request_id"] == "s:1:planning:1:1" for r in records if r["kind"] == uc.GATEWAY_ATTEMPT_INTENT)
    outcomes = [(r["outcome"], r["http_status"]) for r in records if r["kind"] == uc.GATEWAY_ATTEMPT_OUTCOME]
    assert outcomes == [("failed", 503), ("failed", 503), ("completed", None)]
    assert all(r["cost_usd"] is None for r in records if r["kind"] == uc.GATEWAY_ATTEMPT_OUTCOME), "evidence, never a charge"


def test_a_transport_loss_is_uncertain_and_still_propagates(capture):
    usage_capture.begin(None)
    usage_capture.set_request("gw-lost")
    with pytest.raises(ConnectionResetError), usage_capture.physical_attempt():
        raise ConnectionResetError("lost after send")

    records = _records(capture)
    assert [r["outcome"] for r in records if r["kind"] == uc.GATEWAY_ATTEMPT_OUTCOME] == ["uncertain"]
    assert records[0]["host_request_id"] is None


def test_a_malformed_host_request_header_is_never_recorded(capture):
    usage_capture.begin("bad\nheader")
    usage_capture.set_request("gw-1")
    with usage_capture.physical_attempt():
        pass

    assert _records(capture)[0]["host_request_id"] is None


def test_each_enforced_attempt_id_numbers_from_one(capture):
    usage_capture.begin("s:1:planning:1:1")
    for attempt_id in ("gw-a", "gw-b"):
        usage_capture.set_request(attempt_id)
        with usage_capture.physical_attempt():
            pass

    intents = [r for r in _records(capture) if r["kind"] == uc.GATEWAY_ATTEMPT_INTENT]
    assert [(r["gateway_request_id"], r["attempt"]) for r in intents] == [("gw-a", 1), ("gw-b", 1)]


def test_no_request_id_means_no_record(capture):
    usage_capture.begin("s:1:planning:1:1")
    with usage_capture.physical_attempt():
        pass

    capture.close()
    assert not capture.directory.exists()


def test_the_server_reads_the_host_request_header_for_the_routes_physical_attempt(capture):
    import json

    from tests.unit.optimus_gateway.test_server import _post_json, _SmokeUpstreamClient, _start_server

    class _OneAttempt(_SmokeUpstreamClient):
        def create_message(self, *, model: str, input_text: str):
            with usage_capture.physical_attempt():
                return super().create_message(model=model, input_text=input_text)

    server, thread, host, port = _start_server(upstream_client=_OneAttempt())
    try:
        headers = {"Authorization": "Bearer http-test-secret", "Content-Type": "application/json", uc.CAPTURE_REQUEST_HEADER: "s:1:planning:1:1"}
        status, body = _post_json(host, port, "/v1/responses", body=json.dumps({"model": "anthropic/claude-haiku-4.5", "input": "hi"}), headers=headers)
    finally:
        server.shutdown()
        thread.join(5)

    records = _records(capture)
    assert status == 200
    intent = next(r for r in records if r["kind"] == uc.GATEWAY_ATTEMPT_INTENT)
    assert intent["host_request_id"] == "s:1:planning:1:1"
    assert intent["gateway_request_id"] == body["gateway_usage"]["gateway_request_id"]


def test_an_enforced_decision_attempt_is_recorded_through_the_real_client(capture, monkeypatch):
    import json

    from tests.unit.optimus_gateway.model_policy_support import PROVIDER_KEY, Wire, http_reply
    from tests.unit.optimus_gateway.test_decisions import JEV, QUESTIONS, STATE, _reply

    Wire(reply=http_reply(200, json.dumps(_reply()).encode("utf-8"))).install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1", sleep=lambda _s: None)
    usage_capture.begin("s:1:classification:1:1")
    usage_capture.set_request("gw-decision")

    client.create_decision_once(model=JEV, state=STATE, questions=QUESTIONS, provider_controls={"only": ["typesafe"], "allow_fallbacks": False})

    records = _records(capture)
    assert [(r["kind"], r["gateway_request_id"], r["attempt"]) for r in records] == [
        (uc.GATEWAY_ATTEMPT_INTENT, "gw-decision", 1), (uc.GATEWAY_ATTEMPT_OUTCOME, "gw-decision", 1),
    ]
    assert records[1]["outcome"] == "completed"


def test_an_enforced_model_attempt_is_recorded_through_the_real_client(capture, monkeypatch):
    from tests.unit.optimus_gateway.model_policy_support import PROVIDER_KEY, Wire, http_reply

    Wire(reply=http_reply(200, _OK)).install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1", sleep=lambda _s: None)
    usage_capture.begin("s:1:planning:1:1")
    usage_capture.set_request("gw-attempt-1")

    client.create_message_once(model="anthropic/claude-haiku-4.5", input_text="hi", max_tokens=16, provider_controls={"only": ["anthropic"]}, reasoning=None)

    records = _records(capture)
    assert [(r["kind"], r["gateway_request_id"]) for r in records] == [
        (uc.GATEWAY_ATTEMPT_INTENT, "gw-attempt-1"), (uc.GATEWAY_ATTEMPT_OUTCOME, "gw-attempt-1"),
    ]
    assert records[1]["outcome"] == "completed"


def test_an_intent_durable_only_after_the_wait_is_recorded_unconfirmed(tmp_path):
    import threading

    writer = ob.OutboxWriter(tmp_path / "accounting" / "outbox" / "gateway")
    usage_capture.configure(writer, ack_wait=0.05)
    gate = threading.Event()
    original = writer._writer.append

    def slow(payload, *, event_id=None):
        if payload.get("kind") == uc.GATEWAY_ATTEMPT_INTENT:
            gate.wait(5.0)
        return original(payload, event_id=event_id)

    writer._writer.append = slow  # type: ignore[method-assign]
    try:
        usage_capture.begin("s:1:planning:1:1")
        usage_capture.set_request("gw-slow")
        with usage_capture.physical_attempt():
            pass
        gate.set()
    finally:
        usage_capture.configure(None)
        usage_capture.end()

    records = _records(writer)
    assert [r["kind"] for r in records] == [uc.GATEWAY_ATTEMPT_INTENT, uc.GATEWAY_ATTEMPT_OUTCOME]
    assert records[1]["intent_confirmed"] is False and records[1]["outcome"] == "completed"


def test_the_intent_precedes_the_dispatch_budget_check_and_a_refused_dispatch_is_not_sent(capture, monkeypatch):
    import optimus_gateway.upstream_client as upstream_module

    checks: list[int] = []

    def budget(_seconds: float) -> bool:
        checks.append(capture.stats().pending + capture.stats().confirmed_sequence)  # the intent is already queued or written
        return False

    monkeypatch.setattr(upstream_module, "request_budget_admits", budget)
    client = UrllibOpenAICompatibleClient(api_key="or-test", base_url="https://openrouter.ai/api/v1", sleep=lambda _s: None)  # pragma: allowlist secret
    usage_capture.begin("s:1:planning:1:1")
    usage_capture.set_request("gw-refused")

    with pytest.raises(upstream_module.UpstreamBudgetExhausted):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    records = _records(capture)
    assert checks and checks[0] >= 1, "the intent was recorded before the budget check ran"
    assert [(r["kind"], r.get("outcome")) for r in records] == [(uc.GATEWAY_ATTEMPT_INTENT, None), (uc.GATEWAY_ATTEMPT_OUTCOME, "not_sent")]
    assert records[1]["intent_confirmed"] is True


def _raw_capture(host: str, port: int, head: bytes, body: bytes = b"", *, timeout: float = 5.0) -> tuple[int, float]:
    import socket
    import time as _time

    started = _time.monotonic()
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.sendall(head + body)
        reply = b""
        while b"\r\n" not in reply:
            chunk = connection.recv(4096)
            if not chunk:
                break
            reply += chunk
    return int(reply.split(b" ", 2)[1]), _time.monotonic() - started


@pytest.mark.parametrize(("headers", "status"), [
    (b"Authorization: Bearer http-test-secret\r\nTransfer-Encoding: chunked\r\n", 501),
    (b"Authorization: Bearer http-test-secret\r\nContent-Length: 2\r\nContent-Length: 2\r\n", 400),
    (b"Authorization: Bearer http-test-secret\r\nContent-Length: %d\r\n" % (uc.MAX_BODY_BYTES + 1), 413),
    (b"Authorization: Bearer wrong\r\nContent-Length: 100\r\n", 401),
])
def test_the_capture_route_refuses_bad_framing_and_strangers_before_reading_a_body(headers, status):
    from tests.unit.optimus_gateway.test_server import _start_server

    server, thread, host, port = _start_server()
    try:
        code, _ = _raw_capture(host, port, b"POST " + uc.PATH.encode() + b" HTTP/1.1\r\nHost: x\r\n" + headers + b"\r\n")
    finally:
        server.shutdown()
        thread.join(5)

    assert code == status


def test_a_withheld_capture_body_times_out_instead_of_holding_the_handler(monkeypatch):
    import optimus_gateway.server as server_module
    from tests.unit.optimus_gateway.test_server import _start_server

    monkeypatch.setattr(server_module, "_CAPTURE_BODY_SECONDS", 0.5)
    server, thread, host, port = _start_server()
    try:
        head = b"POST " + uc.PATH.encode() + b" HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer http-test-secret\r\nContent-Length: 100\r\n\r\n"
        code, elapsed = _raw_capture(host, port, head, b'{"partial":')  # 11 of the 100 declared bytes, then silence
    finally:
        server.shutdown()
        thread.join(5)

    assert code == 408 and elapsed < 4.0
