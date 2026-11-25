"""Plan 12.14 Task 1: the M2b evaluator's pure parts and the frozen cases' own sizes. The real index runs in calibration, never here."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from context_engine.context_pack import assemble_pack
from context_engine.retrieval import Hit, Ranked, Retrieval
from optimus.context.context_budget import legacy_budget, plan_budget
from tools.plan12_memory import m2b_evaluate as ev
from tools.plan12_memory.contracts import GoldenCase

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT / "reports/plan12-memory-m2b/cases.json").read_text(encoding="utf-8"))
SNAPSHOT = next(c["snapshot"] for c in CASES["paid_q"]["cases"] if c["category"] == "budget").removeprefix("git:")  # main at Task 0
MODEL_AWARE = plan_budget(ev.D3_USABLE_INPUT, input_target_usd=ev.D3_TARGET_USD, input_usd_per_million=ev.D3_INPUT_PRICE, cache_write=True)


def _blob_reader():
    def read(path: str) -> bytes | None:
        done = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", f"{SNAPSHOT}:{path}"], capture_output=True)
        return done.stdout if done.returncode == 0 else None

    return read


def test_the_fresh_set_is_refused_in_calibration():
    with pytest.raises(ev.FreshRefused):
        ev.load_set(ROOT, CASES, "fresh")


def test_the_development_set_loads_from_its_frozen_fixtures():
    cases = ev.load_set(ROOT, CASES, "development")
    assert len(cases) == 16 and sum(len(c.required_evidence) for c in cases) == 35


def test_a_changed_fixture_is_refused(tmp_path):
    record = json.loads(json.dumps(CASES))
    fixture = next(iter(record["packing_sets"]["development"]["fixtures"]))
    record["packing_sets"]["development"]["fixture_sha256"][fixture] = "hex:" + "0" * 64
    with pytest.raises(SystemExit):
        ev.load_set(ROOT, record, "development")


def test_the_budget_cases_have_the_sizes_the_plan_needs():
    """R measured as the pack serializes it, from the snapshot's bytes: two ordinary fits, two in (16,384, C], two outlines over C."""
    read = _blob_reader()
    sizes = {c["case_id"]: ev.required_tokens([f["path"] for f in c["required_files"]], read) for c in CASES["paid_q"]["cases"] if c["required_files"]}
    legacy, ceiling = legacy_budget(ev.D3_USABLE_INPUT), MODEL_AWARE.ceiling
    assert (legacy, ceiling, MODEL_AWARE.target) == (16_384, 32_768, 13_107)
    assert all(sizes[c] < legacy for c in ("QB1", "QB2", "QO3"))
    assert all(legacy < sizes[c] <= ceiling for c in ("QB3", "QB4"))
    assert all(sizes[c] > ceiling for c in ("QO1", "QO2", "QO4"))


def test_required_tokens_is_the_packs_own_serialization():
    read = _blob_reader()
    path = "src/context_engine/repo_map.py"
    pack = assemble_pack(required=(path,), ranked=(), read=read, estimate=ev.estimate, budget_tokens=1_000_000)
    assert ev.required_tokens([path], read) == pack.tokens


def _hit(ident: str, path: str, data: bytes, lines: tuple[int, int], symbol: str) -> Hit:
    return Hit(id=ident, kind="symbol", path=path, file_hash=hashlib.sha256(data).hexdigest(), symbol=symbol, signature=f"def {symbol}()", start_line=lines[0], end_line=lines[1])


def test_a_budget_case_records_both_arms_and_a_substantive_change():
    body = "".join(f"def f{i}():\n    return {i}\n" for i in range(1500)).encode()
    small = b"x = 1\n"
    files = {"req.py": small, "opt.py": body}
    ranked = tuple(Ranked(_hit(str(i), "opt.py", body, (2 * i + 1, 2 * i + 2), f"f{i}"), 1 / (60 + i), {"lexical": i + 1}) for i in range(1500))
    retrieval = Retrieval("ok", 1, {}, None, ranked, {})
    case = {"case_id": "QB9", "kind": "ordinary-fit", "task": 'In "req.py", what is x?', "required_files": [{"path": "req.py"}]}
    small_policy = plan_budget(4_000 * 4, input_target_usd=ev.D3_TARGET_USD, input_usd_per_million=ev.D3_INPUT_PRICE, cache_write=True)
    row = ev.budget_case(case, retrieval, files.get, policy="baseline", model_aware=small_policy, legacy=legacy_budget(4_000 * 4), full_input=lambda text: len(text))
    assert row["arms"]["BU"]["budget"] == 4_000 and row["arms"]["F"]["budget"] == 4_000  # C is the quarter here; T above it is clipped
    big_policy = plan_budget(ev.D3_USABLE_INPUT, input_target_usd=ev.D3_TARGET_USD, input_usd_per_million=ev.D3_INPUT_PRICE, cache_write=True)
    row = ev.budget_case(case, retrieval, files.get, policy="baseline", model_aware=big_policy, legacy=16_384, full_input=lambda text: len(text))
    assert row["arms"]["F"]["budget"] == 13_107 and row["arms"]["BU"]["budget"] == 16_384
    assert row["substantive_change"] and row["arms"]["F"]["complete"] and row["arms"]["F"]["optional_items"] < row["arms"]["BU"]["optional_items"]


