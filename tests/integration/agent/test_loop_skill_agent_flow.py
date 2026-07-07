from decimal import Decimal

from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.loops.models import IterationOutcome, IterationState
from optimus.runtime.modes import ExecutionMode
from optimus.telemetry.events import TelemetryEventKind

SKILL_TEXT = """---
name: pytest-debugging
description: Debug failing pytest tests with a red-green loop.
keywords:
  - pytest
  - debug
  - failing
globs:
  - tests/**/*.py
allowed_tools:
  - shell
  - file_read
owner: maintainer
version: 1.0.0
trust_level: trusted
---

# Pytest Debugging

Run the narrow failing test first, inspect the failure, then patch the smallest code path.
"""


class CompleteOnFirstIteration:
    def run_iteration(self, state: IterationState, tools) -> IterationOutcome:
        return IterationOutcome(summary="pytest tests green", deterministic_completion=True)


class FakeGatewayClient:
    def create_response(self, *, model: str, input_text: str, metadata=None) -> GatewayResponse:
        return GatewayResponse(
            response_id="resp-1",
            output_text="plan",
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                billing_units=1,
                cost_usd=Decimal("0"),
            ),
            raw={"id": "resp-1"},
        )


def test_loop_skill_agent_flow_emits_skill_selection_and_completed_stop_reason(tmp_path):
    skill_path = tmp_path / "skills" / "pytest" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(SKILL_TEXT, encoding="utf-8")
    events: list = []
    runner = AgentRunner(
        gateway_client=FakeGatewayClient(),
        model="glm-5.2",
        event_sink=events.append,
        loop_iteration_runner=CompleteOnFirstIteration(),
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Please debug the failing pytest test",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            skill_paths=(skill_path,),
            completion_condition="pytest tests pass",
        )
    )

    assert result.stop_reason == "COMPLETED"
    assert any(event.kind is TelemetryEventKind.SKILL_SELECTION for event in events)
    assert any(event.kind is TelemetryEventKind.AGENT_RUN for event in events)
    agent_run = next(event for event in events if event.kind is TelemetryEventKind.AGENT_RUN)
    assert agent_run.payload["matched_skills"] == ("pytest-debugging",)
    assert agent_run.payload["stop_reason"] == "COMPLETED"
