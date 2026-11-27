"""#570: a turn that did not complete sends no plan update that marks its work done, and text that is not a plan is
never sent as plan entries. Every stop the issue lists is driven through the real adapter on the direct path (the run
stops while planning) and on the approved path (the run stops after approval). A completed turn sends what it sent
before."""

from __future__ import annotations

from decimal import Decimal

import pytest

from optimus.acp.conversation import ConversationOutcome
from optimus.acp.shapes import plan_entries_from_text
from optimus.acp.spec import (
    _PLANNING_TERMINAL_STOP_REASONS,
    _UNAPPLIED_PLAN_STOP_REASONS,
    _VISIBLE_WORKSPACE_CONTEXT_FAILURES,
)
from optimus.agent.models import TEST_STOP_REASONS, AgentRunStatus, AgentToolCall
from optimus.agent.runner import AgentRunner
from optimus.runtime.process_tree import CommandStopped
from optimus.tools.line_endings import WRITE_LINE_ENDINGS_MIXED
from tests.unit.acp.test_hidden_text_stops_end_turn import PLAN, drive_stop_turn

PROSE = "The planning model's cost could not be confirmed.\nNo file was changed.\nSend your request again."
APPLIED = AgentToolCall(tool_name="write_file", summary="wrote example.py")


def _stopped(stop_reason, *, status=AgentRunStatus.FAILED, output_text=PROSE, tool_calls=(), mutation_count=0):
    def produce(request):
        return AgentRunner._build_result(
            request=request, status=status, final_state=status.value.upper(), output_text=output_text, tool_calls=tool_calls,
            total_cost_usd=Decimal("0"), stop_reason=stop_reason, mutation_count=mutation_count,
        )  # fmt: skip

    return produce


def _test_stop_after_an_applied_change(outcome):
    def produce(request):
        return AgentRunner(gateway_client=object(), model="glm-5.2")._test_stopped_result(
            request=request, stop=CommandStopped(outcome, "timed out"), tool_calls=[APPLIED], mutation_count=1,
            total_cost_usd=Decimal("0"), plan_hash="hash-1",
        )  # fmt: skip

    return produce


def _expired_plan(request):
    return AgentRunner(gateway_client=object(), model="glm-5.2")._missing_plan_result(request)


# Every stop #570 lists: (the run's result, the conversation outcome it commits, the wire stop reason).
_FAILED = ConversationOutcome.FAILED
STOPS = {
    **{code: (_stopped(code), _FAILED, "end_turn") for code in sorted(_PLANNING_TERMINAL_STOP_REASONS)},
    **{code: (_test_stop_after_an_applied_change(outcome), _FAILED, "end_turn") for outcome, code in TEST_STOP_REASONS.items()},
    "PLAN_NOT_FOUND_OR_EXPIRED": (_expired_plan, _FAILED, "end_turn"),
    WRITE_LINE_ENDINGS_MIXED: (_stopped(WRITE_LINE_ENDINGS_MIXED), _FAILED, "end_turn"),
    **{code: (_stopped(code), _FAILED, "end_turn") for code in sorted(_VISIBLE_WORKSPACE_CONTEXT_FAILURES)},
    **{code: (_stopped(code), _FAILED, "end_turn") for code in sorted(_UNAPPLIED_PLAN_STOP_REASONS)},
    "BUDGET_EXHAUSTED": (_stopped("BUDGET_EXHAUSTED", status=AgentRunStatus.TERMINATED), _FAILED, "refusal"),
    "UNPARSEABLE_PLAN": (_stopped("UNPARSEABLE_PLAN"), _FAILED, "refusal"),
    "unlisted code": (_stopped("SOME_UNLISTED_STOP"), _FAILED, "refusal"),
    "no code": (_stopped(None), _FAILED, "refusal"),
    # A run that saw the turn's halt before every approved step started; its text is the plan (runner._cancelled_execution_result).
    "cancelled": (
        _stopped("cancelled", status=AgentRunStatus.TERMINATED, output_text=PLAN, tool_calls=(APPLIED,), mutation_count=1),
        ConversationOutcome.CANCELLED,
        "cancelled",
    ),
}


def _plans(updates):
    return [u["entries"] for u in updates if u["sessionUpdate"] == "plan"]


@pytest.mark.parametrize("approve", [False, True], ids=["direct", "approved"])
@pytest.mark.parametrize("stop", STOPS)
async def test_a_turn_that_did_not_complete_sends_no_completed_plan_and_no_prose_as_plan(stop, approve, tmp_path):
    produce, outcome, wire_stop = STOPS[stop]

    result, updates, runner, records = await drive_stop_turn(tmp_path, produce, approve=approve)

    assert result["stopReason"] == wire_stop
    assert [record.outcome for record in records.values()] == [outcome]  # committed: every declared message was sent
    # Only the plan the person was asked to approve is shown, and still pending; the direct stop shows none.
    assert _plans(updates) == ([plan_entries_from_text(PLAN)] if approve else [])
    final = [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"][-1]
    if wire_stop == "end_turn":  # the client keeps the turn: its text must say why it stopped, now that no plan does
        assert not final.startswith("Turn completed."), final
    if stop == "PLAN_NOT_FOUND_OR_EXPIRED":
        assert "re-run planning and approve the new plan" in final.lower(), final
    assert [r.approval.approved for r in runner.requests] == ([False, True] if approve else [False])


def _completed_after_approval(request):
    return AgentRunner._build_result(
        request=request, status=AgentRunStatus.COMPLETED, final_state="COMPLETED", output_text=PLAN, tool_calls=(APPLIED,),
        total_cost_usd=Decimal("0"), mutation_count=1, plan_hash="hash-1",
    )  # fmt: skip


async def test_a_completed_turn_still_sends_the_pending_then_the_completed_plan(tmp_path):
    result, updates, _, records = await drive_stop_turn(tmp_path, _completed_after_approval, approve=True)

    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": None, "outcome": "completed"}}
    assert [record.outcome for record in records.values()] == [ConversationOutcome.COMPLETED]
    pending = plan_entries_from_text(PLAN)
    assert _plans(updates) == [pending, [{**entry, "status": "completed"} for entry in pending]]
    kinds = [u["sessionUpdate"] for u in updates if u["sessionUpdate"] in ("plan", "agent_message_chunk")]
    assert kinds[-3:] == ["plan", "plan", "agent_message_chunk"], kinds  # the completed plan comes before the final text
    final = [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"][-1]
    assert final.startswith("Completed:\n- wrote example\\.py")  # the path escaped where it is shown (#591)
