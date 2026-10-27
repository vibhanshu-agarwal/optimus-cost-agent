"""Process stop owns one cleanup, independent from a bounded observation."""
from __future__ import annotations

import asyncio
import gc
import importlib
import importlib.util
import io
import os
import signal
import threading
import weakref

import pytest


def lifecycle_module():
    name = "optimus.acp.process_lifecycle"
    assert importlib.util.find_spec(name) is not None, "the CLI needs one retained process-stop owner"
    return importlib.import_module(name)


def test_descriptor_reader_preserves_read_ahead_and_borrowed_handle():
    from optimus.acp.server import _StdinRead

    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"first\nsecond\nbody")
        os.close(write_fd)
        write_fd = None
        reader = _StdinRead(read_fd)
        assert reader.readline() == b"first\n"
        assert reader.readline(3) == b"sec"
        assert reader.readline() == b"ond\n"
        assert reader.read(2) == b"bo"
        assert reader.read(2) == b"dy"
        assert reader.readline() == b""
        os.fstat(read_fd)
    finally:
        if write_fd is not None:
            os.close(write_fd)
        os.close(read_fd)


@pytest.mark.asyncio
async def test_repeated_stop_and_observers_share_one_retained_cleanup():
    module = lifecycle_module()
    lifecycle = module.ProcessLifecycle()
    entered = asyncio.Event()
    closing = asyncio.Event()
    release = asyncio.Event()
    attempts = []

    async def owned():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            attempts.append("close")
            closing.set()
            await release.wait()
        return module.ShutdownObservation(True, "done", 0, ())

    task = asyncio.create_task(owned())
    await entered.wait()
    lifecycle.bind(asyncio.get_running_loop(), task)
    lifecycle.request_stop(module.StopReason.SIGINT)
    await closing.wait()
    lifecycle.request_stop(module.StopReason.SIGTERM)
    first = await lifecycle.observe(timeout=0.001)
    assert not first.complete
    assert not task.done()
    assert lifecycle.reason is module.StopReason.SIGINT
    assert task.cancelling() == 1
    observers = [asyncio.create_task(lifecycle.observe(timeout=2)) for _ in range(2)]
    release.set()
    results = await asyncio.gather(*observers)
    assert all(result.complete for result in results)
    assert attempts == ["close"]
    assert lifecycle.exit_code == 130


@pytest.mark.asyncio
@pytest.mark.parametrize("report_fails", [False, True])
async def test_expired_observation_is_reported_once_and_keeps_writer_custody(report_fails):
    module = lifecycle_module()
    reports = []
    def report(observation):
        reports.append(observation)
        if report_fails:
            raise RuntimeError("report unavailable")

    lifecycle = module.ProcessLifecycle(report=report)
    release = asyncio.Event()

    async def owned():
        lifecycle.begin_cleanup()
        lifecycle.record(module.ShutdownObservation(False, "writer", 1, ()))
        await release.wait()
        return module.ShutdownObservation(True, "done", 0, ())

    task = asyncio.create_task(owned())
    lifecycle.bind(asyncio.get_running_loop(), task)
    await lifecycle.wait_for_stop()
    try:
        assert not (await lifecycle.observe(timeout=0.001)).complete
        assert not (await lifecycle.observe(timeout=0.001)).complete
        assert len(reports) == 1
        assert reports[0].stage == "writer"
        assert lifecycle.exit_code is None, "a non-daemon writer cannot be relabelled borrowed input"
    finally:
        release.set()
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_completed_cleanup_consumes_record_instead_of_serve_return(failed):
    module = lifecycle_module()
    lifecycle = module.ProcessLifecycle()

    async def owned():
        return module.ShutdownObservation(True, "done", 0, ("redis",) if failed else ())

    task = asyncio.create_task(owned())
    lifecycle.bind(asyncio.get_running_loop(), task)
    result = await lifecycle.observe(timeout=2)
    assert result.complete
    assert lifecycle.exit_code == (74 if failed else 0)


@pytest.mark.asyncio
async def test_cancelling_an_observer_never_cancels_the_cleanup():
    module = lifecycle_module()
    lifecycle = module.ProcessLifecycle()
    release = asyncio.Event()

    async def owned():
        await release.wait()
        return module.ShutdownObservation(True, "done", 0, ())

    task = asyncio.create_task(owned())
    lifecycle.bind(asyncio.get_running_loop(), task)
    observer = asyncio.create_task(lifecycle.observe(timeout=2))
    entered = asyncio.Event()
    asyncio.get_running_loop().call_soon(entered.set)
    await entered.wait()
    observer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await observer
    assert not task.cancelled()
    release.set()
    assert (await lifecycle.observe(timeout=2)).complete


def test_startup_handler_interrupts_and_restores_exact_prior_handlers(monkeypatch):
    module = lifecycle_module()
    calls = {}
    original_int = object()
    original_term = object()
    installed = {signal.SIGINT: original_int, signal.SIGTERM: original_term}

    def install(number, callback):
        previous = installed[number]
        installed[number] = callback
        return previous

    monkeypatch.setattr(module.signal, "signal", install)
    monkeypatch.setattr(module.signal, "getsignal", installed.__getitem__)
    monkeypatch.setattr(module.atexit, "register", lambda callback: calls.setdefault("atexit", callback))
    monkeypatch.setattr(module.atexit, "unregister", lambda callback: calls.setdefault("unregistered", callback))
    lifecycle = module.ProcessLifecycle()
    with pytest.raises(KeyboardInterrupt), module.signal_handlers(lifecycle):
        installed[signal.SIGINT](signal.SIGINT, None)
    assert installed == {signal.SIGINT: original_int, signal.SIGTERM: original_term}
    assert calls["atexit"] is calls["unregistered"]
    assert lifecycle.reason is module.StopReason.SIGINT


