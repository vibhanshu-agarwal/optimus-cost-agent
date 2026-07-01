from __future__ import annotations

import json
from typing import Any, Protocol

from optimus.acp.errors import INVALID_REQUEST, PARSE_ERROR


class AsyncByteReader(Protocol):
    async def read(self, size: int) -> bytes:
        ...


class FramingError(ValueError):
    """Raised when an ACP message cannot be framed or decoded."""

    def __init__(self, message: str, code: int = PARSE_ERROR) -> None:
        super().__init__(message)
        self.code = code


def encode_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


def parse_content_length(header_bytes: bytes) -> int:
    for raw_line in header_bytes.splitlines():
        name, separator, value = raw_line.partition(b":")
        if not separator:
            continue
        if name.strip().lower() != b"content-length":
            continue
        try:
            length = int(value.strip())
        except ValueError as exc:
            raise FramingError("invalid Content-Length") from exc
        if length < 0:
            raise FramingError("invalid Content-Length")
        return length
    raise FramingError("missing Content-Length")


async def read_message(reader: AsyncByteReader, header_limit: int = 8192) -> dict[str, Any]:
    header = bytearray()
    while b"\r\n\r\n" not in header:
        chunk = await reader.read(1)
        if chunk == b"":
            raise FramingError("unexpected end of stream")
        header.extend(chunk)
        if len(header) > header_limit:
            raise FramingError("header too large", code=INVALID_REQUEST)

    header_bytes, _, remainder = bytes(header).partition(b"\r\n\r\n")
    content_length = parse_content_length(header_bytes)
    body = bytearray(remainder)
    while len(body) < content_length:
        chunk = await reader.read(content_length - len(body))
        if chunk == b"":
            raise FramingError("unexpected end of stream")
        body.extend(chunk)

    try:
        decoded = json.loads(bytes(body[:content_length]).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FramingError("invalid JSON body") from exc
    if not isinstance(decoded, dict):
        raise FramingError("JSON-RPC message must be an object")
    return decoded
