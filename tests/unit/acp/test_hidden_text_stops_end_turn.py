"""#565: an unsafe TEST and an unexecuted WRITE end the ACP turn as end_turn, not refusal. Zed rewinds a refused turn
behind a generic banner, so the text never reached the person. The conversation outcome stays FAILED, ``_meta`` says so,
and no completed-plan update claims the plan's work was done. Both the direct stop and the approved run are driven
through the real adapter."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from optimus.acp.conversation import ConversationOutcome
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, _conversation_outcome
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.runtime.modes import ExecutionMode
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_context_engine_admission import Runner
from tests.unit.acp.test_spec_protocol import _recording_outbound, _rpc

PLAN = "WRITE example.py\ncontent\n"


def _unsafe_test(request):
    return AgentRunner(gateway_client=object(), model="glm-5.2")._unsafe_test_directive_result(request)


def _write_not_executed(request):
    return AgentRunner(gateway_client=object(), model="glm-5.2")._write_execution_failure_if_needed(
        request=request, plan_text=PLAN, tool_calls=[], total_cost_usd=Decimal("0"), plan_hash="hash-1"
    )


# (produce the run's own result, phrases the person must read: what was not done, and what to do next)
_STOPS = {
    "UNSAFE_TEST_DIRECTIVE": (
        _unsafe_test,
        ("rejected", "not allowed", "none of the plan's file changes were applied", "none of its tests were run", "ask again"),
    ),
    "WRITE_DIRECTIVE_NOT_EXECUTED": (
        _write_not_executed,
        ("file change in the approved plan was not applied", "tests in the plan may still have run", "send your request again"),
    ),
}


class _StopRunner(Runner):
    """Plans ``plan_text`` and awaits approval when ``approve``; otherwise, and for the approved run, returns the stop."""

    def __init__(self, produce, *, approve: bool, plan_text: str) -> None:
        super().__init__(plan_text=plan_text)
        self._produce, self._approve = produce, approve

    def run(self, request, **kwargs):
        if self._approve and not request.approval.approved:
            return super().run(request, **kwargs)
        self.requests.append(request)
        return self._produce(request)


async def drive_stop_turn(tmp_path, produce, *, approve: bool, plan_text: str = PLAN):
    """One Agent prompt through the real adapter; returns the wire result, the session updates and the runner."""
    runner = _StopRunner(produce, approve=approve, plan_text=plan_text)
    outbound = _recording_outbound()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound
    )
    session_id = (
        await _rpc(adapter, {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}})
    )["result"]["sessionId"]
    prompt = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "session/prompt",
        "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Change small.py"}]},
    }
    task = asyncio.create_task(_rpc(adapter, prompt))
    if approve:
        permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)
        outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
    response = await asyncio.wait_for(task, timeout=10)
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    records = adapter._sessions.get(session_id).conversation.records
    return response["result"], updates, runner, records


def assert_failed_turn_shown_without_a_completed_plan(result, updates, records, stop, phrases):
    assert result == {"stopReason": "end_turn", "_meta": {"runStopReason": stop, "outcome": "failed"}}
    # Committed only once every declared terminal message was flushed: a declared but unsent plan would leave none.
    assert [record.outcome for record in records.values()] == [ConversationOutcome.FAILED]
    completed = [u for u in updates if u["sessionUpdate"] == "plan" and any(e["status"] == "completed" for e in u["entries"])]
    assert completed == [], "a completed plan would tell the client the plan's work was done"
    final = [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"][-1].lower()
    for phrase in phrases:
        assert phrase in final, (phrase, final)


@pytest.mark.parametrize("approve", [False, True], ids=["direct", "approved"])
@pytest.mark.parametrize("stop", _STOPS)
async def test_the_stop_ends_the_turn_normally_with_its_text_and_no_completed_plan(stop, approve, tmp_path):
    produce, phrases = _STOPS[stop]

    result, updates, runner, records = await drive_stop_turn(tmp_path, produce, approve=approve)

    assert_failed_turn_shown_without_a_completed_plan(result, updates, records, stop, phrases)
    assert [r.approval.approved for r in runner.requests] == ([False, True] if approve else [False])


@pytest.mark.parametrize("stop", _STOPS)
def test_the_conversation_outcome_stays_failed(stop, tmp_path):
    produce, _ = _STOPS[stop]
    request = AgentRunRequest(run_id="run-1", task="Change small.py", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path)
    result = produce(request)
    assert result.stop_reason == stop
    assert _conversation_outcome(result) is ConversationOutcome.FAILED
