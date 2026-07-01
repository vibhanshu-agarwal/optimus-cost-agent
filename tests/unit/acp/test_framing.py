import json

import pytest

from optimus.acp.errors import INVALID_REQUEST, PARSE_ERROR
from optimus.acp.framing import FramingError, encode_message, parse_content_length


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
