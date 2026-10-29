"""Bounded subprocess retention without any automatic child termination."""

import io
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from optimus.acp.ndjson_subprocess_session import LiveSessionError, NdjsonSubprocessSession


def session(stdout="", stderr="", **limits):
    from optimus.acp.admission import AdmissionLimits

    process = SimpleNamespace(stdout=io.StringIO(stdout), stderr=io.StringIO(stderr), poll=lambda: None, kill=Mock())
    value = NdjsonSubprocessSession(process=process, transcript=Mock(), limits=replace(AdmissionLimits(), **limits))
    value._reader.join(2)
    value._stderr_reader.join(2)
    assert not value._reader.is_alive() and not value._stderr_reader.is_alive()
    return value


def test_stdout_overflow_is_fatal_even_with_queued_data_and_eof():
    value = session('{"id":1}\n{"id":2}\n{"id":3}\n', subprocess_items=2)
    assert value._inbound.maxsize == 2
    assert value._inbound.qsize() <= 2
    for observe in (lambda: value.read_next(deadline=time.monotonic() + 1),
                    lambda: value.wait_for(deadline=time.monotonic() + 1, predicate=lambda _: True, error_message="wait")):
        with pytest.raises(LiveSessionError, match="inbound capacity exceeded"):
            observe()
    value._process.kill.assert_not_called()


def test_stderr_huge_secret_line_is_wholly_discarded_and_gate_is_retained():
    value = session(stderr="optimus-agent: NO_APPROVAL\n" + "token=" + "secret" * 5000 + "\n" + "safe\n" * 100,
                    stderr_bytes=128, stderr_line_bytes=64)
    text = value.stderr_text()
    assert "secret" not in text and "token=" not in text
    assert "NO_APPROVAL" in text
    assert "omitted" in text
    assert len(text.encode()) <= 128 + 64 + 100


def test_stderr_redactor_failure_uses_fixed_fallback(monkeypatch):
    import optimus.acp.ndjson_subprocess_session as module
    def fail(_line):
        raise ValueError("sensitive")
    monkeypatch.setattr(module, "sanitize_for_persistence", fail)
    value = session(stderr="token=sensitive\n")
    assert "sensitive" not in value.stderr_text()
    assert "omitted" in value.stderr_text()


def test_cached_gate_survives_inline_copy_in_later_stderr_tail():
    from optimus.acp.ndjson_subprocess_session import _extract_gate_rejection_message

    value = session(stderr="optimus-agent: NO_APPROVAL\nnoise optimus-agent: NO_APPROVAL\n",
                    stderr_bytes=35, stderr_line_bytes=64)
    assert len(value._stderr_lines) == 1
    assert value._stderr_lines[0].startswith("noise ")
    extracted = _extract_gate_rejection_message(value.stderr_text())
    assert extracted is not None
    assert extracted.startswith("optimus-agent: NO_APPROVAL\n")


def test_stdout_single_oversized_frame_is_fatal_without_transcript():
    value = session('{"secret":"' + "x" * 1000 + '"}\n', frame_bytes=32)
    with pytest.raises(LiveSessionError, match="frame too large"):
        value.read_next(deadline=time.monotonic() + 1)
    value._transcript.record_inbound.assert_not_called()


def test_stderr_secret_across_chunks_is_redacted_as_one_whole_line():
    value = session(stderr=" " * 4088 + "token=boundary-sensitive-value\n")
    assert "boundary-sensitive-value" not in value.stderr_text()


@pytest.mark.parametrize("payload", ["{bad}\n", "[]\n", '{"id":1}'])
def test_malformed_or_partial_stdout_is_fatal(payload):
    value = session(payload)
    with pytest.raises(LiveSessionError):
        value.read_next(deadline=time.monotonic() + 1)


def test_subprocess_bytes_remain_reserved_until_consumed():
    value = session('{"id":1}\n{"id":2}\n')
    assert value._admission.count == 2
    assert value.read_next(deadline=time.monotonic() + 1) == {"id": 1}
    assert value._admission.count == 1
    assert value.read_next(deadline=time.monotonic() + 1) == {"id": 2}
    assert value._admission.count == value._admission.bytes == 0


def test_subprocess_byte_overflow_is_fatal_at_small_item_count():
    value = session('{"id":1}\n{"id":2}\n', inbound_bytes=12)
    assert value._inbound.qsize() == 1
    with pytest.raises(LiveSessionError, match="inbound capacity exceeded"):
        value.read_next(deadline=time.monotonic() + 1)


