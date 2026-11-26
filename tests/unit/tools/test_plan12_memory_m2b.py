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


def test_main_refuses_a_second_opening_of_the_fresh_set(tmp_path, monkeypatch):
    repo = _qualification_repo(tmp_path)
    (repo / "q.json").write_text(json.dumps({"fresh_opened": True}), encoding="utf-8")
    monkeypatch.chdir(repo)
    _refuse_provisioning(monkeypatch)
    with pytest.raises(ev.FreshRefused, match="second use"):
        ev.main(["--config", "config.json", "--phase", "qualification", "--output", "q.json"])


def _refuse_provisioning(monkeypatch) -> None:
    """Everything before provisioning runs cheaply, so a removed guard reaches the provisioning step and fails there by name."""
    from types import SimpleNamespace

    monkeypatch.setattr(ev.subprocess, "run", lambda args, *a, **k: subprocess.CompletedProcess(args, 0, stdout="abc\n", stderr=""))
    monkeypatch.setattr(ev, "production_routes", lambda work: (SimpleNamespace(ceiling=legacy_budget(ev.D3_USABLE_INPUT)), MODEL_AWARE, ev.estimate))
    monkeypatch.setattr(ev.m1_scale, "_provision", lambda *a, **k: pytest.fail("provisioned past a refusal"))


@pytest.mark.parametrize("passes, code", [(True, 0), (False, 1)])
def test_main_exits_with_an_error_when_qualification_fails_its_gates(tmp_path, monkeypatch, passes, code):
    repo = _qualification_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ev, "run_qualification", lambda config, repository, out: {"gates": {"passes": passes}})
    assert ev.main(["--config", "config.json", "--phase", "qualification", "--output", "q.json"]) == code


SPECS = {"replay_seed_held_out": (1, 2), "replay_m1_held_out": (1, 1), "replay_fresh": (1, 1), "replay_fresh2": (1, 1), "fresh": (2, 40)}


