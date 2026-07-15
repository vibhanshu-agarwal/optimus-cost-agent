import json
from decimal import Decimal
from pathlib import Path

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


def test_configure_debug_trace_uses_provenance_root_for_git_sha(tmp_path, monkeypatch):
    import os

    provenance_root = tmp_path / "workspace"
    provenance_root.mkdir()
    monkeypatch.delenv("OPTIMUS_ACP_PROVENANCE_ROOT", raising=False)

    configure_debug_trace(
        enabled=True,
        log_path=tmp_path / "debug-acp.ndjson",
        provenance_root=provenance_root,
    )

    assert Path(os.environ["OPTIMUS_ACP_PROVENANCE_ROOT"]).resolve() == provenance_root.resolve()

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


def test_log_planning_replan_event_includes_cost_completeness_fields(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_TRACE", "1")
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_LOG", str(log_path))

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


def test_log_planning_replan_event_complete_cost_has_true_fields(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_TRACE", "1")
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_LOG", str(log_path))

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


def test_log_planning_replan_event_preserves_positional_association(tmp_path, monkeypatch):
    """Each read_identities[i] corresponds to source_sha256s[i] and read_byte_counts[i]."""
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_TRACE", "1")
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_LOG", str(log_path))

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