def test_stderr_read_failure_is_fixed_fatal_without_raw_thread_exception():
    class Broken:
        def readline(self, size):
            raise OSError("sensitive-stream-value")
    value = session()
    value._process.stderr = Broken()
    value._read_stderr()
    with pytest.raises(LiveSessionError, match="stderr reader failed") as caught:
        value.read_next(deadline=time.monotonic() + 1)
    assert "sensitive-stream-value" not in str(caught.value) + value.stderr_text()


def test_empty_sanitized_stderr_cannot_accumulate_zero_byte_entries(monkeypatch):
    import optimus.acp.ndjson_subprocess_session as module
    monkeypatch.setattr(module, "sanitize_for_persistence", lambda _line: SimpleNamespace(value=""))
    value = session(stderr="line\n" * 100)
    assert not value._stderr_lines
    assert value._stderr_omitted == 100


def test_stderr_encoding_failure_is_fixed_fatal():
    value = session()
    value._process.stderr = io.StringIO("\udcff\n")
    value._read_stderr()
    with pytest.raises(LiveSessionError, match="stderr reader failed"):
        value.read_next(deadline=time.monotonic() + 1)


@pytest.mark.parametrize("method", ["read_next", "wait_for"])
def test_eof_after_empty_observation_still_delivers_final_frame(method, monkeypatch):
    import queue
    value = session('{"id":1}\n')
    pending = value._inbound.get_nowait()
    value._stdout_done.clear()
    value._process.wait = lambda **kwargs: None
    original = value._inbound.get
    def racing_get(*args, **kwargs):
        if kwargs.get("block") is False:
            return original(*args, **kwargs)
        value._inbound.put_nowait(pending)
        value._stdout_done.set()
        raise queue.Empty
    monkeypatch.setattr(value._inbound, "get", racing_get)
    args = {"deadline": time.monotonic() + 1}
    if method == "wait_for":
        args.update(predicate=lambda message: message.get("id") == 1, error_message="wait")
    assert getattr(value, method)(**args) == {"id": 1}
    assert value._admission.count == 0


@pytest.mark.parametrize("method", ["read_next", "wait_for"])
def test_exited_child_cannot_return_queued_success(method):
    value = session('{"id":1,"result":{}}\n')
    value._process.poll = lambda: 1
    value._process.wait = lambda **kwargs: 1
    args = {"deadline": time.monotonic() + 1}
    if method == "wait_for":
        args.update(predicate=lambda _: True, error_message="wait")
    with pytest.raises(LiveSessionError, match="exited"):
        getattr(value, method)(**args)
    value._process.kill.assert_not_called()


def test_real_pipe_slow_consumer_overflow_drains_without_killing_child():
    import os
    import threading

    from optimus.acp.admission import AdmissionLimits
    read_fd, write_fd = os.pipe()
    ready, resume = threading.Event(), threading.Event()
    with os.fdopen(read_fd, "r", encoding="utf-8") as stdout, os.fdopen(write_fd, "w", encoding="utf-8") as producer:
        process = SimpleNamespace(stdout=stdout, stderr=io.StringIO(), poll=lambda: None, kill=Mock())
        transcript = Mock()
        transcript.record_inbound.side_effect = lambda _: ready.set()
        value = NdjsonSubprocessSession(process=process, transcript=transcript,
                                       limits=replace(AdmissionLimits(), subprocess_items=2))
        def write():
            producer.write('{"id":1}\n')
            producer.flush()
            if resume.wait(2):
                producer.write('{"id":2}\n{"id":3}\n{"id":4}\n{"id":5}\n')
                producer.flush()
        thread = threading.Thread(target=write)
        thread.start()
        try:
            assert ready.wait(2)
            assert value.read_next(deadline=time.monotonic() + 2) == {"id": 1}
            resume.set()
            thread.join(2)
            assert not thread.is_alive()
            producer.close()
            value._reader.join(2)
            value._stderr_reader.join(2)
            assert not value._reader.is_alive() and not value._stderr_reader.is_alive()
            assert value._inbound.qsize() == 2
            with pytest.raises(LiveSessionError, match="inbound capacity exceeded"):
                value.read_next(deadline=time.monotonic() + 1)
            process.kill.assert_not_called()
        finally:
            resume.set()
            thread.join(2)
            producer.close()
            value._reader.join(2)
            value._stderr_reader.join(2)
