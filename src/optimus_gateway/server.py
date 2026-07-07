from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.providers import build_upstream_client
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import UpstreamClient


class OptimusGatewayHandler(BaseHTTPRequestHandler):
    config: GatewayServiceConfig
    upstream_client: UpstreamClient

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        if self.path != "/v1/responses":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            request_body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
            return
        if not isinstance(request_body, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "request body must be a JSON object"})
            return

        status, body = handle_responses_request(
            authorization_header=self.headers.get("Authorization"),
            request_body=request_body,
            config=self.config,
            upstream_client=self.upstream_client,
        )
        self._send_json(HTTPStatus(status), body)

    def _send_json(self, status: HTTPStatus | int, body: dict[str, Any]) -> None:
        payload = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        code = int(status)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def serve_gateway(
    *,
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient | None = None,
) -> ThreadingHTTPServer:
    client = upstream_client or build_upstream_client(config)

    class _BoundHandler(OptimusGatewayHandler):
        pass

    _BoundHandler.config = config
    _BoundHandler.upstream_client = client
    server = ThreadingHTTPServer((config.bind_host, config.bind_port), _BoundHandler)
    return server
