"""Plan 12.2 Task 13 (Stage C): the executable claim-to-case schedule (Codex scope agreement, 2026-10-11,
section 5 and S1-S3).

The schedule runs the attached cases offline through the real adapter, engine and attached composition, so
its maintenance calls and history views are the real packing of the pinned seed. Every applicable Task 13
claim maps to a case with steps, expected observations and artifacts, acpx steps included. Each call is
priced at its full reservation with one potentially billed attempt per call and both physical attempts
counted; the totals are the sum of the cases and say whether the envelope fits, without hiding a shortfall.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.acp.conversation import CONVERSATION_MAX_BYTES
from optimus_model_policy import stage_c
from tools import plan12_stage_c_schedule as tool

TASK13_CLAIMS = {
    "chat-non-mutation", "agent-exact-artifact-approval", "key-isolation", "attached-picker", "absent-picker-and-persisted-default",
    "sliding-warning", "meter-versus-storage-notices", "request-capacity-refusal", "storage-refusal", "attached-history-over-512kib",
    "repeated-engine-unavailability", "healthy-recovery", "cancellation-between-maintenance-calls", "checkpoint-reuse", "attached-small-session",
}  # fmt: skip


@pytest.fixture(scope="module")
def schedule() -> dict:
    return tool.build_schedule(8_192)


def test_every_applicable_claim_maps_to_a_case_with_steps_observations_and_artifacts(schedule) -> None:
    assert set(schedule["claims"]) == TASK13_CLAIMS
    for row in schedule["cases"]:
        assert row["steps"] and row["expected"] and row["artifacts"] and row["claims"] and row["unrun_if"], row["case"]
    clients = {row["client"] for row in schedule["cases"]}
    assert clients == {"zed", "acpx"}
    acpx_claims = {claim for row in schedule["cases"] if row["client"] == "acpx" for claim in row["claims"]}
    assert {"chat-non-mutation", "agent-exact-artifact-approval", "key-isolation"} <= acpx_claims


def test_the_attached_cases_are_the_real_packing_of_the_pinned_seed(schedule) -> None:
    turns = {turn["live"]: turn for turn in schedule["attached_run"]["turns"]}
    assert len(turns[1]["summary_inputs"]) >= 2 and len(turns[1]["answer_envelopes"]) == 1  # a cold compaction, then the answer
    assert turns[2]["summary_inputs"] == []  # the steady-state turn reuses the checkpoint
    assert [(turns[n]["summary_inputs"], turns[n]["answer_envelopes"]) for n in (4, 5)] == [([], []), ([], [])]  # zero calls
    assert len(turns[6]["answer_envelopes"]) == 1  # healthy recovery
    assert (turns[7]["stop"], len(turns[7]["summary_inputs"]), turns[7]["answer_envelopes"]) == ("cancelled", 1, [])
    assert all(size <= 131_072 * 4 for turn in turns.values() for size in turn["summary_inputs"])
    assert schedule["source"]["seed"]["records_bytes"] > CONVERSATION_MAX_BYTES


def test_each_call_is_priced_once_for_dollars_and_twice_for_attempts(schedule) -> None:
    total, calls = Decimal(0), 0
    for row in schedule["cases"]:
        reserves = [Decimal(call["reserve_usd"]) for call in row["calls"]]
        assert Decimal(row["billed_attempt_ceiling_usd"]) >= sum(reserves, Decimal(0)) - Decimal("0.000001") * len(reserves)
        assert row["physical_attempts_planned_max"] == [len(row["calls"]), 2 * len(row["calls"])]
        for call in row["calls"]:
            expected = stage_c.reservation_usd(input_tokens=call["input_tokens"], output_tokens=call["output_cap"], input_usd_per_million=Decimal("0.50"), output_usd_per_million=Decimal("2.50"))
            assert Decimal(call["reserve_usd"]) - expected < Decimal("0.000001")
            assert call["output_cap"] == (8_192 if call["kind"] == "summary" else 32_768)
        total += sum(reserves, Decimal(0))
        calls += len(row["calls"])
    totals = schedule["totals"]
    assert totals["calls"] == calls and totals["physical_attempts_planned_max"] == [calls, 2 * calls]
    assert abs(Decimal(totals["billed_attempt_ceiling_usd"]) - total) < Decimal("0.00002")
    assert totals["fits_usd"] == (Decimal(totals["billed_attempt_ceiling_usd"]) <= Decimal("0.50"))
    assert Decimal(totals["usd_shortfall"]) == max(Decimal(0), Decimal(totals["billed_attempt_ceiling_usd"]) - Decimal("0.50"))
    assert totals["fits_attempts_planned"] == (calls <= 24) and totals["fits_attempts_max"] == (2 * calls <= 24)


def test_the_paste_files_hit_the_refusal_they_are_named_for(schedule) -> None:
    files = schedule["prompt_files"]
    usable = 262_144 - 32_768
    assert usable < files["capacity-prompt.txt"]["bytes"] < CONVERSATION_MAX_BYTES  # over request capacity, inside storage
    assert files["capacity-prompt.txt"]["bytes"] * 5 >= CONVERSATION_MAX_BYTES * 4  # also crosses the 80% storage warning
    assert files["storage-prompt.txt"]["bytes"] > CONVERSATION_MAX_BYTES


def test_the_tool_writes_a_new_folder_and_never_reuses_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schedule) -> None:
    monkeypatch.setattr(tool, "build_schedule", lambda _summary_bytes: schedule)
    out = tmp_path / "schedule"
    assert tool.main(["--out", str(out)]) == 0
    written = json.loads((out / "stage-c-schedule.json").read_text(encoding="utf-8"))
    assert written["totals"] == json.loads(json.dumps(schedule["totals"], default=str))
    assert (out / "capacity-prompt.txt").stat().st_size == schedule["prompt_files"]["capacity-prompt.txt"]["bytes"]
    assert (out / "workspace" / "README.md").is_file() and (out / "stage-c-schedule.md").read_text(encoding="utf-8").startswith("# Stage C executable schedule")
    with pytest.raises(SystemExit):
        tool.main(["--out", str(out)])
