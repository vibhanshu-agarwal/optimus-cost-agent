"""#410 (design v3, R7; Codex round 49, correction 3): ACP's final message carries the WRITE refusal's own text,
ahead of the generic "Executed:" listing that a read-before-write tool call would otherwise produce."""

from __future__ import annotations

from optimus.acp.spec import _completion_message, _stop_reason
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
