"""Plan 12.13 Tasks 1 and 3: the M2a evaluator's loader, boundaries, schedule runs and partition choice, on the real planning loop and real files.

The real-index check needs the released Redis and is not run here.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from optimus.agent import planning_loop as pl
from optimus.guardrails.file_policy import FilePolicy, FilePurpose
from tools.plan12_memory import m2a_evaluate as ev

REPOSITORY = Path(__file__).resolve().parents[3]
# the production limits, read before any run substitutes its own
PRODUCTION = (pl.PLANNING_OBSERVATION_MAX_BYTES, pl.PLANNING_NEW_READ_MAX_BYTES)


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
    assert (pl.PLANNING_OBSERVATION_MAX_BYTES, pl.PLANNING_NEW_READ_MAX_BYTES) == PRODUCTION


def test_an_exact_read_boundary_completes_with_every_record(frozen: ev.Frozen, tmp_path: Path) -> None:
    exact = ev.run_schedule(ev.resolve(_schedule(frozen, "S10")), (4, 12), tmp_path / "a")  # current reads 12288
    assert (exact["completed"], exact["evidence_complete"], exact["route_fit"]["status"]) == (True, True, "passed")
    assert exact["route_fit"]["requests_fitted"] == exact["requests"] and exact["route_fit"]["repacks"] == 0


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


def _records(resolved: dict, work: Path) -> tuple[str, list[str]]:
    """The final request's evidence as the real serializers write it, and the separate records."""
    whole = {path: (work / path).read_bytes() for path in {read["path"] for round_ in resolved["rounds"] for read in round_["reads"]}}
    records = []
    for number, round_ in enumerate(resolved["rounds"]):
        for read in round_["reads"]:
            start, end = read["start_byte"], read["start_byte"] + read["range_bytes"]
            sha = hashlib.sha256(whole[read["path"]]).hexdigest()
            records.append(
                pl._serialize_planning_observation(
                    pl.PlanningObservation(
                        path=read["path"],
                        start_byte=start,
                        end_byte=end,
                        source_sha256=sha,
                        observation_text="o" * round_["observation_text_bytes"],
                    )
                )
            )
            if number == len(resolved["rounds"]) - 1:
                text = whole[read["path"]][start:end].decode("utf-8")
                records.append(
                    pl._serialize_planning_read_evidence(
                        pl.PlanningReadEvidence(
                            path=read["path"], start_byte=start, end_byte=end, source_sha256=sha, line_endings="lf", range_text=text
                        )
                    )
                )
    return "".join(records), records


def test_the_evidence_check_needs_every_record_whole_and_counts_alone_are_not_enough(frozen: ev.Frozen, tmp_path: Path) -> None:
    resolved = ev.resolve(_schedule(frozen, "S12"))  # two rounds of three and four reads
    ev.write_workspace(resolved, tmp_path)
    final, records = _records(resolved, tmp_path)
    assert ev.check_evidence(final, resolved, tmp_path) == []
    read_block = next(record for record in records if record.startswith("READ_BLOCK"))
    end = read_block.rindex("\nEND_READ_BLOCK")
    corruptions = {
        "truncated payload": final.replace(read_block, read_block[: end - 1] + read_block[end:], 1),
        "wrong range": final.replace("bytes=0:1800", "bytes=0:1799", 1),
        "duplicate replaces another": final.replace(records[1], records[0], 1),
        "stale hash": final.replace(
            hashlib.sha256((tmp_path / resolved["rounds"][0]["reads"][0]["path"]).read_bytes()).hexdigest(), "0" * 64, 1
        ),
    }
    for name, text in corruptions.items():
        assert text != final and text.count("OBS_RECORD path=") == final.count("OBS_RECORD path="), name
        assert ev.check_evidence(text, resolved, tmp_path), name


def test_an_equal_completion_count_with_fewer_budget_stops_is_chosen() -> None:
    def rows(done: dict[str, bool], budget: set[str]) -> dict[str, dict]:
        return {sid: {"completed": ok, "stop": None, "budget_stop": sid in budget, "weakened": False} for sid, ok in done.items()}

    results = {
        "4/12": rows({"a": True, "b": False}, {"b"}),
        "6/10": rows({"a": True, "b": False}, set()),
        "2/14": rows({"a": True, "b": False}, {"b"}),
        "8/8": rows({"a": True, "b": False}, {"b"}),
    }
    choice = ev.choose_partition(results)
    assert choice["chosen"] == "6/10"  # same completions as 4/12, one budget stop fewer (b stops for another reason)
    assert choice["rejected"]["2/14"].startswith("ranks below 6/10")
    tied = {label: rows({"a": True}, set()) for label in ("4/12", "6/10", "2/14", "8/8")}
    assert ev.choose_partition(tied)["chosen"] is None  # a full tie keeps the baseline, nearest to itself


