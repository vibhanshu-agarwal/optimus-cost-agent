from __future__ import annotations

import json
from typing import Literal

import pytest

from optimus_gateway.mcp_profiles import (
    MCPAttributionPolicy,
    MCPHTTPProfile,
    MCPProfile,
    MCPProfileDefinitionError,
    MCPProfileState,
    MCPResourceLimits,
    MCPStdioProfile,
)
from optimus_gateway.mcp_transports import (
    DockerStdioMCPTransport,
    MCPTransportError,
    StreamableHTTPMCPTransport,
)


def _http_profile(
    *,
    endpoint: str = "https://mcp.example/tools",
    allow_insecure_loopback: bool = False,
    credential_ref: str | None = "context7-token",
    auth_mode: Literal["bearer", "none"] = "bearer",
) -> MCPProfile:
    return MCPProfile(
        profile_id="context7",
        revision="rev-1",
        state=MCPProfileState.PENDING_REGISTRATION,
        transport="http",
        credential_ref=credential_ref,
        upstream_allowlist=("fetch",),
        manifest_hash=None,
        limits=MCPResourceLimits(max_result_bytes=1024),
        attribution_policy=MCPAttributionPolicy(),
        transport_config=MCPHTTPProfile(endpoint, allow_insecure_loopback=allow_insecure_loopback, auth_mode=auth_mode),
    )


def _stdio_profile(*, image: str = "registry.example/mcp@sha256:" + "a" * 64) -> MCPProfile:
    return MCPProfile(
        profile_id="local",
        revision="rev-1",
        state=MCPProfileState.PENDING_REGISTRATION,
        transport="stdio",
        credential_ref="local-token",
        upstream_allowlist=("fetch",),
        manifest_hash=None,
        limits=MCPResourceLimits(max_call_duration_seconds=30, max_result_bytes=1024),
        attribution_policy=MCPAttributionPolicy(),
        transport_config=MCPStdioProfile(
            image=image,
            command="/app/server",
            arguments=("--stdio",),
            environment_names=("MCP_TOKEN",),
        ),
    )


class _HTTPResponse:
    def __init__(self, body: dict[str, object], *, url: str, status: int = 200) -> None:
        self._body = json.dumps(body).encode()
        self._url = url
        self.status = status

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self._body
        result, self._body = self._body[:size], self._body[size:]
        return result

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> _HTTPResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _HTTPOpener:
    def __init__(self, response: _HTTPResponse) -> None:
        self.response = response
        self.requests = []

    def open(self, request, *, timeout: float):
        self.requests.append((request, timeout))
        return self.response


