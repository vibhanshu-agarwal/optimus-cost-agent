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
