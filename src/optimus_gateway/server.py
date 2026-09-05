from __future__ import annotations

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from optimus_gateway.chat_completions import handle_chat_completions_request
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.observability import (
    OpenTelemetryTraceExporter,
    TraceExporter,
    handle_observability_traces_request,
)
from optimus_gateway.providers import build_tool_dependencies, build_upstream_client
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.tool_handlers import TOOL_ROUTE_PATHS, GatewayToolDependencies, handle_tool_request
from optimus_gateway.upstream_client import UpstreamClient

# P11-FU-6: limits for POSTs to routes this handler rejects with 404 (unknown routes and tool routes
# without configured dependencies). The early 404 used to be written, and the connection closed,
# before the request body was consumed; that unread-body-before-close behavior was shown to be
# causally involved in intermittent client-side WinError 10053 failures on the tested Windows host
# (the exact wire-level mechanism was not established). These bounds apply ONLY to that rejection
# path; recognized routes keep their existing behavior. Values are private design choices, not
# configuration.
_REJECTED_POST_MAX_BYTES = 65_536
_REJECTED_POST_BODY_SECONDS = 2.0
_REJECTED_POST_WRITE_SECONDS = 2.0
_REJECTED_POST_READ_CHUNK = 8192
_MAX_LENGTH_DIGITS = len(str(_REJECTED_POST_MAX_BYTES))
_monotonic = time.monotonic


