from datetime import UTC, datetime

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
