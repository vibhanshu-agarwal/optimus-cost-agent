from __future__ import annotations

import asyncio
import io

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


async def test_serve_ndjson_exits_cleanly_on_byte_stream_eof(tmp_path):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")
    stream = io.BytesIO(b"")
    reader = StdioNdjsonLineReader(stream)
    writer = _CapturingNdjsonWriter()

    await asyncio.wait_for(configured.server.serve_ndjson(reader, writer), timeout=1)


async def test_serve_ndjson_reports_invalid_json_to_stderr_and_exits(tmp_path, capsys):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")
    stream = io.BytesIO(b"{not-json\n")
    reader = StdioNdjsonLineReader(stream)
    writer = _CapturingNdjsonWriter()

    await asyncio.wait_for(configured.server.serve_ndjson(reader, writer), timeout=1)

    stderr = capsys.readouterr().err
    assert "invalid ndjson line" in stderr


class _CapturingNdjsonWriter:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def write_line(self, message):
        self.messages.append(dict(message))