class _RejectedPostError(Exception):
    """A framing or limit rejection on the early-404 path: fixed status and label only."""

    def __init__(self, status: HTTPStatus, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.error = error


def _rejected_post_length(headers: Any) -> int:
    """Classify request framing for a rejected route and return the declared body length (may be 0)."""
    lengths = headers.get_all("Content-Length", [])
    encodings = headers.get_all("Transfer-Encoding", [])
    if lengths and encodings:
        raise _RejectedPostError(HTTPStatus.BAD_REQUEST, "invalid request framing")
    if len(lengths) > 1:
        raise _RejectedPostError(HTTPStatus.BAD_REQUEST, "invalid request framing")
    if encodings:
        raise _RejectedPostError(HTTPStatus.NOT_IMPLEMENTED, "transfer encoding not supported")
    significant = ""
    if lengths:
        value = lengths[0].strip(" \t")
        if not value or not value.isascii() or not value.isdigit():
            raise _RejectedPostError(HTTPStatus.BAD_REQUEST, "invalid request framing")
        significant = value.lstrip("0")
    if headers.get_all("Expect", []):
        raise _RejectedPostError(HTTPStatus.EXPECTATION_FAILED, "expectation failed")
    if not significant:
        return 0
    if len(significant) > _MAX_LENGTH_DIGITS:
        raise _RejectedPostError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")
    length = int(significant)
    if length > _REJECTED_POST_MAX_BYTES:
        raise _RejectedPostError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")
    return length


def _discard_rejected_post_body(stream: Any, connection: Any, length: int, deadline: float) -> None:
    """Consume exactly ``length`` bytes from the buffered stream under one total monotonic deadline."""
    remaining = length
    while remaining:
        budget = deadline - _monotonic()
        if budget <= 0:
            raise _RejectedPostError(HTTPStatus.REQUEST_TIMEOUT, "request body timeout")
        connection.settimeout(budget)
        try:
            chunk = stream.read1(min(_REJECTED_POST_READ_CHUNK, remaining))
        except TimeoutError:
            raise _RejectedPostError(HTTPStatus.REQUEST_TIMEOUT, "request body timeout") from None
        if not chunk:
            raise _RejectedPostError(HTTPStatus.BAD_REQUEST, "incomplete request body")
        remaining -= len(chunk)
        if _monotonic() >= deadline:
            raise _RejectedPostError(HTTPStatus.REQUEST_TIMEOUT, "request body timeout")


class OptimusGatewayHandler(BaseHTTPRequestHandler):
    config: GatewayServiceConfig
    upstream_client: UpstreamClient
    tool_dependencies: GatewayToolDependencies | None = None
    trace_exporter: TraceExporter

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        tool_mode = False
        trace_mode = False
        if self.path == "/v1/responses":
            handler = handle_responses_request
        elif self.path == "/v1/chat/completions":
            handler = handle_chat_completions_request
        elif self.path == "/v1/observability/traces":
            handler = handle_observability_traces_request
            trace_mode = True
        elif self.path in TOOL_ROUTE_PATHS and self.tool_dependencies is not None:
            tool_mode = True
        else:
            self._reject_unhandled_post()
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

        if tool_mode:
            status, body = handle_tool_request(
                authorization_header=self.headers.get("Authorization"),
                path=self.path,
                request_body=request_body,
                config=self.config,
                dependencies=self.tool_dependencies,
            )
        elif trace_mode:
            status, body = handler(
                authorization_header=self.headers.get("Authorization"),
                request_body=request_body,
                config=self.config,
                upstream_client=self.upstream_client,
                trace_exporter=self.trace_exporter,
            )
        else:
            status, body = handler(
                authorization_header=self.headers.get("Authorization"),
                request_body=request_body,
                config=self.config,
                upstream_client=self.upstream_client,
            )
        self._send_json(HTTPStatus(status), body)

    def _reject_unhandled_post(self) -> None:
        """Terminal handling for the early-404 branch: consume a bounded, well-framed body first."""
        self.close_connection = True
        deadline = _monotonic() + _REJECTED_POST_BODY_SECONDS
        try:
            length = _rejected_post_length(self.headers)
            if length:
                _discard_rejected_post_body(self.rfile, self.connection, length, deadline)
        except _RejectedPostError as rejection:
            status, body = rejection.status, {"error": rejection.error}
        else:
            status, body = HTTPStatus.NOT_FOUND, {"error": "not found"}
        self._send_json(status, body, write_deadline=_monotonic() + _REJECTED_POST_WRITE_SECONDS)

    def _arm_write_deadline(self, deadline: float) -> None:
        remaining = deadline - _monotonic()
        if remaining <= 0:
            raise TimeoutError("response write deadline expired")
        self.connection.settimeout(remaining)

    def _send_json(self, status: HTTPStatus | int, body: dict[str, Any], *, write_deadline: float | None = None) -> None:
        payload = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        code = int(status)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        if write_deadline is not None:
            self._arm_write_deadline(write_deadline)
        self.end_headers()
        if write_deadline is not None:
            self._arm_write_deadline(write_deadline)
        self.wfile.write(payload)


def serve_gateway(
    *,
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient | None = None,
    tool_dependencies: GatewayToolDependencies | None = None,
    trace_exporter: TraceExporter | None = None,
) -> ThreadingHTTPServer:
    client = upstream_client or build_upstream_client(config)
    resolved_tool_dependencies = tool_dependencies if tool_dependencies is not None else build_tool_dependencies(config)
    # Plan 11.5, Task 4: config carries the Gateway-only OTLP endpoint
    # (`config.otlp_endpoint`, read from `OTEL_EXPORTER_OTLP_ENDPOINT`); the
    # default exporter is built from it here so every `serve_gateway(config=...)`
    # call site (including the standalone `__main__` entrypoint) picks it up
    # without needing its own explicit `trace_exporter=` argument.
    resolved_trace_exporter = (
        trace_exporter if trace_exporter is not None else OpenTelemetryTraceExporter(otlp_endpoint=config.otlp_endpoint)
    )

    class _BoundHandler(OptimusGatewayHandler):
        pass

    _BoundHandler.config = config
    _BoundHandler.upstream_client = client
    _BoundHandler.tool_dependencies = resolved_tool_dependencies
    _BoundHandler.trace_exporter = resolved_trace_exporter
    server = ThreadingHTTPServer((config.bind_host, config.bind_port), _BoundHandler)
    return server
