"""#465: a launch reuses a listening Gateway only when it proves this launch's configuration, and otherwise says why.

Native HTTP against the real Gateway server (ADR-036). The incident's shape is the first test: a launch approved for one
upstream finds another launch's Gateway on its port.
"""

from __future__ import annotations

import ast
import asyncio
import io
import json
import socket
import threading
import time
from collections.abc import Iterator
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from optimus.acp import gateway_refusal, local_infra, spec
from optimus.acp.gateway_refusal import GatewayRefusalServer
from optimus.acp.local_gateway_secrets import CredentialLayer, CredentialProvenance, ProviderCredentialResolution, ProviderSecrets
from optimus.acp.local_infra import LocalInfrastructureError
from optimus.acp.process_lifecycle import ProcessLifecycle, StopReason
from optimus.acp.server import StdioByteReader, StdioByteWriter, StdioNdjsonLineReader, StdioNdjsonLineWriter
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from optimus_gateway.upstream_client import ProviderMessageResult
from optimus_security import gateway_identity as gi

_KEY = b"test-gateway-attach-hmac-key-32!!"
_SECRET = "attach-shared-secret"  # pragma: allowlist secret - synthetic test fixture
_STUB = "http://127.0.0.1:9/stub/v1"
_REAL = "https://openrouter.ai/api/v1"
_PROVIDER_KEY = "sk-or-test"  # pragma: allowlist secret - synthetic test fixture


def _credentials(base_url: str = _STUB) -> ProviderCredentialResolution:
    provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, "test")
    return ProviderCredentialResolution(
        secrets=ProviderSecrets(provider="openrouter", model_provider_api_key=_PROVIDER_KEY, base_url=base_url),
        provider_provenance=provenance, api_key_provenance=provenance, base_url_provenance=provenance,
    )


def _expected(base_url: str = _STUB, **overrides: object) -> gi.GatewayIdentity:
    identity = local_infra.expected_gateway_identity(
        **{"gateway_url": "http://127.0.0.1:8765", "provider_credentials": _credentials(base_url),
           "shared_secret": _SECRET, "manifest_hmac_key": _KEY, "model_registry": "registry", **overrides}
    )
    assert identity is not None
    return identity


class _Upstream:
    def __init__(self) -> None:
        self.calls = 0

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        self.calls += 1
        return ProviderMessageResult(message_id="m", output_text=input_text, input_tokens=1, output_tokens=1, total_tokens=2,
                                     billing_units=2, cost_usd=Decimal("0.00001"), provider="openrouter", resolved_provider=None, requested_model=model,
                                     resolved_model=model, model_version=None, cache_hit=False)


class _Listener:
    def __init__(self, server: ThreadingHTTPServer) -> None:
        self.server = server
        self.url = f"http://127.0.0.1:{server.server_address[1]}"
        self.thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


@pytest.fixture
def listeners() -> Iterator[list[_Listener]]:
    started: list[_Listener] = []
    yield started
    for listener in started:
        listener.close()


def _real_gateway(listeners: list[_Listener], identity: gi.GatewayIdentity | None, *, secret: str = _SECRET) -> tuple[_Listener, _Upstream]:
    upstream = _Upstream()
    config = GatewayServiceConfig(
        bind_host="127.0.0.1", bind_port=0, shared_secret=secret, provider="openrouter", provider_api_key=_PROVIDER_KEY,
        base_url=_STUB, local_identity=None if identity is None else gi.ServedIdentity(identity, gi.proof_key(_KEY)),
    )
    listener = _Listener(serve_gateway(config=config, upstream_client=upstream))  # type: ignore[arg-type]
    listeners.append(listener)
    return listener, upstream


def _answering(listeners: list[_Listener], status: int, body: bytes) -> _Listener:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    listener = _Listener(ThreadingHTTPServer(("127.0.0.1", 0), Handler))
    listeners.append(listener)
    return listener


def _ensure(url: str, tmp_path: Path, **overrides: object) -> local_infra.LocalGatewayProcess | None:
    return local_infra.ensure_local_gateway(
        **{"gateway_url": url, "provider_credentials": _credentials(), "shared_secret": _SECRET, "workspace_digest": "a" * 64,
           "security_snapshot_digest": "b" * 64, "manifest_hmac_key": _KEY, "policy_version": "P9.96-v1",
           "runtime_root": tmp_path / ".optimus", "expected_identity": _expected(), **overrides}
    )


