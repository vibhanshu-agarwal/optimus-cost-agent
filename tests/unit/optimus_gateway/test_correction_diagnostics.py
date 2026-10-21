"""Plan 12.2 diagnosability correction plan v4 (operator-approved 2026-10-21), the Gateway side.

C1: the persisted log line projects every id, upstream metadata value and refusal text to a recognized form;
the wire body is unchanged. C2: a Stage C ledger write failure is named in the log line of the request that hit
it and of every later halted refusal, never in a response body. C6: every module-authored reason slugs. C7:
malformed framing is a logged 400 and a failed log write never breaks a reply. C9: every failed legacy attempt is
logged with its own cause and shares one request-scoped Gateway id with the outcome.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
import socket
import sys
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus_gateway import request_diagnostics
from optimus_gateway.responses import assert_gateway_usage_contract, handle_responses_request, model_request_log_line
from optimus_gateway.server import serve_gateway
from optimus_gateway.upstream_client import UpstreamAttemptFailure, UrllibOpenAICompatibleClient
from optimus_model_policy import stage_c
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.stage_c import StageCGuard
from optimus_security.failure_facts import UNRECOGNIZED, slug
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    PROVIDER_KEY,
    RecordingUpstream,
    Wire,
    binding,
    gateway_config,
    http_reply,
    model_policy,
    ok_completion_body,
    verified_snapshot,
)
from tests.unit.optimus_gateway.test_server import _config

REPO = Path(__file__).resolve().parents[3]
HAIKU = "anthropic/claude-haiku-5.5"
_URL = "https://openrouter.ai/api/v1"
BARE_KEY = "sk-or-v1-" + "0123456789abcdef" * 4  # pragma: allowlist secret - synthetic credential-shaped canary
PROSE = "private note CANARY"
GW = r"gw-[0-9a-f]{32}"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda _seconds: None)


def _host_route_id() -> str:
    return f"session-{uuid.uuid4().hex}:1:answer:1:{uuid.uuid4().hex}"


def _logged(policy: Any, run: Any, path: str = "/v1/responses") -> tuple[int, dict[str, Any], dict[str, Any], str]:
    """One request inside its request diagnostic context, as the server runs it: the reply, then its log line."""
    request_diagnostics.begin()
    try:
        status, body = run()
        line = model_request_log_line(path, status, body, policy=policy)
    finally:
        request_diagnostics.end()
    return status, body, json.loads(line), line


def _reply(*, reply_id: str = "gen-1760001234-AbCd", provider: str = "Anthropic", finish: str = "stop") -> bytes:
    return json.dumps(
        {
            "id": reply_id,
            "model": HAIKU,
            "choices": [{"message": {"content": "ok"}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11, "cost": "0.00001"},
            "openrouter_metadata": {
                "attempt": 1,
                "endpoints": {"total": 1, "available": [{"provider": provider, "model": HAIKU, "selected": True}]},
                "pipeline": [],
            },
        }
    ).encode()


def _enforced_over_wire(monkeypatch: pytest.MonkeyPatch, reply: bytes, *, request_id: str | None = None):
    """The enforced route through the real client and parser over the socket double."""
    Wire(reply=http_reply(200, reply)).install(monkeypatch)
    policy = model_policy(profiles.compose_test_profile_snapshot("qualification"))
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url=_URL, sleep=lambda _s: None)
    route_id = request_id or _host_route_id()

    def run():
        return handle_responses_request(
            authorization_header=AUTH,
            request_body={"model": HAIKU, "input": "hi", "route_binding": binding(policy.snapshot, model=HAIKU, input_text="hi", output_cap=32_768, request_id=route_id)},
            config=gateway_config(policy),
            upstream_client=client,
        )

    return (*_logged(policy, run), route_id)


# --- C1: projections through the real paths; the wire is unchanged --------------------------------------------------


def test_real_ids_and_recognized_metadata_survive_in_the_log(monkeypatch) -> None:
    status, body, line, _raw, route_id = _enforced_over_wire(monkeypatch, _reply())
    assert status == 200
    [attempt] = line["route_attempts"]
    assert attempt["provider_request_id"] == "gen-1760001234-AbCd"
    assert attempt["gateway_request_id"] == body["route_attempts"][0]["gateway_request_id"]
    assert line["route_request_id"] == route_id
    assert (line["usage"]["resolved_provider"], line["usage"]["resolved_model"]) == ("Anthropic", HAIKU)


def test_a_bare_credential_as_the_reply_id_never_reaches_the_log(monkeypatch) -> None:
    _status, body, line, raw, _route = _enforced_over_wire(monkeypatch, _reply(reply_id=BARE_KEY))
    assert BARE_KEY not in raw
    assert line["route_attempts"][0]["provider_request_id"] == UNRECOGNIZED
    assert body["route_attempts"][0]["provider_request_id"] == BARE_KEY  # the wire is unchanged


def test_a_prose_provider_is_projected_in_the_log_and_unchanged_on_the_wire(monkeypatch) -> None:
    status, body, line, raw, _route = _enforced_over_wire(monkeypatch, _reply(provider=PROSE))
    assert (status, body["code"]) == (422, "EMPIRICAL_PROVIDER_MISMATCH")
    assert PROSE in body["error"]  # the wire error is unchanged
    assert "private note" not in raw.lower()
    assert line["usage"]["resolved_provider"] == UNRECOGNIZED
    assert "'unrecognized'" in line["error"] and "'Anthropic'" in line["error"]


def test_a_prose_finish_status_is_projected_in_the_log_and_unchanged_on_the_wire(monkeypatch) -> None:
    status, body, line, raw, _route = _enforced_over_wire(monkeypatch, _reply(finish=PROSE))
    assert (status, body["code"]) == (422, "FINISH_STATUS_UNVERIFIED")
    assert PROSE.casefold() in body["error"]
    assert "private note" not in raw.lower()
    assert "'unrecognized'" in line["error"]


def test_a_prose_binding_request_id_is_projected_in_the_log(monkeypatch) -> None:
    status, body, line, raw, _route = _enforced_over_wire(monkeypatch, _reply(), request_id=PROSE)
    assert status == 200
    assert body["gateway_usage"]["route_request_id"] == PROSE  # the wire is unchanged
    assert line["route_request_id"] == UNRECOGNIZED and "private note" not in raw.lower()


def test_a_legacy_unsupported_model_is_logged_as_fixed_text() -> None:
    def run():
        return handle_responses_request(
            authorization_header=AUTH, request_body={"model": PROSE, "input": "hi"}, config=gateway_config(None), upstream_client=RecordingUpstream()
        )

    status, body, line, raw = _logged(None, run)
    assert (status, body["error"]) == (400, f"unsupported gateway model: {PROSE}")  # the wire is unchanged
    assert line["error"] == "unsupported gateway model" and "private note" not in raw.lower()


def test_a_bare_credential_in_a_refusal_text_is_redacted_from_the_log() -> None:
    line = model_request_log_line("/v1/responses", 400, {"error": f"refused {BARE_KEY}", "code": "X"})
    assert BARE_KEY not in line


# The reviewed interpolations in refusal texts (Codex rounds 14-15): ints, Gateway codes, constant names and
# trusted constants. Anything else must be projected for the log (`log_detail=`) or logged as fixed text.
_REVIEWED_INTERPOLATIONS = {
    ("src/optimus_gateway/model_policy.py", "policy.route_stop.code"),
    ("src/optimus_gateway/model_policy.py", "route.provider_name"),
    ("src/optimus_gateway/model_policy.py", "attempt"),
    ("src/optimus_gateway/model_policy.py", "', '.join(pipeline)"),
    ("src/optimus_gateway/model_policy.py", "result.input_tokens"),
    ("src/optimus_gateway/model_policy.py", "admitted.decision.input_tokens"),
    ("src/optimus_gateway/models.py", "name"),
    ("src/optimus_gateway/models.py", "self.bind_host"),
    ("src/optimus_gateway/models.py", "_GATEWAY_PROVIDER"),
    ("src/optimus_gateway/models.py", "self.provider"),
    ("src/optimus_gateway/models.py", "provider"),
    ("src/optimus_gateway/models.py", "max_calls_name"),
    ("src/optimus_gateway/providers.py", "config.provider"),
    ("src/optimus_gateway/responses.py", "field"),
    ("src/optimus_gateway/tool_provider_http.py", "label"),
    ("src/optimus_gateway/upstream_client.py", "field"),
    ("src/optimus_gateway/upstream_client.py", "description"),
    ("src/optimus_gateway/upstream_client.py", "name"),
    ("src/optimus_gateway/upstream_client.py", "label"),
    ("src/optimus_gateway/upstream_client.py", "fact.get('cause', fact['class'])"),
    ("src/optimus_model_policy/binding.py", "sorted(missing)"),
    ("src/optimus_model_policy/binding.py", "len(unknown)"),
    ("src/optimus_model_policy/binding.py", "field"),
    ("src/optimus_model_policy/binding.py", "version"),
    ("src/optimus_model_policy/registry.py", "model_id"),
    ("src/optimus_model_policy/registry.py", "seen[folded]"),
    ("src/optimus_model_policy/stage_c.py", "r.attempts"),
    ("src/optimus_model_policy/stage_c.py", "self.envelope.max_attempts"),
    ("src/optimus_model_policy/stage_c.py", "r.charged"),
    ("src/optimus_model_policy/stage_c.py", "self.envelope.limit_usd"),
    ("src/optimus_model_policy/stage_c.py", "self._write_failure"),
    ("src/optimus_model_policy/stage_c.py", "kind"),
}
_FIXED_TEXT_IN_THE_LOG = {("src/optimus_gateway/model_mapping.py", "normalized")}
_REFUSALS = {"ModelPolicyRefusal", "BindingError", "StageCRefusal", "ValueError", "RuntimeError", "RetryableUpstreamError", "ModelRequestValidationError"}


def test_every_interpolated_refusal_text_is_reviewed_or_projected_for_the_log() -> None:
    from tools.tracked_repository_files import tracked_repository_files

    unreviewed = []
    for path in tracked_repository_files(REPO, pathspecs=("src/optimus_gateway", "src/optimus_model_policy")):
        if path.suffix != ".py":
            continue
        relative = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            func = node.exc.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name not in _REFUSALS:
                continue
            projected = any(keyword.arg == "log_detail" for keyword in node.exc.keywords)
            for argument in node.exc.args:
                for part in ast.walk(argument):
                    if isinstance(part, ast.FormattedValue):
                        site = (relative, ast.unparse(part.value))
                        if site not in _REVIEWED_INTERPOLATIONS and site not in _FIXED_TEXT_IN_THE_LOG and not projected:
                            unreviewed.append(f"{relative}:{node.lineno} {site[1]}")
    assert unreviewed == []


# --- C2: the ledger write fact is log-only --------------------------------------------------------------------------


class _Disk:
    """An fsync that fails, once armed, after ``ok`` more successful calls."""

    def __init__(self) -> None:
        self.armed = False
        self.ok = 0

    def __call__(self, _fd: int) -> None:
        if not self.armed:
            return
        if self.ok > 0:
            self.ok -= 1
            return
        raise OSError(28, f"No space left: {PROSE}")


class _Arming(RecordingUpstream):
    def __init__(self, disk: _Disk, *, ok: int, attempts: list[UpstreamAttemptFailure | None] | None = None) -> None:
        super().__init__(attempts=attempts)
        self._disk, self._ok = disk, ok

    def create_message_once(self, **kwargs: Any):
        self._disk.armed, self._disk.ok = True, self._ok
        return super().create_message_once(**kwargs)


@pytest.fixture
def ledger(tmp_path: Path):
    clock = lambda: datetime(2026, 10, 12, 9, 0, tzinfo=UTC)  # noqa: E731
    path = stage_c.stage_c_ledger_path(tmp_path / "runtime")
    envelope = stage_c.compose_stage_c_envelope(ledger=path)
    stage_c.initialize_stage_c_ledger(path, envelope, clock=clock)
    disk = _Disk()
    guard = StageCGuard.open(path, envelope, clock=clock, fsync=disk)
    policy = model_policy(verified_snapshot(tmp_path))
    yield policy, guard, disk
    guard.close()


def _guarded(policy, guard, upstream, request_id: str):
    config = dataclasses.replace(gateway_config(policy), stage_c_guard=guard)
    return lambda: handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": "plan the change", "route_binding": binding(policy.snapshot, input_text="plan the change", request_id=request_id)},
        config=config,
        upstream_client=upstream,
    )


def test_a_settlement_write_failure_is_logged_on_its_own_request_and_every_later_halt(ledger) -> None:
    policy, guard, disk = ledger
    status, body, line, raw = _logged(policy, _guarded(policy, guard, _Arming(disk, ok=0), _host_route_id()))
    assert status == 200 and "ledger_write_failure" not in json.dumps(body)
    assert line["ledger_write_failure"] == {"class": "OSError", "errno": 28}
    assert "private note" not in raw.lower()

    status, body, line, _raw = _logged(policy, _guarded(policy, guard, RecordingUpstream(), _host_route_id()))
    assert (status, body["code"]) == (503, "STAGE_C_HALTED")
    assert "ledger_write_failure" not in json.dumps(body)
    assert body["error"] == "model policy refused the request (STAGE_C_HALTED): ledger write failed (OSError errno 28)"  # unchanged
    assert line["ledger_write_failure"] == {"class": "OSError", "errno": 28}


def test_a_failed_halt_append_after_an_existing_halt_reason_keeps_both_facts_in_the_log(ledger) -> None:
    policy, guard, disk = ledger
    uncertain = UpstreamAttemptFailure("uncertain", failure={"kind": "http"}, http_status=502)
    _logged(policy, _guarded(policy, guard, _Arming(disk, ok=1, attempts=[uncertain]), _host_route_id()))  # the settle is durable, the halt is not

    status, body, line, _raw = _logged(policy, _guarded(policy, guard, RecordingUpstream(), _host_route_id()))
    assert (status, body["code"]) == (503, "STAGE_C_HALTED")
    assert body["error"].endswith("attempt 1 has an unknown charge")  # the wire detail is unchanged
    assert line["error"].endswith("attempt 1 has an unknown charge")
    assert line["ledger_write_failure"] == {"class": "OSError", "errno": 28}


# --- C6: every module-authored reason slugs --------------------------------------------------------------------------


def _module_reasons(relative: str, names: set[str]) -> list[str]:
    """Every literal or formatted reason raised as one of ``names`` in the module. An f-string is formatted with every
    lower-case string constant the module passes as a call argument: its field names (``"input token count"``),
    descriptions and labels."""
    tree = ast.parse((REPO / relative).read_text(encoding="utf-8"))
    constants = sorted(
        {
            arg.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and re.fullmatch(r"[a-z0-9 _.-]{1,60}", arg.value)
        }
    )
    reasons = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
            continue
        func = node.exc.func
        if (func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)) not in names:
            continue
        message = node.exc.args[0]
        if isinstance(message, ast.Constant) and isinstance(message.value, str):
            reasons.append(message.value)
        elif isinstance(message, ast.JoinedStr):
            literal = "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in message.values)
            reasons.extend(literal.replace("{}", value) for value in constants if literal.count("{}") == 1)
    return reasons


def test_every_upstream_and_usage_contract_reason_slugs_to_a_reason() -> None:
    reasons = _module_reasons("src/optimus_gateway/upstream_client.py", {"RuntimeError"})
    reasons += _module_reasons("src/optimus_gateway/responses.py", {"ValueError"})
    assert "upstream response missing choices[0]" in reasons
    assert [reason for reason in reasons if slug(reason) == UNRECOGNIZED] == []
    with pytest.raises(ValueError) as caught:
        assert_gateway_usage_contract({})
    assert slug(str(caught.value)) != UNRECOGNIZED


# --- C7 and C9: through the real server --------------------------------------------------------------------------


def _serve(upstream_client: Any = None):
    server = serve_gateway(config=_config(), upstream_client=upstream_client)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, thread, str(host), int(port)


def _stop(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _raw_post(host: str, port: int, path: str, body: bytes, *, length: str | None = None) -> tuple[int, dict[str, Any]]:
    """A POST over a plain socket (never ``socket.create_connection``, which the socket double replaces), so a test
    can send any framing."""
    head = f"POST {path} HTTP/1.1\r\nHost: {host}\r\nAuthorization: Bearer http-test-secret\r\nContent-Type: application/json\r\n"
    head += f"Content-Length: {len(body) if length is None else length}\r\nConnection: close\r\n\r\n"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(10)
        client.connect((host, port))
        client.sendall(head.encode("ascii") + body)
        received = b""
        while chunk := client.recv(65536):
            received += chunk
    status_line, _, rest = received.partition(b"\r\n")
    _headers, _, payload = rest.partition(b"\r\n\r\n")
    return int(status_line.split()[1]), json.loads(payload or b"{}")


def _log(capsys) -> list[dict[str, Any]]:
    return [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.startswith("{")]


@pytest.mark.parametrize("path", ["/v1/responses", "/v1/chat/completions"])
@pytest.mark.parametrize(
    ("body", "length", "error"),
    [(b"\xff\xfe{}", None, "invalid JSON"), (b"{}", "abc", "invalid content length"), (b"{}", "-5", "invalid content length")],
    ids=["invalid-utf8", "non-integer-length", "negative-length"],
)
def test_malformed_framing_is_a_logged_400_on_both_model_routes(capsys, path: str, body: bytes, length: str | None, error: str) -> None:
    server, thread, host, port = _serve(RecordingUpstream())
    try:
        status, reply = _raw_post(host, port, path, body, length=length)
    finally:
        _stop(server, thread)
    assert (status, reply) == (400, {"error": error})
    assert [(line["path"], line["status"], line["error"]) for line in _log(capsys) if line["event"] == "model_request"] == [(path, 400, error)]


class _ClosedStream:
    def write(self, _text: str) -> int:
        raise ValueError("I/O operation on closed file.")

    def flush(self) -> None:
        raise ValueError("I/O operation on closed file.")


def test_a_closed_log_stream_never_breaks_the_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("optimus_gateway.server.handle_responses_request", lambda **_kwargs: (200, {"output_text": "ok"}))
    server, thread, host, port = _serve(RecordingUpstream())
    try:
        monkeypatch.setattr(sys, "stderr", _ClosedStream())
        status, reply = _raw_post(host, port, "/v1/responses", b"{}")
    finally:
        monkeypatch.undo()
        _stop(server, thread)
    assert (status, reply) == (200, {"output_text": "ok"})


def _legacy_post(host: str, port: int) -> tuple[int, dict[str, Any]]:
    return _raw_post(host, port, "/v1/responses", json.dumps({"model": "anthropic/claude-haiku-4.5", "input": "hi"}).encode())


@pytest.mark.parametrize(
    ("wire", "status", "facts"),
    [
        (Wire(connect=ConnectionRefusedError(10061, PROSE), connect_failures=1, reply=http_reply(200, ok_completion_body())), 200,
         [{"kind": "transport", "class": "URLError", "cause": "ConnectionRefusedError", "errno": 10061}]),
        (Wire(replies=[http_reply(503, b"{}"), http_reply(200, ok_completion_body())]), 200, [{"kind": "http", "status": 503}]),
        (Wire(replies=[TimeoutError(110, PROSE), http_reply(200, ok_completion_body())]), 200, [{"kind": "transport", "class": "TimeoutError", "errno": 110}]),
        (Wire(reply=http_reply(200, b"\xff\xfe not utf-8")), 502, [{"kind": "invalid_utf8"}]),
        (Wire(reply=http_reply(200, b"{not json")), 502, [{"kind": "invalid_json"}]),
        (Wire(reply=http_reply(200, b'{"choices": []}')), 502, [{"kind": "schema", "reason": "upstream_response_missing_id"}]),
    ],
    ids=["transport-then-ok", "503-then-ok", "timeout-then-ok", "invalid-utf8", "invalid-json", "schema"],
)
def test_every_failed_legacy_attempt_is_logged_with_its_cause_and_the_request_id(monkeypatch, capsys, wire: Wire, status: int, facts: list) -> None:
    server, thread, host, port = _serve()  # the production upstream client and its retry observer
    wire.install(monkeypatch)
    try:
        replied, body = _legacy_post(host, port)
    finally:
        _stop(server, thread)
    log = _log(capsys)
    attempts = [line for line in log if line["event"] == "model_attempt"]
    [outcome] = [line for line in log if line["event"] == "model_request"]
    assert replied == status
    assert [line["failure"] for line in attempts] == facts
    ids = {line["gateway_request_id"] for line in attempts} | {outcome["gateway_request_id"]}
    assert len(ids) == 1 and re.fullmatch(GW, ids.pop())
    if status == 200:
        assert body["gateway_usage"]["gateway_request_id"] == outcome["gateway_request_id"]
    else:
        assert body["error"] in {"upstream response was invalid JSON", "upstream response missing id"}  # the wire text is unchanged
    assert "private note" not in json.dumps(log).lower()


def test_the_request_context_is_cleared_when_the_request_ends() -> None:
    request_diagnostics.begin()
    request_diagnostics.note(gateway_request_id=f"gw-{uuid.uuid4().hex}")
    assert request_diagnostics.noted()
    request_diagnostics.end()
    assert request_diagnostics.noted() == {}
    request_diagnostics.note(ledger_write_failure={"class": "OSError"})  # outside a request: ignored
    assert request_diagnostics.noted() == {}


def test_concurrent_legacy_requests_keep_their_own_request_ids(monkeypatch, capsys) -> None:
    server, thread, host, port = _serve()
    Wire(connect=ConnectionRefusedError(10061, "refused"), connect_failures=2, reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    results: list[tuple[int, dict[str, Any]]] = []
    try:
        workers = [threading.Thread(target=lambda: results.append(_legacy_post(host, port))) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=20)
    finally:
        _stop(server, thread)
    log = _log(capsys)
    outcomes = {line["gateway_request_id"] for line in log if line["event"] == "model_request"}
    assert len(outcomes) == 2
    assert {line["gateway_request_id"] for line in log if line["event"] == "model_attempt"} <= outcomes
    assert {body["gateway_usage"]["gateway_request_id"] for _status, body in results} == outcomes