def test_files_added_after_indexing_keep_the_frozen_ignore_rules(frozen: ev.Frozen, tmp_path: Path) -> None:
    files = next(item["files"] for item in frozen.cases["ambiguity"]["workspaces"] if item["family"] == "A-F2")
    later = {entry["path"] for entry in files if entry.get("metadata") == "none" and "denied" not in entry}
    ev.materialize(files, tmp_path, skip=later)
    ignore = (tmp_path / ".gitignore").read_bytes()
    ev.after_indexing(files, tmp_path, later)
    assert (tmp_path / ".gitignore").read_bytes() == ignore and (tmp_path / "tools/utils.py").is_file()
    policy = FilePolicy(tmp_path)
    assert not policy.decide("secrets/utils.py", purpose=FilePurpose.AUTOMATIC).allowed
    assert policy.decide("tools/utils.py", purpose=FilePurpose.AUTOMATIC).allowed


# ---------------------------------------------------------------- plan v4: own-limit probes and the non-boundary rule


def test_every_own_limit_probe_solves_on_target_for_every_candidate(frozen: ev.Frozen) -> None:
    """Lengths only, nothing run: every template (held-out included) reaches each candidate's exact and one-over targets in serialized
    bytes, with the other side inside its limit. A payload-only rescale leaves S22 at 8/8 unreachable (read headers do not shrink)."""
    templates = [item for item in frozen.cases["split_schedules"]["schedules"] if "boundary" in item]
    assert len(templates) == 12 and frozen.cases["split_schedules"]["probe_recipe"]["version"] == ev.PROBE_RECIPE
    for item in templates:
        for partition in ev.PARTITIONS:
            variants = ev.probe_variants(item, partition)
            assert len(variants) == (3 if len(ev.boundary_targets(item["boundary"])) == 2 else 2), item["id"]
            for variant in variants:
                assert "blocked" not in variant, (item["id"], partition, variant["variant"], variant.get("blocked"))
                assert all(variant["totals"][side] == target for side, target in variant["targets"].items()), (item["id"], partition)
                assert variant["resolved"]["observation_text"] == "multibyte"


def test_probe_observation_text_is_multibyte_with_unchanged_byte_lengths() -> None:
    for size in (0, 1, 2, 7, 4096):
        text = ev.observation_text({"observation_text": "multibyte"}, size)
        assert len(text.encode("utf-8")) == size and (size < 2 or not text.isascii())
    assert ev.observation_text({}, 5) == "ooooo"


def test_own_limit_probes_at_6_10_complete_exactly_and_stop_one_over(frozen: ev.Frozen, tmp_path: Path) -> None:
    for template in ("S10", "S02"):
        for variant in ev.probe_variants(_schedule(frozen, template), (6, 10)):
            row = ev.run_schedule(variant["resolved"], (6, 10), tmp_path / template / variant["variant"])
            assert ev.probe_passed(variant["variant"], row), (template, variant["variant"], row["stop"], row["evidence_problems"])
            assert row["completed"] is (variant["variant"] == "exact")
    assert (pl.PLANNING_OBSERVATION_MAX_BYTES, pl.PLANNING_NEW_READ_MAX_BYTES) == PRODUCTION


FITTED, UNFITTED = {"status": "passed"}, {"status": "failed"}


def test_a_one_over_probe_needs_a_typed_stop_and_a_plan_after_observation_too_large_fails() -> None:
    stopped = {"completed": False, "planned": False, "stop": "PLANNING_READ_BUDGET_EXHAUSTED", "parse_failures": [], "route_fit": FITTED}
    too_large = {"completed": False, "planned": False, "stop": "X", "parse_failures": ["OBSERVATION_TOO_LARGE"], "route_fit": FITTED}
    f2 = {"completed": False, "planned": True, "stop": None, "parse_failures": ["OBSERVATION_TOO_LARGE"], "route_fit": FITTED}  # plan without that evidence
    other = {"completed": False, "planned": False, "stop": "PLANNING_REPEATED_READ_REQUEST", "parse_failures": [], "route_fit": FITTED}
    assert ev.probe_passed("one_over", stopped) and ev.probe_passed("one_over_reads", too_large)
    assert not ev.probe_passed("one_over", f2) and not ev.probe_passed("one_over_observations", other)
    assert not ev.probe_passed("exact", {**f2, "planned": True}) and ev.probe_passed("exact", {**stopped, "completed": True})
    assert not ev.probe_passed("exact", None) and not ev.probe_passed("one_over", None)  # blocked: never skipped


