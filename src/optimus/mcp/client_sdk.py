"""Agent-owned MCP SDK adapter with injected seams and hard bounds."""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, TypeVar
from urllib.parse import urlparse

from optimus.guardrails.prompt_injection import ConfigTrustScanner, TrustScanSubject, TrustScanVerdict
from optimus.mcp.client_config import ClientMcpRuntimeCapability
from optimus.mcp.client_supervisor import (
    MCPAsyncSupervisor,
    MCPSupervisorError,
    select_process_tree_teardown_seam,
)

_SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-11-25", "2026-07-28"})
T = TypeVar("T")


async def _close_nothing() -> None:
    return None


class ClientMcpSdkError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"ClientMcpSdkError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass
class ClientMcpConnection:
    session_id: str
    identity_key: tuple[str, str, str]
    session: Any
    negotiated_protocol_version: str
    close_resources: Callable[[], Awaitable[None]] = _close_nothing
    dns_rebinding_residual: str = "accepted_residual_initial_origin_only"
    call_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    closed: bool = False


def stdio_server_parameters_from_capability(capability: ClientMcpRuntimeCapability) -> Any:
    """Build MCP StdioServerParameters using only the Task-1-resolved canonical path.

    CVE-2026-30623 precedent: never pass a client-supplied bare command token here.
    """
    from mcp.client.stdio import StdioServerParameters

    identity = capability.safe_identity
    if identity.transport != "stdio":
        raise ClientMcpSdkError("INVALID_TRANSPORT")
    return StdioServerParameters(
        command=identity.canonical_target,
        args=list(identity.arguments),
        env=capability.constructed_child_environ() or None,
    )


