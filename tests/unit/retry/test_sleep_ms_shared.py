from __future__ import annotations

import time
from decimal import Decimal

from optimus.gates.fitness import GateResult
from optimus.retry.gated_run import GatedRetryRunner
from optimus.retry.policy import RetryController, RetryPolicy, TransientGatewayError
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


class _FailOnceGate:
    name = "fitness"
    required = True

    def __init__(self) -> None:
        self.calls = 0

    def run(self) -> GateResult:
        self.calls += 1
        if self.calls == 1:
            return GateResult.fail(name=self.name, summary="failure")
        return GateResult.pass_(name=self.name, summary="passed")


def test_both_retry_paths_convert_the_same_delay_to_the_same_seconds(monkeypatch, tmp_path):
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    retry_policy = RetryPolicy(max_retries=2, base_delay_ms=1500, jitter_ms=(0,))

    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise TransientGatewayError("temporary")
        return "ok"

    RetryController(policy=retry_policy).run(flaky)

    gate = _FailOnceGate()
    GatedRetryRunner(policy=retry_policy).run(
        context=RuntimeContext(
            execution_mode=ExecutionMode.AGENT,
            state=AgentState.EXECUTING,
            approval_granted=True,
            user_approval_id="approval-1",
        ),
        workspace_root=tmp_path,
        checks_factory=lambda candidate, shadow_root: (gate,),
        plan_candidate=lambda attempt, prior_failures: "candidate",
        apply_candidate=lambda candidate, shadow_root: None,
        candidate_cost_usd=lambda candidate: Decimal("0"),
    )

    assert slept == [1.5, 1.5]
