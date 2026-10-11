"""Plan 12.2 Task 13 (Stage C): the executable claim-to-case schedule (Codex scope agreement, 2026-10-11,
section 5 and S1-S3; Codex completion review R3 and R4).

Three figures are kept apart. The conservative complete-case bound sizes an envelope: each case's calls are
bounded by host limits taken from source (planning turns, the turn-wide maintenance allowance, the
scenario's zero-call and cancellation turns, sliding's no-maintenance view), and each call at the most its
request can reserve (the Gateway refuses more input before any attempt). Measured allocations run the real
adapter, engine and attached composition on fixed fake replies of several sizes: they show how replies move
later packing and maintenance, and are never a bound. Expected spend is informational only.

The runbook is executable with the installed acpx 0.12.0: a pinned agent wrapper, a one-shot `exec` for the
denied Agent case, an explicit fresh named session whose mode acpx replays on the prompt's own fresh
runtime session, an explicit close, and a custody check after every launch, all on one ledger and window.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from context_engine.summary import build_summary_prompt
from optimus.acp import stage_c as host
from optimus.acp.conversation import CONVERSATION_MAX_BYTES
from optimus.acp.launch_policy import DEFAULT_MAX_PLANNING_TURNS
from optimus_model_policy import stage_c
from optimus_model_policy import test_profiles as profiles
from tools import plan12_stage_c_schedule as tool

TASK13_CLAIMS = {
    "chat-non-mutation", "agent-exact-artifact-approval", "key-isolation", "attached-picker", "absent-picker-and-persisted-default",
    "sliding-warning", "meter-versus-storage-notices", "request-capacity-refusal", "storage-refusal", "attached-history-over-512kib",
    "repeated-engine-unavailability", "healthy-recovery", "cancellation-between-maintenance-calls", "checkpoint-reuse", "attached-small-session",
}  # fmt: skip
PRICES = (Decimal("0.50"), Decimal("2.50"))


@pytest.fixture(scope="module")
def schedule(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("schedule-paths")
    paths = tool.RunbookPaths(agent_exe=root / "venv" / "optimus-agent.exe", workspace=root / "workspace", evidence=root / "evidence")
    return tool.build_schedule(summary_bytes=8_192, reply_sizes=(3, 32_768), paths=paths)


def _reserve(input_tokens: int, output_cap: int) -> Decimal:
    return stage_c.reservation_usd(input_tokens=input_tokens, output_tokens=output_cap, input_usd_per_million=PRICES[0], output_usd_per_million=PRICES[1])


def test_every_applicable_claim_maps_to_a_case_with_steps_observations_and_artifacts(schedule) -> None:
    assert set(schedule["claims"]) == TASK13_CLAIMS
    for row in schedule["cases"]:
        assert row["steps"] and row["expected"] and row["artifacts"] and row["claims"] and row["unrun_if"], row["case"]
    acpx_claims = {claim for row in schedule["cases"] if row["client"] == "acpx" for claim in row["claims"]}
    assert {"chat-non-mutation", "agent-exact-artifact-approval", "key-isolation"} <= acpx_claims


# --- The conservative complete-case bound ----------------------------------------------------------------------


def test_each_call_is_bounded_by_the_most_its_request_can_reserve(schedule) -> None:
    limits = host.stage_c_limits(profiles.compose_test_profile_snapshot("attached"), tool.HAIKU)
    widest_summary = build_summary_prompt("x" * limits.limits.maintenance_input_tokens)  # one token per byte under the profile
    per_call = schedule["bound"]["per_call"]

    assert (per_call["answer"]["input_tokens"], per_call["answer"]["output_cap"]) == (limits.usable_input_tokens, 32_768) == (229_376, 32_768)
    assert (per_call["summary"]["input_tokens"], per_call["summary"]["output_cap"]) == (limits.estimate_request(widest_summary), 8_192)
    for kind in ("answer", "summary"):  # rounded up to the micro-dollar, so still a bound
        exact = _reserve(per_call[kind]["input_tokens"], per_call[kind]["output_cap"])
        assert Decimal(per_call[kind]["reserve_usd"]) == exact.quantize(Decimal("0.000001"), rounding="ROUND_CEILING") >= exact


def test_each_cases_calls_are_bounded_by_the_host_limits_in_source(schedule) -> None:
    scenario = stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["schedule"]
    allowance = host.MAX_MAINTENANCE_CALLS
    bounds = {row["case"]: (row["bound"]["answer_calls"], row["bound"]["summary_calls"]) for row in schedule["cases"]}

    assert bounds["A1"] == bounds["A7"] == (1, 0)
    assert bounds["A2"] == bounds["A6"] == (DEFAULT_MAX_PLANNING_TURNS, 0) == (3, 0)
    assert bounds["A3"] == bounds["A4"] == bounds["A5"] == (0, 0)  # refused before any attempt, or no prompt
    for live, case, strategy, _prompt in tool.ATTACHED_TURNS:
        key = f"{case}.{live}"
        if live in scenario["engine_unavailable_turns"]:
            assert bounds[key] == (0, 0), key
        elif live == scenario["cancel_pause_turn"]:
            assert bounds[key] == (1, scenario["cancel_pause_before_call"] - 1), key  # paused before the turn's 2nd call
        elif strategy == "sliding_window":
            assert bounds[key] == (1, 0), key  # a sliding view makes no maintenance call
        else:
            assert bounds[key] == (1, allowance), key
    assert bounds["B2"] == (1, 0)  # the unseeded session's first turn: its prompt alone, far under every allowance


def test_the_bound_totals_count_one_billed_attempt_and_two_physical_attempts_per_call(schedule) -> None:
    bound, per_call = schedule["bound"], schedule["bound"]["per_call"]
    answer, summary = Decimal(per_call["answer"]["reserve_usd"]), Decimal(per_call["summary"]["reserve_usd"])
    total, calls = Decimal(0), 0
    for row in schedule["cases"]:
        b = row["bound"]
        case_total = b["answer_calls"] * answer + b["summary_calls"] * summary
        assert Decimal(b["billed_attempt_bound_usd"]) == case_total.quantize(Decimal("0.000001"), rounding="ROUND_CEILING")
        assert b["physical_attempts_max"] == 2 * (b["answer_calls"] + b["summary_calls"])
        total += case_total
        calls += b["answer_calls"] + b["summary_calls"]
    totals = bound["totals"]
    assert totals["calls"] == calls and totals["physical_attempts_planned_max"] == [calls, 2 * calls]
    assert Decimal(totals["billed_attempt_bound_usd"]) == total.quantize(Decimal("0.000001"), rounding="ROUND_CEILING")
    assert totals["fits_usd"] is (total <= Decimal("0.50")) and totals["fits_attempts_max"] is (2 * calls <= 24)
    assert Decimal(totals["usd_shortfall"]) == max(Decimal(0), Decimal(totals["billed_attempt_bound_usd"]) - Decimal("0.50"))
    assert bound["assumptions"] and all(isinstance(text, str) and text for text in bound["assumptions"])


# --- Measured allocations on fixed fake replies -----------------------------------------------------------------


def test_the_measured_paths_are_the_real_packing_of_the_pinned_seed(schedule) -> None:
    [short, long] = schedule["measured"]["paths"]
    assert (short["reply_bytes"], long["reply_bytes"]) == (3, 32_768) and "not a bound" in schedule["measured"]["basis"]
    turns = {turn["live"]: turn for turn in short["turns"]}
    assert len(turns[1]["summary_inputs"]) >= 2 and len(turns[1]["answer_envelopes"]) == 1  # a cold compaction, then the answer
    assert [(turns[n]["summary_inputs"], turns[n]["answer_envelopes"]) for n in (4, 5)] == [([], []), ([], [])]  # zero calls
    assert (turns[7]["stop"], len(turns[7]["summary_inputs"]), turns[7]["answer_envelopes"]) == ("cancelled", 1, [])
    assert schedule["source"]["seed"]["records_bytes"] > CONVERSATION_MAX_BYTES


def test_longer_replies_move_later_packing_and_maintenance(schedule) -> None:
    """Replies become history (Codex completion review R3): on the longer-reply path the steady-state turn no
    longer just reuses the checkpoint, the path makes more calls, and the views change in no fixed direction,
    which is why a measured path is never a bound."""
    short, long = ({turn["live"]: turn for turn in path["turns"]} for path in schedule["measured"]["paths"])
    assert short[2]["summary_inputs"] == [] and len(long[2]["summary_inputs"]) >= 1
    assert long[2]["answer_envelopes"] != short[2]["answer_envelopes"]
    assert sum(len(t["summary_inputs"]) for t in long.values()) > sum(len(t["summary_inputs"]) for t in short.values())
    totals = [path["totals"]["calls"] for path in schedule["measured"]["paths"]]
    assert totals[1] > totals[0]


def test_a2s_history_is_a1s_rendered_record_not_an_allowance(schedule) -> None:
    short, long = schedule["measured"]["paths"]
    a2 = {path["reply_bytes"]: path["calls_by_case"]["A2"][0]["input_tokens"] for path in (short, long)}
    assert a2[32_768] - a2[3] == 32_768 - 3  # exactly A1's longer reply, one token per byte


def test_the_bound_dominates_every_measured_path(schedule) -> None:
    bound = schedule["bound"]
    for path in schedule["measured"]["paths"]:
        assert path["totals"]["calls"] <= bound["totals"]["calls"]
        assert Decimal(path["totals"]["billed_attempt_allocation_usd"]) <= Decimal(bound["totals"]["billed_attempt_bound_usd"])
        for case, calls in path["calls_by_case"].items():
            row = next(r for r in schedule["cases"] if r["case"] == case)["bound"]
            kinds = [c["kind"] for c in calls]
            assert kinds.count("summary") <= row["summary_calls"] and len(kinds) - kinds.count("summary") <= row["answer_calls"], case
            per_call = bound["per_call"]
            assert all(c["input_tokens"] <= per_call["summary" if c["kind"] == "summary" else "answer"]["input_tokens"] for c in calls), case


# --- The executable runbook -----------------------------------------------------------------------------------


def _commands(schedule) -> list[str]:
    return [command for step in schedule["runbook"]["steps"] for command in step["commands"]]


def test_the_agent_wrapper_is_pinned(schedule) -> None:
    wrapper = schedule["runbook"]["agent_wrapper"]
    paths = schedule["runbook"]["paths"]
    assert wrapper["content"] == (
        "@echo off\r\n"
        f'"{paths["agent_exe"]}" --workspace-root "{paths["workspace"]}" --plan12-test-profile qualification --plan12-stage-c\r\n'
    )
    import hashlib

    assert wrapper["sha256"] == hashlib.sha256(wrapper["content"].encode("ascii")).hexdigest()


def test_the_acpx_cases_never_rely_on_a_saved_or_recovered_session(schedule) -> None:
    commands = [c for c in _commands(schedule) if c.startswith("acpx ")]
    wrapper = schedule["runbook"]["agent_wrapper"]["path"]
    assert all(f'--agent "{wrapper}"' in c for c in commands)
    exec_steps = [c for c in commands if " exec " in c]
    assert len(exec_steps) == 1 and "--deny-all" in exec_steps[0]  # A6: one-shot, its own fresh session
    named = [c for c in commands if "stage-c-a7" in c]
    kinds = [next(k for k in ("sessions new", "set-mode chat", "prompt", "sessions close") if k in c) for c in named]
    assert kinds == ["sessions new", "set-mode chat", "prompt", "sessions close"]  # fresh, mode saved, replayed, closed
    assert "--ttl 0" in named[2] and "--name stage-c-a7" in named[0]
    assert all("stage-c-a7" in c for c in commands if " prompt " in c or " set-mode " in c)  # never an unnamed saved session


def test_every_launch_is_followed_by_a_custody_check_on_the_same_ledger(schedule) -> None:
    steps = schedule["runbook"]["steps"]
    checks = [n for n, step in enumerate(steps) if step["kind"] == "custody-check"]
    launches = [n for n, step in enumerate(steps) if step["kind"] in {"zed-launch", "acpx-launch"}]
    assert checks[0] < launches[0]  # the prior qualification host is stopped and checked first
    for n in launches:
        assert any(c > n for c in checks), steps[n]["title"]
        next_launch = min((m for m in launches if m > n), default=len(steps))
        assert any(n < c < next_launch for c in checks), f"no custody check between {steps[n]['title']} and the next launch"
    previous = None
    for n in checks:
        command = steps[n]["commands"][0]
        assert command.startswith("python tools/plan12_stage_c_transition_check.py") and "--out" in command
        if previous is not None:
            assert f"--previous {previous}" in command  # the same ledger, window and non-decreasing totals
        previous = steps[n]["evidence"][0]
    approvals = [step for step in steps if step["kind"] == "approval"]
    profiles_approved = [s["commands"][0].split("--plan12-test-profile ")[1].split()[0] for s in approvals]
    assert profiles_approved == ["qualification", "attached"] and all("--plan12-stage-c" in s["commands"][0] for s in approvals)
    evidence_root = schedule["runbook"]["paths"]["evidence"]
    assert all(path.startswith(evidence_root) for step in steps for path in step["evidence"])


def test_the_tool_writes_a_new_folder_and_never_reuses_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schedule) -> None:
    monkeypatch.setattr(tool, "build_schedule", lambda **_kwargs: schedule)
    out = tmp_path / "schedule"
    assert tool.main(["--out", str(out)]) == 0
    written = json.loads((out / "stage-c-schedule.json").read_text(encoding="utf-8"))
    assert written["bound"]["totals"] == json.loads(json.dumps(schedule["bound"]["totals"], default=str))
    assert (out / "capacity-prompt.txt").stat().st_size == schedule["prompt_files"]["capacity-prompt.txt"]["bytes"]
    assert (out / "run-optimus-agent.cmd").read_bytes() == schedule["runbook"]["agent_wrapper"]["content"].encode("ascii")
    assert (out / "workspace" / "README.md").is_file() and (out / "stage-c-schedule.md").read_text(encoding="utf-8").startswith("# Stage C executable schedule")
    with pytest.raises(SystemExit):
        tool.main(["--out", str(out)])


def test_the_paste_files_hit_the_refusal_they_are_named_for(schedule) -> None:
    files = schedule["prompt_files"]
    usable = 262_144 - 32_768
    assert usable < files["capacity-prompt.txt"]["bytes"] < CONVERSATION_MAX_BYTES  # over request capacity, inside storage
    assert files["capacity-prompt.txt"]["bytes"] * 5 >= CONVERSATION_MAX_BYTES * 4  # also crosses the 80% storage warning
    assert files["storage-prompt.txt"]["bytes"] > CONVERSATION_MAX_BYTES