def test_http_transport_posts_only_json_with_pinned_auth_and_request_metadata() -> None:
    opener = _HTTPOpener(
        _HTTPResponse(
            {"result": {"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}}},
            url="https://mcp.example/tools",
        )
    )
    transport = StreamableHTTPMCPTransport(
        _http_profile(), opener=opener, credential_resolver=lambda _ref: "secret"
    )

    result = transport.server_discover(protocol_version="2026-07-28", client_meta={"name": "client", "version": "1"})

    request, timeout = opener.requests[0]
    payload = json.loads(request.data)
    assert request.method == "POST"
    assert request.full_url == "https://mcp.example/tools"
    assert request.headers["Content-type"] == "application/json"
    assert request.headers["Accept"] == "application/json, text/event-stream"
    assert request.headers["Authorization"] == "Bearer secret"
    assert request.headers["Mcp-protocol-version"] == "2026-07-28"
    assert "Mcp-session-id" not in request.headers
    assert payload["method"] == "server/discover"
    assert payload["params"]["_meta"] == {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "client", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {"tools": {}},
    }
    assert result["protocolVersion"] == "2026-07-28"
    assert timeout == 30.0


def test_http_transport_emits_namespaced_2026_metadata_and_method_headers():
    opener = _HTTPOpener(
        _HTTPResponse(
            {"result": {"capabilities": {"tools": {}}}},
            url="https://mcp.example/tools",
        )
    )
    transport = StreamableHTTPMCPTransport(
        _http_profile(), opener=opener, credential_resolver=lambda _ref: "secret"
    )

    transport.tools_call(
        upstream_tool_name="resolve-library-id",
        arguments={"libraryName": "pytest"},
        protocol_version="2026-07-28",
    )

    request, _timeout = opener.requests[0]
    payload = json.loads(request.data)
    assert request.headers["Accept"] == "application/json, text/event-stream"
    assert request.headers["Mcp-method"] == "tools/call"
    assert request.headers["Mcp-name"] == "resolve-library-id"
    assert payload["params"]["_meta"] == {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "optimus-gateway", "version": "1.0"},
        "io.modelcontextprotocol/clientCapabilities": {"tools": {}},
    }


def test_http_none_does_not_resolve_or_send_a_bearer_credential():
    opener = _HTTPOpener(
        _HTTPResponse(
            {"result": {"capabilities": {"tools": {}}}},
            url="https://mcp.example/tools",
        )
    )
    resolver_calls: list[str | None] = []
    transport = StreamableHTTPMCPTransport(
        _http_profile(auth_mode="none", credential_ref=None),
        opener=opener,
        credential_resolver=lambda ref: resolver_calls.append(ref) or "must-not-be-used",
    )

    transport.server_discover(protocol_version="2026-07-28", client_meta={"name": "client", "version": "1"})

    request, _timeout = opener.requests[0]
    assert resolver_calls == []
    assert "Authorization" not in request.headers


@pytest.mark.parametrize(
    ("endpoint", "allow_insecure_loopback"),
    [("http://mcp.example/tools", False), ("http://127.0.0.1:8765/tools", False)],
)
def test_http_transport_rejects_non_tls_or_unprovisioned_loopback(endpoint: str, allow_insecure_loopback: bool) -> None:
    with pytest.raises(MCPTransportError, match="HTTPS"):
        StreamableHTTPMCPTransport(
            _http_profile(endpoint=endpoint, allow_insecure_loopback=allow_insecure_loopback),
            opener=_HTTPOpener(_HTTPResponse({}, url=endpoint)),
        )


def test_http_transport_accepts_explicit_loopback_exception_and_rejects_redirect_origin() -> None:
    endpoint = "http://127.0.0.1:8765/tools"
    transport = StreamableHTTPMCPTransport(
        _http_profile(endpoint=endpoint, allow_insecure_loopback=True),
        opener=_HTTPOpener(_HTTPResponse({}, url="https://attacker.example/tools")),
        credential_resolver=lambda _ref: "secret",
    )
    with pytest.raises(MCPTransportError, match="redirect|origin"):
        transport.tools_list(cursor=None, protocol_version="2026-07-28", client_meta={"name": "c", "version": "1"})


def test_http_transport_requires_profile_credential_resolution_before_request() -> None:
    transport = StreamableHTTPMCPTransport(
        _http_profile(), opener=_HTTPOpener(_HTTPResponse({}, url="https://mcp.example/tools"))
    )
    with pytest.raises(MCPTransportError, match="credential"):
        transport.tools_list(cursor=None, protocol_version="2026-07-28", client_meta={"name": "c", "version": "1"})


def test_http_transport_rejects_forbidden_capabilities_and_oversized_results() -> None:
    endpoint = "https://mcp.example/tools"
    forbidden = _HTTPOpener(
        _HTTPResponse(
            {"result": {"protocolVersion": "2026-07-28", "capabilities": {"tools": {}, "sampling": {}}}},
            url=endpoint,
        )
    )
    with pytest.raises(MCPTransportError, match="capabilit"):
        StreamableHTTPMCPTransport(
            _http_profile(), opener=forbidden, credential_resolver=lambda _ref: "secret"
        ).server_discover(
            protocol_version="2026-07-28", client_meta={"name": "c", "version": "1"}
        )

    oversized = _HTTPOpener(_HTTPResponse({"result": {"ok": True}}, url=endpoint))
    profile = _http_profile()
    transport = StreamableHTTPMCPTransport(
        profile, opener=oversized, credential_resolver=lambda _ref: "secret", max_response_bytes=1
    )
    with pytest.raises(MCPTransportError, match="byte"):
        transport.tools_list(cursor=None, protocol_version="2026-07-28", client_meta={"name": "c", "version": "1"})


def test_http_transport_enforces_duration_between_response_chunks() -> None:
    now = [0.0]
    clock_calls = [0]

    class _SlowChunkedResponse:
        status = 200

        def geturl(self) -> str:
            return "https://mcp.example/tools"

        def read(self, _size: int = -1) -> bytes:
            if not clock_calls[0]:
                clock_calls[0] += 1
                now[0] = 31.0
                return b"{"
            if clock_calls[0] == 1:
                pytest.fail("transport requested another chunk after the duration deadline")
            return b""

    opener = _HTTPOpener(_SlowChunkedResponse())
    transport = StreamableHTTPMCPTransport(
        _http_profile(),
        opener=opener,
        credential_resolver=lambda _ref: "secret",
        clock=lambda: now[0],
    )
    with pytest.raises(MCPTransportError, match="duration"):
        transport.tools_list(cursor=None, protocol_version="2026-07-28", client_meta={"name": "c", "version": "1"})


class _Pipe:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = responses
        self.writes: list[bytes] = []

    def write(self, value: bytes) -> int:
        self.writes.append(value)
        return len(value)

    def flush(self) -> None:
        return None

    def readline(self, _size: int = -1) -> bytes:
        return self.responses.pop(0)


class _Process:
    def __init__(self, responses: list[bytes]) -> None:
        self.stdin = _Pipe([])
        self.stdout = _Pipe(responses)
        self.stderr = _Pipe([])
        self.terminated = False

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True

    def wait(self, *, timeout: float) -> None:
        del timeout


class _ProcessControl:
    def __init__(self) -> None:
        self.closed = []

    def readline(self, stream, *, timeout: float) -> bytes:
        del timeout
        return stream.readline()

    def terminate_tree(self, process) -> None:
        self.closed.append(process)


def test_stdio_transport_builds_digest_pinned_no_mount_docker_argv_and_safe_environment() -> None:
    process = _Process([json.dumps({"result": {"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}}}).encode() + b"\n"])
    created = []
    control = _ProcessControl()
    transport = DockerStdioMCPTransport(
        _stdio_profile(),
        process_factory=lambda argv, env: created.append((argv, env)) or process,
        credential_resolver=lambda _ref: {"MCP_TOKEN": "secret"},
        process_control=control,
    )
    transport.server_discover(protocol_version="2026-07-28", client_meta={"name": "client", "version": "1"})

    argv, env = created[0]
    assert argv == [
        "docker", "run", "--rm", "--init", "--read-only", "--network", "none", "--env", "MCP_TOKEN",
        "registry.example/mcp@sha256:" + "a" * 64, "/app/server", "--stdio",
    ]
    assert env == {"MCP_TOKEN": "secret"}
    assert not any("=" in token for token in argv)
    assert not any(token in argv for token in ("--mount", "-v", "--device", "/var/run/docker.sock"))
    assert process.stdin.writes
    assert json.loads(process.stdin.writes[0])["method"] == "server/discover"
    transport.close()
    assert control.closed == [process]


@pytest.mark.parametrize("image", ["registry.example/mcp:latest", "registry.example/mcp@sha256:bad"])
def test_stdio_transport_rejects_non_digest_images_before_spawning(image: str) -> None:
    with pytest.raises((MCPTransportError, MCPProfileDefinitionError), match="digest"):
        DockerStdioMCPTransport(
            _stdio_profile(image=image), process_factory=lambda _argv, _env: pytest.fail("must not spawn")
        )


def test_stdio_transport_falls_back_to_tools_only_legacy_initialization() -> None:
    responses = [
        json.dumps({"error": {"code": -32601, "message": "method not found"}}).encode() + b"\n",
        json.dumps({"result": {"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}}}).encode() + b"\n",
    ]
    process = _Process(responses)
    transport = DockerStdioMCPTransport(
        _stdio_profile(), process_factory=lambda _argv, _env: process,
        credential_resolver=lambda _ref: {"MCP_TOKEN": "secret"},
    )
    result = transport.server_discover(protocol_version="2026-07-28", client_meta={"name": "c", "version": "1"})
    methods = [json.loads(written)["method"] for written in process.stdin.writes]
    assert methods == ["server/discover", "initialize"]
    assert result["protocolVersion"] == "2026-07-28"


def test_stdio_transport_rejects_forbidden_capabilities() -> None:
    process = _Process(
        [
            json.dumps(
                {"result": {"protocolVersion": "2026-07-28", "capabilities": {"tools": {}, "sampling": {}}}}
            ).encode()
            + b"\n"
        ]
    )
    transport = DockerStdioMCPTransport(
        _stdio_profile(),
        process_factory=lambda _argv, _env: process,
        credential_resolver=lambda _ref: {"MCP_TOKEN": "secret"},
    )
    with pytest.raises(MCPTransportError, match="capabilit"):
        transport.server_discover(protocol_version="2026-07-28", client_meta={"name": "c", "version": "1"})


def test_stdio_transport_enforces_response_bytes_and_duration_limits() -> None:
    oversized = _Process([json.dumps({"result": {"payload": "x" * 1100}}).encode() + b"\n"])
    transport = DockerStdioMCPTransport(
        _stdio_profile(), process_factory=lambda _argv, _env: oversized,
        credential_resolver=lambda _ref: {"MCP_TOKEN": "secret"},
    )
    with pytest.raises(MCPTransportError, match="byte"):
        transport.tools_list(cursor=None, protocol_version="2026-07-28", client_meta={"name": "c", "version": "1"})

    timed = _Process([json.dumps({"result": {"ok": True}}).encode() + b"\n"])
    clock_values = iter((0.0, 31.0))
    transport = DockerStdioMCPTransport(
        _stdio_profile(), process_factory=lambda _argv, _env: timed,
        credential_resolver=lambda _ref: {"MCP_TOKEN": "secret"},
        clock=lambda: next(clock_values),
    )
    with pytest.raises(MCPTransportError, match="duration"):
        transport.tools_list(cursor=None, protocol_version="2026-07-28", client_meta={"name": "c", "version": "1"})
