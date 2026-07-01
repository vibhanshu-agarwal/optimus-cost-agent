import asyncio
import json

from optimus.acp.errors import PARSE_ERROR
from optimus.acp.framing import encode_message
from optimus.acp.server import AcpStreamServer


class MemoryReader:
    """Test fake for optimus.acp.server.AsyncByteReader.

    Replays scripted byte chunks so integration tests can feed fragmented input
    without a real stdin/socket. Production uses asyncio.StreamReader instead.
    """

    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, size: int) -> bytes:
        # Match stream semantics: return up to size bytes; b"" means EOF.
        await asyncio.sleep(0)
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if len(chunk) <= size:
            return chunk
        self._chunks.insert(0, chunk[size:])
        return chunk[:size]


class MemoryWriter:
    """Test fake for optimus.acp.server.AsyncByteWriter.

    Captures framed response bytes in memory for assertions. Production would
    write to stdout (or another stream) and await drain() to flush.
    """

    def __init__(self):
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)


def decode_framed_response(data: bytes) -> dict:
    _, body = data.split(b"\r\n\r\n", 1)
    return json.loads(body.decode("utf-8"))


async def test_stream_handler_handles_fragmented_ping():
    framed = encode_message({"jsonrpc": "2.0", "id": 1, "method": "optimus.ping"})
    reader = MemoryReader([framed[:2], framed[2:9], framed[9:]])
    writer = MemoryWriter()

    await AcpStreamServer().handle_one(reader, writer)

    assert decode_framed_response(bytes(writer.data)) == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"message": "pong"},
    }


async def test_stream_handler_maps_framing_error_to_json_rpc_error():
    reader = MemoryReader([b"Content-Length: 1\r\n\r\n{"])
    writer = MemoryWriter()

    await AcpStreamServer().handle_one(reader, writer)

    response = decode_framed_response(bytes(writer.data))
    assert response["id"] is None
    assert response["error"]["code"] == PARSE_ERROR
    assert response["error"]["message"] == "invalid JSON body"
