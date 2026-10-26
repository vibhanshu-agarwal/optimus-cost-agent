"""Agent-owned MCP SDK adapter with injected seams and hard bounds."""

from __future__ import annotations

import asyncio
import contextvars
import ipaddress
import logging
import threading
import uuid
import weakref
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Never, SupportsIndex, TypeVar
from urllib.parse import urlparse

from optimus.guardrails.prompt_injection import ConfigTrustScanner, TrustScanSubject, TrustScanVerdict
from optimus.mcp.client_config import ClientMcpRuntimeCapability
from optimus.mcp.client_supervisor import (
    MCPAsyncSupervisor,
    MCPSupervisorError,
    select_process_tree_teardown_seam,
)

if TYPE_CHECKING:
    import httpx2
    from mcp.types import CallToolResult, InputRequiredResult, Result


_SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-11-25", "2026-07-28"})
T = TypeVar("T")

_warning_context: contextvars.ContextVar[Any] = contextvars.ContextVar("optimus_sdk_owner", default=None)
_observer_lock = threading.RLock()
_observer_owners: weakref.WeakSet[Any] = weakref.WeakSet()


class _OwnedWarningObserver(logging.Handler):
    def filter(self, record: logging.LogRecord) -> bool:
        context = _warning_context.get()
        if context is not None:
            adapter, connection = context[0](), context[1]()
            if adapter is not None and connection is not None:
                if "still alive after the kill escalation" in str(record.msg):
                    connection.survivor_warning = True
                    adapter.record_diagnostic("SDK_SURVIVOR_WARNING")
                # SDK records may contain raw commands; sanitize only our owned context.
                record.msg, record.args = "owned MCP SDK diagnostic", ()
                record.exc_info = record.exc_text = record.stack_info = None
        return True

    def emit(self, record: logging.LogRecord) -> None:
        pass


_warning_observer: _OwnedWarningObserver | None = None


def _release_warning_observer() -> None:
    global _warning_observer
    with _observer_lock:
        if not tuple(_observer_owners) and _warning_observer is not None:
            logger = logging.getLogger("mcp.client.stdio")
            logger.removeFilter(_warning_observer)
            logger.removeHandler(_warning_observer)
            _warning_observer.close()
            _warning_observer = None


def _warning_snapshot() -> tuple[object, ...]:
    logger = logging.getLogger("mcp.client.stdio")
    with _observer_lock:
        observer = _warning_observer
        channel: list[object] = []
        cursor: logging.Logger | None = logger
        while cursor is not None:
            channel.append((id(cursor), cursor.disabled, cursor.level, cursor.propagate,
                            tuple(map(id, cursor.filters)),
                            tuple((id(h), h.level, tuple(map(id, h.filters))) for h in cursor.handlers)))
            cursor = cursor.parent if cursor.propagate else None
        observable = (observer is not None and observer in logger.handlers and observer in logger.filters
                      and not logger.disabled and logger.getEffectiveLevel() <= logging.WARNING
                      and logging.root.manager.disable < logging.WARNING
                      and logger.filters == [observer] and not observer.filters
                      and observer.level <= logging.WARNING)
        return observable, logging.root.manager.disable, tuple(channel)


