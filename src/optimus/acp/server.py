from __future__ import annotations

import asyncio
import concurrent.futures
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from optimus.acp.debug_trace import acp_debug_log, log_provenance_once
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import (
    INTERNAL_ERROR,
    AcpOutboundError,
    JsonRpcError,
    error_response,
    sanitize_protocol_error_message,
)
from optimus.acp.framing import FramingError, encode_message, read_message
from optimus.acp.lifecycle import NoticeControl, ResponseKind
from optimus.acp.outbound_writer import DedicatedOutboundWriter, OutboundQueueItem
from optimus.acp.settlement import SendOutcome
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore


# A Protocol describes a shape ("anything with async read(size) -> bytes") without
# requiring inheritance. handle_one() accepts asyncio.StreamReader in production or
# in-memory test fakes, as long as they implement the same methods.
class AsyncByteReader(Protocol):
    """Async byte input for ACP framing (e.g. asyncio.StreamReader on stdin)."""

    async def read(self, size: int) -> bytes:
        ...


class AsyncByteWriter(Protocol):
    """Async byte output for framed responses (e.g. stdout with drain())."""

    def write(self, data: bytes) -> None:
        ...

    async def drain(self) -> None:
        ...


class StdioByteReader:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    async def read(self, size: int) -> bytes:
        return await asyncio.to_thread(self._stream.read, size)


class StdioByteWriter:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    def write(self, data: bytes) -> None:
        self._stream.write(data)

    async def drain(self) -> None:
        await asyncio.to_thread(self._stream.flush)


class StdioNdjsonLineReader:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    async def readline(self) -> bytes:
        return await asyncio.to_thread(self._stream.readline)


class StdioNdjsonLineWriter:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    def write_bytes(self, data: bytes) -> None:
        self._stream.write(data)

    def flush(self) -> None:
        self._stream.flush()

    async def write_line(self, message: Mapping[str, Any]) -> None:
        payload = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        await asyncio.to_thread(self.write_bytes, payload)
        await asyncio.to_thread(self.flush)


class NdjsonLineReader(Protocol):
    async def readline(self) -> bytes:
        ...


class NdjsonLineWriter(Protocol):
    async def write_line(self, message: Mapping[str, Any]) -> None:
        ...