@pytest.fixture
def no_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    def spawned(*_a: object, **_k: object) -> None:
        raise AssertionError("a Gateway was started")

    monkeypatch.setattr(local_infra.subprocess, "Popen", spawned)


def test_a_launch_approved_for_a_stub_refuses_a_gateway_serving_a_real_upstream(listeners, tmp_path, no_spawn) -> None:
    """The incident: the other entry's Gateway took the port first, and this launch sent its prompts there."""
    listener, upstream = _real_gateway(listeners, _expected(_REAL))
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(listener.url, tmp_path)
    assert raised.value.code == "GATEWAY_CONFIGURATION_MISMATCH"
    assert "upstream URL" in raised.value.user_message
    assert "no model request was sent" in raised.value.user_message
    assert "OPTIMUS_GATEWAY_URL" in raised.value.user_message
    assert _REAL not in raised.value.user_message and _PROVIDER_KEY not in raised.value.user_message
    assert upstream.calls == 0


def test_the_refused_gateway_is_left_serving(listeners, tmp_path, no_spawn) -> None:
    listener, _ = _real_gateway(listeners, _expected(_REAL))
    with pytest.raises(LocalInfrastructureError):
        _ensure(listener.url, tmp_path)
    nonce = gi.new_nonce()
    settings = local_infra.OptimusGatewaySettings(gateway_url=listener.url, optimus_api_key=_SECRET)
    status, _ = local_infra.gateway_post(settings, timeout=2, path=gi.PATH)(gi.build_request(nonce))
    assert status == 200


def test_the_same_configuration_is_reused(listeners, tmp_path, no_spawn) -> None:
    listener, upstream = _real_gateway(listeners, _expected())
    assert _ensure(listener.url, tmp_path) is None
    assert upstream.calls == 0


def test_two_workspaces_on_the_same_configuration_share_one_gateway(listeners, tmp_path, no_spawn) -> None:
    listener, _ = _real_gateway(listeners, _expected())
    assert _ensure(listener.url, tmp_path / "one", workspace_digest="1" * 64, security_snapshot_digest="3" * 64) is None
    assert _ensure(listener.url, tmp_path / "two", workspace_digest="2" * 64, security_snapshot_digest="4" * 64) is None


@pytest.mark.parametrize(
    ("overrides", "label"),
    [
        ({"model_registry": "other"}, "model registry"),
        ({"auto_composition": True}, "composition"),
        ({"test_profile": "profile"}, "composition"),
        ({"stage_c_envelope": "envelope"}, "test envelope"),
    ],
)
def test_each_launch_difference_refuses_by_name(listeners, tmp_path, no_spawn, overrides: dict[str, object], label: str) -> None:
    listener, _ = _real_gateway(listeners, _expected())
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(listener.url, tmp_path, expected_identity=_expected(**overrides))
    assert label in raised.value.user_message


def test_tool_configuration_from_the_config_root_refuses_by_name(listeners, tmp_path, no_spawn) -> None:
    listener, _ = _real_gateway(listeners, _expected())
    (tmp_path / ".env.gateway").write_text("OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS=example.com\n", encoding="utf-8")
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(listener.url, tmp_path, expected_identity=_expected(config_root=tmp_path))
    assert "tool configuration" in raised.value.user_message


def test_an_approved_accounting_difference_refuses_by_name(listeners, tmp_path, no_spawn) -> None:
    listener, _ = _real_gateway(listeners, _expected())
    identity = _expected(config_root=tmp_path, usage_accounting=True)
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(listener.url, tmp_path, expected_identity=identity)
    assert "usage accounting" in raised.value.user_message


def test_an_older_gateway_with_no_identity_route_is_refused(listeners, tmp_path, no_spawn) -> None:
    listener, upstream = _real_gateway(listeners, None)
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(listener.url, tmp_path)
    assert raised.value.code == "GATEWAY_IDENTITY_UNCONFIRMED"
    assert upstream.calls == 0


def test_a_gateway_with_another_key_is_refused(listeners, tmp_path, no_spawn) -> None:
    listener, _ = _real_gateway(listeners, _expected(), secret="another-secret")  # pragma: allowlist secret - synthetic test fixture
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(listener.url, tmp_path)
    assert raised.value.code == "GATEWAY_KEY_REJECTED"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, b"not json"),
        (200, b"{}"),
        (200, b"[]"),
        (500, b'{"error":"x"}'),
        (404, b'{"error":"not found"}'),
    ],
)
def test_a_listener_that_is_not_a_current_gateway_is_refused(listeners, tmp_path, no_spawn, status: int, body: bytes) -> None:
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(_answering(listeners, status, body).url, tmp_path)
    assert raised.value.code == "GATEWAY_IDENTITY_UNCONFIRMED"


