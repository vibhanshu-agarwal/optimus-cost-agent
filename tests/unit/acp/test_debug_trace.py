import json
from decimal import Decimal

from optimus.acp.debug_trace import acp_debug_log, log_planning_replan_event, resolve_debug_log_path
from optimus.agent.planning_loop import PlanningProgressEvent


def test_log_planning_replan_event_writes_content_free_fields(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_TRACE", "1")
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_LOG", str(log_path))

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
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_TRACE", "1")
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_LOG", str(log_path))

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


def test_acp_debug_log_noop_when_disabled(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    monkeypatch.delenv("OPTIMUS_ACP_DEBUG_TRACE", raising=False)

    acp_debug_log(location="test", message="ignored", data={"secret": "value"})

    assert not log_path.exists()


def test_acp_debug_log_redacts_secret_shaped_fields_and_free_text_by_default(tmp_path, monkeypatch):
    """Every acp_debug_log call is redacted at the sink, regardless of what an
    individual call site (including a generic `except Exception: ...str(exc)`
    handler) happens to pass in."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_TRACE", "1")
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_LOG", str(log_path))

    acp_debug_log(
        location="test:leaky_call_site",
        message="upstream call failed: Authorization: Bearer sk-live-abc123xyz",
        data={
            "api_key": "sk-live-abc123xyz",
            "OPTIMUS_API_KEY": "sk-live-abc123xyz",
            "nested": {"password": "hunter2"},
            "url": "https://user:hunter2@example.com/path",
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
