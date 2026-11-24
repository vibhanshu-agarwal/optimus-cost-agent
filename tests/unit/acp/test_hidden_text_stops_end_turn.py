"""#565: an unsafe TEST and an unexecuted WRITE end the ACP turn as end_turn, not refusal. Zed rewinds a refused turn
behind a generic banner, so the text never reached the person. The conversation outcome stays FAILED."""

from __future__ import annotations

from decimal import Decimal

import pytest

from optimus.acp.conversation import ConversationOutcome
from optimus.acp.shapes import AGENT_MESSAGE_BLOCK_SEPARATOR
from optimus.acp.spec import _WRITE_NOT_EXECUTED_MESSAGE, AcpDuplexAdapter, InMemoryAcpSpecSessionStore, _conversation_outcome
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.runtime.modes import ExecutionMode
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_spec_protocol import _recording_outbound, _rpc

PLAN = "WRITE example.py\ncontent\n"


def _unsafe_test(request):
    return AgentRunner(gateway_client=object(), model="glm-5.2")._unsafe_test_directive_result(request)


def _write_not_executed(request):
    return AgentRunner(gateway_client=object(), model="glm-5.2")._write_execution_failure_if_needed(
        request=request, plan_text=PLAN, tool_calls=[], total_cost_usd=Decimal("0"), plan_hash="hash-1"
    )


# (produce the run's own result, the text the person must be sent)
_STOPS = {
    "UNSAFE_TEST_DIRECTIVE": (_unsafe_test, None),
    "WRITE_DIRECTIVE_NOT_EXECUTED": (_write_not_executed, _WRITE_NOT_EXECUTED_MESSAGE),
}


def _request(**ids):
    return AgentRunRequest(
        run_id=ids.get("run_id", "run-1"), task="Change small.py", execution_mode=ExecutionMode.AGENT, workspace_root=ids["root"]
    )


class _StopRunner:
    def __init__(self, produce):
        self._produce = produce

    def run(self, request, *, planning_progress_observer=None, **runtime_kwargs):
        del planning_progress_observer
        return self._produce(request)


@pytest.mark.parametrize("stop", _STOPS)
async def test_the_stop_ends_the_turn_normally_with_its_text_shown(stop, tmp_path):
    produce, text = _STOPS[stop]
    expected = text or produce(_request(root=tmp_path)).output_text
    outbound = _recording_outbound()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(_StopRunner(produce)),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    session_id = (
        await _rpc(adapter, {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}})
    )["result"]["sessionId"]

    response = await _rpc(
        adapter,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Change small.py"}]},
        },
    )

    assert response["result"]["stopReason"] == "end_turn"
    messages = [
        item["params"]["update"]["content"]["text"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    ]
    assert messages[-1] == expected + AGENT_MESSAGE_BLOCK_SEPARATOR
    assert expected != "Turn completed."
    if stop == "WRITE_DIRECTIVE_NOT_EXECUTED":
        assert expected != PLAN  # the plan is the run's output_text; the person gets the corrective text instead


@pytest.mark.parametrize("stop", _STOPS)
def test_the_conversation_outcome_stays_failed(stop, tmp_path):
    produce, _ = _STOPS[stop]
    result = produce(_request(root=tmp_path))
    assert result.stop_reason == stop
    assert _conversation_outcome(result) is ConversationOutcome.FAILED
