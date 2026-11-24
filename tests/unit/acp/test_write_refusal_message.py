"""#410 (design v3, R7; Codex round 49, correction 3): ACP's final message carries the WRITE refusal's own text,
ahead of the generic "Executed:" listing that a read-before-write tool call would otherwise produce."""

from __future__ import annotations

import pytest

from optimus.acp.conversation import ConversationOutcome
from optimus.acp.spec import _completion_message, _conversation_outcome, _stop_reason
from optimus.agent.models import AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.runtime.modes import ExecutionMode
from optimus.tools.line_endings import WRITE_LINE_ENDINGS_MIXED

TEXT = "a.py has mixed line endings, which Optimus does not rewrite. This WRITE did not change the file. No subsequent TEST directives from this plan ran."


def _refused() -> AgentRunResult:
    return AgentRunResult(
        run_id="run-1",
        session_id="sess-1",
        execution_mode=ExecutionMode.AGENT,
        status=AgentRunStatus.FAILED,
        final_state="FAILED",
        output_text=TEXT,
        tool_calls=(AgentToolCall(tool_name="file_reader", summary="read a.py", authorization_outcome="ALLOW"),),
        stop_reason=WRITE_LINE_ENDINGS_MIXED,
    )


def test_the_final_message_is_the_refusal_text() -> None:
    assert _completion_message(_refused()) == TEXT


def test_the_refusal_ends_the_turn_normally() -> None:
    assert _stop_reason(_refused()) == "end_turn"


@pytest.mark.parametrize("reason", [
    "PLANNING_MODEL_REFUSED", "PLANNING_HALTED", "PLANNING_BUDGET_EXHAUSTED",
    "PLANNING_TURN_LIMIT_EXHAUSTED", "PLANNING_REPEATED_MCP_REQUEST", "CONTEXT_CAPACITY_EXCEEDED",
    "WORKSPACE_REFERENCE_NOT_READABLE", "cancelled",
])
def test_mcp_records_do_not_hide_terminal_explanations(reason):
    text = "Planning stopped; review the task before continuing."
    result = _refused().model_copy(update={
        "stop_reason": reason, "output_text": text,
        "status": AgentRunStatus.TERMINATED,
        "tool_calls": (AgentToolCall(tool_name="mcp_call", summary="authorized MCP call", authorization_outcome="ALLOW"),),
    })
    assert _completion_message(result) == text
    if reason == "PLANNING_BUDGET_EXHAUSTED":
        assert _stop_reason(result) == "end_turn"


@pytest.mark.parametrize("reason", [
    "AMBIGUOUS_WORKSPACE_REFERENCE", "REQUIRED_WORKSPACE_FILE_TOO_LARGE", "WORKSPACE_REFERENCE_NOT_READABLE",
])
def test_a_workspace_stop_the_person_must_read_ends_the_turn_normally(reason):
    """Plan 12.13 Task 4 (live Zed): a "refusal" makes Zed rewind the turn behind a generic content-policy banner, so the
    ranked candidates (#242) never reached the person. The conversation outcome, not the stop reason, records the failure."""
    result = _refused().model_copy(update={"stop_reason": reason, "output_text": "Retry with one exact path.", "tool_calls": ()})
    assert _completion_message(result) == "Retry with one exact path."
    assert _stop_reason(result) == "end_turn"
    assert _conversation_outcome(result) is ConversationOutcome.FAILED


def test_an_unlisted_failure_still_ends_as_a_refusal():
    assert _stop_reason(_refused().model_copy(update={"stop_reason": "SOMETHING_ELSE"})) == "refusal"


@pytest.mark.parametrize("outcome", ["ALLOW", "HOLD", "BLOCK"])
def test_mcp_attempt_summary_uses_neutral_wording_and_preserves_outcome(outcome):
    result = _refused().model_copy(update={
        "stop_reason": None, "status": AgentRunStatus.AWAITING_APPROVAL,
        "tool_calls": (AgentToolCall(tool_name="mcp_call", summary="MCP lookup attempt", authorization_outcome=outcome),),
    })
    assert _completion_message(result) == "Tool activity:\n- MCP lookup attempt"