def test_a_replayed_good_reply_is_refused(listeners, tmp_path, no_spawn) -> None:
    served = gi.ServedIdentity(_expected(), gi.proof_key(_KEY))
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(_answering(listeners, 200, json.dumps(served.reply(gi.new_nonce())).encode()).url, tmp_path)
    assert raised.value.code == "GATEWAY_IDENTITY_UNCONFIRMED"


def test_a_silent_listener_is_refused_within_the_bound(tmp_path, no_spawn, monkeypatch) -> None:
    monkeypatch.setattr(gi, "READ_SECONDS", 0.2)
    with socket.create_server(("127.0.0.1", 0)) as silent:
        url = f"http://127.0.0.1:{silent.getsockname()[1]}"
        started = time.monotonic()
        with pytest.raises(LocalInfrastructureError) as raised:
            _ensure(url, tmp_path)
    assert raised.value.code == "GATEWAY_IDENTITY_UNCONFIRMED"
    assert time.monotonic() - started < 5


def test_a_host_with_no_upstream_of_its_own_still_needs_a_current_gateway(listeners, tmp_path, no_spawn) -> None:
    """Only a URL and a key: its approval binds no upstream to compare, so any current Gateway answering the key will do."""
    no_upstream = {"provider_credentials": None, "shared_secret": None, "api_key": _SECRET, "expected_identity": None}
    listener, _ = _real_gateway(listeners, _expected(_REAL))
    assert _ensure(listener.url, tmp_path, **no_upstream) is None
    older, _ = _real_gateway(listeners, None)
    with pytest.raises(LocalInfrastructureError):
        _ensure(older.url, tmp_path, **no_upstream)


def test_no_identity_is_expected_without_a_local_upstream() -> None:
    assert local_infra.expected_gateway_identity(gateway_url="http://127.0.0.1:8765", provider_credentials=None,
                                                 shared_secret=_SECRET, manifest_hmac_key=_KEY) is None
    assert local_infra.expected_gateway_identity(gateway_url="https://gateway.optimus.ai", provider_credentials=_credentials(),
                                                 shared_secret=_SECRET, manifest_hmac_key=_KEY) is None


class _ExitedChild:
    pid = 1
    returncode = 1

    def poll(self) -> int:
        return 1


def _child_that_lost_the_port(monkeypatch: pytest.MonkeyPatch, listener: _Listener) -> None:
    """Two launches started at once: this one saw a free port, then its child could not bind."""
    real = local_infra._tcp_reachable
    calls = {"n": 0}

    def reachable(host: str, port: int, *, timeout: float = 1.0) -> bool:
        calls["n"] += 1
        return calls["n"] > 1 and real(host, port, timeout=timeout)

    monkeypatch.setattr(local_infra, "_tcp_reachable", reachable)
    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *_a, **_k: _ExitedChild())


def test_losing_the_start_race_to_a_compatible_gateway_reuses_it(listeners, tmp_path, monkeypatch) -> None:
    listener, _ = _real_gateway(listeners, _expected())
    _child_that_lost_the_port(monkeypatch, listener)
    assert _ensure(listener.url, tmp_path) is None


def test_losing_the_start_race_to_another_configuration_refuses(listeners, tmp_path, monkeypatch) -> None:
    listener, _ = _real_gateway(listeners, _expected(_REAL))
    _child_that_lost_the_port(monkeypatch, listener)
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(listener.url, tmp_path)
    assert raised.value.code == "GATEWAY_CONFIGURATION_MISMATCH"


def test_a_listener_of_another_configuration_while_the_child_starts_stops_the_child(listeners, tmp_path, monkeypatch) -> None:
    listener, _ = _real_gateway(listeners, _expected(_REAL))
    stopped: list[str] = []

    class Starting:
        pid = 1
        returncode = None

        def poll(self) -> int | None:
            return 0 if stopped else None

        def terminate(self) -> None:
            stopped.append("terminate")

        def wait(self, timeout: float | None = None) -> int:
            return 0

    real = local_infra._tcp_reachable
    calls = {"n": 0}

    def reachable(host: str, port: int, *, timeout: float = 1.0) -> bool:
        calls["n"] += 1
        return calls["n"] > 1 and real(host, port, timeout=timeout)

    monkeypatch.setattr(local_infra, "_tcp_reachable", reachable)
    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *_a, **_k: Starting())
    with pytest.raises(LocalInfrastructureError):
        _ensure(listener.url, tmp_path)
    assert stopped == ["terminate"]


