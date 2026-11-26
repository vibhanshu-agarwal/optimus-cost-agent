import asyncio
import functools
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimus.acp import debug_trace
from optimus.acp.debug_trace import DiagnosticLevel, configure_debug_trace, observe_operation
from optimus.acp.process_lifecycle import ProcessLifecycle, StopReason
from optimus.acp.request_correlation import RequestCorrelation, request_correlation


def test_operation_observes_the_whole_retry_cache_stack_without_payload(tmp_path, monkeypatch):
    trace = tmp_path / "operations.ndjson"
    configure_debug_trace(enabled=True, log_path=trace, minimum_level=DiagnosticLevel.DEBUG)
    times = iter((10, 20, 30, 42))
    monkeypatch.setattr(debug_trace, "time", SimpleNamespace(time=lambda: 1, monotonic_ns=lambda: next(times)))
    calls = 0
    sentinel = object()

    def lookup(key: str) -> object:
        """Return the cached object."""
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError(key)
        return sentinel

    @functools.wraps(lookup)
    def retry(key: str) -> object:
        try:
            return lookup(key)
        except ValueError:
            return lookup(key)

    class Owner:
        operation = staticmethod(observe_operation(functools.cache(retry)))

    context = RequestCorrelation("owned", "framed", "optimus.ping")
    token = request_correlation.set(context)
    try:
        assert Owner.operation("synthetic-private-argument") is sentinel
        assert Owner.operation("synthetic-private-argument") is sentinel
    finally:
        request_correlation.reset(token)

    assert calls == 2
    assert inspect.signature(Owner.operation) == inspect.signature(lookup)
    assert Owner.operation.__name__ == lookup.__name__
    assert Owner.operation.__module__ == lookup.__module__
    assert Owner.operation.__doc__ == lookup.__doc__
    lines = trace.read_text(encoding="utf-8")
    assert "synthetic-private-argument" not in lines
    rows = [json.loads(line) for line in lines.splitlines()]
    assert [row["data"] for row in rows] == [
        {"durationNs": 10, "outcome": "returned"},
        {"durationNs": 12, "outcome": "returned"},
    ]
    assert [row["correlation"]["operationId"] for row in rows] == ["owned", "owned"]
    assert all(row["location"].endswith(".lookup") for row in rows)


@pytest.mark.parametrize("error", [ValueError("private-error-text"), asyncio.CancelledError(), KeyboardInterrupt()])
async def test_async_operation_preserves_the_exact_termination(tmp_path, error):
    trace = tmp_path / "async.ndjson"
    configure_debug_trace(enabled=True, log_path=trace, minimum_level=DiagnosticLevel.DEBUG)

    @observe_operation
    async def operation() -> None:
        raise error

    assert inspect.iscoroutinefunction(operation)
    with pytest.raises(type(error)) as caught:
        await operation()
    assert caught.value is error
    lines = trace.read_text(encoding="utf-8")
    assert "private-error-text" not in lines
    line, = lines.splitlines()
    record = json.loads(line)
    assert record["data"]["durationNs"] >= 0
    assert record["data"]["outcome"] == ("cancelled" if isinstance(error, asyncio.CancelledError) else "raised")


def test_operation_contains_a_broken_clock_and_ordinary_sink_failure(tmp_path, monkeypatch):
    trace = tmp_path / "failure.ndjson"
    configure_debug_trace(enabled=True, log_path=trace, minimum_level=DiagnosticLevel.DEBUG)
    sentinel = object()

    @observe_operation
    def operation() -> object:
        return sentinel

    def fail(*args, **kwargs):
        raise OSError("test failure")

    monkeypatch.setattr(debug_trace, "acp_debug_log", fail)
    assert operation() is sentinel
    monkeypatch.setattr(debug_trace, "time", SimpleNamespace(time=lambda: 1, monotonic_ns=fail))
    assert operation() is sentinel
    assert not trace.exists()


@pytest.mark.parametrize("enabled,level", [(False, DiagnosticLevel.DEBUG), (True, None), (True, DiagnosticLevel.INFO)])
def test_disabled_filtered_and_legacy_operations_skip_clock_and_output(tmp_path, monkeypatch, enabled, level):
    trace = tmp_path / "filtered.ndjson"
    configure_debug_trace(enabled=enabled, log_path=trace, minimum_level=level)

    def unexpected(*args):
        pytest.fail("operation timing ran outside versioned debug")

    monkeypatch.setattr(debug_trace, "_observe_operation", unexpected)
    monkeypatch.setattr(debug_trace, "time", SimpleNamespace(time=lambda: 1, monotonic_ns=unexpected))

    @observe_operation
    def operation() -> Path:
        return trace

    assert operation() is trace
    assert not trace.exists()


def test_real_cleanup_boundary_emits_one_local_completion(tmp_path, capsys):
    path = tmp_path / "process.ndjson"
    configure_debug_trace(enabled=True, log_path=path, minimum_level=DiagnosticLevel.DEBUG)
    lifecycle = ProcessLifecycle()

    assert lifecycle.begin_cleanup() is None
    assert (lifecycle.state, lifecycle.reason) == ("DRAINING", StopReason.EOF)
    assert capsys.readouterr().out == ""
    line, = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(line)
    assert row["location"] == "operation:optimus.acp.process_lifecycle.ProcessLifecycle.begin_cleanup"
    assert row["data"]["outcome"] == "returned"


def test_an_async_callable_hidden_by_a_sync_cache_is_refused():
    async def operation() -> None:
        return None

    with pytest.raises(TypeError, match="async operation"):
        observe_operation(functools.cache(operation))
