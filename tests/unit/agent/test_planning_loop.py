from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.agent.planning_loop import (
    PLANNING_NEW_READ_MAX_BYTES,
    PLANNING_OBSERVATION_MAX_BYTES,
    PlanningEvidenceBudgetError,
    PlanningLoopPolicy,
    PlanningObservation,
    PlanningReadEvidence,
    PlanningTurnKind,
    PlanningTurnParseError,
    pack_planning_evidence,
    parse_planning_turn,
    run_planning_with_budget,
)
from optimus.agent.workspace_context import DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES


def test_planning_policy_defaults_to_three_turns_and_two_repeated_failures():
    policy = PlanningLoopPolicy()
    assert policy.max_planning_turns == 3
    assert policy.max_wall_clock_minutes == 30
    loop_policy = policy.to_loop_budget_policy(max_cost_usd=Decimal("0.05"))
    assert loop_policy.max_iterations == 3
    assert loop_policy.max_budget_credits == Decimal("0.05")
    assert loop_policy.repeated_failure_limit == 2


def test_zero_run_budget_fails_before_loop_policy_construction():
    result = run_planning_with_budget(Decimal("0"))
    assert result.stop_reason == "PLANNING_BUDGET_EXHAUSTED"
    assert result.settled_turns == 0


@pytest.mark.parametrize("turns", [0, -1])
def test_planning_policy_rejects_non_positive_turn_caps(turns: int):
    with pytest.raises(ValidationError):
        PlanningLoopPolicy(max_planning_turns=turns)


@pytest.mark.parametrize("turns", [1, 2])
def test_planning_policy_accepts_deterministic_boundary_caps(turns: int):
    assert PlanningLoopPolicy(max_planning_turns=turns).max_planning_turns == turns


def test_planning_policy_rejects_non_positive_wall_clock():
    with pytest.raises(ValidationError):
        PlanningLoopPolicy(max_wall_clock_minutes=0)


def test_planning_policy_rejects_non_positive_budget_for_loop_policy():
    policy = PlanningLoopPolicy()
    with pytest.raises(ValueError, match="max_cost_usd must be positive"):
        policy.to_loop_budget_policy(max_cost_usd=Decimal("0"))


def test_planning_evidence_partition_matches_workspace_context_cap():
    assert PLANNING_OBSERVATION_MAX_BYTES + PLANNING_NEW_READ_MAX_BYTES == DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES


def test_parse_planning_turn_accepts_single_ranged_read():
    decision = parse_planning_turn(
        "OBSERVE: Need the header.\n"
        "READ: src/example.py#bytes=0:128\n"
    )
    assert decision.kind is PlanningTurnKind.READ_MORE
    assert decision.observation_text == "Need the header."
    assert len(decision.read_requests) == 1
    assert decision.read_requests[0].path == "src/example.py"
    assert decision.read_requests[0].start_byte == 0
    assert decision.read_requests[0].end_byte == 128
    assert decision.failure_signature == "src/example.py#bytes=0:128"


def test_parse_planning_turn_normalizes_failure_signature_for_multiple_reads():
    decision = parse_planning_turn(
        "OBSERVE: Need both definitions.\n"
        "READ: src/b.py#bytes=0:128\n"
        "READ: src/a.py#bytes=128:256\n"
    )
    assert decision.kind is PlanningTurnKind.READ_MORE
    assert decision.failure_signature == (
        "src/a.py#bytes=128:256|src/b.py#bytes=0:128"
    )


@pytest.mark.parametrize(
    "path",
    (
        "/etc/passwd",
        "C:/Windows/System32",
        "../secret.py",
        "src/../../outside.py",
    ),
)
def test_parse_planning_turn_rejects_unsafe_read_paths(path: str):
    text = f"OBSERVE: note\nREAD: {path}#bytes=0:10\n"
    with pytest.raises(PlanningTurnParseError):
        parse_planning_turn(text)


