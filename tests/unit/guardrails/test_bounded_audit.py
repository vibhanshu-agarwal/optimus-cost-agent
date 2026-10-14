from concurrent.futures import ThreadPoolExecutor

import pytest

from optimus.guardrails.audit import InMemoryAuditSink, ToolInvocationAuditEvent
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest
from optimus.runtime.modes import ExecutionMode


def test_default_guard_audit_retains_recent_events_with_exact_drop_count(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    for index in range(20):
        guard.check(
            PreToolRequest(
                run_id=f"run-{index}",
                session_id="session-1",
                execution_mode=ExecutionMode.PLAN,
                tool_surface=ToolSurface.SHELL,
                action="blocked",
            )
        )

    assert len(guard.audit_events()) == 16
    assert guard.audit_event_limit == 16
    assert guard.audit_events()[0].run_id == "run-4"
    assert guard.audit_events()[-1].run_id == "run-19"
    assert guard.audit_events_dropped == 4


def test_audit_sink_rejects_nonpositive_limit():
    for invalid in (0, -1):
        with pytest.raises(ValueError, match="max_events"):
            InMemoryAuditSink(max_events=invalid)


def test_audit_sink_concurrent_append_keeps_count_and_recent_snapshot_consistent():
    sink = InMemoryAuditSink()

    def append(index: int) -> None:
        sink.append(
            ToolInvocationAuditEvent(
                run_id=f"run-{index}", session_id=None, tool_surface="shell", verdict="BLOCK",
                layer="pre_tool", rule_id="rule", reason="blocked", failed_checks=(),
                sanitized_subject="safe", requires_human_approval=False,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(100)))

    assert len(sink.events()) == sink.max_events == 16
    assert sink.dropped_count == 84
    assert len({event.run_id for event in sink.events()}) == 16


def test_custom_audit_limit_retains_newest_decisions_and_exact_drop_count():
    sink = InMemoryAuditSink(max_events=2)
    for index in range(5):
        sink.append(ToolInvocationAuditEvent(
            run_id=f"run-{index}", session_id=None, tool_surface="shell", verdict="BLOCK", layer="pre_tool",
            rule_id="rule", reason="blocked", failed_checks=(), sanitized_subject="safe", requires_human_approval=False,
        ))
    assert [event.run_id for event in sink.events()] == ["run-3", "run-4"]
    assert sink.dropped_count == 3


def test_guard_preserves_mandatory_audit_write_failure(tmp_path, monkeypatch):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())

    def fail_audit(event):
        raise OSError("mandatory audit failure")

    monkeypatch.setattr(guard._audit_sink, "append", fail_audit)
    with pytest.raises(OSError, match="mandatory audit failure"):
        guard.check(PreToolRequest(run_id="run-1", session_id="session-1", execution_mode=ExecutionMode.PLAN,
                                   tool_surface=ToolSurface.SHELL, action="blocked"))
