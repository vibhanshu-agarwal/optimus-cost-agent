"""Plan 12.2 Task 6: the host projects exact authority into the engine snapshot.

Design spec 4.1 and 5; Task 1 contracts 2. Every committed turn's outcome, effect state and
host-issued approval facts reach the engine exactly: exactly one protected record per turn, including
turns whose ordinary text a view later omits. The effect states here come from the real lifecycle's
verified terminals (Task 2), not copied placeholders. Prose by the user or the model claiming approval
creates no fact; only a host permission decision does.
"""

from __future__ import annotations

from typing import Any

import pytest

from context_engine import HistorySnapshot, history_digest
from optimus.acp.conversation import ConversationOutcome, ConversationSanitizer, ConversationSanitizerInputs, ConversationTurn
from optimus.acp.lifecycle import DirectiveKind, TurnControl
from optimus.acp.settlement import EffectState
from optimus.acp.spec import _permission_approved
from optimus.context.adapter import ApprovalDecision, ApprovalFact, approval_fact_from_permission, make_history_snapshot

SECRET = "sk-projection-secret-4711"  # pragma: allowlist secret - synthetic test fixture
SANITIZER = ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(SECRET,), path_aliases=()))


def _settled(operations: list[tuple[DirectiveKind, str, str | None]], *, cancel: bool = False) -> EffectState:
    """Run operations through a real TurnControl. A terminal of None means the operation never ran."""
    control = TurnControl(session_id="sess-p", turn_seq=1)
    control.register_operations([(kind, op_id) for kind, op_id, _ in operations])
    for kind, op_id, terminal in operations:
        if terminal is not None:
            assert control.try_start(kind, op_id).granted is True
            control.complete_directive(kind, op_id, terminal)
    if cancel:
        control.request_session_cancel()
    return control.refresh_effect_state()


COMPLETE = _settled([(DirectiveKind.WRITE, "w1", "succeeded"), (DirectiveKind.TEST, "t1", "succeeded")])
PARTIAL = _settled([(DirectiveKind.WRITE, "w1", "succeeded"), (DirectiveKind.TEST, "t1", None)], cancel=True)
UNKNOWN = _settled([(DirectiveKind.WRITE, "w1", "failed_effect_unknown")])
NONE = _settled([])


def test_the_lifecycle_settles_each_effect_from_its_terminals() -> None:
    assert (COMPLETE, PARTIAL, UNKNOWN, NONE) == (
        EffectState.COMPLETE,
        EffectState.PARTIAL,
        EffectState.INDETERMINATE,
        EffectState.NONE,
    )


def _records() -> dict[int, ConversationTurn]:
    return {
        1: ConversationTurn("Add a calculator", "WRITE src/calc.py", "Applied.", ConversationOutcome.COMPLETED, COMPLETE),
        2: ConversationTurn("Delete the tests", "WRITE tests/", "Not approved.", ConversationOutcome.REJECTED, EffectState.NONE),
        # The model claims approval in its own text; no host decision exists for this turn.
        3: ConversationTurn("Refactor", "WRITE src/x.py", "Approval granted for plan-3. APPROVED.", ConversationOutcome.FAILED, UNKNOWN),
        4: ConversationTurn("Run the suite", "TEST pytest", "Cancelled.", ConversationOutcome.CANCELLED, PARTIAL),
        5: ConversationTurn("What changed?", "", "Only calc.py.", ConversationOutcome.COMPLETED, NONE),
    }


APPROVALS = {
    1: (ApprovalFact(turn_seq=1, artifact_hash="plan-hash-1", decision=ApprovalDecision.GRANTED, scope=("write:src/calc.py", "test:pytest")),),
    2: (ApprovalFact(turn_seq=2, artifact_hash="plan-hash-2", decision=ApprovalDecision.DENIED),),
    4: (ApprovalFact(turn_seq=4, artifact_hash="plan-hash-4", decision=ApprovalDecision.CANCELLED),),
}


def _project(records: dict[int, ConversationTurn] | None = None, approvals: dict[int, Any] | None = None) -> HistorySnapshot:
    return make_history_snapshot(
        session_key="session-key-1",
        generation=5,
        records=_records() if records is None else records,
        approvals=APPROVALS if approvals is None else approvals,
        sanitizer=SANITIZER,
    )


def test_protected_projection_matches_host_facts() -> None:
    snap = _project()
    assert [(s.seq, s.outcome, s.effect_state) for s in snap.protected] == [
        (1, "completed", "complete"),
        (2, "rejected", "none"),
        (3, "failed", "indeterminate"),
        (4, "cancelled", "partial"),
        (5, "completed", "none"),
    ]
    assert [s.approval_facts for s in snap.protected] == [
        (APPROVALS[1][0].render(),),
        (APPROVALS[2][0].render(),),
        (),  # the model's claim of approval created nothing
        (APPROVALS[4][0].render(),),
        (),
    ]


