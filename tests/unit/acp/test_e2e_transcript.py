from __future__ import annotations

import json

import pytest

from optimus.acp.e2e_transcript import (
    E2eAcpTranscriptWriter,
    E2eTranscriptSerializationError,
    assert_transcript_payload_safe,
)


def test_transcript_writer_records_stdio_lines(tmp_path):
    writer = E2eAcpTranscriptWriter()
    writer.record_outbound({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    writer.record_inbound({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": 1}})

    path = writer.write(tmp_path / "transcript.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert len(payload["stdio_lines"]) == 2
    assert payload["stdio_lines"][0]["direction"] == "outbound"
    assert payload["stdio_lines"][1]["direction"] == "inbound"


def test_transcript_writer_rejects_process_env_mapping():
    with pytest.raises(E2eTranscriptSerializationError, match="process environment"):
        assert_transcript_payload_safe({"environ": {"OPTIMUS_API_KEY": "secret"}})


def test_transcript_writer_rejects_sensitive_env_like_mapping():
    with pytest.raises(E2eTranscriptSerializationError, match="process environment"):
        assert_transcript_payload_safe({"OPENAI_API_KEY": "sk-test", "PATH": "/usr/bin"})


def test_transcript_writer_rejects_env_nested_in_write_payload(tmp_path):
    writer = E2eAcpTranscriptWriter()
    with pytest.raises(E2eTranscriptSerializationError, match="process environment"):
        writer.record_outbound({"env": {"OPTIMUS_API_KEY": "secret"}})
        writer.write(tmp_path / "transcript.json")