@pytest.mark.parametrize(
    "read_line",
    (
        "READ: src/a.py#bytes=bad",
        "READ: src/a.py#bytes=0",
        "READ: src/a.py#bytes=10:5",
        "READ: src/a.py#bytes=0:10:20",
    ),
)
def test_parse_planning_turn_rejects_malformed_read_ranges(read_line: str):
    with pytest.raises(PlanningTurnParseError):
        parse_planning_turn(f"OBSERVE: note\n{read_line}\n")


def test_parse_planning_turn_rejects_overlapping_ranges_for_same_file():
    text = (
        "OBSERVE: overlapping\n"
        "READ: src/a.py#bytes=0:128\n"
        "READ: src/a.py#bytes=64:192\n"
    )
    with pytest.raises(PlanningTurnParseError, match="overlapping"):
        parse_planning_turn(text)


def test_parse_planning_turn_rejects_duplicate_ranges_for_same_file():
    text = (
        "OBSERVE: duplicate\n"
        "READ: src/a.py#bytes=0:128\n"
        "READ: src/a.py#bytes=0:128\n"
    )
    with pytest.raises(PlanningTurnParseError, match="duplicate"):
        parse_planning_turn(text)


def test_parse_planning_turn_rejects_missing_observation():
    with pytest.raises(PlanningTurnParseError, match="OBSERVE"):
        parse_planning_turn("READ: src/a.py#bytes=0:128\n")


def test_parse_planning_turn_rejects_oversized_observation():
    observation = "x" * (PLANNING_OBSERVATION_MAX_BYTES + 1)
    with pytest.raises(PlanningTurnParseError, match="observation"):
        parse_planning_turn(f"OBSERVE: {observation}\nREAD: src/a.py#bytes=0:10\n")


def test_parse_planning_turn_rejects_intermediate_write():
    with pytest.raises(PlanningTurnParseError):
        parse_planning_turn(
            "OBSERVE: note\n"
            "READ: src/a.py#bytes=0:10\n"
            "WRITE: src/a.py\n"
            "content\n"
        )


def test_parse_planning_turn_rejects_intermediate_test():
    with pytest.raises(PlanningTurnParseError):
        parse_planning_turn(
            "OBSERVE: note\n"
            "READ: src/a.py#bytes=0:10\n"
            "TEST pytest tests/unit -q\n"
        )


def test_parse_planning_turn_rejects_mixed_intermediate_and_final_grammar():
    with pytest.raises(PlanningTurnParseError):
        parse_planning_turn(
            "OBSERVE: note\n"
            "READ: src/a.py#bytes=0:10\n"
            "READ: src/a.py\n"
            "WRITE: src/a.py\n"
            "content\n"
        )


def test_parse_planning_turn_accepts_valid_final_plan():
    plan_text = "READ src/example.py\nWRITE src/example.py\nnew content\nTEST pytest tests/unit -q"
    decision = parse_planning_turn(plan_text)
    assert decision.kind is PlanningTurnKind.FINAL_PLAN
    assert decision.plan_text == plan_text
    assert decision.directives is not None
    assert decision.directives.read_paths == ("src/example.py",)
    assert decision.failure_signature is None


def test_parse_planning_turn_accepts_final_plan_whose_write_content_contains_ranged_read_example():
    plan_text = (
        "READ src/example.py\n"
        "WRITE docs/example.md\n"
        "Some doc text.\n"
        "READ: src/b.py#bytes=0:128\n"
        "More doc text.\n"
        "TEST pytest tests/unit -q"
    )
    decision = parse_planning_turn(plan_text)
    assert decision.kind is PlanningTurnKind.FINAL_PLAN
    assert decision.directives is not None
    assert decision.directives.write is not None
    assert "READ: src/b.py#bytes=0:128" in decision.directives.write.content


