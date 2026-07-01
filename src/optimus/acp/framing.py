from __future__ import annotations

import json
from typing import Any

from optimus.acp.errors import PARSE_ERROR


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