def test_atexit_observes_only_retained_state_without_report_io(monkeypatch):
    module = lifecycle_module()
    callbacks = []
    reports = []
    monkeypatch.setattr(module.atexit, "register", callbacks.append)
    monkeypatch.setattr(module.atexit, "unregister", lambda _callback: None)
    lifecycle = module.ProcessLifecycle(report=reports.append)
    lifecycle.record(module.ShutdownObservation(False, "writer", 1, ()))
    with module.signal_handlers(lifecycle):
        [callback] = callbacks
        callback()
        assert reports == [], "atexit must not write to a potentially blocked diagnostic stream"
        assert lifecycle.observation.pending == 1


@pytest.mark.asyncio
async def test_cancelled_stdio_read_retains_one_daemon_owner_until_pipe_returns():
    from optimus.acp.server import StdioNdjsonLineReader

    read_fd, write_fd = os.pipe()
    entered = threading.Event()
    stream = os.fdopen(read_fd, "rb", buffering=0)

    class Input:
        def readline(self):
            entered.set()
            return stream.readline()

    reader = StdioNdjsonLineReader(Input())
    task = asyncio.create_task(reader.readline())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert hasattr(reader, "pending_read"), "cancelling an await must retain the physical read future"
        pending = reader.pending_read
        assert pending is not None and not pending.done()
        assert reader.read_thread.daemon
        reader.request_close()
        assert not await asyncio.to_thread(reader.observe_closed, 0.001)
        os.write(write_fd, b"late\n")
        assert await asyncio.to_thread(pending.result, 2) == b"late\n"
        assert await asyncio.to_thread(reader.observe_closed, 2)
        assert not reader.read_thread.is_alive()
    finally:
        os.close(write_fd)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if hasattr(reader, "request_close"):
            reader.request_close()
            await asyncio.to_thread(reader.observe_closed, 2)
        stream.close()


@pytest.mark.asyncio
async def test_retired_reader_does_not_leak_an_idle_daemon_thread():
    from optimus.acp.server import StdioNdjsonLineReader

    reader = StdioNdjsonLineReader(io.BytesIO(b"one\n"))
    assert await reader.readline() == b"one\n"
    thread = reader.read_thread
    reference = weakref.ref(reader)
    del reader
    try:
        gc.collect()
        assert reference() is None, "an idle owner thread must not keep its facade alive forever"
        await asyncio.to_thread(thread.join, 2)
        assert not thread.is_alive()
    finally:
        survivor = reference()
        if survivor is not None:
            survivor.request_close()
            await asyncio.to_thread(survivor.observe_closed, 2)


@pytest.mark.asyncio
async def test_serve_failure_does_not_erase_recorded_pending_ownership():
    module = lifecycle_module()
    lifecycle = module.ProcessLifecycle()
    expected = RuntimeError("serve failed with a retained writer")

    async def owned():
        lifecycle.record(module.ShutdownObservation(False, "writer", 1, ()))
        raise expected

    task = asyncio.create_task(owned())
    lifecycle.bind(asyncio.get_running_loop(), task)
    with pytest.raises(RuntimeError) as raised:
        await lifecycle.observe(timeout=2)
    assert raised.value is expected
    assert lifecycle.exit_code is None
    assert lifecycle.state != "COMPLETE"


@pytest.mark.asyncio
async def test_framed_write_admission_does_not_block_on_the_physical_stream():
    from optimus.acp.server import StdioByteWriter

    entered, release = threading.Event(), threading.Event()
    data = bytearray()

    class Output:
        def write(self, payload):
            entered.set()
            assert release.wait(5), "fixture must release its physical writer"
            data.extend(payload)
            return len(payload)

        def flush(self):
            pass

    writer = StdioByteWriter(Output())
    call = asyncio.create_task(asyncio.to_thread(writer.write, b"frame"))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await asyncio.wait_for(asyncio.shield(call), 0.03)
        assert data == b"", "write admission cannot pretend physical completion"
        release.set()
        await writer.drain()
        assert data == b"frame"
    finally:
        release.set()
        await call
        await writer.drain()
        if hasattr(writer, "close_and_join"):
            await asyncio.to_thread(writer.close_and_join)


@pytest.mark.asyncio
async def test_retired_framed_facade_retires_its_non_daemon_writer():
    from optimus.acp.server import StdioByteWriter

    writer = StdioByteWriter(io.BytesIO())
    writer.write(b"frame")
    await writer.drain()
    thread = writer._dedicated._thread
    reference = weakref.ref(writer)
    del writer
    try:
        gc.collect()
        assert reference() is None, "the physical transport cannot retain the retired facade"
        await asyncio.to_thread(thread.join, 2)
        assert not thread.is_alive()
    finally:
        survivor = reference()
        if survivor is not None:
            await asyncio.to_thread(survivor.close_and_join)
