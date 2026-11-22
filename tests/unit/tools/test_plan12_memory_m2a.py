"""Plan 12.13 Task 1: the M2a evaluator's loader, boundaries, schedule runs and partition choice, on the real planning loop and real files.

The real-index check needs the released Redis and is not run here.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from optimus.agent import planning_loop as pl
from tools.plan12_memory import m2a_evaluate as ev

REPOSITORY = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def frozen() -> ev.Frozen:
    return ev.load_frozen(REPOSITORY)


def _schedule(frozen: ev.Frozen, schedule_id: str) -> dict:
    return next(item for item in frozen.cases["split_schedules"]["schedules"] if item["id"] == schedule_id)


def test_a_changed_frozen_file_is_refused(tmp_path: Path) -> None:
    copy = tmp_path / "repo"
    shutil.copytree(REPOSITORY / ev.REPORTS, copy / ev.REPORTS)
    ev.load_frozen(copy)  # unchanged copy loads
    cases = copy / ev.REPORTS / "cases.json"
    cases.write_bytes(cases.read_bytes().replace(b'"S01"', b'"S99"', 1))
    with pytest.raises(ev.FrozenInputChanged, match="cases.json"):
        ev.load_frozen(copy)


def test_calibration_refuses_held_out(frozen: ev.Frozen) -> None:
    with pytest.raises(ev.HeldOutRefused):
        ev.selected(frozen.cases["split_schedules"]["schedules"], phase="calibration", splits=("train", "held_out"))
    chosen = ev.selected(frozen.cases["split_schedules"]["schedules"], phase="calibration", splits=("train", "development"))
    assert len(chosen) == 18 and {item["split"] for item in chosen} == {"train", "development"}


def test_every_boundary_solves_exactly_under_the_real_serializers(frozen: ev.Frozen) -> None:
    boundaries = [item for item in frozen.cases["split_schedules"]["schedules"] if "boundary" in item]
    assert len(boundaries) == 12
    for item in boundaries:
        resolved = ev.resolve(item)
        totals = ev.serialized_totals(resolved)
        target = item["boundary"]["target"]
        expected = target if isinstance(target, list) else [target]
        names = (
            ["observations", "current_reads"]
            if isinstance(target, list)
            else (["observations"] if "observations" in item["boundary"]["total"] else ["current_reads"])
        )
        assert [totals[name] for name in names] == expected, item["id"]
        assert all(read["range_bytes"] is not None for round_ in resolved["rounds"] for read in round_["reads"])


def test_a_one_over_read_stops_at_the_baseline_fits_a_wider_read_limit_and_restores_the_limits(frozen: ev.Frozen, tmp_path: Path) -> None:
    resolved = ev.resolve(_schedule(frozen, "S11"))  # current reads 12289
    baseline = ev.run_schedule(resolved, (4, 12), tmp_path / "a")
    wider = ev.run_schedule(resolved, (2, 14), tmp_path / "b")
    assert (baseline["completed"], baseline["stop"]) == (False, "PLANNING_READ_BUDGET_EXHAUSTED")
    assert (wider["completed"], wider["stop"], wider["evidence_complete"]) == (True, None, True)
    assert baseline["cost_usd"] == wider["cost_usd"] == "0"
    assert (pl.PLANNING_OBSERVATION_MAX_BYTES, pl.PLANNING_NEW_READ_MAX_BYTES) == (4096, 12288)


def test_an_exact_read_boundary_completes_with_every_record(frozen: ev.Frozen, tmp_path: Path) -> None:
    exact = ev.run_schedule(ev.resolve(_schedule(frozen, "S10")), (4, 12), tmp_path / "a")  # current reads 12288
    assert (exact["completed"], exact["evidence_complete"]) == (True, True)


def test_an_observation_over_the_limit_never_counts_as_completed_even_when_a_plan_follows(frozen: ev.Frozen, tmp_path: Path) -> None:
    cumulative = ev.run_schedule(ev.resolve(_schedule(frozen, "S03")), (4, 12), tmp_path / "a")  # observations 4097 across two turns
    assert (cumulative["completed"], cumulative["stop"]) == (False, "PLANNING_OBSERVATION_BUDGET_EXHAUSTED")
    # S19's first turn alone carries an 8 KiB observation: the loop asks for a shorter note, the script moves on, and a plan is accepted
    # without that turn's evidence. A plan is not a completion.
    oversized = ev.run_schedule(ev.resolve(_schedule(frozen, "S19")), (4, 12), tmp_path / "b")
    assert (oversized["planned"], oversized["stop"], oversized["parse_failures"]) == (True, None, ["OBSERVATION_TOO_LARGE"])
    assert (oversized["evidence_complete"], oversized["completed"]) == (False, False)


def _rows(**outcomes: dict[str, bool]) -> dict[str, dict[str, dict]]:
    return {
        partition: {sid: {"completed": done, "stop": None if done else "X", "weakened": False} for sid, done in rows.items()}
        for partition, rows in outcomes.items()
    }


def test_partition_choice_needs_no_baseline_loss_then_most_completions_then_fewer_stops_then_nearest() -> None:
    results = _rows(
        **{
            "4/12": {"a": True, "b": False, "c": False},
            "2/14": {"a": False, "b": True, "c": True},
            "6/10": {"a": True, "b": True, "c": False},
            "8/8": {"a": True, "b": True, "c": False},
        }
    )
    choice = ev.choose_partition(results)
    assert choice["chosen"] == "6/10"  # 2/14 loses baseline-success a; 6/10 and 8/8 tie, 6/10 is nearer 4/12
    assert choice["rejected"]["2/14"] == "loses baseline-success schedules: a"
    none = ev.choose_partition(_rows(**{"4/12": {"a": True}, "2/14": {"a": False}, "6/10": {"a": True}, "8/8": {"a": True}}))
    assert none["chosen"] is None  # no partition completes more than the baseline
    weakened = _rows(**{"4/12": {"a": False}, "2/14": {"a": False}, "6/10": {"a": True}, "8/8": {"a": False}})
    weakened["6/10"]["a"]["weakened"] = True
    assert ev.choose_partition(weakened)["chosen"] is None


def test_the_ambiguity_baseline_on_real_files(frozen: ev.Frozen, tmp_path: Path) -> None:
    rows = {
        case["id"]: ev.ambiguity_baseline(frozen, case, tmp_path / case["id"])
        for case in frozen.cases["ambiguity"]["cases"]
        if case["id"] in {"A01", "A05", "A06", "A09", "A12"}
    }
    assert rows["A01"]["outcome"] == "ambiguous_stop"
    assert rows["A01"]["candidates"] == ["src/agent/config.py", "src/gateway/config.py", "tests/fixtures/config.py"]  # path order
    assert rows["A01"]["path_only_rank"] == 2
    assert "secrets/utils.py" not in rows["A05"]["candidates"] and rows["A05"]["outcome"] == "ambiguous_stop"
    assert (rows["A06"]["outcome"], rows["A06"]["resolved"]) == ("resolved", "src/a/helpers.py")
    assert rows["A09"]["retry"] == {"outcome": "resolved", "resolved": "src/optimus_gateway/models.py"}
    assert rows["A12"]["retry"]["outcome"] == "not_found" and rows["A12"]["retry"]["resolved"] is None
    assert all(row["wrong_target_selections"] == 0 for row in rows.values())


def test_ambiguity_scores_count_decidable_cases_only() -> None:
    rows = [
        {"split": "train", "decidable": True, "path_only_rank": 1, "outcome": "ambiguous_stop", "wrong_target_selections": 0},
        {"split": "train", "decidable": True, "path_only_rank": 3, "outcome": "ambiguous_stop", "wrong_target_selections": 0},
        {"split": "train", "decidable": False, "path_only_rank": None, "outcome": "ambiguous_stop", "wrong_target_selections": 0},
        {
            "split": "train",
            "decidable": True,
            "path_only_rank": None,
            "outcome": "resolved",
            "resolved_correct": True,
            "wrong_target_selections": 0,
        },
    ]
    score = ev.score_ambiguity(rows)["train"]
    assert (score["decidable"], score["undecidable"], score["ranked_cases"]) == (3, 1, 2)
    assert score["path_only_top_one"] == 0.5 and score["path_only_reciprocal_rank"] == pytest.approx((1 + 1 / 3) / 2)
    assert score["oracle_regret"] == pytest.approx((0.25 + 0.25 + 0) / 3) and score["wrong_target_selections"] == 0


def test_the_run_config_names_only_released_resources() -> None:
    config = json.loads((REPOSITORY / ev.REPORTS / "run-config.json").read_text(encoding="utf-8"))
    assert config["container"] == "p1213-index-test-redis" and config["volume"] == "p1213-index-test-data" and config["port"] == 6397
    assert config["release_prefix"] == "p1213-"


def test_no_schedule_reads_a_range_twice(frozen: ev.Frozen) -> None:
    for item in frozen.cases["split_schedules"]["schedules"]:  # cases v2: v1 repeated round 1 in round 2, which the loop stops as a repeat
        ranges = [
            (read["path"], read["start_byte"], read["range_bytes"]) for round_ in ev.resolve(item)["rounds"] for read in round_["reads"]
        ]
        spans = sorted((path, start, start + size) for path, start, size in ranges)
        assert all(not (a[0] == b[0] and b[1] < a[2]) for a, b in zip(spans, spans[1:], strict=False)), item["id"]
