"""#559: an EDIT that cannot be applied ends the ACP turn as end_turn, not refusal. Zed rewinds a refused turn behind a
generic banner, so the corrective text never reached the person. The conversation outcome stays FAILED."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from optimus.acp.conversation import ConversationOutcome
from optimus.acp.shapes import AGENT_MESSAGE_BLOCK_SEPARATOR
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, _conversation_outcome
from optimus.agent.edits import edit_failure_text
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.runtime.modes import ExecutionMode
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_spec_protocol import _recording_outbound, _rpc

TEXT = edit_failure_text("EDIT_OLD_NOT_FOUND", "small.py")


class _EditNotApplicableRunner:
    def run(self, request, *, planning_progress_observer=None, **runtime_kwargs):
        del planning_progress_observer
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.FAILED,
            final_state="FAILED",
            output_text=TEXT,
            tool_calls=(),
            total_cost_usd=Decimal("0"),
            mutation_count=0,
            provider_keys_resolvable=(),
            stop_reason="EDIT_NOT_APPLICABLE",
        )


async def test_an_edit_that_cannot_be_applied_ends_the_turn_normally_with_its_text_shown(tmp_path):
    outbound = _recording_outbound()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(_EditNotApplicableRunner()),
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
    assert messages[-1] == TEXT + AGENT_MESSAGE_BLOCK_SEPARATOR


def test_the_conversation_outcome_stays_failed():
    request = SimpleNamespace(run_id="run-1", session_id="sess-1", execution_mode=ExecutionMode.AGENT)
    assert _conversation_outcome(_EditNotApplicableRunner().run(request)) is ConversationOutcome.FAILED
