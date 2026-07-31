"""Real process-boundary truncation evidence for ACP NDJSON handling."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from evidence_handoff.redaction.models import Disposition


def _structured():
    from evidence_handoff.redaction import structured as structured_mod

    return structured_mod


_WRITER = r"""
import sys, time
path = sys.argv[1]
mode = sys.argv[2]
with open(path, "wb") as handle:
    handle.write(b'{"sessionUpdate":"agent_message_chunk","n":1}\n')
    handle.flush()
    os_fsync = __import__("os").fsync
    os_fsync(handle.fileno())
    time.sleep(0.3)
    if mode == "utf8_prefix":
        handle.write(b'{"sessionUpdate":"agent_message_chunk","content":"partial')
    else:
        handle.write(b'{"note":"\xe2\x82')  # incomplete euro
    handle.flush()
    os_fsync(handle.fileno())
    time.sleep(60)
"""


def _spawn_and_kill(path: Path, mode: str) -> None:
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "-c", _WRITER, str(path), mode],
        env=env,
    )
    # Wait until the first complete line is present, then kill during the tail write window.
    deadline = time.time() + 10
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            raw = path.read_bytes()
            if b"\n" in raw and (mode == "utf8_prefix" and b"partial" in raw or mode != "utf8_prefix" and b"\xe2\x82" in raw):
                break
        time.sleep(0.05)
    else:
        proc.kill()
        proc.wait(timeout=5)
        pytest.fail("writer did not produce expected truncated content in time")
    if sys.platform == "win32":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("utf8_prefix", Disposition.PROMOTED),
        ("utf8_mid_char", Disposition.QUARANTINED),
    ],
)
def test_real_subprocess_truncation(tmp_path: Path, mode: str, expected: Disposition) -> None:
    structured = _structured()
    capture = tmp_path / "cap"
    staging = tmp_path / "staging"
    capture.mkdir()
    staging.mkdir()
    source = capture / "live.ndjson"
    _spawn_and_kill(source, mode)
    raw = source.read_bytes()
    assert b"\n" in raw
    assert not raw.endswith(b"\n")
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="acp_debug_trace",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=True,
    )
    assert result.disposition is expected
    if expected is Disposition.PROMOTED:
        assert result.truncated_tail_dropped is True
        assert result.dropped_tail_bytes is not None and result.dropped_tail_bytes > 0
        out = result.staging_path.read_bytes()
        assert b"partial" not in out
        assert json.loads(out.splitlines()[0])
    else:
        assert result.reason_code == "invalid_utf8"
        assert result.staging_path is None
