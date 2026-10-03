"""Plan 12.2 Task 11: product cost policy - accounting foundation now, cost-stop removal held.

Accepted Q3 (ADR-015) removes the product $0.05 stop only after the accounting foundation and the D6
unknown-cost/governed policy successor are accepted. That acceptance has not happened, so:

- the removal's acceptance tests are strict expected failures. They pass the day the removal lands,
  and strict mode then fails the run, so the marker cannot outlive the hold silently;
- the bounds that stay after removal (3 planning rounds, 30 minutes, repeated-failure limit 2,
  single-call Chat) and independently authorized evaluation caps are pinned now;
- planning cost through approval is charged once, and a stored plan's cost completeness survives
  storage, with a legacy record missing it treated as unverified, never complete.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.planning_loop import PlanningLoopPolicy
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import AgentPlanRecord, InMemoryAgentStateStore, _record_from_mapping, _record_to_mapping
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode

HELD = pytest.mark.xfail(
    strict=True,
    reason="HELD: product cost-stop removal waits for D6/governed successor acceptance (ADR-015 Q3); "
    "accounting foundation only in CP3",
)


class _Gateway:
    def __init__(self, output_text: str, cost: str) -> None:
        self.output_text, self.cost = output_text, cost
        self.calls: list[str] = []

    def create_response(self, *, model, input_text, metadata=None):
        self.calls.append(input_text)
        usage = GatewayUsage(gateway_request_id=f"gw-{len(self.calls)}", provider="p", billing_units=1, cost_usd=Decimal(self.cost))
        return GatewayResponse(output_text=self.output_text, gateway_usage=usage, raw={}, finish_reason="stop")


def _request(tmp_path: Path, mode: ExecutionMode, **fields) -> AgentRunRequest:
    return AgentRunRequest(run_id="s:1", session_id="s", task="Explain calc.py", execution_mode=mode, workspace_root=tmp_path, **fields)


# --- Held: the removal's acceptance tests ----------------------------------------------------------


@HELD
def test_a_product_answer_above_the_former_cap_is_delivered(tmp_path):
    result = AgentRunner(gateway_client=_Gateway("An answer.", "0.06"), model="m").run(_request(tmp_path, ExecutionMode.CHAT))

    assert result.status is AgentRunStatus.COMPLETED and result.output_text == "An answer."


@HELD
def test_the_planner_prompt_carries_no_remaining_dollar_budget(tmp_path):
    gateway = _Gateway("REFUSE: no", "0.001")
    AgentRunner(gateway_client=gateway, model="m").run(_request(tmp_path, ExecutionMode.AGENT))

    assert "Remaining budget (USD)" not in gateway.calls[0]


@HELD
def test_planning_needs_no_positive_dollar_budget():
    from optimus.loops.models import LoopBudgetPolicy

    LoopBudgetPolicy(max_iterations=3, max_wall_clock_minutes=30, repeated_failure_limit=2)


# --- Retained now and after removal ----------------------------------------------------------------


def test_the_retained_planning_bounds_are_three_rounds_thirty_minutes_and_two_repeated_failures():
    policy = PlanningLoopPolicy()
    loop = policy.to_loop_budget_policy(max_cost_usd=Decimal("0.05"))

    assert (policy.max_planning_turns, policy.max_wall_clock_minutes) == (3, 30)
    assert (loop.max_iterations, loop.max_wall_clock_minutes, loop.repeated_failure_limit) == (3, 30, 2)


def test_chat_is_a_single_call(tmp_path):
    gateway = _Gateway("An answer.", "0.001")
    AgentRunner(gateway_client=gateway, model="m").run(_request(tmp_path, ExecutionMode.CHAT))
    assert len(gateway.calls) == 1


def test_an_evaluation_keeps_its_own_dollar_cap():
    import tools.evaluate_context_summarizer as evaluation

    assert evaluation.MAX_FIXTURE_CALLS == 2
    assert hasattr(evaluation, "CapRefused")


# --- Planning cost through approval ----------------------------------------------------------------


def _plan_and_apply(tmp_path: Path):
    (tmp_path / "example.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    gateway = _Gateway('WRITE example.py\ndef f():\n    """One."""\n    return 1\n', "0.002")
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=gateway, model="m", state_store=store)
    planned = runner.run(_request(tmp_path, ExecutionMode.AGENT))
    approval = AgentApproval(approved=True, approval_id="a", plan_hash=planned.plan_hash)
    return runner, gateway, store, planned, approval


def test_the_stored_plan_keeps_its_cost_completeness_and_attempts(tmp_path):
    _, _, store, planned, _ = _plan_and_apply(tmp_path)

    record = store.load_plan(run_id="s:1", plan_hash=planned.plan_hash)

    assert record.record_version == 2
    assert record.cost_complete is True and record.gateway_request_ids == ("gw-1",)


def test_an_incomplete_planning_cost_stays_incomplete_through_application(tmp_path):
    runner, gateway, store, planned, approval = _plan_and_apply(tmp_path)
    record = store.load_plan(run_id="s:1", plan_hash=planned.plan_hash)
    store.save_plan(record.model_copy(update={"cost_complete": False}))

    applied = runner.run(_request(tmp_path, ExecutionMode.AGENT, approval=approval))

    assert applied.status is AgentRunStatus.COMPLETED
    assert applied.cost_complete is False
    assert len(gateway.calls) == 1  # application makes no model call and adds no planning charge


def test_a_legacy_record_without_completeness_is_unverified_never_complete():
    record = AgentPlanRecord(
        run_id="r", task="t", execution_mode=ExecutionMode.AGENT, workspace_root="/w", plan_hash="h",
        plan_text="WRITE a.py\nx", gateway_request_id="gw", model="m", provider="p", cost_usd=Decimal("0.002"),
        created_at_ms=1, expires_at_ms=2,
    )  # fmt: skip
    legacy = {key: value for key, value in _record_to_mapping(record).items() if key not in {"record_version", "cost_complete"}}

    loaded = _record_from_mapping(legacy)

    assert loaded.record_version == 1 and loaded.cost_complete is None
    assert _record_from_mapping(_record_to_mapping(record.model_copy(update={"cost_complete": False}))).cost_complete is False


def test_applying_a_legacy_plan_reports_its_cost_as_unverified(tmp_path):
    runner, _, store, planned, approval = _plan_and_apply(tmp_path)
    record = store.load_plan(run_id="s:1", plan_hash=planned.plan_hash)
    store.save_plan(record.model_copy(update={"cost_complete": None, "record_version": 1}))

    applied = runner.run(_request(tmp_path, ExecutionMode.AGENT, approval=approval))

    assert applied.cost_complete is False