class NdjsonOutboundChannel:
    """
    Handles the outbound communication channel over NDJSON protocol.

    This class is responsible for sending notifications and requests in the
    NDJSON-RPC format, managing request IDs, handling responses from the client,
    and providing means to cancel pending requests. Physical writes go through
    the dedicated FIFO writer when configured.
    """

    def __init__(
        self,
        writer: NdjsonLineWriter,
        *,
        dedicated_writer: Any | None = None,
    ) -> None:
        self._writer = writer
        self._dedicated_writer = dedicated_writer
        self._agent_request_ids = iter(range(10_000, 100_000))
        self._futures: dict[str | int, asyncio.Future[dict[str, Any]]] = {}
        self.last_outbound_request_id: str | int | None = None
        self._ephemeral_owners: list[Any] = []

    def allocate_permission_request(
        self, method: str, params: dict[str, Any]
    ) -> Any:
        """Synchronously allocate request_id, future, and correlation (no await)."""
        from optimus.acp.lifecycle import PermissionRequestHandle

        request_id = next(self._agent_request_ids)
        self.last_outbound_request_id = request_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._futures[request_id] = future
        return PermissionRequestHandle(
            channel=self,
            request_id=request_id,
            response_future=future,
            method=method,
            params=params,
        )

    async def _submit_payload(self, message: Mapping[str, Any], *, kind: str) -> None:
        if self._dedicated_writer is None:
            await self._writer.write_line(message)
            return
        from optimus.acp.outbound_writer import (
            EphemeralSendOwner,
            OutboundQueueItem,
            next_ephemeral_send_key,
        )

        owner = EphemeralSendOwner()
        send_key = next_ephemeral_send_key(kind)
        owner.create_queued(send_key)
        source = concurrent.futures.Future()
        item = OutboundQueueItem(
            payload=message,
            send_key=send_key,
            owner=owner,
            source_future=source,
        )
        self._dedicated_writer.submit(item)
        loop = asyncio.get_running_loop()
        completion = await asyncio.shield(asyncio.wrap_future(source, loop=loop))
        if completion.outcome is SendOutcome.CONCLUSIVE_FAILURE:
            raise AcpOutboundError(code=INTERNAL_ERROR, message="outbound delivery failed")

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        # region agent log
        acp_debug_log(
            location="server.py:NdjsonOutboundChannel.notify",
            message="outbound notification",
            data={"method": method, "param_keys": sorted(params.keys())},
            hypothesis_id="H2",
        )
        # endregion
        await self._submit_payload(
            {"jsonrpc": "2.0", "method": method, "params": params},
            kind="notify",
        )

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = next(self._agent_request_ids)
        self.last_outbound_request_id = request_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._futures[request_id] = future
        # region agent log
        acp_debug_log(
            location="server.py:NdjsonOutboundChannel.request",
            message="outbound request sent",
            data={
                "request_id": request_id,
                "method": method,
                "param_keys": sorted(params.keys()),
                "has_toolCall": "toolCall" in params,
            },
            hypothesis_id="H2",
        )
        # endregion
        await self._submit_payload(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            kind="request",
        )
        return await future

    def cancel_request(self, request_id: str | int, result: dict[str, Any]) -> None:
        future = self._futures.get(request_id)
        if future is not None and not future.done():
            future.set_result(result)

    def deliver_client_response(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        # region agent log
        acp_debug_log(
            location="server.py:NdjsonOutboundChannel.deliver_client_response",
            message="client response delivered (post-mapping)",
            data={
                "request_id": request_id,
                "has_result": "result" in message,
                "has_error": "error" in message,
                "mapped_to_cancelled": False,
                "propagated_error": "error" in message,
                "result_keys": sorted(message.get("result", {}).keys()) if isinstance(message.get("result"), dict) else [],
            },
            hypothesis_id="H1",
        )
        # endregion
        if request_id is None:
            return
        future = self._futures.pop(request_id, None)
        if future is not None and not future.done():
            if "result" in message and isinstance(message["result"], dict):
                future.set_result(message["result"])
            elif "error" in message:
                error_payload = message["error"]
                code = error_payload.get("code", INTERNAL_ERROR) if isinstance(error_payload, dict) else INTERNAL_ERROR
                msg = error_payload.get("message", "client error") if isinstance(error_payload, dict) else "client error"
                data = error_payload.get("data") if isinstance(error_payload, dict) else None
                data_dict = data if isinstance(data, dict) else None
                future.set_exception(AcpOutboundError(code=code, message=msg, data=data_dict))


class AcpStreamServer:
    """
    Handles Advanced Control Protocol (ACP) stream server functionality, allowing
    interaction between a client and server using JSON-RPC or NDJSON over various
    communication channels.

    This class facilitates processing of client requests and manages the interaction
    using provided or default JsonRpcDispatcher instances, supporting multiple
    communication patterns (streaming or newline-delimited JSON). Intended for
    scenarios requiring structured communication, such as IDE integrations, build
    automation, or custom tooling.

    :ivar dispatcher: JSON-RPC dispatcher instance used to process incoming
        requests and route them to the correct handling functions.
    :type dispatcher: JsonRpcDispatcher
    """
    def __init__(
        self,
        dispatcher: JsonRpcDispatcher | None = None,
        *,
        max_planning_turns: int | None = None,
        client_mcp_runtime: Any | None = None,
        conversation_sanitizer_inputs: Any | None = None,
    ) -> None:
        self._dispatcher = dispatcher or JsonRpcDispatcher()
        # Plan 9.96, Task 5 Step 2: resolved once by build_configured_server()
        # from the authorized agent environ and threaded down into
        # AcpDuplexAdapter via serve_ndjson — never read from os.environ here.
        self._max_planning_turns = max_planning_turns
        self._client_mcp_runtime = client_mcp_runtime
        self._conversation_sanitizer_inputs = conversation_sanitizer_inputs
        self._request_tasks: set[asyncio.Task[Any]] = set()

    @property
    def client_mcp_runtime(self) -> Any | None:
        return self._client_mcp_runtime

    @property
    def conversation_sanitizer_inputs(self) -> Any | None:
        return self._conversation_sanitizer_inputs

    async def handle_one(self, reader: AsyncByteReader, writer: AsyncByteWriter) -> None:
        # reader/writer are typed by Protocol: no shared base class required.
        try:
            request = await read_message(reader)
            response = self._dispatcher.dispatch(request)
        except FramingError as exc:
            response = error_response(
                request_id=None,
                error=JsonRpcError(code=exc.code, message=str(exc)),
            )
        writer.write(encode_message(response))
        await writer.drain()

    async def serve(self, reader: AsyncByteReader, writer: AsyncByteWriter) -> None:
        while True:
            try:
                request = await read_message(reader)
            except FramingError as exc:
                if str(exc) == "unexpected end of stream":
                    return
                response = error_response(
                    request_id=None,
                    error=JsonRpcError(code=exc.code, message=str(exc)),
                )
                writer.write(encode_message(response))
                await writer.drain()
                continue
            response = self._dispatcher.dispatch(request)
            writer.write(encode_message(response))
            await writer.drain()

    async def serve_ndjson(self, reader: NdjsonLineReader, writer: NdjsonLineWriter) -> None:
        log_provenance_once()
        agent_runner = self._dispatcher.agent_runner
        if agent_runner is None:
            raise RuntimeError("agent runner not configured for ndjson ACP serving")
        workspace_root = self._dispatcher.workspace_root or Path.cwd()
        notice_control = NoticeControl()
        physical = writer if hasattr(writer, "write_bytes") and hasattr(writer, "flush") else None
        dedicated: DedicatedOutboundWriter | None = None
        if physical is not None:
            dedicated = DedicatedOutboundWriter(physical)  # type: ignore[arg-type]
            dedicated.start()
        outbound = NdjsonOutboundChannel(writer, dedicated_writer=dedicated)
        sessions = InMemoryAcpSpecSessionStore()
        adapter = AcpDuplexAdapter(
            runner=agent_runner,
            workspace_root=workspace_root,
            sessions=sessions,
            outbound=outbound,
            max_planning_turns=self._max_planning_turns,
            client_mcp_runtime=self._client_mcp_runtime,
        )
        message_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        request_tasks: set[asyncio.Task[Any]] = set()

        async def emit_response(response: Mapping[str, Any]) -> None:
            if dedicated is None:
                await writer.write_line(response)
                return
            handle = notice_control.allocate_response_handle(ResponseKind.ORDINARY)
            ticket = handle.start_non_turn_response_send()
            if ticket.immediate_completion is not None:
                handle.finalize_once(ticket.immediate_completion)
                return
            assert ticket.source_future is not None
            item = OutboundQueueItem(
                payload=response,
                send_key=ticket.send_key,
                owner=handle,
                source_future=ticket.source_future,
                writer_token=ticket.writer_token,
                handle=handle,
            )
            dedicated.submit(item)
            loop = asyncio.get_running_loop()
            completion = await asyncio.shield(
                asyncio.wrap_future(ticket.source_future, loop=loop)
            )
            handle.finalize_once(completion)

        async def read_lines() -> None:
            try:
                while True:
                    line = await reader.readline()
                    if line == b"":
                        await message_queue.put(None)
                        return
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        await message_queue.put(json.loads(stripped.decode("utf-8")))
                    except json.JSONDecodeError as exc:
                        print(f"optimus.acp: invalid ndjson line: {sanitize_protocol_error_message(str(exc))}", file=sys.stderr)
                        await message_queue.put(None)
                        return
            except Exception as exc:
                print(f"optimus.acp: ndjson reader failed: {sanitize_protocol_error_message(str(exc))}", file=sys.stderr)
                await message_queue.put(None)

        async def process_request(message: dict[str, Any]) -> None:
            request_id = message.get("id")
            method = message.get("method")
            pending_permission_id = outbound.last_outbound_request_id
            try:
                # region agent log
                acp_debug_log(
                    location="server.py:process_request:entry",
                    message="handling client request",
                    data={"request_id": request_id, "method": method, "pending_permission_id": pending_permission_id},
                    hypothesis_id="H4",
                )
                # endregion
                response = await adapter.handle_client_request(message)
                # region agent log
                acp_debug_log(
                    location="server.py:process_request:exit",
                    message="client request handled",
                    data={
                        "request_id": request_id,
                        "method": method,
                        "has_error": "error" in response,
                        "stop_reason": response.get("result", {}).get("stopReason")
                        if isinstance(response.get("result"), dict)
                        else None,
                    },
                    hypothesis_id="H4",
                )
                # endregion
                await emit_response(response)
            except AcpOutboundError as exc:
                await emit_response(
                    error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=exc.code, message=exc.message, data=exc.data),
                    )
                )
            except Exception as exc:
                # region agent log
                acp_debug_log(
                    location="server.py:process_request:exception",
                    message=str(exc),
                    data={
                        "request_id": request_id,
                        "method": method,
                        "pending_permission_id": pending_permission_id,
                        "exception_type": type(exc).__name__,
                    },
                    hypothesis_id="H4",
                )
                # endregion
                print(
                    f"optimus.acp: process_request failed id={request_id!r} method={method!r} "
                    f"pending_permission_id={pending_permission_id!r}: {sanitize_protocol_error_message(str(exc))}",
                    file=sys.stderr,
                )
                await emit_response(
                    error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INTERNAL_ERROR, message=str(exc)),
                    )
                )

        reader_task = asyncio.create_task(read_lines())
        try:
            while True:
                message = await message_queue.get()
                if message is None:
                    break
                if "method" in message and "id" not in message:
                    await adapter.handle_client_notification(message)
                    continue
                if "id" in message and ("result" in message or "error" in message) and "method" not in message:
                    # region agent log
                    acp_debug_log(
                        location="server.py:serve_ndjson:inbound_client_response_raw",
                        message="raw inbound id-bearing client response before deliver_client_response",
                        data={
                            "id": message.get("id"),
                            "has_result": "result" in message,
                            "has_error": "error" in message,
                            "error": message.get("error") if "error" in message else None,
                            "result": message.get("result") if "result" in message else None,
                        },
                        hypothesis_id="H2-REPLY",
                    )
                    # endregion
                    outbound.deliver_client_response(message)
                    continue
                if "method" in message and "id" in message:
                    task = asyncio.create_task(process_request(message))
                    request_tasks.add(task)
                    task.add_done_callback(request_tasks.discard)
        finally:
            notice_control.mark_transport_abandoned()
            for task in list(request_tasks):
                task.cancel()
            if request_tasks:
                await asyncio.gather(*request_tasks, return_exceptions=True)
            adapter.close_all()
            if self._client_mcp_runtime is not None:
                self._client_mcp_runtime.close()
            if dedicated is not None:
                dedicated.close_and_join()
            await reader_task
