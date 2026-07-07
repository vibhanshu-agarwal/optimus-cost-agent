from __future__ import annotations

import asyncio
from typing import Protocol

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import JsonRpcError, error_response
from optimus.acp.framing import FramingError, encode_message, read_message


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