class ClientMcpSdkAdapter:
    def __init__(
        self,
        *,
        supervisor: MCPAsyncSupervisor,
        session_factory: Callable[[ClientMcpRuntimeCapability], Any],
        http_client_factory: Callable[[], Any],
        stdio_transport_factory: Callable[[ClientMcpRuntimeCapability], Any],
        process_control: Any,
        transport_context_factory: Callable[[ClientMcpRuntimeCapability], Any] | None = None,
        session_context_factory: Callable[[Any, Any], Any] | None = None,
        connection_budget: int = 8,
        scanner: ConfigTrustScanner | None = None,
        operation_timeout_seconds: float = 30.0,
        max_message_bytes: int = 1 * 1024 * 1024,
    ) -> None:
        self._supervisor = supervisor
        self._session_factory = session_factory
        self._http_client_factory = http_client_factory
        self._stdio_transport_factory = stdio_transport_factory
        self._process_control = process_control
        if (transport_context_factory is None) != (session_context_factory is None):
            raise ValueError("SDK transport and session context factories must be supplied together")
        self._transport_context_factory = transport_context_factory
        self._session_context_factory = session_context_factory
        self._connection_budget = connection_budget
        self._scanner = scanner or ConfigTrustScanner()
        self._operation_timeout_seconds = operation_timeout_seconds
        self._max_message_bytes = max_message_bytes
        self._connections: dict[tuple[str, str, str], ClientMcpConnection] = {}
        self._open_lock = asyncio.Lock()

    def __getstate__(self) -> None:
        raise TypeError("client mcp sdk adapter is not serializable")

    def __reduce__(self) -> None:
        raise TypeError("client mcp sdk adapter is not serializable")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("client mcp sdk adapter is not serializable")

    def _submit_operation(self, coro: Coroutine[object, object, T]) -> T:
        try:
            return self._supervisor.submit(coro, timeout_seconds=self._operation_timeout_seconds)
        except MCPSupervisorError as exc:
            if exc.code == "SUBMIT_TIMEOUT":
                raise ClientMcpSdkError("OPERATION_TIMEOUT") from exc
            raise

    def open(
        self,
        capability: ClientMcpRuntimeCapability,
        *,
        session_id: str,
        proposed_protocol_version: str = "2026-07-28",
    ) -> ClientMcpConnection:
        return self._submit_operation(
            self._open_async(
                capability,
                session_id=session_id,
                proposed_protocol_version=proposed_protocol_version,
            )
        )

    def discover(self, connection: ClientMcpConnection) -> list[dict[str, Any]]:
        return self._submit_operation(self._discover_async(connection))

    def call(self, connection: ClientMcpConnection, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._submit_operation(self._call_async(connection, tool, arguments))

    def close(self, connection: ClientMcpConnection) -> None:
        self._submit_operation(self._close_async(connection))

    def close_all(self) -> None:
        for connection in tuple(self._connections.values()):
            self.close(connection)

    def read_streamed_bytes_for_tests(
        self,
        client: Any,
        *,
        budget_bytes: int,
        url: str = "https://example.invalid/stream",
    ) -> bytes:
        return self._submit_operation(
            self._read_streamed_bytes(client, budget_bytes=budget_bytes, url=url)
        )

    async def _open_async(
        self,
        capability: ClientMcpRuntimeCapability,
        *,
        session_id: str,
        proposed_protocol_version: str,
    ) -> ClientMcpConnection:
        identity = capability.safe_identity
        identity_key = (session_id, identity.server_name, identity.canonical_target)

        if identity.transport in {"http", "sse"}:
            _deny_reserved_address(identity.canonical_target)

        # Single-flight: reuse a live connection for the same identity key so the
        # process-wide budget tracks real sessions, not dict-key overwrites.
        async with self._open_lock:
            existing = self._connections.get(identity_key)
            if existing is not None and not existing.closed:
                return existing

            if len(self._connections) >= self._connection_budget:
                raise ClientMcpSdkError("CONNECTION_BUDGET_EXCEEDED")

            if self._transport_context_factory is not None:
                return await self._open_owned_sdk_contexts(
                    capability,
                    session_id=session_id,
                    identity_key=identity_key,
                    proposed_protocol_version=proposed_protocol_version,
                )

            if identity.transport == "stdio":
                # Resolve StdioServerParameters only from canonical_target (CVE-2026-30623).
                _ = stdio_server_parameters_from_capability(capability)
                transport = self._stdio_transport_factory(capability)
                try:
                    frame = await asyncio.wait_for(
                        transport.read_message(),
                        timeout=self._operation_timeout_seconds,
                    )
                except TimeoutError as exc:
                    await transport.close()
                    raise ClientMcpSdkError("OPERATION_TIMEOUT") from exc
                if len(frame) > self._max_message_bytes:
                    await transport.close()
                    raise ClientMcpSdkError("STDIO_FRAME_OVERFLOW")

            # Ensure http client is constructed with hardened flags when factory is used.
            http_client = self._http_client_factory()
            if getattr(http_client, "follow_redirects", False) is not False:
                raise ClientMcpSdkError("HTTP_REDIRECTS_ENABLED")
            if getattr(http_client, "trust_env", False) is not False:
                raise ClientMcpSdkError("HTTP_TRUST_ENV_ENABLED")

            session = self._session_factory(capability)
            try:
                result = await asyncio.wait_for(
                    session.initialize(proposed_protocol_version=proposed_protocol_version),
                    timeout=self._operation_timeout_seconds,
                )
            except TimeoutError as exc:
                raise ClientMcpSdkError("OPERATION_TIMEOUT") from exc

            protocol_version = getattr(result, "protocol_version", None)
            if not isinstance(protocol_version, str) or protocol_version not in _SUPPORTED_PROTOCOL_VERSIONS:
                raise ClientMcpSdkError("INVALID_PROTOCOL_VERSION")

            scan_text = "\n".join(
                [
                    str(getattr(result, "instructions", "") or ""),
                    str((getattr(result, "server_info", {}) or {}).get("description", "")),
                    str((getattr(result, "server_info", {}) or {}).get("name", "")),
                ]
            )
            scan = self._scanner.scan_text(
                scan_text,
                subject=TrustScanSubject.MCP_INITIALIZE_RESULT,
                source_path="mcp:initialize",
            )
            if scan.verdict is TrustScanVerdict.BLOCK:
                code = scan.findings[0].rule_id if scan.findings else "INITIALIZE_BLOCKED"
                raise ClientMcpSdkError(code)

            # Advertised prompts/resources are ignored; tools-only client continues.
            connection = ClientMcpConnection(
                session_id=session_id,
                identity_key=identity_key,
                session=session,
                negotiated_protocol_version=protocol_version,
            )
            self._connections[identity_key] = connection
            return connection

    async def _open_owned_sdk_contexts(
        self,
        capability: ClientMcpRuntimeCapability,
        *,
        session_id: str,
        identity_key: tuple[str, str, str],
        proposed_protocol_version: str,
    ) -> ClientMcpConnection:
        """Enter and retain the exact SDK contexts that own one connection."""
        assert self._transport_context_factory is not None
        assert self._session_context_factory is not None
        transport_context = self._transport_context_factory(capability)
        entered_transport = False
        session_context: Any | None = None
        entered_session = False

        async def _close_resources() -> None:
            if entered_session:
                assert session_context is not None
                try:
                    await session_context.__aexit__(None, None, None)
                finally:
                    if entered_transport:
                        await transport_context.__aexit__(None, None, None)
            elif entered_transport:
                await transport_context.__aexit__(None, None, None)

        try:
            streams = await transport_context.__aenter__()
            entered_transport = True
            read_stream, write_stream = _stream_pair(streams)
            session_context = self._session_context_factory(read_stream, write_stream)
            session = await session_context.__aenter__()
            entered_session = True
            protocol_version = await self._initialize_and_scan(
                session,
                proposed_protocol_version=proposed_protocol_version,
            )
        except BaseException:
            with suppress(Exception):
                await _close_resources()
            raise

        connection = ClientMcpConnection(
            session_id=session_id,
            identity_key=identity_key,
            session=session,
            negotiated_protocol_version=protocol_version,
            close_resources=_close_resources,
        )
        self._connections[identity_key] = connection
        return connection

    async def _initialize_and_scan(self, session: Any, *, proposed_protocol_version: str) -> str:
        try:
            result = await asyncio.wait_for(
                session.initialize(proposed_protocol_version=proposed_protocol_version),
                timeout=self._operation_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ClientMcpSdkError("OPERATION_TIMEOUT") from exc

        protocol_version = getattr(result, "protocol_version", None)
        if not isinstance(protocol_version, str) or protocol_version not in _SUPPORTED_PROTOCOL_VERSIONS:
            raise ClientMcpSdkError("INVALID_PROTOCOL_VERSION")

        scan_text = "\n".join(
            [
                str(getattr(result, "instructions", "") or ""),
                str((getattr(result, "server_info", {}) or {}).get("description", "")),
                str((getattr(result, "server_info", {}) or {}).get("name", "")),
            ]
        )
        scan = self._scanner.scan_text(
            scan_text,
            subject=TrustScanSubject.MCP_INITIALIZE_RESULT,
            source_path="mcp:initialize",
        )
        if scan.verdict is TrustScanVerdict.BLOCK:
            code = scan.findings[0].rule_id if scan.findings else "INITIALIZE_BLOCKED"
            raise ClientMcpSdkError(code)
        return protocol_version

    async def _close_async(self, connection: ClientMcpConnection) -> None:
        if connection.closed:
            return
        connection.closed = True
        key = connection.identity_key
        # Only tear down the slot if this handle is the live tracked connection.
        # Popping by key alone would close a different live session after reuse races.
        if self._connections.get(key) is not connection:
            return
        self._connections.pop(key, None)
        try:
            await connection.close_resources()
        finally:
            seam = select_process_tree_teardown_seam()
            self._process_control.terminate_tree(seam=seam)

    async def _discover_async(self, connection: ClientMcpConnection) -> list[dict[str, Any]]:
        async with connection.call_lock:
            try:
                return await asyncio.wait_for(
                    connection.session.list_tools(),
                    timeout=self._operation_timeout_seconds,
                )
            except TimeoutError as exc:
                raise ClientMcpSdkError("OPERATION_TIMEOUT") from exc

    async def _call_async(
        self, connection: ClientMcpConnection, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        async with connection.call_lock:
            try:
                return await asyncio.wait_for(
                    connection.session.call_tool(tool, arguments),
                    timeout=self._operation_timeout_seconds,
                )
            except TimeoutError as exc:
                raise ClientMcpSdkError("OPERATION_TIMEOUT") from exc
            except ClientMcpSdkError:
                raise
            except Exception as exc:
                raise ClientMcpSdkError("CALL_FAILED") from exc

    async def _read_streamed_bytes(self, client: Any, *, budget_bytes: int, url: str) -> bytes:
        """Enforce an Optimus-owned streamed byte budget on a real or test HTTP client.

        Matches ``httpx2.AsyncClient.stream`` (async context manager). Legacy awaitable
        stream factories used by unit fakes are still accepted.
        """
        stream_obj = client.stream("GET", url)
        if hasattr(stream_obj, "__await__"):
            stream_obj = await stream_obj
        total = bytearray()
        async with stream_obj as response:
            aiter = getattr(response, "aiter_bytes", None)
            if aiter is None:
                aiter = stream_obj.aiter_bytes
            async for chunk in aiter():
                total.extend(chunk)
                if len(total) > budget_bytes:
                    raise ClientMcpSdkError("REMOTE_BYTE_OVERFLOW")
        return bytes(total)


def _deny_reserved_address(url: str) -> None:
    host = (urlparse(url).hostname or "").strip().lower()
    if not host:
        raise ClientMcpSdkError("RESERVED_ADDRESS_DENIED")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_loopback or address.is_private or address.is_link_local or address.is_reserved:
        raise ClientMcpSdkError("RESERVED_ADDRESS_DENIED")


def _stream_pair(streams: Any) -> tuple[Any, Any]:
    if hasattr(streams, "read_stream") and hasattr(streams, "write_stream"):
        return streams.read_stream, streams.write_stream
    return streams[0], streams[1]


def build_sdk_transport_context_factory(
    *,
    http_client_factory: Callable[[], Any],
) -> Callable[[ClientMcpRuntimeCapability], Any]:
    """Build the production MCP SDK transport factory without opening a connection."""

    def _factory(capability: ClientMcpRuntimeCapability) -> Any:
        identity = capability.safe_identity
        if identity.transport == "stdio":
            from mcp.client.stdio import stdio_client

            return stdio_client(stdio_server_parameters_from_capability(capability))
        if identity.transport == "http":
            return _streamable_http_transport_context(
                identity.canonical_target,
                http_client_factory=http_client_factory,
            )
        if identity.transport == "sse":
            return _sse_transport_context(
                identity.canonical_target,
                http_client_factory=http_client_factory,
            )
        raise ClientMcpSdkError("INVALID_TRANSPORT")

    return _factory


def build_sdk_session_context_factory() -> Callable[[Any, Any], Any]:
    def _factory(read_stream: Any, write_stream: Any) -> Any:
        from mcp import ClientSession

        return ClientSession(read_stream, write_stream)

    return _factory


@asynccontextmanager
async def _streamable_http_transport_context(
    url: str,
    *,
    http_client_factory: Callable[[], Any],
) -> AsyncIterator[Any]:
    from mcp.client.streamable_http import streamable_http_client

    client = http_client_factory()
    try:
        async with streamable_http_client(url, http_client=client) as streams:
            yield streams
    finally:
        await client.aclose()


@asynccontextmanager
async def _sse_transport_context(
    url: str,
    *,
    http_client_factory: Callable[[], Any],
) -> AsyncIterator[Any]:
    from mcp.client.sse import sse_client

    client = http_client_factory()
    try:
        async with sse_client(url, httpx_client_factory=lambda **_kwargs: client) as streams:
            yield streams
    finally:
        await client.aclose()