def test_a_launch_that_starts_nothing_confirms_a_listening_gateway(listeners) -> None:
    listener, _ = _real_gateway(listeners, _expected(_REAL))
    with pytest.raises(LocalInfrastructureError):
        local_infra.confirm_running_gateway(listener.url, api_key=_SECRET, hmac_key=_KEY, expected=_expected())
    local_infra.confirm_running_gateway(listener.url, api_key=_SECRET, hmac_key=_KEY, expected=_expected(_REAL))


def test_a_url_with_no_port_is_confirmed_where_its_requests_would_go(monkeypatch) -> None:
    """Pre-flight and the prompts use the scheme's default port; confirming 8765 instead would pass an older Gateway on 80."""
    probed: list[tuple[str, int]] = []
    verified: list[str] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda host, port, **_k: probed.append((host, port)) or True)
    monkeypatch.setattr(local_infra, "verify_local_gateway", lambda url, **_k: verified.append(url))
    local_infra.confirm_running_gateway("http://127.0.0.1", api_key=_SECRET, hmac_key=_KEY, expected=_expected())
    assert probed == [("127.0.0.1", 80)]
    assert verified == ["http://127.0.0.1"]


def test_a_url_with_no_port_is_not_started_or_confirmed_elsewhere(tmp_path, monkeypatch, no_spawn) -> None:
    probed: list[int] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda _host, port, **_k: probed.append(port) or True)
    monkeypatch.setattr(local_infra, "verify_local_gateway", lambda *_a, **_k: None)
    assert _ensure("http://127.0.0.1", tmp_path) is None
    assert probed == [80]


def test_a_refusal_names_only_the_address_of_a_url_with_a_path_and_query(listeners, tmp_path, no_spawn) -> None:
    listener, _ = _real_gateway(listeners, _expected(_REAL))
    url = f"{listener.url}/private-marker?token=sensitive-value"
    with pytest.raises(LocalInfrastructureError) as raised:
        _ensure(url, tmp_path)
    assert listener.url in raised.value.user_message
    assert "private-marker" not in raised.value.user_message and "sensitive-value" not in raised.value.user_message


def test_a_launch_that_starts_nothing_leaves_an_absent_gateway_to_preflight() -> None:
    with socket.create_server(("127.0.0.1", 0)) as free:
        url = f"http://127.0.0.1:{free.getsockname()[1]}"
    local_infra.confirm_running_gateway(url, api_key=_SECRET, hmac_key=_KEY, expected=_expected())
    local_infra.confirm_running_gateway("https://gateway.optimus.ai", api_key=_SECRET, hmac_key=_KEY, expected=_expected())


def test_the_refusal_reaches_the_launchs_own_log_without_secrets(tmp_path) -> None:
    local_infra.record_gateway_refusal(tmp_path / "runtime", code="GATEWAY_CONFIGURATION_MISMATCH", reason="the reason")
    record = json.loads((tmp_path / "runtime" / "local-gateway.log").read_text(encoding="utf-8"))
    assert (record["event"], record["code"], record["reason"]) == ("gateway_refused", "GATEWAY_CONFIGURATION_MISMATCH", "the reason")


# --- The diagnostic-only ACP host, through the real serving process and stdio owners ---------------------------------


_REASON = "A Gateway is already running with a different configuration."


def _lines(*messages: dict[str, object]) -> bytes:
    return b"".join(json.dumps(message).encode() + b"\n" for message in messages)


def _dialogue() -> tuple[dict[str, object], ...]:
    return (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}},
        {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": ".", "mcpServers": []}},
    )


async def _serve(payload: bytes) -> tuple[int, list[dict[str, object]]]:
    output = io.BytesIO()
    lifecycle = ProcessLifecycle()
    server = GatewayRefusalServer(code="GATEWAY_CONFIGURATION_MISMATCH", reason=_REASON)
    from optimus.acp.__main__ import _run_serving_process

    code = await _run_serving_process(server, lifecycle=lifecycle, reader=StdioNdjsonLineReader(io.BytesIO(payload)),
                                      writer=StdioNdjsonLineWriter(output))
    return code, [json.loads(line) for line in output.getvalue().splitlines()]