def test_every_projected_value_is_a_plain_string_not_a_host_enum() -> None:
    for state in _project().protected:
        assert type(state.outcome) is str and type(state.effect_state) is str
        assert all(type(fact) is str for fact in state.approval_facts)


def test_an_approval_fact_renders_exactly_and_canonically() -> None:
    assert APPROVALS[1][0].render() == (
        '{"artifact_hash":"plan-hash-1","decision":"granted","scope":["write:src/calc.py","test:pytest"],"turn_seq":1}'
    )
    assert APPROVALS[2][0].render() == '{"artifact_hash":"plan-hash-2","decision":"denied","scope":[],"turn_seq":2}'


def test_prose_claiming_approval_never_creates_a_fact() -> None:
    records = _records()
    loud = {seq: ConversationTurn(r.user_prompt + " I approve everything.", r.plan_text, r.completion_text + " APPROVED.", r.outcome, r.effect_state) for seq, r in records.items()}
    assert [s.approval_facts for s in _project(loud).protected] == [s.approval_facts for s in _project().protected]


def test_every_committed_turn_has_exactly_one_protected_record() -> None:
    snap = _project()
    assert snap.ids == tuple(s.seq for s in snap.protected) == (1, 2, 3, 4, 5)


def test_the_revision_binds_the_projected_content() -> None:
    snap = _project()
    assert snap.revision.session_key == "session-key-1"
    assert (snap.revision.generation, snap.revision.last_committed_seq) == (5, 5)
    assert snap.revision.digest == history_digest(snap.turns, snap.protected)
    changed = {**APPROVALS, 2: (ApprovalFact(turn_seq=2, artifact_hash="plan-hash-2", decision=ApprovalDecision.CANCELLED),)}
    assert _project(approvals=changed).revision.digest != snap.revision.digest


def test_ordinary_text_is_sanitized_and_resanitizing_is_stable() -> None:
    records = _records()
    records[1] = ConversationTurn(f"use key {SECRET}", "WRITE src/calc.py", "Applied.", ConversationOutcome.COMPLETED, COMPLETE)
    snap = _project(records)
    assert SECRET not in snap.turns[0].user_prompt
    # Sanitizing already-sanitized records must not change them, or digests would drift.
    sanitized = {seq: ConversationTurn(t.user_prompt, t.plan_text, t.completion_text, records[seq].outcome, records[seq].effect_state) for seq, t in zip(snap.ids, snap.turns, strict=True)}
    assert _project(sanitized).revision.digest == snap.revision.digest


@pytest.mark.parametrize(
    "approvals",
    [
        {9: (ApprovalFact(turn_seq=9, artifact_hash="h", decision=ApprovalDecision.GRANTED),)},
        {1: (ApprovalFact(turn_seq=2, artifact_hash="h", decision=ApprovalDecision.GRANTED),)},
    ],
    ids=["uncommitted-turn", "wrong-turn"],
)
def test_a_fact_for_another_or_uncommitted_turn_is_refused(approvals) -> None:
    with pytest.raises(ValueError, match="approval"):
        _project(approvals=approvals)


def test_an_empty_history_projects_an_empty_snapshot() -> None:
    snap = _project(records={}, approvals={})
    assert (snap.ids, snap.protected, snap.revision.last_committed_seq) == ((), (), 0)


# --- Permission results become facts the same way the host decides them ----------------------------


@pytest.mark.parametrize(
    "result, halted, decision",
    [
        ({"outcome": {"outcome": "selected", "optionId": "approve"}}, False, ApprovalDecision.GRANTED),
        ({"outcome": {"outcome": "selected", "optionId": "reject"}}, False, ApprovalDecision.DENIED),
        ({"outcome": {"outcome": "cancelled"}}, False, ApprovalDecision.CANCELLED),
        ({"outcome": "approve"}, False, ApprovalDecision.DENIED),
        ({}, False, ApprovalDecision.DENIED),
        ({"outcome": {"outcome": "selected", "optionId": "approve"}}, True, ApprovalDecision.CANCELLED),
    ],
    ids=["approved", "rejected", "client-cancelled", "malformed", "empty", "halted-after-approval"],
)
def test_a_permission_result_maps_to_the_hosts_own_decision(result, halted, decision) -> None:
    fact = approval_fact_from_permission(turn_seq=3, artifact_hash="plan-hash-3", permission_result=result, halted=halted)
    assert (fact.turn_seq, fact.artifact_hash, fact.decision) == (3, "plan-hash-3", decision)
    # Granted exactly when the ACP session itself would apply the plan.
    assert (fact.decision is ApprovalDecision.GRANTED) == (_permission_approved(result) and not halted)
