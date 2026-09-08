import asyncio
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimus.acp import debug_trace
from optimus.acp.debug_trace import (
    acp_debug_log,
    configure_debug_trace,
    log_planning_replan_event,
    resolve_debug_log_path,
)
from optimus.agent.planning_loop import PlanningProgressEvent


def test_log_planning_replan_event_writes_content_free_fields(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    log_planning_replan_event(
        PlanningProgressEvent(
            run_id="run-1",
            session_id="session-1",
            settled_turn=2,
            max_planning_turns=3,
            read_request_count=2,
            read_identities=("src/a.py#bytes=0:5", "src/b.py#bytes=0:10"),
            source_sha256s=("a" * 64, "b" * 64),
            read_byte_counts=(5, 10),
            total_cost_usd=Decimal("0.004"),
            remaining_budget_usd=Decimal("0.046"),
            gateway_request_ids=("gw-1", "gw-2"),
            wire_retry_count=1,
        ),
        stop_reason=None,
    )

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert line["hypothesisId"] == "P9.85-REPLAN"
    data = line["data"]
    assert data["settled_turn"] == 2
    assert data["max_planning_turns"] == 3
    assert data["read_identities"] == ["src/a.py#bytes=0:5", "src/b.py#bytes=0:10"]
    assert data["gateway_request_ids"] == ["gw-1", "gw-2"]
    assert "observation" not in json.dumps(data).lower()
    assert "alpha content" not in json.dumps(data)


def test_log_planning_replan_event_uses_event_stop_reason_when_not_overridden(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    log_planning_replan_event(
        PlanningProgressEvent(
            run_id="run-1",
            session_id="session-1",
            settled_turn=3,
            max_planning_turns=3,
            gateway_request_ids=("gw-1", "gw-2", "gw-3"),
            stop_reason="PLANNING_TURN_LIMIT_EXHAUSTED",
        ),
    )

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert line["data"]["loop_stop"] == "PLANNING_TURN_LIMIT_EXHAUSTED"


def test_acp_debug_log_noop_when_disabled(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    # No configure_debug_trace() call: context defaults to disabled per the
    # autouse reset_debug_trace_context() fixture.

    acp_debug_log(location="test", message="ignored", data={"secret": "value"})  # pragma: allowlist secret

    assert not log_path.exists()


def test_acp_debug_log_redacts_secret_shaped_fields_and_free_text_by_default(tmp_path):
    """Every acp_debug_log call is redacted at the sink, regardless of what an
    individual call site (including a generic `except Exception: ...str(exc)`
    handler) happens to pass in."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    acp_debug_log(
        location="test:leaky_call_site",
        message="upstream call failed: Authorization: Bearer sk-live-abc123xyz",
        data={
            "api_key": "sk-live-abc123xyz",  # pragma: allowlist secret
            "OPTIMUS_API_KEY": "sk-live-abc123xyz",  # pragma: allowlist secret
            "nested": {"password": "hunter2"},  # pragma: allowlist secret
            "url": "https://user:hunter2@example.com/path",  # pragma: allowlist secret
            "safe_field": "run-1",
        },
    )

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert "sk-live-abc123xyz" not in json.dumps(line)
    assert "hunter2" not in json.dumps(line)
    assert line["data"]["api_key"] == "**********"
    assert line["data"]["OPTIMUS_API_KEY"] == "**********"
    assert line["data"]["nested"]["password"] == "**********"
    assert line["data"]["safe_field"] == "run-1"


def test_acp_debug_log_serializes_unsupported_objects_as_safe_type_metadata(tmp_path):
    """The debug sink must persist unsupported values without invoking user
    serialization code or dropping the log line."""
    from optimus.acp.debug_trace import _json_default_handler

    class HostileObject:
        def __repr__(self) -> str:
            raise AssertionError("repr must not run")

        def __str__(self) -> str:
            raise AssertionError("str must not run")

    value = HostileObject()
    expected_type_metadata = f"<{type(value).__module__}.{type(value).__qualname__}>"
    assert _json_default_handler(value) == expected_type_metadata

    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    acp_debug_log(location="test:unsupported", message="safe", data={"value": value})

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert line["data"]["value"] == expected_type_metadata



def test_acp_debug_log_has_no_redaction_opt_out_parameters():
    """The debug sink must never expose a caller-controlled raw-write mode."""
    import ast

    tree = ast.parse(Path(debug_trace.__file__).read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "acp_debug_log"
    )
    parameter_names = {
        argument.arg
        for argument in function.args.posonlyargs + function.args.args + function.args.kwonlyargs
    }
    assert not parameter_names.intersection({"raw", "redact", "unsafe", "skip_redaction", "no_redact"})


def test_authorized_launch_comparison_accepts_no_caller_supplied_secret():
    """Tags may be derived only from an AuthorizedLaunch comparison point."""
    import ast

    tree = ast.parse(Path(debug_trace.__file__).read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "log_authorized_launch_comparison"
    )
    parameter_names = [
        argument.arg
        for argument in function.args.posonlyargs + function.args.args + function.args.kwonlyargs
    ]
    assert parameter_names == ["authorized_launch"]


def test_configure_debug_trace_uses_provenance_root_for_git_sha(tmp_path, monkeypatch):
    provenance_root = tmp_path / "workspace"
    provenance_root.mkdir()

    configure_debug_trace(
        enabled=True,
        log_path=tmp_path / "debug-acp.ndjson",
        provenance_root=provenance_root,
    )

    context = debug_trace._ACTIVE_CONTEXT
    assert context is not None
    assert context.provenance_root == provenance_root.resolve()

    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cwd"] = kwargs["cwd"]

        class Result:
            stdout = "deadbeef\n"

        return Result()

    monkeypatch.setattr(debug_trace.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(debug_trace.subprocess, "run", fake_run)

    assert debug_trace._git_sha() == "deadbeef"
    assert Path(str(captured["cwd"])).resolve() == provenance_root.resolve()


# --- Plan 9.95 Task 3 Step 4: cost completeness in debug progress ---


def test_log_planning_replan_event_includes_cost_completeness_fields(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    log_planning_replan_event(
        PlanningProgressEvent(
            run_id="run-unknown-cost",
            session_id="session-1",
            settled_turn=1,
            max_planning_turns=3,
            total_cost_usd=Decimal("0.001"),
            cost_complete=False,
            unknown_cost_attempt_count=1,
            remaining_budget_usd=Decimal("0.049"),
            gateway_request_ids=("gw-1",),
            wire_retry_count=0,
        ),
        stop_reason="PLANNING_GATEWAY_COST_UNKNOWN",
    )

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    data = line["data"]
    assert data["cost_complete"] is False
    assert data["unknown_cost_attempt_count"] == 1
    assert data["reported_aggregate_cost_usd"] == "0.001"
    assert data["loop_stop"] == "PLANNING_GATEWAY_COST_UNKNOWN"
    # Content-free: no prompt, response, credential, or exception body.
    serialized = json.dumps(line)
    assert "SENTINEL" not in serialized
    assert "Bearer" not in serialized
    assert "sk-live" not in serialized
    assert "opt_live" not in serialized


def test_log_planning_replan_event_complete_cost_has_true_fields(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    log_planning_replan_event(
        PlanningProgressEvent(
            run_id="run-complete",
            session_id="session-2",
            settled_turn=2,
            max_planning_turns=3,
            total_cost_usd=Decimal("0.004"),
            cost_complete=True,
            unknown_cost_attempt_count=0,
            remaining_budget_usd=Decimal("0.046"),
            gateway_request_ids=("gw-1", "gw-2"),
            wire_retry_count=1,
        ),
    )

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    data = line["data"]
    assert data["cost_complete"] is True
    assert data["unknown_cost_attempt_count"] == 0


# --- Plan 9.95 Task 4 Step 4: debug trace association test ---


def test_log_planning_replan_event_preserves_positional_association(tmp_path):
    """Each read_identities[i] corresponds to source_sha256s[i] and read_byte_counts[i]."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    log_planning_replan_event(
        PlanningProgressEvent(
            run_id="run-assoc",
            session_id="session-1",
            settled_turn=1,
            max_planning_turns=3,
            read_request_count=2,
            read_identities=("alpha.py#bytes=2:9", "zeta.py#bytes=0:3"),
            source_sha256s=("a" * 64, "z" * 64),
            read_byte_counts=(7, 3),
            total_cost_usd=Decimal("0.001"),
            remaining_budget_usd=Decimal("0.049"),
            gateway_request_ids=("gw-1",),
        ),
    )

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    data = line["data"]
    # Positional check: index 0 is alpha (7 bytes), index 1 is zeta (3 bytes).
    assert data["read_identities"][0] == "alpha.py#bytes=2:9"
    assert data["source_sha256s"][0] == "a" * 64
    assert data["read_byte_counts"][0] == 7
    assert data["read_identities"][1] == "zeta.py#bytes=0:3"
    assert data["source_sha256s"][1] == "z" * 64
    assert data["read_byte_counts"][1] == 3


# --- seam 1: lazy, failure-contained payload supplier contract -------------------
#
# Ported from sandbox tag `sandbox-seam1` (commit ad9deeb7) and adapted to main. The
# sink accepts a zero-argument synchronous supplier as well as a dict. The supplier is
# invoked once, only after the enabled check, inside the sink's ordinary-failure
# boundary; callables nested in a payload are never invoked; BaseException-derived
# control flow propagates.


class _NestedCallableInvoked(BaseException):
    """BaseException on purpose: the sink contains ordinary Exceptions, so an invocation
    must escape its boundary loudly rather than degrade to a missing log line."""


class _NestedHostile:
    """A class-defined hostile callable. Any invocation or formatting is an error."""

    def __call__(self):
        raise _NestedCallableInvoked("a nested callable must never be invoked")

    def __str__(self):
        raise _NestedCallableInvoked("str() must not run on a nested callable")

    def __repr__(self):
        raise _NestedCallableInvoked("repr() must not run on a nested callable")


def test_supplier_is_not_called_when_tracing_is_unset(tmp_path):
    """No configure_debug_trace() call at all: the autouse reset leaves tracing unset."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    calls = []

    acp_debug_log(location="test", message="ignored", data=lambda: calls.append(1) or {"a": 1})

    assert calls == []
    assert not log_path.exists()


def test_supplier_is_not_called_when_tracing_is_explicitly_disabled(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=False, log_path=log_path)
    calls = []

    acp_debug_log(location="test", message="ignored", data=lambda: calls.append(1) or {"a": 1})

    assert calls == []
    assert not log_path.exists()


def test_supplier_is_called_exactly_once_when_enabled(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    calls = []

    def supplier():
        calls.append(1)
        return {"outcome": "unknown", "reason": "pid_reused_start_mismatch"}

    acp_debug_log(location="test:supplier", message="decided", data=supplier)

    assert calls == [1]
    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert line["data"]["reason"] == "pid_reused_start_mismatch"
    assert line["location"] == "test:supplier"
    assert line["message"] == "decided"


def test_stateful_supplier_is_evaluated_exactly_once_and_that_evaluation_is_written(tmp_path):
    """A supplier whose result changes per call: the record carries the FIRST evaluation."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    calls = []

    def stateful():
        calls.append(1)
        return {"attempt": len(calls)}

    acp_debug_log(location="test:stateful", message="x", data=stateful)

    assert calls == [1]
    assert json.loads(log_path.read_text(encoding="utf-8").strip())["data"] == {"attempt": 1}


def test_fail_once_supplier_is_not_retried(tmp_path):
    """Containment is one attempt: a supplier that fails first is not called again."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    calls = []

    def fail_once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("first evaluation fails")
        return {"attempt": len(calls)}

    acp_debug_log(location="test:fail-once", message="x", data=fail_once)

    assert calls == [1]
    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_supplier_is_evaluated_synchronously_before_the_sink_returns(tmp_path):
    """Not queued, not deferred: the caller's frame is still live when the supplier runs."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    order = []

    def supplier():
        order.append("supplier")
        return {"k": 1}

    acp_debug_log(location="test:sync", message="x", data=supplier)
    order.append("after-return")

    assert order == ["supplier", "after-return"]


def test_dict_and_none_payloads_remain_supported(tmp_path):
    """Backward compatibility: cold call sites still pass a dict literal or nothing."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    acp_debug_log(location="test:dict", message="plain", data={"outcome": "alive"})
    acp_debug_log(location="test:none", message="bare")

    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["data"] == {"outcome": "alive"}
    assert lines[1]["data"] == {}
    assert set(lines[1]) == {"sessionId", "timestamp", "location", "message", "data", "hypothesisId", "runId"}


def test_supplier_returning_none_is_treated_as_empty(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    acp_debug_log(location="test:none-supplier", message="x", data=lambda: None)

    assert json.loads(log_path.read_text(encoding="utf-8").strip())["data"] == {}


def test_supplier_result_is_redacted_identically_to_a_dict(tmp_path):
    """Redaction parity between the two payload shapes, without restating what redaction does."""
    payload = {"api_key": "sk-live-not-a-real-key", "safe": "run-1"}  # pragma: allowlist secret
    written = []
    for index, source in enumerate(({**payload}, lambda: {**payload})):
        log_path = resolve_debug_log_path(workspace_root=tmp_path / str(index))
        configure_debug_trace(enabled=True, log_path=log_path)
        acp_debug_log(location="test:redaction", message="x", data=source)
        written.append(json.loads(log_path.read_text(encoding="utf-8").strip())["data"])

    assert written[0] == written[1]
    assert written[0] != payload, "the supplier path must not bypass redaction"
    assert written[0]["safe"] == "run-1"
    assert "sk-live-not-a-real-key" not in json.dumps(written)


def test_supplier_exception_is_contained_and_cannot_break_the_caller(tmp_path):
    """A diagnostic that raises degrades to 'no log line', never to an error."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    def exploding():
        raise RuntimeError("diagnostic blew up")

    acp_debug_log(location="test:boom", message="x", data=exploding)  # must not raise

    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_redaction_failure_is_contained_and_writes_nothing(tmp_path, monkeypatch):
    """Redaction sits INSIDE the boundary: a failure there is contained AND nothing unredacted leaks."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    def broken_redaction(value):
        raise RuntimeError("redaction blew up")

    monkeypatch.setattr(debug_trace, "redact_for_telemetry", broken_redaction)

    acp_debug_log(location="test:redaction-failure", message="x", data={"token": "fixture-value"})  # pragma: allowlist secret

    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_serialization_failure_is_contained(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    def broken_dumps(*args, **kwargs):
        raise TypeError("serialization blew up")

    monkeypatch.setattr(debug_trace.json, "dumps", broken_dumps)

    acp_debug_log(location="test:serialization-failure", message="x", data={"k": 1})

    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_path_resolution_failure_is_contained(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    def broken_log_path():
        raise OSError("path resolution blew up")

    monkeypatch.setattr(debug_trace, "_log_path", broken_log_path)

    acp_debug_log(location="test:path-failure", message="x", data={"k": 1})

    assert not log_path.exists()


def test_write_failure_is_contained_control(tmp_path):
    """Control: the pre-existing write boundary. A directory at the log path makes open() fail."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    log_path.mkdir(parents=True)
    configure_debug_trace(enabled=True, log_path=log_path)

    acp_debug_log(location="test:write-failure", message="x", data={"k": 1})

    assert log_path.is_dir()


def test_enabled_supplier_success_control_writes_one_complete_line(tmp_path):
    """Control for the containment tests: the same shape succeeds when nothing fails."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path, provenance_root=tmp_path)

    acp_debug_log(
        location="test:control",
        message="control",
        data=lambda: {"k": 1},
        hypothesis_id="SEAM1",
        run_id="run-control",
    )

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    line = json.loads(lines[0])
    assert line["data"] == {"k": 1}
    assert line["hypothesisId"] == "SEAM1"
    assert line["runId"] == "run-control"
    assert line["sessionId"].startswith("debug_")
    assert isinstance(line["timestamp"], int)


def test_callables_nested_in_a_payload_are_never_invoked(tmp_path):
    """Only the explicit supplier is called. Nested callables are data, not code."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    hostile = _NestedHostile()

    acp_debug_log(location="test:nested", message="x", data=lambda: {"fn": hostile, "inner": {"fn": hostile}})

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert isinstance(line["data"]["fn"], str) and line["data"]["fn"].startswith("<")
    assert line["data"]["inner"]["fn"] == line["data"]["fn"]


def test_callables_nested_in_a_dict_payload_are_never_invoked(tmp_path):
    """The same guarantee for the dict shape: a callable value is serialized as type metadata."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    acp_debug_log(location="test:nested-dict", message="x", data={"fn": _NestedHostile()})

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert isinstance(line["data"]["fn"], str) and line["data"]["fn"].startswith("<")


def test_supplier_is_not_evaluated_recursively(tmp_path):
    """A supplier returning a callable is not called again: the result is data."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    hostile = _NestedHostile()

    acp_debug_log(location="test:no-recursion", message="x", data=lambda: hostile)

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert isinstance(line["data"], str) and line["data"].startswith("<")


@pytest.mark.parametrize("control_flow", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_control_flow_raised_inside_a_supplier_propagates(tmp_path, control_flow):
    """Containment is for ordinary Exceptions only; control flow must escape the sink."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    def interrupting():
        raise control_flow()

    with pytest.raises(control_flow):
        acp_debug_log(location="test:control-flow", message="x", data=interrupting)

    assert not log_path.exists()


@pytest.mark.parametrize("control_flow", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_control_flow_raised_at_the_write_propagates(tmp_path, monkeypatch, control_flow):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    def interrupting_log_path():
        raise control_flow()

    monkeypatch.setattr(debug_trace, "_log_path", interrupting_log_path)

    with pytest.raises(control_flow):
        acp_debug_log(location="test:control-flow-write", message="x", data={"k": 1})


# --- seam 1: the four helpers in this module defer their own payload work -------------


class _DiagnosticInputRead(BaseException):
    """Raised by an opaque input on ANY inspection; BaseException so no boundary absorbs it."""


class _Opaque:
    """An input whose every inspection is an error. Identity and default-capture are free."""

    def __getattr__(self, name):
        raise _DiagnosticInputRead(f"attribute {name!r}")

    def __getitem__(self, key):
        raise _DiagnosticInputRead(f"item {key!r}")

    def __iter__(self):
        raise _DiagnosticInputRead("iteration")

    def __len__(self):
        raise _DiagnosticInputRead("len")

    def __contains__(self, item):
        raise _DiagnosticInputRead("contains")

    def __str__(self):
        raise _DiagnosticInputRead("str")

    def __bool__(self):
        raise _DiagnosticInputRead("bool")


def _workspace_result_shape():
    reference = SimpleNamespace(
        reference="src/a.py", status=SimpleNamespace(value="resolved"), candidates=("src/a.py",)
    )
    return SimpleNamespace(
        max_total_bytes=4096,
        used_bytes=12,
        prioritized_paths=("src/a.py",),
        omitted_paths=("src/b.py", "src/c.py"),
        diagnostics=(reference,),
        blocking_stop_reason=None,
    )


def test_log_workspace_context_result_does_no_payload_work_when_disabled(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=False, log_path=log_path)

    try:
        debug_trace.log_workspace_context_result(_Opaque(), _Opaque())
    except _DiagnosticInputRead as read:
        pytest.fail(f"disabled trace evaluated a workspace diagnostic input: {read}")

    assert not log_path.exists()


def test_log_workspace_context_result_preserves_fields_when_enabled(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    request = SimpleNamespace(run_id="run-ws", session_id="session-ws")

    debug_trace.log_workspace_context_result(request, _workspace_result_shape())

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert line["hypothesisId"] == "P9.8-CONTEXT"
    assert line["runId"] == "run-ws"
    assert line["data"] == {
        "run_id": "run-ws",
        "session_id": "session-ws",
        "max_total_bytes": 4096,
        "used_bytes": 12,
        "prioritized_paths": ["src/a.py"],
        "omitted_count": 2,
        "references": [
            {"reference": "src/a.py", "status": "resolved", "candidate_count": 1, "candidates": ["src/a.py"]}
        ],
        "blocking_stop_reason": None,
    }


def test_log_workspace_context_result_payload_failure_is_contained(tmp_path):
    """An ordinary failure while assembling the payload cannot reach the caller."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    request = SimpleNamespace(run_id="run-ws", session_id="session-ws")
    result = _workspace_result_shape()
    result.diagnostics = (SimpleNamespace(reference="x"),)  # no .status -> AttributeError inside the payload

    debug_trace.log_workspace_context_result(request, result)  # must not raise

    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_log_planning_replan_event_does_no_payload_work_when_disabled(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=False, log_path=log_path)

    try:
        log_planning_replan_event(_Opaque(), stop_reason="OVERRIDE")
    except _DiagnosticInputRead as read:
        pytest.fail(f"disabled trace evaluated a planning event input: {read}")

    assert not log_path.exists()


def test_log_planning_replan_event_payload_failure_is_contained(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    class _BrokenEvent:
        run_id = "run-broken"
        stop_reason = None

        def __getattr__(self, name):
            raise RuntimeError(f"event field {name!r} unavailable")

    log_planning_replan_event(_BrokenEvent())  # must not raise

    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def _authorized_launch(*, grant, inherited, inventory):
    candidate = SimpleNamespace(inherited=SimpleNamespace(values=inherited), secret_inventory=inventory)
    return SimpleNamespace(diagnostic_grant=grant, candidate=candidate)


def test_launch_comparison_without_a_grant_touches_no_candidate_field(tmp_path):
    """The predeclared-grant gate stays ahead of every diagnostic read, enabled or not."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    launch = SimpleNamespace(diagnostic_grant=None, candidate=_Opaque())

    try:
        debug_trace.log_authorized_launch_comparison(launch)
    except _DiagnosticInputRead as read:
        pytest.fail(f"a grant-less comparison read a candidate field: {read}")

    assert not log_path.exists()


def test_launch_comparison_when_disabled_does_no_hmac_work(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=False, log_path=log_path)
    launch = SimpleNamespace(diagnostic_grant=object(), candidate=_Opaque())

    def unexpected_tag(*args, **kwargs):
        pytest.fail("disabled trace computed a correlation tag")

    monkeypatch.setattr(debug_trace, "session_correlation_tag", unexpected_tag)

    try:
        debug_trace.log_authorized_launch_comparison(launch)
    except _DiagnosticInputRead as read:
        pytest.fail(f"disabled trace read a candidate field: {read}")

    assert not log_path.exists()


def test_launch_comparison_when_enabled_emits_one_tag_per_present_secret(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    launch = _authorized_launch(
        grant=object(),
        inherited={"OPTIMUS_API_KEY": "fixture-secret-value", "EMPTY": ""},  # pragma: allowlist secret
        inventory=("OPTIMUS_API_KEY", "EMPTY", "ABSENT"),
    )

    debug_trace.log_authorized_launch_comparison(launch)

    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert line["location"] == "launch_authorization_comparison"
    tags = line["data"]["correlation_tags"]
    assert [tag["field_name"] for tag in tags] == ["OPTIMUS_API_KEY"]
    assert isinstance(tags[0]["tag"], str) and tags[0]["tag"]
    assert "fixture-secret-value" not in log_path.read_text(encoding="utf-8")


def test_launch_comparison_tag_failure_is_contained(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    launch = _authorized_launch(grant=object(), inherited={"OPTIMUS_API_KEY": "x"}, inventory=("OPTIMUS_API_KEY",))

    def broken_tag(*args, **kwargs):
        raise RuntimeError("hmac unavailable")

    monkeypatch.setattr(debug_trace, "session_correlation_tag", broken_tag)

    debug_trace.log_authorized_launch_comparison(launch)  # must not raise

    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_provenance_once_policy_survives_a_failing_field(tmp_path, monkeypatch):
    """The once-only attempt is consumed even when the payload fails; nothing retries."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    monkeypatch.setattr(debug_trace, "_PROVENANCE_LOGGED", False)
    calls = []

    def broken_version():
        calls.append(1)
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(debug_trace, "_package_version", broken_version)

    debug_trace.log_provenance_once()  # must not raise
    debug_trace.log_provenance_once()

    assert calls == [1]
    assert debug_trace._PROVENANCE_LOGGED is True
    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_provenance_disabled_does_no_provenance_work(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=False, log_path=log_path)
    monkeypatch.setattr(debug_trace, "_PROVENANCE_LOGGED", False)

    def unexpected(*args, **kwargs):
        pytest.fail("disabled trace computed provenance")

    monkeypatch.setattr(debug_trace, "_git_sha", unexpected)
    monkeypatch.setattr(debug_trace, "_package_version", unexpected)

    debug_trace.log_provenance_once()

    assert debug_trace._PROVENANCE_LOGGED is False
    assert not log_path.exists()
