from __future__ import annotations

import asyncio
import io
import json

from optimus.acp import errors, server
from optimus.acp.server import StdioNdjsonLineReader, StdioNdjsonLineWriter
from tests.integration.acp.test_server_stream import configured_test_agent_server


async def test_stdio_ndjson_line_reader_returns_bytes_and_detects_eof():
    stream = io.BytesIO(b'{"jsonrpc":"2.0","id":1}\n')
    reader = StdioNdjsonLineReader(stream)

    assert await reader.readline() == b'{"jsonrpc":"2.0","id":1}\n'
    assert await reader.readline() == b""


async def test_stdio_ndjson_line_writer_writes_bytes_to_bytesio():
    stream = io.BytesIO()
    writer = StdioNdjsonLineWriter(stream)

    await writer.write_line({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

    stream.seek(0)
    assert stream.read() == b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n'


async def test_handle_one_sanitizes_framing_error_in_encoded_response(monkeypatch) -> None:
    from optimus.acp.framing import FramingError

    async def failing_read_message(_reader):
        raise FramingError("OPTIMUS_API_KEY=top-secret-canary")

    class Writer:
        def __init__(self):
            self.payload = b""

        def write(self, payload):
            self.payload = payload

        async def drain(self):
            return None

    monkeypatch.setattr(server, "read_message", failing_read_message)
    writer = Writer()
    await server.AcpStreamServer().handle_one(object(), writer)
    body = json.loads(writer.payload.split(b"\r\n\r\n", 1)[1])
    assert body["error"]["code"] == -32700
    assert body["error"]["message"]
    assert "top-secret-canary" not in json.dumps(body)

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    failed_writer = Writer()
    await server.AcpStreamServer().handle_one(object(), failed_writer)
    failed_body = json.loads(failed_writer.payload.split(b"\r\n\r\n", 1)[1])
    assert failed_body["error"]["message"] == "internal error"
    assert "top-secret-canary" not in json.dumps(failed_body)


async def test_serve_sanitizes_framing_error_before_loop_exit(monkeypatch) -> None:
    from optimus.acp.framing import FramingError

    calls = 0

    async def read_then_eof(_reader):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FramingError("OPTIMUS_API_KEY=top-secret-canary")
        raise FramingError("unexpected end of stream")

    class Writer:
        def __init__(self):
            self.payloads = []

        def write(self, payload):
            self.payloads.append(payload)

        async def drain(self):
            return None

    monkeypatch.setattr(server, "read_message", read_then_eof)
    writer = Writer()
    await server.AcpStreamServer().serve(object(), writer)
    body = json.loads(writer.payloads[0].split(b"\r\n\r\n", 1)[1])
    assert body["error"]["message"]
    assert "top-secret-canary" not in json.dumps(body)

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    failed_writer = Writer()
    calls = 0
    await server.AcpStreamServer().serve(object(), failed_writer)
    failed_body = json.loads(failed_writer.payloads[0].split(b"\r\n\r\n", 1)[1])
    assert failed_body["error"]["message"] == "internal error"
    assert "top-secret-canary" not in json.dumps(failed_body)


async def test_serve_ndjson_exits_cleanly_on_byte_stream_eof(tmp_path):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")
    stream = io.BytesIO(b"")
    reader = StdioNdjsonLineReader(stream)
    writer = _CapturingNdjsonWriter()

    await asyncio.wait_for(configured.server.serve_ndjson(reader, writer), timeout=1)


async def test_serve_ndjson_reports_invalid_json_to_stderr_and_exits(tmp_path, monkeypatch, capsys):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")
    stream = io.BytesIO(b'{"token":"OPTIMUS_API_KEY=top-secret-canary"\n')
    reader = StdioNdjsonLineReader(stream)
    writer = _CapturingNdjsonWriter()

    await asyncio.wait_for(configured.server.serve_ndjson(reader, writer), timeout=1)

    stderr = capsys.readouterr().err
    assert "invalid ndjson line" in stderr
    assert "top-secret-canary" not in stderr

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    failed_stream = io.BytesIO(b'{"token":"OPTIMUS_API_KEY=top-secret-canary"\n')
    await asyncio.wait_for(configured.server.serve_ndjson(StdioNdjsonLineReader(failed_stream), _CapturingNdjsonWriter()), timeout=1)
    failed_stderr = capsys.readouterr().err
    assert "internal error" in failed_stderr
    assert "top-secret-canary" not in failed_stderr


def test_protocol_error_data_redacts_nested_canary_and_drops_on_failure(monkeypatch) -> None:
    data = {"nested": {"message": "OPTIMUS_API_KEY=top-secret-canary"}}

    sanitized = errors.sanitize_protocol_error_data(data)
    assert "top-secret-canary" not in json.dumps(sanitized)

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    assert errors.sanitize_protocol_error_data(data) is None


def test_protocol_error_message_redacts_canary_and_fails_safe(monkeypatch) -> None:
    canary = "OPTIMUS_API_KEY=top-secret-canary"

    assert "top-secret-canary" not in errors.sanitize_protocol_error_message(canary)
    assert errors.sanitize_protocol_error_message(canary)

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(canary)))
    fallback = errors.sanitize_protocol_error_message(canary)
    assert fallback
    assert "top-secret-canary" not in fallback


async def test_serve_ndjson_sanitizes_request_processing_response_and_stderr(tmp_path, monkeypatch, capsys):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")

    async def failing_handle_client_request(_self, _message):
        raise RuntimeError("OPTIMUS_API_KEY=top-secret-canary")

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", failing_handle_client_request)
    reader = StdioNdjsonLineReader(io.BytesIO(b'{"jsonrpc":"2.0","id":1,"method":"session/prompt"}\n'))
    writer = _CapturingNdjsonWriter()

    await asyncio.wait_for(configured.server.serve_ndjson(reader, writer), timeout=1)

    response = writer.messages[0]
    assert response["error"]["message"]
    assert "top-secret-canary" not in json.dumps(response)
    assert "top-secret-canary" not in capsys.readouterr().err

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    failed_reader = StdioNdjsonLineReader(io.BytesIO(b'{"jsonrpc":"2.0","id":2,"method":"session/prompt"}\n'))
    failed_writer = _CapturingNdjsonWriter()
    await asyncio.wait_for(configured.server.serve_ndjson(failed_reader, failed_writer), timeout=1)
    failed_response = failed_writer.messages[0]
    assert failed_response["error"]["message"] == "internal error"
    assert "top-secret-canary" not in json.dumps(failed_response)
    assert "top-secret-canary" not in capsys.readouterr().err


async def test_serve_ndjson_sanitizes_reader_failure_to_stderr(tmp_path, monkeypatch, capsys):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")

    class FailingReader:
        async def readline(self):
            raise RuntimeError("OPTIMUS_API_KEY=top-secret-canary")

    await asyncio.wait_for(configured.server.serve_ndjson(FailingReader(), _CapturingNdjsonWriter()), timeout=1)

    stderr = capsys.readouterr().err
    assert "ndjson reader failed" in stderr
    assert "top-secret-canary" not in stderr

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    await asyncio.wait_for(configured.server.serve_ndjson(FailingReader(), _CapturingNdjsonWriter()), timeout=1)
    failed_stderr = capsys.readouterr().err
    assert "internal error" in failed_stderr
    assert "top-secret-canary" not in failed_stderr


class _CapturingNdjsonWriter:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def write_line(self, message):
        self.messages.append(dict(message))