def test_the_v4_choice_scores_non_boundary_schedules_and_rejects_a_failed_probe() -> None:
    results = _rows(
        **{
            "4/12": {"a": True, "b": False, "p": True},
            "2/14": {"a": True, "b": True, "p": False},
            "6/10": {"a": True, "b": True, "p": False},
            "8/8": {"a": False, "b": True, "p": True},
        }
    )
    for rows in results.values():
        rows["p"]["boundary"] = True  # a probe template: its loss under 6/10 and 2/14 does not count
    probes = {
        "4/12": [{"template": "p", "variant": "exact", "passed": False}],
        "2/14": [{"template": "p", "variant": "one_over", "passed": False}],
        "6/10": [{"template": "p", "variant": "exact", "passed": True}],
        "8/8": [],
    }
    choice = ev.choose_partition(results, probes)
    assert choice["chosen"] == "6/10"
    assert choice["rejected"]["2/14"] == "fails own-limit probes: p:one_over"
    assert choice["rejected"]["8/8"] == "loses baseline-success schedules: a"
    assert choice["baseline_probe_failures"] == ["p:exact"]  # reported; the baseline stays the fallback
    # Without the probe gate 2/14 survives: it ties 6/10 on completions and stops and is as near 4/12, and the label breaks the tie.
    assert "2/14" not in ev.choose_partition(results)["rejected"]


# ---------------------------------------------------------------- Task 3: production partition, route fitting, qualification


def test_production_limits_are_the_partition_calibration_chose(frozen: ev.Frozen) -> None:
    observation, read = ev.chosen_partition(REPOSITORY, frozen)
    assert PRODUCTION == (observation * 1024, read * 1024) == (6144, 10240)
    assert sum(PRODUCTION) == 16 * 1024  # the combined ceiling is unchanged


def test_a_request_the_route_cannot_fit_is_never_a_completion(frozen: ev.Frozen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot, model_id, limits = ev._route()
    monkeypatch.setattr(ev, "_route", lambda: (snapshot, model_id, dataclasses.replace(limits, usable_input_tokens=2000)))
    row = ev.run_schedule(ev.resolve(_schedule(frozen, "S12")), (6, 10), tmp_path)
    assert (row["completed"], row["stop"], row["route_fit"]["status"]) == (False, "CONTEXT_CAPACITY_EXCEEDED", "failed")
    monkeypatch.undo()
    real = ev.route_packer

    def unrecorded():  # requests that reach the model without the packer seeing them
        turn = real()
        turn.record_dispatch = lambda _text, **_where: None
        return turn

    monkeypatch.setattr(ev, "route_packer", unrecorded)
    bypassed = ev.run_schedule(ev.resolve(_schedule(frozen, "S12")), (6, 10), tmp_path / "bypassed")
    assert bypassed["planned"] and (bypassed["completed"], bypassed["route_fit"]["status"]) == (False, "failed")


def test_the_index_order_comes_from_the_real_index_records_and_keeps_every_candidate(frozen: ev.Frozen, tmp_path: Path) -> None:
    records = ev.index_records(REPOSITORY, frozen)
    cases = {case["id"]: case for case in frozen.cases["ambiguity"]["cases"]}
    neighbour = ev.ambiguity_baseline(frozen, cases["A08"], tmp_path / "a", records=records[cases["A08"]["family"]])
    assert (neighbour["path_only_rank"], neighbour["ranked_rank"], neighbour["index_rank"]) == (3, 3, 1)
    # A04's only distinguishing hint is stale: it contributes nothing, the stale target stays listed, and the order loses (frozen note)
    stale = ev.ambiguity_baseline(frozen, cases["A04"], tmp_path / "b", records=records["A-F2"])
    assert stale["index_candidates"] == ["src/optimus/context/utils.py", "src/optimus/acp/utils.py", "tools/utils.py"]
    assert stale["index_rank"] == 2 and stale["candidates_kept"] and stale["denied_listed"] == []


def test_index_records_must_cover_the_frozen_files(frozen: ev.Frozen, tmp_path: Path) -> None:
    copy = tmp_path / "repo"
    shutil.copytree(REPOSITORY / ev.REPORTS, copy / ev.REPORTS)
    report = json.loads((copy / ev.REPORTS / "index-check.json").read_text(encoding="utf-8"))
    report["families"][0]["candidates"].pop()
    (copy / ev.REPORTS / "index-check.json").write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ev.FrozenInputChanged, match="A-F1"):
        ev.index_records(copy, frozen)


