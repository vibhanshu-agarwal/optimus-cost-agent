from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from typing import Any

import pytest

from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from optimus_gateway.upstream_client import ProviderMessageResult


class _SmokeUpstreamClient:
    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        return ProviderMessageResult(
            message_id="msg-http-1",
            output_text=f"echo:{input_text}",
            input_tokens=3,
            output_tokens=2,
        )


def _config() -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        shared_secret="http-test-secret",
        provider="openrouter",
        provider_api_key="or-test",
        base_url="https://openrouter.ai/api/v1",
    )


def _start_server(*, upstream_client: Any | None = None):
    server = serve_gateway(
        config=_config(),
        upstream_client=upstream_client if upstream_client is not None else _SmokeUpstreamClient(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def _stop_server(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _post_json(host: str, port: int, path: str, *, body: bytes | str | None, headers: dict[str, str] | None = None):
    connection = HTTPConnection(host, port, timeout=5)
    connection.request(
        "POST",
        path,
        body=body,
        headers=headers
        or {
            "Authorization": "Bearer http-test-secret",
            "Content-Type": "application/json",
        },
    )
    response = connection.getresponse()
    raw = response.read().decode("utf-8")
    parsed: Any
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw
    return response.status, parsed


def test_server_serves_v1_responses_over_http():
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(
            host,
            port,
            "/v1/responses",
            body=json.dumps({"model": "claude-haiku", "input": "ping"}),
        )
        assert status == 200
        assert body["output_text"] == "echo:ping"
        assert body["gateway_usage"]["provider"] == "openrouter"
    finally:
        _stop_server(server, thread)


def test_server_returns_401_for_bad_auth():
    server, thread, host, port = _start_server()
    try:
        status, _body = _post_json(
            host,
            port,
            "/v1/responses",
            body=json.dumps({"model": "claude-haiku", "input": "ping"}),
            headers={"Content-Type": "application/json"},
        )
        assert status == 401
    finally:
        _stop_server(server, thread)


def test_core_routes_dispatch_to_distinct_handlers(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def _track(name: str):
        def _handler(**_kwargs: Any) -> tuple[int, dict[str, Any]]:
            calls.append(name)
            return 200, {"handler": name}

        return _handler

    monkeypatch.setattr("optimus_gateway.server.handle_responses_request", _track("responses"))
    monkeypatch.setattr(
        "optimus_gateway.server.handle_chat_completions_request",
        _track("chat_completions"),
    )
    monkeypatch.setattr(
        "optimus_gateway.server.handle_observability_traces_request",
        _track("observability_traces"),
    )

    server, thread, host, port = _start_server(upstream_client=_SmokeUpstreamClient())
    try:
        for path, expected in (
            ("/v1/responses", "responses"),
            ("/v1/chat/completions", "chat_completions"),
            ("/v1/observability/traces", "observability_traces"),
        ):
            status, body = _post_json(host, port, path, body=json.dumps({"probe": True}))
            assert status == 200, path
            assert body == {"handler": expected}
        assert calls == ["responses", "chat_completions", "observability_traces"]
    finally:
        _stop_server(server, thread)


def test_tools_routes_remain_not_found():
    server, thread, host, port = _start_server()
    try:
        for path in ("/v1/tools/web/search", "/v1/tools/web/extract"):
            status, body = _post_json(host, port, path, body=json.dumps({"q": "x"}))
            assert status == 404, path
            assert body == {"error": "not found"}
    finally:
        _stop_server(server, thread)


@pytest.mark.parametrize(
    "path",
    ("/v1/responses", "/v1/chat/completions", "/v1/observability/traces"),
)
def test_core_routes_reject_invalid_json(path: str):
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(host, port, path, body="{not-json")
        assert status == 400
        assert body == {"error": "invalid JSON"}
    finally:
        _stop_server(server, thread)


@pytest.mark.parametrize(
    "path",
    ("/v1/responses", "/v1/chat/completions", "/v1/observability/traces"),
)
def test_core_routes_reject_non_object_body(path: str):
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(host, port, path, body=json.dumps(["not", "an", "object"]))
        assert status == 400
        assert body == {"error": "request body must be a JSON object"}
    finally:
        _stop_server(server, thread)


def test_unknown_route_remains_not_found():
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(host, port, "/v1/unknown", body=json.dumps({"x": 1}))
        assert status == 404
        assert body == {"error": "not found"}
    finally:
        _stop_server(server, thread)
