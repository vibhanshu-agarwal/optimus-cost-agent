"""Agent-owned MCP SDK adapter with injected seams and hard bounds."""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from optimus.guardrails.prompt_injection import ConfigTrustScanner, TrustScanSubject, TrustScanVerdict
from optimus.mcp.client_config import ClientMcpRuntimeCapability
from optimus.mcp.client_supervisor import (
    MCPAsyncSupervisor,
    MCPSupervisorError,
    select_process_tree_teardown_seam,
)

_SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-11-25", "2026-07-28"})


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
        self._connection_budget = connection_budget
        self._scanner = scanner or ConfigTrustScanner()
        self._operation_timeout_seconds = operation_timeout_seconds
        self._max_message_bytes = max_message_bytes
        self._connections: dict[tuple[str, str, str], ClientMcpConnection] = {}
        self._open_lock = asyncio.Lock()

    def open(
        self,
        capability: ClientMcpRuntimeCapability,
        *,
        session_id: str,
        proposed_protocol_version: str = "2026-07-28",
    ) -> ClientMcpConnection:
        return self._supervisor.submit(
            self._open_async(
                capability,
                session_id=session_id,
                proposed_protocol_version=proposed_protocol_version,
            ),
            timeout_seconds=self._operation_timeout_seconds + 1.0,
        )

    def discover(self, connection: ClientMcpConnection) -> list[dict[str, Any]]:
        return self._supervisor.submit(
            self._discover_async(connection),
            timeout_seconds=self._operation_timeout_seconds + 1.0,
        )

    def call(self, connection: ClientMcpConnection, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._supervisor.submit(
                self._call_async(connection, tool, arguments),
                timeout_seconds=self._operation_timeout_seconds + 1.0,
            )
        except MCPSupervisorError as exc:
            raise ClientMcpSdkError(exc.code) from exc

    def close(self, connection: ClientMcpConnection) -> None:
        connection.closed = True
        key = connection.identity_key
        # Only tear down the slot if this handle is the live tracked connection.
        # Popping by key alone would close a different live session after reuse races.
        if self._connections.get(key) is not connection:
            return
        self._connections.pop(key, None)
        seam = select_process_tree_teardown_seam()
        self._process_control.terminate_tree(seam=seam)

    def read_streamed_bytes_for_tests(
        self,
        client: Any,
        *,
        budget_bytes: int,
        url: str = "https://example.invalid/stream",
    ) -> bytes:
        return self._supervisor.submit(
            self._read_streamed_bytes(client, budget_bytes=budget_bytes, url=url),
            timeout_seconds=self._operation_timeout_seconds + 1.0,
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
