from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import JsonRpcError, error_response
from optimus.acp.framing import FramingError, encode_message, read_message
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


class NdjsonLineReader(Protocol):
    async def readline(self) -> bytes:
        ...


class NdjsonLineWriter(Protocol):
    async def write_line(self, message: Mapping[str, Any]) -> None:
        ...


class NdjsonOutboundChannel:
    def __init__(self, writer: NdjsonLineWriter) -> None:
        self._writer = writer
        self._agent_request_ids = iter(range(10_000, 100_000))
        self._futures: dict[str | int, asyncio.Future[dict[str, Any]]] = {}
        self.last_outbound_request_id: str | int | None = None

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._writer.write_line({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = next(self._agent_request_ids)
        self.last_outbound_request_id = request_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._futures[request_id] = future
        await self._writer.write_line({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await future

    def cancel_request(self, request_id: str | int, result: dict[str, Any]) -> None:
        future = self._futures.get(request_id)
        if future is not None and not future.done():
            future.set_result(result)

    def deliver_client_response(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        if request_id is None:
            return
        future = self._futures.pop(request_id, None)
        if future is not None and not future.done():
            if "result" in message and isinstance(message["result"], dict):
                future.set_result(message["result"])
            elif "error" in message:
                future.set_result({"outcome": {"outcome": "cancelled"}})


class AcpStreamServer:
    def __init__(self, dispatcher: JsonRpcDispatcher | None = None) -> None:
        self._dispatcher = dispatcher or JsonRpcDispatcher()

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
        agent_runner = self._dispatcher.agent_runner
        if agent_runner is None:
            raise RuntimeError("agent runner not configured for ndjson ACP serving")
        workspace_root = self._dispatcher.workspace_root or Path.cwd()
        outbound = NdjsonOutboundChannel(writer)
        adapter = AcpDuplexAdapter(
            runner=agent_runner,
            workspace_root=workspace_root,
            sessions=InMemoryAcpSpecSessionStore(),
            outbound=outbound,
        )
        message_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def read_lines() -> None:
            while True:
                line = await reader.readline()
                if line == b"":
                    await message_queue.put(None)
                    return
                stripped = line.strip()
                if not stripped:
                    continue
                await message_queue.put(json.loads(stripped.decode("utf-8")))

        async def process_request(message: dict[str, Any]) -> None:
            response = await adapter.handle_client_request(message)
            await writer.write_line(response)

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
                    outbound.deliver_client_response(message)
                    continue
                if "method" in message and "id" in message:
                    asyncio.create_task(process_request(message))
        finally:
            await reader_task