def _held(**orders: tuple[float, float]) -> dict:
    score = {"wrong_target_selections": 0, "candidates_lost": 0, "denied_listed": 0}
    for order, (top, rr) in orders.items():
        score[f"{order}_top_one"], score[f"{order}_reciprocal_rank"] = top, rr
    return {"held_out": score}


def _split(done: dict[str, set[str]], failed: tuple[str, ...] = ()) -> dict:
    ids = {"a", "b", "c", "p"}
    return {
        "runs": {label: {sid: {"completed": sid in ok, "boundary": sid == "p"} for sid in ids} for label, ok in done.items()},
        "probes": {"6/10": [{"template": "p", "variant": name, "passed": name not in failed} for name in ("exact", "one_over")]},
    }


def test_qualification_needs_ranking_benefit_on_the_same_rows_and_a_completion_gain_without_loss() -> None:
    rows = [{"outcome": "ambiguous_stop", "expected": "ambiguous_stop"}]
    split = _split({"4/12": {"a", "p"}, "6/10": {"a", "b"}})
    gates = ev.qualify(_held(path_only=(0.5, 0.7), ranked=(0.5, 0.8), index=(0.5, 0.7)), rows, split, "6/10")
    assert gates["ambiguity_242"]["ranked"]["passed"] and not gates["ambiguity_242"]["index"]["passed"]  # equal is no benefit
    assert gates["split_245"] == {
        "passed": True, "chosen": "6/10", "failed_probes": [], "baseline_successes_lost": [], "non_boundary_completions_gained": ["b"]
    }  # p is a probe template: losing its absolute run is not a loss
    worse = ev.qualify(_held(path_only=(0.5, 0.7), ranked=(0.6, 0.6), index=(0.5, 0.7)), rows, split, "6/10")
    assert not worse["ambiguity_242"]["ranked"]["passed"]  # one metric down
    unsafe = _held(path_only=(0.5, 0.7), ranked=(1.0, 1.0), index=(1.0, 1.0))
    unsafe["held_out"]["wrong_target_selections"] = 1
    assert not ev.qualify(unsafe, rows, split, "6/10")["ambiguity_242"]["ranked"]["passed"]
    hidden = ev.qualify(_held(path_only=(0.5, 0.7), ranked=(1.0, 1.0), index=(1.0, 1.0)), [{"outcome": "resolved", "expected": "ambiguous_stop"}], split, "6/10")
    assert not hidden["ambiguity_242"]["ranked"]["passed"]  # an expected stop that resolved
    assert not ev.qualify(_held(path_only=(0.5, 0.7), ranked=(1.0, 1.0), index=(1.0, 1.0)), rows, _split({"4/12": {"a"}, "6/10": {"b"}}), "6/10")["split_245"]["passed"]
    assert not ev.qualify(_held(path_only=(0.5, 0.7), ranked=(1.0, 1.0), index=(1.0, 1.0)), rows, _split({"4/12": {"a"}, "6/10": {"a"}}), "6/10")["split_245"]["passed"]
    failed = ev.qualify(_held(path_only=(0.5, 0.7), ranked=(1.0, 1.0), index=(1.0, 1.0)), rows, _split({"4/12": {"a"}, "6/10": {"a", "b"}}, ("one_over",)), "6/10")
    assert failed["split_245"]["failed_probes"] == ["p:one_over"] and not failed["split_245"]["passed"]
    assert ev.qualify(_held(path_only=(None, None), ranked=(1.0, 1.0), index=(1.0, 1.0)), rows, split, "6/10")["ambiguity_242"]["ranked"] == {
        "passed": False, "reason": "unmeasured"
    }