def _qualification_repo(tmp_path: Path, *, selected: str = "baseline", fresh_requirements: int = 40) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    calibration = json.dumps({"selection": {"selected": selected, "u_equals_b": selected == "baseline"}}).encode()
    (repo / "calibration.json").write_bytes(calibration)
    specs = {**SPECS, "fresh": (2, fresh_requirements)}
    (repo / "cases.json").write_text(json.dumps({"packing_sets": {name: {"cases": c, "requirements": r} for name, (c, r) in specs.items()},
                                                 "injections": {"sets": {"fresh": {"poison": {"path": "p.md"}}}}}), encoding="utf-8")
    config = {"label": "t", "authorization": "operator, test", "cases": "cases.json", "work_dir": "work", "calibration": "calibration.json",
              "calibration_sha256": "hex:" + hashlib.sha256(calibration).hexdigest(), "container": "none-c", "volume": "none-v", "embedding_threads": 1,
              "output": "q.json"}
    (repo / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return repo


def _arm_row(role: str, requirements: int, u: int, f: int) -> dict:
    def arm(met: int) -> dict:
        return {"requirements": requirements, "evidence_in_context": met, "irrelevant_tokens": 0, "stale_paths": 0, "poison_tokens": 0}

    return {"role": role, "arms": {"U": arm(u), "F": arm(f)}}


def _set_rows(name: str) -> list[dict]:
    cases, requirements = SPECS[name]
    rows = [_arm_row("probe", requirements // cases + (requirements % cases if i == 0 else 0), 1, 1) for i in range(cases)]
    return rows + ([_arm_row("control", 1, 1, 1)] if name == "fresh" else [])


def _sets(**changes) -> dict:
    return {name: {"arms": ev.arm_totals(changes.get(name, _set_rows(name)))} for name in SPECS}


def test_the_qualification_gates_need_every_set_its_frozen_counts_and_f_coverage_at_least_u(tmp_path):
    record = json.loads((_qualification_repo(tmp_path) / "cases.json").read_text(encoding="utf-8"))
    assert ev.qualification_gates(_sets(), record)["passes"]
    try:
        missing = ev.qualification_gates({k: v for k, v in _sets().items() if k != "replay_fresh"}, record)
    except KeyError:
        pytest.fail("a missing set crashed the gates instead of failing them")
    assert not missing["passes"] and missing["checks"] == {"every_set_measured": False}
    worse = ev.qualification_gates(_sets(replay_fresh2=[_arm_row("probe", 1, 1, 0)]), record)
    assert not worse["passes"] and not worse["checks"]["replay_fresh2: F required coverage >= U"]
    short = ev.qualification_gates(_sets(replay_m1_held_out=[_arm_row("probe", 1, 1, 1), _arm_row("probe", 1, 1, 1)]), record)
    assert not short["passes"] and not short["checks"]["replay_m1_held_out: every frozen case and requirement"]
    no_control = ev.qualification_gates(_sets(fresh=[_arm_row("probe", 20, 1, 1), _arm_row("probe", 20, 1, 1)]), record)
    assert not no_control["passes"] and not no_control["checks"]["fresh: its positive control measured"]
    lost_control = ev.qualification_gates(_sets(fresh=[_arm_row("probe", 20, 1, 1), _arm_row("probe", 20, 1, 1), _arm_row("control", 1, 1, 0)]), record)
    assert not lost_control["passes"] and not lost_control["checks"]["fresh: F admits the control at least as often as U"]


def test_the_cases_where_f_shows_less_than_u_are_named():
    rows = [{**_arm_row("probe", 2, 2, 1), "case_id": "A"}, {**_arm_row("probe", 2, 1, 2), "case_id": "B"}, {**_arm_row("probe", 1, 1, 1), "case_id": "C"}]
    assert ev.f_below_u(rows) == ["A"]


def test_a_fresh_set_under_forty_requirements_fails_even_when_it_matches_its_record(tmp_path):
    record = json.loads((_qualification_repo(tmp_path, fresh_requirements=39) / "cases.json").read_text(encoding="utf-8"))
    gates = ev.qualification_gates(_sets(fresh=[_arm_row("probe", 20, 1, 1), _arm_row("probe", 19, 1, 1), _arm_row("control", 1, 1, 1)]), record)
    assert gates["checks"]["fresh: every frozen case and requirement"] and not gates["checks"]["fresh: at least 40 requirements"] and not gates["passes"]


def test_f_packs_the_selected_policy_at_the_model_aware_budget_and_u_at_the_legacy_one():
    filler = "".join(f"def f{i}():\n    return {i}\n" for i in range(100)).encode()
    far = b"def target():\n    return 1\n"
    files = {"opt.py": filler, "far.py": far}
    ranked = tuple(Ranked(_hit(str(i), "opt.py", filler, (2 * i + 1, 2 * i + 2), f"f{i}"), 1 / (60 + i), {"lexical": i + 1}) for i in range(100))
    ranked += (Ranked(_hit("far", "far.py", far, (1, 2), "target"), 1 / 400, {"lexical": 101}),)
    control = {"control": {"case": {"case_id": "XC01-a", "query": "where is target?", "required_evidence": [{"requirement_id": "R1", "any_of": ["path:far.py"]}]}}}
    case = ev.control_case(control, "git:" + "a" * 40, "2026-11-24T18:08:04+05:30")
    capture = ev.Capture(case, "where is target?", ranked, (), files.get)
    arms = ev.budget_arms(capture, policy="baseline", legacy=1_000, model_aware=MODEL_AWARE, pack_estimate=ev.estimate, poison_path=None)
    assert arms["U"]["budget"] == 1_000 and arms["F"]["budget"] == MODEL_AWARE.target
    assert arms["U"]["evidence_in_context"] == 0 and arms["F"]["evidence_in_context"] == 1


class _Handle:
    def __init__(self):
        self.calls: list[str] = []

    def close(self):
        self.calls.append("close")

    def kill(self):
        self.calls.append("kill")

    def wait(self, _timeout):
        self.calls.append("wait")


def _driver(monkeypatch, repo: Path, qualify):
    from types import SimpleNamespace

    commands: list = []
    handle = _Handle()

    def run(args, *a, **k):
        commands.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="abc\n", stderr="")

    monkeypatch.setattr(ev.subprocess, "run", run)
    monkeypatch.setattr(ev, "production_routes", lambda work: (SimpleNamespace(ceiling=legacy_budget(ev.D3_USABLE_INPUT)), MODEL_AWARE, ev.estimate))
    monkeypatch.setattr(ev.m1_scale, "_provision", lambda *a, **k: (repo, SimpleNamespace(embedding=None), None, handle, handle, None, {"embedding": {"artifact_directory": "x"}}))
    monkeypatch.setattr(ev, "FastembedEmbedder", lambda *a, **k: None)
    monkeypatch.setattr(ev.m1_evaluate, "CachedEmbedder", lambda *a, **k: SimpleNamespace(embedded=0, reused=0))
    monkeypatch.setattr(ev.m1_evaluate, "wrong_branch_control", lambda *a, **k: {"passes": True})
    opened: list = []

    def load(repository, record, name, *, qualification=False):
        assert qualification
        out = repo / "q.json"
        opened.append((name, json.loads(out.read_text(encoding="utf-8")).get("fresh_opened") if out.exists() else None))
        return [name]

    monkeypatch.setattr(ev, "load_set", load)
    monkeypatch.setattr(ev, "_qualify_set", qualify)
    return commands, handle, opened


def _policies(rows: list[dict]) -> list[dict]:
    blank = {"requirements": 0, "evidence_in_context": 0, "irrelevant_tokens": 0, "max_irrelevant_tokens": 0, "poison_tokens": 0, "poison_shown": 0, "stale_paths": 0}
    return [{**row, "policies": {p: blank for p in ev.POLICIES}, "ranking": {"met_at_k": 0}} for row in rows]


def test_qualification_replays_the_historical_sets_first_and_records_the_fresh_opening_before_reading_it(tmp_path, monkeypatch):
    repo = _qualification_repo(tmp_path)
    seen = []

    def qualify(name, cases, injection, *a, policy, **k):
        seen.append((name, injection is not None, policy))
        return _policies(_set_rows(name)), None

    commands, handle, opened = _driver(monkeypatch, repo, qualify)
    report = ev.run_qualification(json.loads((repo / "config.json").read_text(encoding="utf-8")), repo, repo / "q.json")
    assert [name for name, *_ in seen] == list(ev.QUALIFICATION_SETS) == [name for name, _ in opened]
    assert [state for _, state in opened] == [None, False, False, False, True]  # the opening is on disk before the fresh fixture is read
    assert [(n, p) for n, injected, p in seen if injected] == [("fresh", "baseline")]  # only the fresh set has its poison and control
    assert report["gates"]["passes"] and json.loads((repo / "q.json").read_text(encoding="utf-8"))["gates"]["passes"]
    assert all(report["sets"][name]["f_below_u"] == [] for name in ev.QUALIFICATION_SETS)
    assert handle.calls == ["close", "kill", "wait"] and ["docker", "rm", "-f", "none-c"] in commands and ["docker", "volume", "rm", "-f", "none-v"] in commands


def test_a_historical_set_that_fails_its_gates_stops_the_run_before_the_fresh_set_opens(tmp_path, monkeypatch):
    repo = _qualification_repo(tmp_path)

    def qualify(name, *a, **k):
        rows = _set_rows(name)
        if name == "replay_fresh":
            rows = [_arm_row("probe", 1, 1, 0)]  # F shows less than U
        return _policies([{**row, "case_id": f"{name}-{i}"} for i, row in enumerate(rows)]), None

    _commands, handle, opened = _driver(monkeypatch, repo, qualify)
    report = ev.run_qualification(json.loads((repo / "config.json").read_text(encoding="utf-8")), repo, repo / "q.json")
    on_disk = json.loads((repo / "q.json").read_text(encoding="utf-8"))
    assert [name for name, _ in opened] == list(ev.QUALIFICATION_SETS[:4]) and report["fresh_opened"] is False and on_disk["fresh_opened"] is False
    assert not on_disk["gates"]["passes"] and on_disk["gates"]["stopped"] and not on_disk["gates"]["checks"]["replay_fresh: F required coverage >= U"]
    assert on_disk["sets"]["replay_fresh"]["f_below_u"] == ["replay_fresh-0"] and "fresh" not in on_disk["sets"] and handle.calls == ["close", "kill", "wait"]


def test_each_finished_tree_is_on_disk_before_the_next_one_starts(tmp_path, monkeypatch):
    repo = _qualification_repo(tmp_path)
    seen = []

    def qualify(name, *a, on_tree, **k):
        rows = _policies(_set_rows(name))
        on_tree(rows[:1])
        out = repo / "q.json"
        seen.append(json.loads(out.read_text(encoding="utf-8"))["sets"].get(name, {}) if out.exists() else {})
        return rows, None

    _driver(monkeypatch, repo, qualify)
    ev.run_qualification(json.loads((repo / "config.json").read_text(encoding="utf-8")), repo, repo / "q.json")
    assert len(seen) == 5 and all(record.get("partial") and len(record["rows"]) == 1 for record in seen)


def test_a_stuck_gateway_still_removes_the_container_and_volume(tmp_path, monkeypatch):
    repo = _qualification_repo(tmp_path)
    commands, handle, _opened = _driver(monkeypatch, repo, lambda name, *a, **k: (_policies(_set_rows(name)), None))

    def stuck(_timeout):
        raise TimeoutError("the Gateway did not stop")

    handle.wait = stuck
    with pytest.raises(TimeoutError):
        ev.run_qualification(json.loads((repo / "config.json").read_text(encoding="utf-8")), repo, repo / "q.json")
    assert ["docker", "rm", "-f", "none-c"] in commands and ["docker", "volume", "rm", "-f", "none-v"] in commands


def test_a_report_path_other_than_the_pinned_one_is_refused(tmp_path, monkeypatch):
    repo = _qualification_repo(tmp_path)
    _refuse_provisioning(monkeypatch)
    with pytest.raises(ev.FreshRefused, match="the qualification report is q.json"):
        ev.run_qualification(json.loads((repo / "config.json").read_text(encoding="utf-8")), repo, repo / "elsewhere.json")


def test_a_failure_before_the_fresh_set_spends_no_opening_and_tears_down(tmp_path, monkeypatch):
    repo = _qualification_repo(tmp_path)

    def qualify(name, *a, **k):
        if name == "replay_fresh2":
            raise RuntimeError("index failed")
        return _policies(_set_rows(name)), None

    _commands, handle, _opened = _driver(monkeypatch, repo, qualify)
    config = json.loads((repo / "config.json").read_text(encoding="utf-8"))
    with pytest.raises(RuntimeError):
        ev.run_qualification(config, repo, repo / "q.json")
    assert json.loads((repo / "q.json").read_text(encoding="utf-8"))["fresh_opened"] is False and handle.calls == ["close", "kill", "wait"]
    with pytest.raises(RuntimeError):  # not refused: the fresh set was never opened
        ev.run_qualification(config, repo, repo / "q.json")


@pytest.mark.parametrize("change, message", [({"authorization": ""}, "no recorded release"), ({"calibration_sha256": "hex:" + "0" * 64}, "not the released calibration")])
def test_qualification_refuses_without_a_release_or_with_another_calibration(tmp_path, monkeypatch, change, message):
    repo = _qualification_repo(tmp_path)
    _refuse_provisioning(monkeypatch)
    config = {**json.loads((repo / "config.json").read_text(encoding="utf-8")), **change}
    with pytest.raises(ev.FreshRefused, match=message):
        ev.run_qualification(config, repo, repo / "q.json")


def test_a_calibration_that_selected_a_candidate_is_refused_before_the_fresh_set_opens(tmp_path, monkeypatch):
    repo = _qualification_repo(tmp_path, selected="density")
    _refuse_provisioning(monkeypatch)
    with pytest.raises(ev.FreshRefused, match="selected density"):
        ev.run_qualification(json.loads((repo / "config.json").read_text(encoding="utf-8")), repo, repo / "q.json")


def test_a_set_with_an_injection_gets_its_poison_and_control_and_a_replay_gets_neither(tmp_path, monkeypatch):
    from types import SimpleNamespace

    injected, queries, captures = [], [], []
    monkeypatch.setattr(ev.m1_evaluate, "materialize", lambda *a, **k: None)
    monkeypatch.setattr(ev, "inject", lambda tree, injection: injected.append(tree.name))

    def index(tree, settings, embedder, trees, revision):
        trees.append({"revision": revision})
        return SimpleNamespace(storage=None)

    def retrieve(retriever, query, *, named):
        queries.append(named)
        return Retrieval("ok", 1, {}, None, (), {})

    def capture(path, item):
        captures.append(path.parent.name)
        return "hex:0"

    monkeypatch.setattr(ev, "_index", index)
    monkeypatch.setattr(ev, "Retriever", lambda *a: None)
    monkeypatch.setattr(ev, "policy_reader", lambda tree: (lambda path: None))
    monkeypatch.setattr(ev, "production_retrieve", retrieve)
    monkeypatch.setattr(ev.m1_evaluate, "stale_or_missing_hits", lambda ranked, tree: 0)
    monkeypatch.setattr(ev, "save_capture", capture)
    monkeypatch.setattr(ev, "_rotate", lambda previous, index, work, tree: index)
    injection = CASES["injections"]["sets"]["fresh"]
    probe = ev.control_case(injection, "git:" + "b" * 40, "2026-11-24T18:08:04+05:30").model_copy(update={"role": "probe", "case_id": "P1"})
    kwargs = {"policy": "baseline", "legacy": 16_384, "model_aware": MODEL_AWARE, "pack_estimate": ev.estimate}
    trees: list = []
    written: list = []
    rows, _ = ev._qualify_set("fresh", [probe], injection, ROOT, tmp_path, None, None, trees, None, on_tree=written.append, **kwargs)
    assert injected == ["4-bbbbbbbbbbbb"] and [r["case_id"] for r in rows] == ["P1", "FC01-a@bbbbbbbbbbbb"] and trees[0]["set"] == "fresh"
    assert queries == [(), ()] and captures == ["fresh", "fresh"] and all(set(r["arms"]) == {"U", "F"} for r in rows) and written == [rows]
    rows, _ = ev._qualify_set("replay_fresh", [probe], None, ROOT, tmp_path, None, None, trees, None, **kwargs)
    assert injected == ["4-bbbbbbbbbbbb"] and [r["case_id"] for r in rows] == ["P1"] and trees[1]["set"] == "replay_fresh"
    dropped: list = []
    monkeypatch.setattr(ev, "drop_retrying", lambda line: (dropped.append(line), 3)[1])
    ev._qualify_set("replay_fresh", [probe], None, ROOT, tmp_path, None, None, trees, "the previous line", **kwargs)
    assert dropped == ["the previous line"] and trees[2].get("drop_timeouts") == 3  # each drop's timeouts on the record


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


def test_with_the_outline_f_completes_exactly_the_outline_cases_with_one():
    """Plan 12.14 Task 3: once the outline exists, F completes QO1/QO2 by outlining them, B/U never outlines, and no other row may."""
    rows = _budget_rows()
    for row in rows:
        row["arms"]["F"]["complete"] = ev.OUTLINE_OUTCOMES[row["kind"]][1]
        row["arms"]["F"]["outline"] = row["kind"] == "outline"
        row["fits_q_cap"] = True
    assert ev.budget_gates(rows, outline_available=True)["passes"]
    assert not ev.budget_gates(rows)["passes"], "the pre-outline gates refuse an outlined F"
    for broken, check in ((_with(rows, "QO1", F__outline=False), "outline_only_where_asked"), (_with(rows, "QO3", F__outline=True), "outline_only_where_asked"),
                          (_with(rows, "QO2", BU__outline=True), "outline_only_where_asked"), (_with(rows, "QO1", F__complete=False), "each_kinds_outcome"),
                          (_with(rows, "QO4", F__complete=True), "each_kinds_outcome")):
        result = ev.budget_gates(broken, outline_available=True)
        assert not result["passes"] and result["checks"][check] is False, check


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


class _DropStore:
    """The index store's drop: two steps (a cursor between them); each code in `fail` is raised once, in order, before a step answers."""

    def __init__(self, fail: list[str]):
        self.fail, self.calls = list(fail), []

    def call(self, op, **body):
        self.calls.append((op, body.get("cursor")))
        if op == "lease":
            return {"token": "t"}
        if self.fail:
            raise ev.StorageUnavailableError(self.fail.pop(0))
        return {"status": "ok", "cursor": None if body.get("cursor") else "c1"}


def _line(store):
    from types import SimpleNamespace

    return SimpleNamespace(storage=store, owner="o")


def test_a_timed_out_drop_step_is_repeated_from_its_cursor_and_counted():
    store = _DropStore(["INDEX_TIMEOUT", "INDEX_TIMEOUT"])
    try:
        timeouts = ev.drop_retrying(_line(store), pause=0)
    except ev.StorageUnavailableError:
        pytest.fail("a timed-out drop step was not repeated")
    assert timeouts == 2
    assert store.calls == [("lease", None), ("cleanup", None), ("cleanup", None), ("cleanup", None), ("cleanup", "c1")]


def test_another_refusal_or_a_step_timing_out_every_attempt_stops_the_drop():
    with pytest.raises(ev.StorageUnavailableError, match="SCOPE_UNKNOWN"):
        ev.drop_retrying(_line(_DropStore(["SCOPE_UNKNOWN"])), pause=0)
    store = _DropStore(["INDEX_TIMEOUT"] * 3)
    try:
        ev.drop_retrying(_line(store), attempts=3, pause=0)
    except ev.StorageUnavailableError as error:
        assert str(error) == "INDEX_TIMEOUT"
    except Exception as error:  # noqa: BLE001 - any other end means the bound did not hold
        pytest.fail(f"the drop did not stop at its bound: {type(error).__name__}")
    else:
        pytest.fail("the drop did not stop at its bound")
    assert [op for op, _ in store.calls].count("cleanup") == 3
