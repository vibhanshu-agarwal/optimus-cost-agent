import asyncio
import json

import pytest

from optimus.acp.errors import INVALID_REQUEST, PARSE_ERROR
from optimus.acp.framing import FramingError, encode_message, parse_content_length, read_message


def test_encode_message_prefixes_utf8_body_with_content_length():
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"message": "pong"}}

    framed = encode_message(payload)
    header, body = framed.split(b"\r\n\r\n", 1)

    assert header == f"Content-Length: {len(body)}".encode("ascii")
    assert json.loads(body.decode("utf-8")) == payload


def test_parse_content_length_is_case_insensitive():
    headers = b"content-length: 42\r\nX-Ignored: yes\r\n"

    assert parse_content_length(headers) == 42


def test_parse_content_length_rejects_missing_header():
    with pytest.raises(FramingError, match="missing Content-Length"):
        parse_content_length(b"X-Other: 42\r\n")


def test_parse_content_length_rejects_negative_length():
    with pytest.raises(FramingError, match="invalid Content-Length") as exc_info:
        parse_content_length(b"Content-Length: -1\r\n")

    assert exc_info.value.code == PARSE_ERROR


def test_parse_content_length_rejects_non_numeric_length():
    with pytest.raises(FramingError, match="invalid Content-Length") as exc_info:
        parse_content_length(b"Content-Length: nope\r\n")

    assert exc_info.value.code == PARSE_ERROR


def test_header_too_large_error_uses_invalid_request_code():
    error = FramingError("header too large", code=INVALID_REQUEST)

    assert error.code == INVALID_REQUEST


class ChunkedReader:
    """Test fake for optimus.acp.framing.AsyncByteReader.

    Production code passes a real async byte source such as asyncio.StreamReader
    (stdio ACP transport). This fake replays caller-supplied chunks so tests can
    simulate fragmented reads without sockets or subprocess I/O.
    """

    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, size: int) -> bytes:
        # Yield control like a real stream reader; honor read(size) byte limits.
        await asyncio.sleep(0)
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if len(chunk) <= size:
            return chunk
        self._chunks.insert(0, chunk[size:])
        return chunk[:size]


async def test_read_message_reassembles_fragmented_header_and_body():
    framed = encode_message({"jsonrpc": "2.0", "id": "a", "method": "optimus.ping"})
    reader = ChunkedReader([framed[:5], framed[5:17], framed[17:25], framed[25:]])

    message = await read_message(reader)

    assert message == {"jsonrpc": "2.0", "id": "a", "method": "optimus.ping"}


async def test_read_message_rejects_truncated_body():
    reader = ChunkedReader([b"Content-Length: 10\r\n\r\n{}"])

    with pytest.raises(FramingError, match="unexpected end of stream"):
        await read_message(reader)


async def test_read_message_rejects_content_length_zero_as_invalid_json_body():
    reader = ChunkedReader([b"Content-Length: 0\r\n\r\n"])

    with pytest.raises(FramingError, match="invalid JSON body") as exc_info:
        await read_message(reader)

    assert exc_info.value.code == PARSE_ERROR


async def test_read_message_rejects_oversized_header_with_invalid_request_code():
    reader = ChunkedReader([b"X-Ignored: 123456\r\nContent-Length: 2\r\n\r\n{}"])

    with pytest.raises(FramingError, match="header too large") as exc_info:
        await read_message(reader, header_limit=8)

    assert exc_info.value.code == INVALID_REQUEST


async def test_read_message_leaves_next_framed_message_available():
    first = encode_message({"jsonrpc": "2.0", "id": "a", "method": "optimus.ping"})
    second = encode_message({"jsonrpc": "2.0", "id": "b", "method": "optimus.ping"})
    reader = ChunkedReader([first + second])

    first_message = await read_message(reader)
    second_message = await read_message(reader)

    assert first_message["id"] == "a"
    assert second_message["id"] == "b"
