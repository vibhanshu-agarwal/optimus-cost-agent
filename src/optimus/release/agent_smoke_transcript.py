from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from optimus.agent.models import AgentRunRequest, AgentRunResult
from optimus.agent.prompts import AGENT_PLANNER_PROMPT_VERSION

PLAN_9_5_SMOKE_TRANSCRIPT_PATH = Path("reports/plan-9-5-working-agent-smoke-transcript.json")


@dataclass
class AgentRunObservation:
    task_id: str
    request: AgentRunRequest
    result: AgentRunResult


@dataclass
class SmokeTranscriptRecorder:
    model: str
    observations: list[AgentRunObservation] = field(default_factory=list)

    def record(self, *, task_id: str, request: AgentRunRequest, result: AgentRunResult) -> None:
        self.observations.append(AgentRunObservation(task_id=task_id, request=request, result=result))

    def write(self, path: Path = PLAN_9_5_SMOKE_TRANSCRIPT_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "prompt_version": AGENT_PLANNER_PROMPT_VERSION,
            "model": self.model,
            "runs": [_observation_payload(self.model, observation) for observation in self.observations],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path


class RecordingAgentRunner:
    def __init__(self, runner: Any, *, recorder: SmokeTranscriptRecorder) -> None:
        self._runner = runner
        self._recorder = recorder
        self._current_task_id: str | None = None

    def set_task_id(self, task_id: str) -> None:
        self._current_task_id = task_id

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        result = self._runner.run(request)
        if self._current_task_id is not None:
            self._recorder.record(task_id=self._current_task_id, request=request, result=result)
        return result


def _observation_payload(model: str, observation: AgentRunObservation) -> dict[str, Any]:
    request = observation.request
    result = observation.result
    return {
        "task_id": observation.task_id,
        "run_id": result.run_id,
        "session_id": result.session_id,
        "approval_id": request.approval.approval_id,
        "plan_hash": result.plan_hash,
        "model": model,
        "prompt_version": AGENT_PLANNER_PROMPT_VERSION,
        "tool_names": [call.tool_name for call in result.tool_calls],
        "final_state": result.final_state,
        "status": result.status.value,
        "stop_reason": result.stop_reason,
        "total_cost_usd": str(result.total_cost_usd),
        "mutation_count": result.mutation_count,
    }
