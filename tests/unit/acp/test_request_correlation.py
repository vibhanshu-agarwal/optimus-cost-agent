import asyncio
import json
from contextvars import ContextVar
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from optimus.acp import debug_trace
from optimus.acp.debug_trace import DiagnosticLevel, acp_debug_log, configure_debug_trace, observe_request
from optimus.acp.request_correlation import (
    RequestCorrelation,
    add_trusted_request_identity,
    detached_request_context,
    request_correlation,
)


@pytest.mark.parametrize("interrupt", [asyncio.CancelledError(), KeyboardInterrupt()], ids=["cancel", "interrupt"])
async def test_terminating_a_nested_request_restores_its_parent(tmp_path, monkeypatch, interrupt):
    trace = tmp_path / "nested.ndjson"
    configure_debug_trace(enabled=True, log_path=trace, minimum_level=DiagnosticLevel.DEBUG)
    monotonic_ticks = iter((1, 10, 15, 30))
    monkeypatch.setattr(debug_trace, "time", SimpleNamespace(time=lambda: 999, monotonic_ns=lambda: next(monotonic_ticks)))
    parent = RequestCorrelation("parent", "ndjson", "session/prompt")
    child = RequestCorrelation("child", "framed", "optimus.ping")
    with observe_request(parent) as parent_state:
        with pytest.raises(type(interrupt)) as caught, observe_request(child):
            raise interrupt
        assert caught.value is interrupt
        assert request_correlation.get() is parent
        parent_state.returned(has_error=False)
    assert request_correlation.get() is None

    records = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    outer_start, inner_start, inner_end, outer_end = records
    assert [r["correlation"]["operationId"] for r in records] == ["parent", "child", "child", "parent"]
    assert inner_end["data"]["durationNs"] == 5
    assert outer_end["data"]["durationNs"] == 29
    assert inner_end["data"]["termination"] == ("cancelled" if isinstance(interrupt, asyncio.CancelledError) else "raised")


async def test_task_context_keeps_the_owned_snapshot_and_clears_detached_identity(tmp_path):
    trace = tmp_path / "tasks.ndjson"
    configure_debug_trace(enabled=True, log_path=trace, minimum_level=DiagnosticLevel.DEBUG)
    other_state = ContextVar("other_state", default="missing")
    other_state.set("preserved")
    session = "session-" + "a" * 32
    parent = RequestCorrelation("parent", "ndjson", "session/prompt")
    release = asyncio.Event()

    async def report(kind):
        await release.wait()
        acp_debug_log(location=f"test:{kind}", message="task observed")
        return other_state.get()

    with observe_request(parent, trusted_session_id=session) as seen:
        add_trusted_request_identity(session_id=session, run_id=f"{session}:1")
        current = request_correlation.get()
        with pytest.raises(FrozenInstanceError):
            current.run_id = "foreign"
        owned = asyncio.create_task(report("owned"))
        detached = asyncio.create_task(report("detached"), context=detached_request_context())
        seen.returned(has_error=False)
    release.set()
    assert await owned == await detached == "preserved"
    assert request_correlation.get() is None
    records = {row["location"]: row for row in map(json.loads, trace.read_text(encoding="utf-8").splitlines())}
    assert records["test:owned"]["correlation"]["runId"] == f"{session}:1"
    assert "correlation" not in records["test:detached"]


def test_legacy_trace_keeps_its_envelope_and_omits_request_lifecycle(tmp_path):
    path = tmp_path / "legacy.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    with observe_request(RequestCorrelation("test", "framed", "optimus.ping")) as seen:
        acp_debug_log(location="test:legacy", message="legacy record")
        seen.returned(has_error=False)
    line, = path.read_text(encoding="utf-8").splitlines()
    assert set(json.loads(line)) == {"sessionId", "timestamp", "location", "message", "data", "hypothesisId", "runId"}