def test_parse_planning_turn_accepts_valid_refuse():
    decision = parse_planning_turn("REFUSE: Current raw evidence is insufficient for a safe write.")
    assert decision.kind is PlanningTurnKind.REFUSE
    assert decision.reason == "Current raw evidence is insufficient for a safe write."
    assert decision.failure_signature is None


@pytest.mark.parametrize(
    "reason",
    (
        "",
        "line one\nline two",
        "x" * 513,
    ),
)
def test_parse_planning_turn_rejects_invalid_refuse_reasons(reason: str):
    with pytest.raises(PlanningTurnParseError, match="REFUSE"):
        parse_planning_turn(f"REFUSE: {reason}")


def test_parse_planning_turn_rejects_refuse_with_directive_prefix_in_reason():
    with pytest.raises(PlanningTurnParseError, match="REFUSE"):
        parse_planning_turn("REFUSE: READ: src/a.py")


def test_parse_planning_turn_accepts_refuse_reason_containing_test_word():
    decision = parse_planning_turn("REFUSE: I need to see the full file before any TEST can run safely.")
    assert decision.kind is PlanningTurnKind.REFUSE
    assert "TEST can run safely" in decision.reason


def test_parse_planning_turn_raises_for_unrecognized_grammar():
    with pytest.raises(PlanningTurnParseError, match="no recognized planning-turn grammar"):
        parse_planning_turn("Here is what I would do in prose.")


def test_parse_planning_turn_rejects_intermediate_without_read():
    with pytest.raises(PlanningTurnParseError, match="READ"):
        parse_planning_turn("OBSERVE: note only\n")


def test_pack_planning_evidence_serializes_observations_and_current_reads_in_order():
    observations = (
        PlanningObservation(
            path="src/a.py",
            start_byte=0,
            end_byte=4,
            source_sha256="hash-a",
            observation_text="note a",
        ),
        PlanningObservation(
            path="src/b.py",
            start_byte=8,
            end_byte=16,
            source_sha256="hash-b",
            observation_text="note b",
        ),
    )
    current_reads = (
        PlanningReadEvidence(
            path="src/c.py",
            start_byte=0,
            end_byte=5,
            source_sha256="hash-c",
            range_text="hello",
        ),
    )

    envelope = pack_planning_evidence(observations=observations, current_reads=current_reads)

    assert envelope.text.index("src/a.py") < envelope.text.index("src/b.py") < envelope.text.index("src/c.py")
    assert "note a" in envelope.text
    assert "hello" in envelope.text
    assert envelope.byte_size == len(envelope.text.encode("utf-8"))
    assert envelope.byte_size <= PLANNING_OBSERVATION_MAX_BYTES + PLANNING_NEW_READ_MAX_BYTES


def test_pack_planning_evidence_rejects_observation_budget_overflow():
    oversized = "x" * (PLANNING_OBSERVATION_MAX_BYTES + 1)
    observations = (
        PlanningObservation(
            path="src/a.py",
            start_byte=0,
            end_byte=4,
            source_sha256="hash-a",
            observation_text=oversized,
        ),
    )

    with pytest.raises(PlanningEvidenceBudgetError) as exc:
        pack_planning_evidence(observations=observations, current_reads=())
    assert exc.value.code == "PLANNING_OBSERVATION_BUDGET_EXHAUSTED"


def test_pack_planning_evidence_rejects_current_read_budget_overflow():
    oversized = "x" * (PLANNING_NEW_READ_MAX_BYTES + 1)
    current_reads = (
        PlanningReadEvidence(
            path="src/a.py",
            start_byte=0,
            end_byte=len(oversized.encode("utf-8")),
            source_sha256="hash-a",
            range_text=oversized,
        ),
    )

    with pytest.raises(PlanningEvidenceBudgetError) as exc:
        pack_planning_evidence(observations=(), current_reads=current_reads)
    assert exc.value.code == "PLANNING_READ_BUDGET_EXHAUSTED"
