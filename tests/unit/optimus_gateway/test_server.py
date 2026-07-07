from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

from optimus_gateway.anthropic_client import AnthropicMessageResult
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway


class _SmokeAnthropicClient:
    def create_message(self, *, model: str, input_text: str) -> AnthropicMessageResult:
        return AnthropicMessageResult(
            message_id="msg-http-1",
            output_text=f"echo:{input_text}",
            input_tokens=3,
            output_tokens=2,
        )


def test_server_serves_v1_responses_over_http():
    config = GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        shared_secret="http-test-secret",
        anthropic_api_key="sk-ant-test",
    )
    server = serve_gateway(config=config, anthropic_client=_SmokeAnthropicClient())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request(
            "POST",
            "/v1/responses",
            body=json.dumps({"model": "claude-haiku", "input": "ping"}),
            headers={
                "Authorization": "Bearer http-test-secret",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert body["output_text"] == "echo:ping"
        assert body["gateway_usage"]["provider"] == "anthropic"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_returns_401_for_bad_auth():
    config = GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        shared_secret="http-test-secret",
        anthropic_api_key="sk-ant-test",
    )
    server = serve_gateway(config=config, anthropic_client=_SmokeAnthropicClient())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request(
            "POST",
            "/v1/responses",
            body=json.dumps({"model": "claude-haiku", "input": "ping"}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