def test_required_text_over_legacy_is_incomplete_for_bu_and_whole_for_f():
    big = b"#" * 20_000 + b"\n"
    retrieval = Retrieval("ok", 1, {}, None, (), {})
    case = {"case_id": "QB8", "kind": "required-over-legacy", "task": 't', "required_files": [{"path": "big.py"}]}
    row = ev.budget_case(case, retrieval, {"big.py": big}.get, policy="baseline", model_aware=MODEL_AWARE, legacy=16_384, full_input=lambda text: len(text) + 288)
    assert not row["arms"]["BU"]["complete"] and row["arms"]["F"]["complete"] and row["r_in_legacy_to_ceiling"] and row["substantive_change"]
    assert row["arms"]["F"]["budget"] == row["R"] + 1_024 and row["fits_q_cap"]


def _totals(evidence: int, irrelevant: int = 100, *, met5: int = 5, poison: int = 0, control: int = 1, stale: int = 0, worst: int = 100) -> dict:
    return {"evidence_in_context": evidence, "irrelevant_tokens": irrelevant, "max_irrelevant_tokens": worst, "met_at_5": met5, "poison_tokens": poison,
            "control_admitted": control, "stale_paths": stale}


def _rep(base: dict, density: dict, coverage: dict) -> dict:
    return {"baseline": base, "density": density, "coverage": coverage}


def test_selection_needs_every_repetition_and_a_strict_gain():
    same = [_rep(_totals(10), _totals(10), _totals(10))] * 3
    assert ev.select_candidate(same)["selected"] == "baseline"
    better = [_rep(_totals(10), _totals(11), _totals(12, irrelevant=90))] * 3
    choice = ev.select_candidate(better)
    assert choice["selected"] == "coverage" and not choice["u_equals_b"]
    assert ev.select_candidate(better[:2])["verdicts"]["density"]["inconclusive"]


@pytest.mark.parametrize("change", [{"irrelevant": 101}, {"met5": 4}, {"poison": 1}, {"control": 0}, {"stale": 1}, {"worst": 16_001}])
def test_each_development_gate_can_reject_a_candidate(change):
    bad = _totals(12, **{"irrelevant": 100, **change})
    reps = [_rep(_totals(10), bad, _totals(10))] * 3
    verdict = ev.candidate_passes("density", reps)
    assert not verdict["passes"] and verdict["reasons"]


def test_one_repetition_below_the_baseline_rejects():
    reps = [_rep(_totals(10), _totals(12), _totals(10))] * 2 + [_rep(_totals(10), _totals(9), _totals(10))]
    assert not ev.candidate_passes("density", reps)["passes"]