def _safe_warning_snapshot() -> tuple[object, ...] | None:
    try:
        return _warning_snapshot()
    except Exception:
        return None


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
    pending_token: str = field(default_factory=lambda: uuid.uuid4().hex)
    transport: str = ""
    owner_request: Callable[[str, tuple[Any, ...]], Awaitable[Any]] | None = field(default=None, repr=False)
    owner_task: asyncio.Task[None] | None = field(default=None, repr=False)
    owner_enter_task_id: int | None = None
    owner_exit_task_id: int | None = None
    owner_terminal: bool = False
    owner_error: BaseException | None = field(default=None, repr=False)
    warning_start: tuple[object, ...] | None = None
    warning_end: tuple[object, ...] | None = None
    survivor_warning: bool = False
    close_requested: bool = False


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
        self.close_failure_recorded = False
        self._diagnostics: deque[str] = deque(maxlen=256)
        self.diagnostics_dropped = 0
        global _warning_observer
        with _observer_lock:
            if _warning_observer is None:
                _warning_observer = _OwnedWarningObserver()
                logger = logging.getLogger("mcp.client.stdio")
                logger.addFilter(_warning_observer)
                logger.addHandler(_warning_observer)
            _observer_owners.add(self)
        weakref.finalize(self, _release_warning_observer)

    @staticmethod
    def stdio_warning_channel_observable() -> bool:
        snapshot = _safe_warning_snapshot()
        return snapshot is not None and bool(snapshot[0])

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(self._diagnostics)

    def record_diagnostic(self, code: str) -> None:
        if code not in {"SDK_SURVIVOR_WARNING", "CLOSE_FAILED", "CLEANUP_UNCERTAIN", "WARNING_UNOBSERVABLE"}:
            raise ValueError("unknown SDK diagnostic")
        with _observer_lock:
            if len(self._diagnostics) == self._diagnostics.maxlen:
                self.diagnostics_dropped += 1
            self._diagnostics.append(code)

    def pending_connections(self) -> tuple[str, ...]:
        if not self._connections:
            return ()
        async def inspect() -> tuple[str, ...]:
            return tuple(connection.pending_token for connection in self._connections.values())
        return self._submit_operation(inspect())

    def has_pending_connections_for_session(self, session_id: str) -> bool:
        if not self._connections:
            return False
        async def inspect() -> bool:
            return any(connection.session_id == session_id for connection in self._connections.values())
        return self._submit_operation(inspect())

    def __getstate__(self) -> None:
        raise TypeError("client mcp sdk adapter is not serializable")

    def __reduce__(self) -> Never:
        raise TypeError("client mcp sdk adapter is not serializable")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
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
    ) -> ClientMcpConnection:
        return self._submit_operation(
            self._open_async(
                capability,
                session_id=session_id,
            )
        )

    def discover(self, connection: ClientMcpConnection) -> list[dict[str, Any]]:
        return self._submit_operation(self._discover_async(connection))

    def call(
        self, connection: ClientMcpConnection, tool: str, arguments: dict[str, Any]
    ) -> CallToolResult | InputRequiredResult | Result:
        return self._submit_operation(self._call_async(connection, tool, arguments))

    def close(self, connection: ClientMcpConnection) -> None:
        self._submit_operation(self._close_async(connection))

    def close_all(self) -> None:
        failures: list[BaseException] = []
        for connection in tuple(self._connections.values()):
            try:
                self.close(connection)
            except BaseException as exc:
                self.close_failure_recorded = True
                failures.append(exc)
        if failures:
            raise next((exc for exc in failures if not isinstance(exc, Exception)), failures[0])

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
                if existing.owner_terminal or existing.close_requested:
                    raise ClientMcpSdkError("CONNECTION_CLOSING")
                return existing

            if len(self._connections) >= self._connection_budget:
                raise ClientMcpSdkError("CONNECTION_BUDGET_EXCEEDED")

            if self._transport_context_factory is not None:
                return await self._open_owned_sdk_contexts(
                    capability,
                    session_id=session_id,
                    identity_key=identity_key,
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
            protocol_version = await self._initialize_and_scan(session)

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
    ) -> ClientMcpConnection:
        """One persistent task enters, dispatches and exits both SDK contexts."""
        assert self._transport_context_factory is not None
        assert self._session_context_factory is not None
        transport_factory = self._transport_context_factory
        session_factory = self._session_context_factory
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[ClientMcpConnection] = loop.create_future()
        ready.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        queue: asyncio.Queue[tuple[str, tuple[Any, ...], asyncio.Future[Any]]] = asyncio.Queue(maxsize=2)
        connection = ClientMcpConnection(
            session_id=session_id, identity_key=identity_key, session=None,
            negotiated_protocol_version="", transport=capability.safe_identity.transport,
        )
        active_response: asyncio.Future[Any] | None = None
        active_operation: asyncio.Task[Any] | None = None
        close_response: asyncio.Future[Any] | None = None

        async def request(kind: str, args: tuple[Any, ...]) -> Any:
            nonlocal close_response
            if connection.owner_terminal:
                if kind == "close":
                    return None
                raise ClientMcpSdkError("CONNECTION_CLOSED")
            if connection.close_requested:
                if kind != "close":
                    raise ClientMcpSdkError("CONNECTION_CLOSING")
                assert close_response is not None
                return await asyncio.shield(close_response)
            if kind != "close" and queue.qsize() >= 1:
                raise ClientMcpSdkError("REQUEST_QUEUE_FULL")
            response: asyncio.Future[Any] = loop.create_future()
            if kind == "close":
                connection.close_requested = True
                close_response = response
            queue.put_nowait((kind, args, response))
            try:
                return await asyncio.shield(response)
            except asyncio.CancelledError:
                if kind != "close":
                    response.cancel()
                    if active_response is response and active_operation is not None:
                        active_operation.cancel()
                raise

        async def owner() -> None:
            nonlocal active_response, active_operation
            stack = AsyncExitStack()
            warning_token = _warning_context.set((weakref.ref(self), weakref.ref(connection)))
            connection.owner_enter_task_id = id(asyncio.current_task())
            try:
                try:
                    streams = await stack.enter_async_context(transport_factory(capability))
                    read, write = _stream_pair(streams)
                    connection.session = await stack.enter_async_context(session_factory(read, write))
                    connection.negotiated_protocol_version = await self._initialize_and_scan(connection.session)
                    ready.set_result(connection)
                    while True:
                        kind, args, response = await queue.get()
                        if kind == "close":
                            break
                        if response.cancelled():
                            continue
                        active_response = response
                        try:
                            operation = (self._discover_async(connection, direct=True) if kind == "discover"
                                         else self._call_async(connection, *args, direct=True))
                            active_operation = asyncio.create_task(operation)
                            result = await active_operation
                        except asyncio.CancelledError:
                            task = asyncio.current_task()
                            if not response.cancelled() or task is None or task.cancelling():
                                raise
                        except Exception as exc:
                            if not response.done():
                                response.set_exception(exc)
                        else:
                            if not response.done():
                                response.set_result(result)
                        finally:
                            active_operation = None
                            if response.done():
                                active_response = None
                except BaseException as exc:
                    if not ready.done():
                        ready.set_exception(exc)
                    raise
                finally:
                    # shortcut: a logging flip entirely between these snapshots is undetectable;
                    # upgrade to SDK-owned release telemetry when that contract becomes available.
                    connection.warning_start = _safe_warning_snapshot()
                    try:
                        await stack.aclose()
                    except BaseException as exc:
                        connection.owner_error = exc
                        raise
                    finally:
                        connection.warning_end = _safe_warning_snapshot()
            except BaseException as exc:
                if not ready.done():
                    ready.set_exception(exc)
            finally:
                connection.owner_exit_task_id = id(asyncio.current_task())
                connection.owner_terminal = True
                if not ready.done():
                    ready.set_exception(ClientMcpSdkError("OWNER_EXITED"))
                pending = [active_response, close_response]
                while not queue.empty():
                    pending.append(queue.get_nowait()[2])
                for pending_response in pending:
                    if pending_response is not None and not pending_response.done():
                        if pending_response is close_response and connection.owner_error is None:
                            pending_response.set_result(None)
                        else:
                            pending_response.set_exception(ClientMcpSdkError("OWNER_EXITED"))
                _warning_context.reset(warning_token)

        connection.owner_request = request
        connection.owner_task = asyncio.create_task(owner(), name="optimus-mcp-lifetime-owner")
        self._connections[identity_key] = connection
        try:
            await asyncio.shield(ready)
        except BaseException as primary:
            if not ready.done() or (isinstance(primary, asyncio.CancelledError)
                                    and not ready.cancelled() and ready.exception() is None):
                connection.owner_task.cancel()
            # Keep a timed-out owner in the pending map, including failed opens.
            with suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(connection.owner_task), self._operation_timeout_seconds)
            if self._release_established(connection):
                self._connections.pop(identity_key, None)
            else:
                self.close_failure_recorded = True
            raise
        return connection

    async def _initialize_and_scan(self, session: Any) -> str:
        try:
            result = await asyncio.wait_for(
                session.initialize(),
                timeout=self._operation_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ClientMcpSdkError("OPERATION_TIMEOUT") from exc

        protocol_version = getattr(result, "protocol_version", None)
        if not isinstance(protocol_version, str) or protocol_version not in _SUPPORTED_PROTOCOL_VERSIONS:
            raise ClientMcpSdkError("INVALID_PROTOCOL_VERSION")

        server_info = getattr(result, "server_info", None)
        scan_text = "\n".join(
            [
                str(getattr(result, "instructions", "") or ""),
                str(getattr(server_info, "description", "") or ""),
                str(getattr(server_info, "name", "") or ""),
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
        key = connection.identity_key
        # Only tear down the slot if this handle is the live tracked connection.
        # Popping by key alone would close a different live session after reuse races.
        if self._connections.get(key) is not connection:
            connection.closed = True
            return
        try:
            if connection.owner_request is not None:
                await connection.owner_request("close", ())
                assert connection.owner_task is not None
                await asyncio.shield(connection.owner_task)
                if not self._release_established(connection):
                    raise ClientMcpSdkError("CLEANUP_UNCERTAIN")
            else:
                await connection.close_resources()
            seam = select_process_tree_teardown_seam()
            self._process_control.terminate_tree(seam=seam)
        except BaseException:
            self.close_failure_recorded = True
            self.record_diagnostic("CLOSE_FAILED")
            raise
        connection.closed = True
        connection.owner_request = None
        self._connections.pop(key, None)

    @staticmethod
    def _release_established(connection: ClientMcpConnection) -> bool:
        return (connection.owner_terminal and connection.owner_error is None
                and not connection.survivor_warning
                and (connection.transport != "stdio" or (
                    connection.warning_start is not None and bool(connection.warning_start[0])
                    and connection.warning_start == connection.warning_end)))

    async def _discover_async(self, connection: ClientMcpConnection, *, direct: bool = False) -> list[dict[str, Any]]:
        if connection.owner_request is not None and not direct:
            return await connection.owner_request("discover", ())
        from mcp.types import ListToolsResult, PaginatedRequestParams

        # Catalog imports this adapter; defer the reverse import until discovery.
        from optimus.mcp.client_catalog import MAX_CATALOG_PAGES, ClientMcpCatalogError

        async with connection.call_lock:
            pages: list[dict[str, Any]] = []
            seen_cursors: set[str] = set()
            cursor: str | None = None
            while len(pages) < MAX_CATALOG_PAGES:
                try:
                    result = await asyncio.wait_for(
                        connection.session.list_tools(
                            params=PaginatedRequestParams(cursor=cursor) if cursor else None
                        ),
                        timeout=self._operation_timeout_seconds,
                    )
                except TimeoutError as exc:
                    raise ClientMcpSdkError("OPERATION_TIMEOUT") from exc
                if not isinstance(result, ListToolsResult):
                    raise ClientMcpCatalogError("CATALOG_MALFORMED_PAGE")
                try:
                    page = result.model_dump(mode="json", by_alias=True, exclude_none=True)
                except Exception as exc:
                    raise ClientMcpCatalogError("CATALOG_MALFORMED_PAGE") from exc
                pages.append(page)
                cursor = page.get("nextCursor")
                if cursor is None or cursor == "":
                    return pages
                if not isinstance(cursor, str):
                    raise ClientMcpCatalogError("CATALOG_MALFORMED_PAGE")
                if cursor in seen_cursors:
                    raise ClientMcpCatalogError("CATALOG_CURSOR_LOOP")
                seen_cursors.add(cursor)
            raise ClientMcpCatalogError("CATALOG_BUDGET_EXCEEDED")

    async def _call_async(
        self, connection: ClientMcpConnection, tool: str, arguments: dict[str, Any], *, direct: bool = False
    ) -> CallToolResult | InputRequiredResult | Result:
        if connection.owner_request is not None and not direct:
            return await connection.owner_request("call", (tool, arguments))
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
    http_client_factory: Callable[[], httpx2.AsyncClient],
) -> AsyncIterator[Any]:
    from mcp.client.sse import sse_client

    client = http_client_factory()
    try:
        def pinned_client(
            headers: dict[str, str] | None = None,
            timeout: httpx2.Timeout | None = None,
            auth: httpx2.Auth | None = None,
        ) -> httpx2.AsyncClient:
            return client

        async with sse_client(url, httpx_client_factory=pinned_client) as streams:
            yield streams
    finally:
        await client.aclose()
