from datetime import UTC, datetime

import pytest

from optimus.telemetry import redaction
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.jsonl import JsonlTelemetryWriter


def test_jsonl_writer_appends_one_event_per_line(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    writer = JsonlTelemetryWriter(path)

    writer.append(
        TelemetryEvent.tool_call(
            run_id="run-1",
            session_id="session-1",
            request_id="req-1",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
            tool_name="web.search",
            parameters={"query": "pytest"},
            result_summary="2 results",
            latency_ms=100,
            policy_reason="USER_REQUESTED",
            authorization_outcome="ALLOW",
        )
    )
    writer.append(
        TelemetryEvent.guardrail_audit(
            run_id="run-1",
            session_id="session-1",
            request_id="req-2",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
            tool_surface="mcp",
            verdict="HOLD",
            rule_id="mcp.server_not_registered",
            failed_checks=("mcp.server_not_registered",),
            requires_human_approval=True,
        )
    )

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert '"kind":"tool_call"' in lines[0]
    assert '"kind":"guardrail_audit"' in lines[1]


def test_jsonl_writer_sanitizes_nested_free_text_uri_and_unsupported_values(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    writer = JsonlTelemetryWriter(path)
    writer.append(
        TelemetryEvent.tool_call(
            run_id="run-1",
            session_id="session-1",
            request_id="req-1",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
            tool_name="web.search",
            parameters={
                "nested": {
                    "message": "OPTIMUS_API_KEY=top-secret-canary",
                    "uri": "redis://user:top-secret-canary@host/0",
                    "opaque": object(),
                }
            },
            result_summary="Authorization: Bearer top-secret-canary",
            latency_ms=100,
            policy_reason="USER_REQUESTED",
            authorization_outcome="ALLOW",
        )
    )

    persisted = path.read_text(encoding="utf-8")

    assert "top-secret-canary" not in persisted
    assert "redis://**********@host/0" in persisted
    assert "<builtins.object>" in persisted


def test_jsonl_writer_does_not_write_raw_event_when_sanitization_fails(tmp_path, monkeypatch):
    path = tmp_path / "telemetry.jsonl"
    writer = JsonlTelemetryWriter(path)
    event = TelemetryEvent.error(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        error_type="gateway",
        message="OPTIMUS_API_KEY=top-secret-canary",
        disposition="failed",
    )
    monkeypatch.setattr(
        redaction,
        "sanitize_for_persistence",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("sanitizer failure")),
    )

    with pytest.raises(RuntimeError, match="sanitizer failure"):
        writer.append(event)

    assert not path.exists() or "top-secret-canary" not in path.read_text(encoding="utf-8")