@pytest.mark.asyncio
async def test_the_panel_opens_and_every_prompt_shows_the_reason_and_ends_normally() -> None:
    _code, first = await _serve(_lines(*_dialogue()))
    assert next(m["result"]["sessionId"] for m in first if m.get("id") == 2).startswith("refused-")

    server = GatewayRefusalServer(code="GATEWAY_CONFIGURATION_MISMATCH", reason=_REASON)
    created = server._answer({"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": "."}})[0]["result"]["sessionId"]
    prompt = {"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": created, "prompt": [{"type": "text", "text": "hi"}]}}
    for _ in range(2):
        update, result = server._answer(prompt)
        text = update["params"]["update"]["content"]["text"]
        assert update["method"] == "session/update" and update["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
        assert _REASON in text and "GATEWAY_CONFIGURATION_MISMATCH" in text
        assert result["result"] == {"stopReason": "end_turn"}


@pytest.mark.asyncio
async def test_the_diagnostic_host_exits_cleanly_at_end_of_input() -> None:
    code, messages = await _serve(_lines(*_dialogue(), {"jsonrpc": "2.0", "method": "session/cancel", "params": {}}))
    assert code == 0
    assert [m["id"] for m in messages] == [1, 2]


@pytest.mark.asyncio
async def test_the_diagnostic_host_answers_only_the_framed_transport_too() -> None:
    from optimus.acp.__main__ import _run_serving_process
    from optimus.acp.framing import encode_message

    output = io.BytesIO()
    server = GatewayRefusalServer(code="C", reason=_REASON)
    code = await _run_serving_process(server, lifecycle=ProcessLifecycle(), framed=True,
                                      reader=StdioByteReader(io.BytesIO(encode_message(_dialogue()[0]))), writer=StdioByteWriter(output))
    assert code == 0
    assert b'"protocolVersion":1' in output.getvalue().replace(b" ", b"")


@pytest.mark.asyncio
async def test_shutdown_waits_for_a_diagnostic_write_the_client_is_blocking() -> None:
    """Zed stopped reading: the write stays owned, so the process does not report itself finished while it is stuck."""
    from optimus.acp.__main__ import _run_serving_process

    entered, release = threading.Event(), threading.Event()

    class BlockedOutput:
        def write(self, data: bytes) -> int:
            entered.set()
            release.wait(10)
            return len(data)

        def flush(self) -> None:
            return None

    lifecycle = ProcessLifecycle()
    call = asyncio.create_task(_run_serving_process(
        GatewayRefusalServer(code="C", reason=_REASON), lifecycle=lifecycle, observation_seconds=0.03,
        reader=StdioNdjsonLineReader(io.BytesIO(_lines(_dialogue()[0]))), writer=StdioNdjsonLineWriter(BlockedOutput()),
    ))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        lifecycle.request_stop(StopReason.SIGTERM)
        await asyncio.sleep(0.3)
        assert not call.done()
    finally:
        release.set()
    assert await asyncio.wait_for(call, 10) == 143


def test_other_requests_are_refused_and_a_foreign_session_is_unknown() -> None:
    server = GatewayRefusalServer(code="C", reason=_REASON)
    assert server._answer({"jsonrpc": "2.0", "id": 1, "method": "session/set_mode", "params": {}})[0]["error"]["code"] == -32601
    assert "error" in server._answer({"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {"sessionId": "x"}})[0]
    assert "error" in server._answer({"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": ["x"]}})[0]
    assert server._answer({"jsonrpc": "2.0", "id": 9, "result": {}}) == []


def test_it_speaks_the_serving_hosts_protocol_version() -> None:
    assert gateway_refusal._initialize_result()["protocolVersion"] == spec.ACP_PROTOCOL_VERSION


def test_the_diagnostic_host_is_given_no_path_to_a_model() -> None:
    """The channel is only its writer. Nothing else here can send anything anywhere."""
    source = Path(gateway_refusal.__file__).read_text(encoding="utf-8")
    imported = {node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)}
    assert imported <= {"__future__", "collections.abc", "typing", "optimus.acp.errors", "optimus.acp.framing",
                        "optimus.acp.server", "optimus.acp.shapes"}
    names = {node.names[0].name for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.ImportFrom) and node.module == "optimus.acp.server"}
    assert names == {"NdjsonOutboundChannel"}
