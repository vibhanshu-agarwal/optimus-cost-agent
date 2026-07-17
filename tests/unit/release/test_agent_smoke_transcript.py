from __future__ import annotations

from decimal import Decimal

import pytest

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus
from optimus.release import agent_smoke_transcript
from optimus.release.agent_smoke_transcript import SmokeTranscriptRecorder
from optimus.runtime.modes import ExecutionMode


def _request(tmp_path) -> AgentRunRequest:
    return AgentRunRequest(
        run_id="run-1",
        session_id="session-1",
        task="Inspect credentials",
        execution_mode=ExecutionMode.AGENT,
        workspace_root=tmp_path,
        approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="hash-1"),
    )


def _result() -> AgentRunResult:
    return AgentRunResult(
        run_id="run-1",
        session_id="session-1",
        execution_mode=ExecutionMode.AGENT,
        status=AgentRunStatus.COMPLETED,
        final_state="COMPLETED",
        output_text="completed",
        total_cost_usd=Decimal("0"),
    )


def test_smoke_transcript_sanitizes_canary_before_disk_and_fails_closed(tmp_path, monkeypatch) -> None:
    path = tmp_path / "smoke.json"
    recorder = SmokeTranscriptRecorder(model="model OPTIMUS_API_KEY=top-secret-canary")
    recorder.record(task_id="task-OPTIMUS_API_KEY=top-secret-canary", request=_request(tmp_path), result=_result())

    recorder.write(path)

    assert "top-secret-canary" not in path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        agent_smoke_transcript,
        "sanitize_for_persistence",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("sanitizer failure")),
    )
    failed_path = tmp_path / "failed-smoke.json"
    with pytest.raises(RuntimeError, match="sanitizer failure"):
        recorder.write(failed_path)
    assert not failed_path.exists()