def test_injections_are_written_only_with_their_frozen_bytes(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ev.m1_scale, "_git", lambda tree, *args: calls.append(args))
    (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
    injection = CASES["injections"]["sets"]["development"]
    ev.inject(tmp_path, injection)
    assert (tmp_path / injection["poison"]["path"]).read_text(encoding="utf-8") == injection["poison"]["text"]
    assert calls[-1][:2] == ("commit", "-q")
    tampered = json.loads(json.dumps(injection))
    tampered["control"]["text"] += "x"
    with pytest.raises(AssertionError):
        ev.inject(tmp_path, tampered)


def test_the_control_case_is_a_valid_development_control():
    injection = CASES["injections"]["sets"]["development"]
    case = ev.control_case(injection, f"git:{SNAPSHOT}", "2026-11-24T18:08:04+05:30")
    assert isinstance(case, GoldenCase) and case.role == "control" and case.required_evidence[0].any_of == ("path:docs/notes/dev-control.md",)


def test_the_report_is_written_as_sorted_ascii_json(tmp_path):
    out = tmp_path / "report.json"
    ev._write({"b": 1, "a": "é"}, out)
    text = out.read_text(encoding="utf-8")
    assert text.isascii() and text.index('"a"') < text.index('"b"') and json.loads(text) == {"a": "é", "b": 1}


def test_main_refuses_qualification_before_task_4(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    with pytest.raises(ev.FreshRefused):
        ev.main(["--config", "reports/plan12-memory-m2b/run-config.json", "--phase", "qualification", "--output", str(tmp_path / "q.json")])


def test_injections_take_the_trees_own_archive_date(tmp_path, monkeypatch):
    import os

    monkeypatch.setattr(ev.m1_scale, "_git", lambda tree, *args: None)
    (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
    os.utime(tmp_path / "pyproject.toml", (1_000_000_000, 1_000_000_000))
    injection = CASES["injections"]["sets"]["fresh"]
    ev.inject(tmp_path, injection)
    assert {(tmp_path / injection[k]["path"]).stat().st_mtime for k in ("poison", "control")} == {1_000_000_000}


def test_a_capture_keeps_ids_and_ranks_never_text(tmp_path):
    hit = Hit(id="h", kind="symbol", path="a.py", file_hash="0" * 64, symbol="f", start_line=1, end_line=2)
    case = ev.control_case(CASES["injections"]["sets"]["development"], f"git:{SNAPSHOT}", "2026-11-24T18:08:04+05:30")
    capture = ev.Capture(case, "secret words", (Ranked(hit, 0.5, {"lexical": 1}),), ("h",), lambda _p: b"body")
    digest = ev.save_capture(tmp_path / "c.json", capture)
    text = (tmp_path / "c.json").read_text(encoding="utf-8")
    assert "secret words" not in text and "body" not in text and json.loads(text)["protected"] == ["h"]
    assert digest == "hex:" + hashlib.sha256((tmp_path / "c.json").read_bytes()).hexdigest()


KINDS = {"QB1": "ordinary-fit", "QB2": "ordinary-fit", "QB3": "required-over-legacy", "QB4": "required-over-legacy", "QO1": "outline", "QO2": "outline",
         "QO3": "whole-summary", "QO4": "exact-over-ceiling"}
R = {"ordinary-fit": 7_000, "required-over-legacy": 20_000, "outline": 50_000, "whole-summary": 5_000, "exact-over-ceiling": 50_000}


def _budget_rows() -> list[dict]:
    rows = []
    for case_id, kind in KINDS.items():
        bu, f = ev.BUDGET_OUTCOMES[kind]
        rows.append({"case_id": case_id, "kind": kind, "R": R[kind], "C": 32_768, "substantive_change": case_id.startswith("QB"), "fits_q_cap": f,
                     "r_in_legacy_to_ceiling": kind == "required-over-legacy", "arms": {"BU": {"complete": bu}, "F": {"complete": f}}})
    return rows


def _with(rows: list[dict], case_id: str, **changes) -> list[dict]:
    out = [dict(row, arms={arm: dict(values) for arm, values in row["arms"].items()}) for row in rows]
    row = next(r for r in out if r["case_id"] == case_id)
    for key, value in changes.items():
        arm, _, field = key.partition("__")
        if field:
            row["arms"][arm][field] = value
        else:
            row[key] = value
    return out


def test_budget_gates_need_the_exact_eight_cases_both_arms_and_each_kinds_outcome():
    rows = _budget_rows()
    assert ev.budget_gates(rows)["passes"]
    for wrong in (rows + [rows[0]], rows[:-1], rows[:-1] + [dict(rows[0], case_id="QX9")]):  # a duplicate, a missing case, a stranger
        assert ev.budget_gates(wrong)["checks"] == {"exact_case_set": False} and not ev.budget_gates(wrong)["passes"]
    only_f = [dict(row, arms={"F": row["arms"]["F"]}) for row in rows]  # Codex attempt 2 finding 6: an F-only reduction passed
    try:
        refused = ev.budget_gates(only_f)
    except (KeyError, TypeError) as error:
        pytest.fail(f"an F-only reduction must be refused, not crash: {error!r}")
    assert refused["checks"].get("both_arms") is False and not refused["passes"]
    for broken, check in ((_with(rows, "QO3", F__complete=False), "each_kinds_outcome"),  # QO3's F incomplete was filtered out before
                          (_with(rows, "QB3", BU__complete=True), "each_kinds_outcome"),
                          (_with(rows, "QO1", F__complete=True), "each_kinds_outcome"),
                          (_with(rows, "QO4", R=30_000), "three_r_over_ceiling"),
                          (_with(rows, "QB1", substantive_change=False), "two_ordinary_allocation_changes")):
        result = ev.budget_gates(broken)
        assert not result["passes"] and result["checks"][check] is False, check
    swapped = [dict(row, case_id={"QO1": "QO3", "QO3": "QO1"}.get(row["case_id"], row["case_id"])) for row in rows]  # Codex attempt 3 finding 6
    assert ev.budget_gates(swapped)["checks"] == {"exact_case_set": True, "both_arms": True, "kinds_pinned": False} and not ev.budget_gates(swapped)["passes"]


def test_the_released_budget_pass_meets_the_stricter_gates():
    report = json.loads((ROOT / "reports/plan12-memory-m2b/calibration-budget.json").read_text(encoding="utf-8"))
    assert ev.budget_gates(report["rows"])["passes"]


def test_the_production_routes_give_the_forecast_budgets_and_the_routes_estimator(tmp_path):
    legacy, model_aware, estimate_request = ev.production_routes(tmp_path)
    assert (legacy.ceiling, model_aware.ceiling, model_aware.target) == (16_384, 32_768, 13_107)
    assert estimate_request("x" * 1000) == 1000 + 272  # 16 per message and 256 fixed on D3's estimator


def test_the_policy_reader_refuses_what_production_would_not_read(tmp_path):
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    read = ev.policy_reader(tmp_path)
    assert read("a.py") == b"x = 1\n" and read(".env") is None
