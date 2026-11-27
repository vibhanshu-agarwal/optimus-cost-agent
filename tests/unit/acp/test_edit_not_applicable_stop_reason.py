"""#559: an EDIT that cannot be applied ends the ACP turn as end_turn, not refusal. Zed rewinds a refused turn behind a
generic banner, so the corrective text never reached the person. The conversation outcome stays FAILED, ``_meta`` says
so, and no completed-plan update claims the EDIT was done (#565)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from optimus.acp import spec
from optimus.acp.conversation import ConversationOutcome, ConversationSanitizer, ConversationSanitizerInputs, ConversationState
from optimus.acp.spec import _conversation_outcome
from optimus.agent.edits import edit_failure_text
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.runtime.modes import ExecutionMode
from tests.unit.acp.test_hidden_text_stops_end_turn import assert_failed_turn_shown_without_a_completed_plan, drive_stop_turn

PLAN = "EDIT small.py\nOLD\nold\nNEW\nnew\nEND\n"
# What the person must read, independent of the production text: what was not made, where, why, that the plan changed
# nothing and ran none of its tests, and what to do next (#574).
# The path is escaped for Markdown where it is shown (#591).
PHRASES = ("was not made to small\\.py,", "not in the file", "made no changes", "ran none of its tests", "send your request again")
CODE = "(EDIT_OLD_NOT_FOUND)"


def _edit_not_applicable(request):
    return AgentRunResult(
        run_id=request.run_id,
        session_id=request.session_id,
        execution_mode=request.execution_mode,
        status=AgentRunStatus.FAILED,
        final_state="FAILED",
        output_text=edit_failure_text("EDIT_OLD_NOT_FOUND", "small.py"),
        tool_calls=(),
        total_cost_usd=Decimal("0"),
        mutation_count=0,
        provider_keys_resolvable=(),
        stop_reason="EDIT_NOT_APPLICABLE",
    )


@pytest.mark.parametrize("approve", [False, True], ids=["direct", "approved"])
async def test_an_edit_that_cannot_be_applied_ends_the_turn_normally_with_its_text_and_no_completed_plan(approve, tmp_path):
    result, updates, runner, records = await drive_stop_turn(tmp_path, _edit_not_applicable, approve=approve, plan_text=PLAN)

    assert_failed_turn_shown_without_a_completed_plan(result, updates, records, "EDIT_NOT_APPLICABLE", PHRASES)
    assert [r.approval.approved for r in runner.requests] == ([False, True] if approve else [False])
    final = [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"][-1]
    assert final.rstrip().endswith(CODE)  # the chunk carries the message's trailing break
    # The next turn's model-facing history keeps the same sentence and the code (#574).
    [record] = records.values()
    assert "was not made" in record.completion_text and record.completion_text.endswith(CODE)


@pytest.mark.parametrize("path", ["token", "config/secret", "password", "my-api_key"])
def test_a_secret_like_file_name_keeps_the_sentence_in_history(path):
    """Codex #574 finding 4: "token was not made" read as a secret assignment and lost its negation. With the negation
    first and a comma after the path, the sanitizer masks nothing in the sentence."""
    state = ConversationState(ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=())))
    text = edit_failure_text("EDIT_OLD_NOT_FOUND", path)

    stored = state.sanitize_text(text)  # what _commit_turn stores

    assert stored == text
    assert f"was not made to {path}," in stored
    assert stored.endswith(CODE)


async def test_the_completion_diagnostic_counts_no_plan_entries_when_none_is_sent(tmp_path, monkeypatch):
    logged = []

    def record(*, location, data=None, **_):
        if location == "spec.py:_emit_completion_message":
            logged.append(data())

    monkeypatch.setattr(spec, "acp_debug_log", record)
    await drive_stop_turn(tmp_path, _edit_not_applicable, approve=False, plan_text=PLAN)

    assert [entry["plan_entry_count"] for entry in logged] == [0]


def test_the_conversation_outcome_stays_failed():
    request = SimpleNamespace(run_id="run-1", session_id="sess-1", execution_mode=ExecutionMode.AGENT)
    assert _conversation_outcome(_edit_not_applicable(request)) is ConversationOutcome.FAILED
