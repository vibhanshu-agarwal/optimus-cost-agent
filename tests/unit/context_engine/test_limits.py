"""Plan 12.2 Task 12: the limit measurements are exact where they claim to be (design spec 4.2, 6, 9.4).

The measurement tool (`tools/measure_context_engine_limits.py`) produces the D1-D3 evidence. These
tests hold its boundary claims to the real host and engine code: each admitted or refused boundary is
off by nothing, the protected-authority arithmetic matches the engine turn for turn, the output reserve
is counted once, and a truncated or unfinished reply is never used. They also pin the accepted
engine-absent floor (524288 bytes, inclusive). Proposed attached values get their own boundary
assertions only once the operator accepts them. No timing or memory figure is asserted here.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
from decimal import Decimal

import pytest

from optimus.acp.conversation import CONVERSATION_MAX_BYTES
from optimus.agent.directives import parse_agent_plan
from tools import measure_context_engine_limits as limits


@pytest.mark.parametrize("alphabet", sorted(limits.ALPHABETS))
@pytest.mark.parametrize("size", [0, 1, 3, 5, 1023, 4096])
def test_synthetic_text_has_exactly_the_requested_utf8_size(alphabet, size) -> None:
    assert len(limits.text_of(alphabet, size).encode("utf-8")) == size


def test_prose_alphabets_keep_word_runs_short_so_the_sanitizer_stays_linear() -> None:
    def longest_run(alphabet: str, size: int) -> int:
        return max(len(run) for run in re.findall(r"\w+", limits.text_of(alphabet, size)))

    for alphabet in ("ascii", "latin", "cjk"):
        unit = len(limits.ALPHABETS[alphabet].encode("utf-8"))
        for size in (4_096 + 7, 65_536 + 11, (1 << 20) + 13):
            # A run never exceeds one repeating unit (or the ASCII padding, shorter than a unit).
            assert longest_run(alphabet, size) < unit, (alphabet, size)


@pytest.mark.parametrize("alphabet", ["ascii", "emoji", "escapes"])
def test_storage_admission_boundaries_are_exact(alphabet) -> None:
    boundaries = limits.storage_boundaries(alphabet, source_max_bytes=96 * 1024, reservation=8 * 1024)

    assert boundaries["attached_at_limit_minus_reservation"] == {"admitted": True, "projected_bytes": 88 * 1024, "refuse_reason": None}
    assert boundaries["attached_one_over_reservation"] == {"admitted": False, "projected_bytes": 88 * 1024 + 1, "refuse_reason": "reservation"}
    assert boundaries["attached_one_over_limit"] == {"admitted": False, "projected_bytes": 96 * 1024 + 1, "refuse_reason": "cap"}


def test_the_accepted_engine_absent_floor_is_inclusive_at_524288_bytes() -> None:
    boundaries = limits.storage_boundaries("ascii", source_max_bytes=96 * 1024, reservation=0)

    assert CONVERSATION_MAX_BYTES == 524_288
    assert boundaries["absent_at_floor"] == {"admitted": True, "projected_bytes": 524_288, "refuse_reason": None}
    assert boundaries["absent_one_over_floor"] == {"admitted": False, "projected_bytes": 524_289, "refuse_reason": "cap"}


@pytest.mark.parametrize("alphabet", ["ascii", "cjk", "escapes"])
def test_the_engine_source_check_is_inclusive_and_measures_rendered_turns(alphabet) -> None:
    boundary = limits.engine_source_boundary(alphabet, turns=2)

    assert boundary["at_limit"] == {"available": True, "reason": None}
    assert boundary["one_under_needed"] == {"available": False, "reason": "source exceeds limit"}
    assert boundary["engine_source_bytes"] != boundary["canonical_bytes"]  # two different measures, both reported


@pytest.mark.parametrize(("facts", "ratio"), [(0, Decimal("1")), (1, Decimal("1")), (4, Decimal("0.5"))])
def test_the_exact_authority_turn_count_matches_the_engine_turn_for_turn(facts, ratio) -> None:
    check = limits.protected_growth_check(facts, ratio, 4_096)

    assert check["at_most"] == {"turns": check["computed_most"], "available": True, "reason": None}
    assert check["one_more"] == {"turns": check["computed_most"] + 1, "available": False, "reason": "exact authority exceeds history capacity"}


def test_protected_records_grow_with_turn_number_and_facts() -> None:
    assert limits.protected_record_bytes(1000, 0) > limits.protected_record_bytes(1, 0)
    assert limits.protected_record_bytes(1, 4) > limits.protected_record_bytes(1, 1) > limits.protected_record_bytes(1, 0)


def test_the_output_reserve_is_counted_once_and_history_gets_the_rest() -> None:
    wide = limits.allocation(window=1_000_000, ceiling=262_144, reserve=32_768, fixed_tokens=1_000, prompt_tokens=10)
    narrow = limits.allocation(window=200_000, ceiling=262_144, reserve=32_768, fixed_tokens=1_000, prompt_tokens=10)

    assert wide == {"effective_total": 262_144, "usable_input": 229_376, "history_capacity": 228_366}
    assert narrow == {"effective_total": 200_000, "usable_input": 167_232, "history_capacity": 166_222}
    assert limits.allocation(window=None, ceiling=262_144, reserve=1, fixed_tokens=0, prompt_tokens=0)["reason"] == "window unrecorded"


@pytest.mark.parametrize(("usable", "target", "expected"), [(229_376, 100_000, 100_000), (100_000, 131_072, 80_000), (100_000, 80_000, 80_000)])
def test_the_adr003_trigger_is_the_smaller_of_80_percent_and_the_tier_target(usable, target, expected) -> None:
    assert limits.adr003_trigger(usable, target) == expected


def test_a_representative_plan_is_one_complete_write_in_the_real_grammar() -> None:
    content = 'def greet():\n    return "hi"\n'
    plan = limits.write_plan("src/greet.py", content)

    directives = parse_agent_plan(plan)

    assert (directives.write.path, directives.write.content.rstrip("\n")) == ("src/greet.py", content.rstrip("\n"))
    assert limits.record_bytes(plan) > len(plan.encode("utf-8"))  # newlines and quotes are escaped in the record


def test_write_plan_sizes_cover_every_file_given() -> None:
    paths = limits.tracked_text_files()[:5]

    sizes = limits.write_plan_sizes(paths, (Decimal("1"), Decimal("0.25")))

    assert sizes["files"] == 5
    assert sizes["plan_bytes"]["p100"] == max(len(limits.write_plan(p, (limits.REPO_ROOT / p).read_text(encoding="utf-8")).encode()) for p in paths)
    assert sizes["reserve_tokens_by_ratio"]["1"]["p100"] == sizes["plan_bytes"]["p100"]


def test_a_truncated_or_unfinished_reply_is_never_used_in_any_mode() -> None:
    rows = {(row["mode"], row["finish_reason"]): row for row in limits.completion_status(("stop", "length", "content_filter", "error"))}

    for mode in ("CHAT", "PLAN", "AGENT"):
        for finish in ("length", "content_filter", "error"):
            row = rows[(mode, finish)]
            assert (row["plan_for_approval"], row["answer_shown"], row["mutations"], row["gateway_calls"]) == (False, False, 0, 1), (mode, finish)
            assert row["stop_reason"] is not None
    assert rows[("AGENT", "stop")]["plan_for_approval"] and rows[("CHAT", "stop")]["answer_shown"]


def test_fixed_request_material_includes_every_existing_maximum() -> None:
    fixed = limits.fixed_request_material()

    assert fixed["planning"] >= (16 + 4 + 12 + 8) * 1024  # workspace, observations, new reads, MCP evidence
    assert fixed["chat"] >= 16 * 1024
    assert 0 < fixed["summarizer"] < fixed["chat"] < fixed["planning"]


def test_allocations_report_the_floor_ratio_for_every_recorded_implementer_route() -> None:
    rows = limits.allocations(limits.load_policy(), {"implementer": 32_768}, {"planning": 40_000, "summarizer": 1_000}, (Decimal("1"),), 0, (100_000,))

    recorded = [row for row in rows if row["usable_input"] is not None]
    assert recorded and all(row["reserve_class"] == "implementer" for row in rows)
    for row in recorded:
        assert row["absent_floor_max_ratio"] == round(row["usable_input"] / (CONVERSATION_MAX_BYTES + 40_000), 4)
        assert row["absent_floor_fits"] is False  # at the byte-level bound the full floor cannot fit (D7)
        assert row["adr003_triggers"][0]["trigger_tokens"] == min(row["usable_input"] * 4 // 5, 100_000)


def test_the_quick_report_has_every_section(tmp_path) -> None:
    out = tmp_path / "limits.json"

    assert limits.main(["--quick", "--out", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{40}", report["environment"]["git_head"])
    for section in (
        "history_scaling", "concurrency", "storage_boundaries", "engine_source_boundary", "protected_growth", "protected_growth_check",
        "huge_anchor", "sanitizer_scaling", "write_plans", "completion_status", "fixed_request_material_bytes", "allocations",
    ):  # fmt: skip
        assert report[section], section
    assert all(not row["failures"] for row in report["concurrency"])


# --- Checking a proposed value set (no value is accepted here) --------------------------------------

PROPOSAL = {
    "source_max_bytes": 1_048_576,
    "record_reservation_bytes": 131_072,
    "view_source_max_bytes": 1_048_576,
    "transient_max_bytes": 524_288,
    "maintenance_input_tokens": 131_072,
    "summary_output_tokens": 8_192,
    "max_maintenance_calls": 18,
    "anchor_input_tokens": 16_384,
    "compaction_tail_input_tokens": 32_768,
    "hybrid_tail_input_tokens": 65_536,
    "implementer_output_reserve": 32_768,
    "summarizer_output_reserve": 8_192,
    "history_input_tokens_by_tier": {"ultra-cheap": 131_072, "cheap": 131_072},
    "prompt_allowance_bytes": 16_384,
}
# Measured with `fixed_request_material()` after Task 11 removed the planner's remaining-dollar line and
# bumped its prompt version (43819 before, in the older measured envelope); pinned below so the D7
# figures always come from the current measurement.
FIXED = {"planning": 43_795, "chat": 17_126, "summarizer": 989}


def test_the_pinned_fixed_material_is_the_current_measurement() -> None:
    assert limits.fixed_request_material() == FIXED


def test_the_d7_absent_engine_history_bound_at_ratio_one() -> None:
    """D7 (operator's request-capacity exception): with r=1, Agent history and prompt fit in the usable
    input less the planning material, before any further overhead; a share of the 512 KiB floor."""
    usable = 262_144 - PROPOSAL["implementer_output_reserve"]
    bound = usable - FIXED["planning"]
    assert (usable, bound, round(100 * bound / 524_288, 2)) == (229_376, 185_581, 35.4)


def check(**changes: object) -> dict:
    return limits.check_proposal({**PROPOSAL, **changes}, policy=limits.load_policy(), plan_bytes=[1_000, 30_000, 100_000], record_bytes_measured=[1_100, 31_000, 140_000], fixed=FIXED)


def test_a_consistent_proposal_has_no_violations_and_reports_its_coverage() -> None:
    result = check()

    assert result["violations"] == []
    coverage = result["coverage"]
    assert coverage["plans_within_implementer_reserve"] == {"1": 0.6667, "0.5": 0.6667, "0.25": 1.0}
    assert coverage["records_within_reservation"] == 0.6667
    # A chunk after the first carries the prior summary at its maximum in each budget, its header and a
    # separator: 131072 - 8192 - 15 - 1 tokens and 524288 - 8192 - 15 - 1 bytes at the byte-level bound.
    assert limits.chunk_capacity(PROPOSAL) == {"tokens": 122_864, "bytes": 516_080, "summary_max_bytes": 8_192}
    # At 0.2 tokens per byte a summary may be floor(8192 / 0.2) = 40960 bytes, and the byte budget can bind.
    assert limits.chunk_capacity(PROPOSAL, Decimal("0.2")) == {"tokens": 122_876, "bytes": 483_312, "summary_max_bytes": 40_960}
    # The proven whole-turn bound per estimator ratio (Codex's final corrections C2), not a packing guess.
    worst = coverage["cold_rebuild_whole_turn_worst_by_ratio"]
    assert {ratio: (row["calls"], row["binding"]) for ratio, row in worst.items()} == {
        "1": (17, "tokens"),
        "0.5": (9, "tokens"),
        "0.25": (5, "tokens"),
        "0.2": (9, "tokens or bytes"),
    }
    largest = coverage["largest_single_turn_bytes_summarizable_by_ratio"]
    assert largest["1"] == {"steady_state": 122_864, "oldest_turn_of_a_cold_rebuild": 131_072}
    assert largest["0.2"] == {"steady_state": 483_312, "oldest_turn_of_a_cold_rebuild": 524_288}
    # D7: the floor already includes the current prompt, so only the path's other material is added.
    assert coverage["absent_floor_max_ratio"] == round((262_144 - 32_768) / (524_288 + FIXED["planning"]), 4)
    assert coverage["trigger_binding_term_by_tier"] == {"ultra-cheap": "tier target", "cheap": "tier target"}
    assert set(coverage["cold_rebuild_list_price_usd"]) == {"qwen/qwen3.7-flash", "openai/gpt-6-luna"}


@pytest.mark.parametrize("ratio", ["1", "0.5", "0.3", "0.25", "0.2", "0.1", "0.3333333333333333333333333333"])
@pytest.mark.parametrize("summary_tokens", [1, 8_192, 99_999])
def test_the_derived_summary_byte_bound_is_exactly_what_the_token_cap_admits(ratio, summary_tokens) -> None:
    """floor(S / r) in exact rational arithmetic: the longest summary whose ceil(r * bytes) estimate fits
    S tokens, and one byte more does not (Fable review of the CP4 corrections, NIT-3)."""
    from fractions import Fraction

    r = Fraction(Decimal(ratio))
    bound = limits.summary_max_bytes_for(summary_tokens, Decimal(ratio))
    assert math.ceil(bound * r) <= summary_tokens < math.ceil((bound + 1) * r)


@pytest.mark.parametrize("ratio", [Decimal("1"), Decimal("0.2")], ids=["1", "0.2"])
def test_the_proven_whole_turn_worst_case_bounds_the_engines_real_call_count(ratio) -> None:
    """The engine's actual cold-rebuild calls, with the proposal's source and transient byte bounds
    applied, stay within the checker's proven whole-turn bound; turns just over half the binding chunk
    capacity take more calls than small turns (Fable CP4 MAJOR-1; Codex's final corrections C2)."""
    small = {
        **PROPOSAL,
        "maintenance_input_tokens": 16_384,
        "summary_output_tokens": 1_024,
        "summarizer_output_reserve": 1_024,
        "transient_max_bytes": 65_536,
        "view_source_max_bytes": 262_144,
    }
    bound = limits.whole_turn_worst_calls(small, ratio)["calls"]
    capacity = limits.chunk_capacity(small, ratio)
    adverse = min(int(Decimal(capacity["tokens"]) / ratio), capacity["bytes"]) // 2 + 1
    fixture = dataclasses.replace(limits.EngineFixture.from_proposal(small, ratio=ratio), history_input_tokens=400_000, tail_tokens=1, hybrid_tail_tokens=2, max_calls=1_000)

    calls = {}
    for turn in (2_048, adverse):
        state, approvals = limits._history_of_turns(turn, 262_144 - 16_384)
        outcome = limits.turn_pipeline(state, approvals, strategy="compaction", fixture=fixture)
        assert outcome["available"], outcome["reason"]
        calls[turn] = outcome["maintenance_calls"]

    assert all(count <= bound for count in calls.values()), (calls, bound)
    assert calls[adverse] > calls[2_048], calls


def test_a_steady_state_turn_reuses_its_checkpoint_with_at_most_one_call() -> None:
    import tracemalloc

    proposal = {**PROPOSAL, "source_max_bytes": 600_000, "record_reservation_bytes": 100_000}

    tracemalloc.start()
    try:
        by_ratio = limits.proposed_policy_rows(proposal, ratios=(Decimal("1"), Decimal("0.2")))
    finally:
        tracemalloc.stop()

    assert set(by_ratio) == {"1", "0.2"}
    # At the byte-level bound this cold rebuild needs several calls; at 0.2 tokens per byte the same
    # history fits one 524288-byte maintenance input, which the planner now packs within its byte bound.
    assert by_ratio["1"]["cold_rebuild_8kib_turns"]["maintenance_calls"] > 1
    for ratio, rows in by_ratio.items():
        assert rows["cold_rebuild_8kib_turns"]["available"] and rows["cold_rebuild_8kib_turns"]["maintenance_calls"] >= 1, ratio
        assert rows["steady_state_turn"]["available"] and rows["steady_state_turn"]["maintenance_calls"] <= 1, ratio
        worst = rows["cold_rebuild_worst_whole_turns"]
        assert worst["available"] and worst["maintenance_calls"] <= proposal["max_maintenance_calls"], ratio


@pytest.mark.parametrize(
    ("changes", "violation"),
    [
        ({"source_max_bytes": 524_288}, "attached source limit must exceed the engine-absent floor"),
        ({"record_reservation_bytes": 1_048_576}, "record reservation must be below the source limit"),
        ({"view_source_max_bytes": 1_048_575}, "the engine's source limit must admit every history storage admits"),
        ({"hybrid_tail_input_tokens": 32_768}, "hybrid's exact tail must exceed compaction's"),
        ({"summary_output_tokens": 8_193}, "a summary must fit the summarizer's output reserve"),
        ({"transient_max_bytes": 524_287}, "the transient byte bound must not bind before the token bound"),
        ({"max_maintenance_calls": 16}, "the call allowance cannot rebuild the whole source in its whole-turn worst case at ratio 1"),
        ({"summary_output_tokens": 110_000, "summarizer_output_reserve": 110_000}, "the derived summary byte bound at ratio 0.2 must be below the transient bound"),
        ({"implementer_output_reserve": 0}, "every output reserve must be positive"),
        ({"history_input_tokens_by_tier": {"ultra-cheap": 131_072, "cheap": 80_000}}, "hybrid's anchor, tail and summary must fit the smallest history target"),
        ({"history_input_tokens_by_tier": {"cheap": 40_000}}, "compaction's tail and summary must fit the smallest history target"),
        ({"history_input_tokens_by_tier": {"cheap": 131_072, "review": 131_072}}, "history target for review has no active implementer route"),
        ({"implementer_output_reserve": 128_001}, "implementer reserve exceeds openai/gpt-6-luna's max output"),
        ({"summarizer_output_reserve": 65_537, "summary_output_tokens": 65_537}, "summarizer reserve exceeds qwen/qwen3.7-flash's max output"),
        ({"maintenance_input_tokens": 260_000, "transient_max_bytes": 1_040_000}, "a maintenance call does not fit qwen/qwen3.7-flash"),
        ({"history_input_tokens_by_tier": {"cheap": 200_000}}, "cheap history target leaves no room for planning material"),
    ],
)
def test_each_inconsistent_value_is_named(changes, violation) -> None:
    assert any(message.startswith(violation) for message in check(**changes)["violations"]), check(**changes)["violations"]


def test_a_proposal_missing_a_value_is_refused_whole() -> None:
    proposal = {key: value for key, value in PROPOSAL.items() if key != "max_maintenance_calls"}

    result = limits.check_proposal(proposal, policy=limits.load_policy(), plan_bytes=[1], record_bytes_measured=[1], fixed=FIXED)

    assert result == {"violations": ["missing max_maintenance_calls"], "coverage": {}}
