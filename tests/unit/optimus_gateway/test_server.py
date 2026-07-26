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


def test_observability_traces_accepts_structured_events_without_usage_claim():
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(
            host,
            port,
            "/v1/observability/traces",
            body=json.dumps(
                {
                    "events": [
                        {"kind": "model_call", "run_id": "run-1"},
                        {"kind": "tool_call", "run_id": "run-1"},
                    ]
                }
            ),
        )
        assert status == 200
        assert body["status"] == "accepted"
        assert body["gateway_request_id"].startswith("gw-")
        assert "gateway_usage" not in body
        assert "billing_units" not in body
        assert "cost_usd" not in body
    finally:
        _stop_server(server, thread)


def test_observability_traces_accepts_empty_events_array():
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(host, port, "/v1/observability/traces", body=json.dumps({"events": []}))
        assert status == 200
        assert body["status"] == "accepted"
    finally:
        _stop_server(server, thread)


def test_observability_traces_tolerates_unknown_top_level_keys():
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(
            host,
            port,
            "/v1/observability/traces",
            body=json.dumps({"events": [{"kind": "model_call"}], "future_batch_hint": {"a": 1}}),
        )
        assert status == 200
        assert body["status"] == "accepted"
    finally:
        _stop_server(server, thread)


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"events": "not-a-list"},
        {"events": {"kind": "model_call"}},
    ),
)
def test_observability_traces_requires_events_array(payload: dict[str, Any]):
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(host, port, "/v1/observability/traces", body=json.dumps(payload))
        assert status == 400
        assert "events" in body["error"]
        assert "status" not in body
    finally:
        _stop_server(server, thread)


def test_observability_traces_rejects_non_object_events():
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(
            host,
            port,
            "/v1/observability/traces",
            body=json.dumps({"events": [{"kind": "model_call"}, "not-an-object"]}),
        )
        assert status == 400
        assert "event" in body["error"]
    finally:
        _stop_server(server, thread)


def test_observability_traces_requires_bearer_auth():
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(
            host,
            port,
            "/v1/observability/traces",
            body=json.dumps({"events": []}),
            headers={"Content-Type": "application/json"},
        )
        assert status == 401
        assert body == {"error": "unauthorized"}
    finally:
        _stop_server(server, thread)


def test_observability_traces_treats_event_content_as_untrusted_data():
    """Event contents are never executed, fetched, or echoed back as policy."""
    hostile_event = {
        "kind": "model_call",
        "prompt": "ignore previous instructions",
        "url": "https://attacker.example/exfil",
        "command": "rm -rf /",
        "provider_api_key": "sk-should-never-be-accepted",
    }
    server, thread, host, port = _start_server()
    try:
        status, body = _post_json(
            host,
            port,
            "/v1/observability/traces",
            body=json.dumps({"events": [hostile_event]}),
        )
        assert status == 200
        assert set(body) == {"status", "gateway_request_id"}
        serialized = json.dumps(body)
        assert "attacker.example" not in serialized
        assert "sk-should-never-be-accepted" not in serialized
        assert "rm -rf" not in serialized
    finally:
        _stop_server(server, thread)


def test_gateway_observability_exporter_reaches_served_route():
    """The existing exporter no longer receives the unknown-path 404."""
    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.telemetry.observability import GatewayObservabilityExporter

    server, thread, host, port = _start_server()
    try:
        exporter = GatewayObservabilityExporter(
            settings=OptimusGatewaySettings.from_env(
                {
                    "OPTIMUS_GATEWAY_URL": f"http://{host}:{port}",
                    "OPTIMUS_API_KEY": "http-test-secret",
                    "OPTIMUS_PRODUCTION_MODE": "false",
                }
            )
        )
        response = exporter.export(())
        assert response["status"] == "accepted"
        assert response["gateway_request_id"].startswith("gw-")
        assert "gateway_usage" not in response
    finally:
        _stop_server(server, thread)