def test_the_capacity_trade_names_every_baseline_completion_the_choice_loses() -> None:
    runs = {"4/12": {"S10": {"completed": True}, "S12": {"completed": True}}, "6/10": {"S10": {"completed": False}, "S12": {"completed": True}}}
    trade = ev.capacity_trade(runs, "6/10")
    assert trade["lost_completions"] == ["S10"] and trade["current_read_bytes_lost"] == 2048
    assert trade["current_read_bytes"] == {"4/12": 12288, "6/10": 10240}


def test_ambiguity_scores_every_order_over_the_same_rows() -> None:
    rows = [
        {"split": "held_out", "decidable": True, "outcome": "ambiguous_stop", "path_only_rank": 2, "ranked_rank": 1, "index_rank": 1,
         "wrong_target_selections": 0, "candidates_kept": True, "denied_listed": []},
        {"split": "held_out", "decidable": True, "outcome": "ambiguous_stop", "path_only_rank": 1, "ranked_rank": 2, "index_rank": None,
         "wrong_target_selections": 0, "candidates_kept": False, "denied_listed": ["secrets/x.py"]},
    ]
    score = ev.score_ambiguity(rows)["held_out"]
    assert (score["path_only_top_one"], score["ranked_top_one"]) == (0.5, 0.5)
    assert score["ranked_reciprocal_rank"] == pytest.approx(0.75) and score["index_top_one"] is None  # an unmeasured row: no score
    assert (score["candidates_lost"], score["denied_listed"]) == (1, 1)


def test_cache_identity_shows_the_prefix_moved_and_the_registry_did_not() -> None:
    report = ev.cache_identity(REPOSITORY)
    assert report["prefix_changed"] and report["registry"]["files_changed"] == []
    assert report["digests"]["production"]["limits"] == [6144, 10240, 16384]
    assert set(report["registry"]["test_profiles"]) == {"qualification", "attached", "evaluation"}


def test_determinism_reports_identical_reruns_and_names_a_difference(frozen: ev.Frozen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = json.loads(json.dumps(frozen.cases))
    cases["ambiguity"]["cases"] = [case for case in cases["ambiguity"]["cases"] if case["id"] in {"A01", "A04"}]
    cases["split_schedules"]["schedules"] = [item for item in cases["split_schedules"]["schedules"] if item["id"] == "S12"]
    trimmed = ev.Frozen(cases, frozen.digests)
    report = ev.determinism(trimmed, tmp_path / "a", (6, 10))
    assert report["identical"] and (report["ambiguity"]["cases"], report["schedules"]["runs"]) == (2, 1)
    real = ev.run_schedule
    calls = iter(range(2))
    monkeypatch.setattr(ev, "run_schedule", lambda *args: {**real(*args), "requests": next(calls)})
    changed = ev.determinism(trimmed, tmp_path / "b", (6, 10))
    assert changed["schedules"]["differing"] == ["S12"] and not changed["identical"]


def test_a_probe_whose_requests_were_not_all_fitted_never_passes() -> None:
    """Codex CP2 review 1, finding 2: a typed budget stop after an unrecorded request, or a capacity stop after OBSERVATION_TOO_LARGE."""
    unrecorded = {"completed": False, "planned": False, "stop": "PLANNING_READ_BUDGET_EXHAUSTED", "parse_failures": [], "route_fit": UNFITTED}
    capacity = {"completed": False, "planned": False, "stop": "CONTEXT_CAPACITY_EXCEEDED", "parse_failures": ["OBSERVATION_TOO_LARGE"],
                "route_fit": UNFITTED}
    assert not ev.probe_passed("one_over", unrecorded) and not ev.probe_passed("one_over_observations", capacity)
    assert ev.probe_passed("one_over", {**unrecorded, "route_fit": FITTED})


def test_a_probe_record_keeps_its_route_fit_and_request_count(frozen: ev.Frozen, tmp_path: Path) -> None:
    cases = json.loads(json.dumps(frozen.cases))
    cases["ambiguity"]["cases"] = []
    cases["split_schedules"]["schedules"] = [item for item in cases["split_schedules"]["schedules"] if item["id"] == "S10"]
    report = ev.calibration(ev.Frozen(cases, frozen.digests), tmp_path / "w", ("train",), phase="calibration", partitions=((4, 12), (6, 10)))
    probes = report["split"]["probes"]["6/10"]
    assert probes and all(probe["route_fit"]["status"] == "passed" and probe["requests"] >= 1 for probe in probes)
