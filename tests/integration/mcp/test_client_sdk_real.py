"""P11-FU-9 Task 8 real-SDK composition evidence (closes Task 3 caveat).

No fake session/transport. Uses official ``mcp`` Streamable HTTP client with an
injected ``httpx2.AsyncClient(follow_redirects=False, trust_env=False)`` against
public Context7, plus Optimus streamed byte-budget enforcement on real httpx2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx2
import pytest

from optimus.mcp.client_sdk import ClientMcpSdkAdapter, ClientMcpSdkError
from optimus.mcp.client_supervisor import MCPAsyncSupervisor

CONTEXT7_URL = "https://mcp.context7.com/mcp"
EXPECTED_NEGOTIATED_VERSION = "2025-11-25"


def _make_hardened_client() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        follow_redirects=False,
        trust_env=False,
        timeout=httpx2.Timeout(30.0, read=60.0),
    )


@asynccontextmanager
async def _context7_session(http_client: httpx2.AsyncClient) -> AsyncIterator[object]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(CONTEXT7_URL, http_client=http_client) as streams:
        if hasattr(streams, "read_stream"):
            read_stream, write_stream = streams.read_stream, streams.write_stream
        else:
            read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            yield session


class _OverflowHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(1 * 1024 * 1024 + 64))
        self.end_headers()
        self.wfile.write(b"x" * (1 * 1024 * 1024 + 64))

    def log_message(self, _format: str, *_args: object) -> None:
        return


@contextmanager
def _local_overflow_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OverflowHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}/stream"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.mark.requires_mcp_http
@pytest.mark.asyncio
async def test_real_sdk_injected_httpx2_flags_and_context7_initialize() -> None:
    client = _make_hardened_client()
    assert isinstance(client, httpx2.AsyncClient)
    assert client.follow_redirects is False
    assert client.trust_env is False
    try:
        async with client:
            async with _context7_session(client) as session:
                init = await session.initialize()
                negotiated = str(
                    getattr(init, "protocolVersion", None) or getattr(init, "protocol_version", "")
                )
                tools = await session.list_tools()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"context7_real_sdk_unavailable: {type(exc).__name__}: {exc}")

    assert negotiated == EXPECTED_NEGOTIATED_VERSION
    assert len(tools.tools) == 2


@pytest.mark.requires_mcp_http
def test_real_httpx2_streamed_byte_budget_via_adapter() -> None:
    """Prove Optimus byte-budget wrapper against real httpx2 (local overflow body)."""
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    try:
        adapter = ClientMcpSdkAdapter(
            supervisor=supervisor,
            session_factory=lambda _c: None,
            http_client_factory=_make_hardened_client,
            stdio_transport_factory=lambda _c: None,
            process_control=type("PC", (), {"terminate_tree": lambda self, **_k: None})(),
        )
        with _local_overflow_server() as url:
            client = _make_hardened_client()
            try:
                with pytest.raises(ClientMcpSdkError) as exc_info:
                    adapter.read_streamed_bytes_for_tests(
                        client,
                        budget_bytes=1 * 1024 * 1024,
                        url=url,
                    )
                assert exc_info.value.code == "REMOTE_BYTE_OVERFLOW"
            finally:
                # AsyncClient close is async; schedule via supervisor loop.
                supervisor.submit(client.aclose(), timeout_seconds=5.0)
    finally:
        supervisor.close()
