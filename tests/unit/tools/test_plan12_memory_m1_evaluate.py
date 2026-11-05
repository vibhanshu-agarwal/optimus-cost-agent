"""Plan 12.10: the retrieval evaluation's scoring and its held-out gate, on real files. The evaluation itself needs a released Redis."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from context_engine.retrieval import Hit, Ranked
from tools.plan12_memory import m1_evaluate as ev
from tools.plan12_memory import m1_scale
from tools.plan12_memory.contracts import GoldenCase


def _case(*requirements: tuple[str, ...]) -> GoldenCase:
    return GoldenCase.model_validate({
        "schema": "plan12-memory-case/1", "case_id": "T01-a", "version": 1, "family": "T01", "split": "train", "kind": "localization", "role": "probe", "oracles": ["K2"],
        "inputs": [{"seq": 0, "actor": "user", "text": "where is it", "attempt": None}], "project_id": "p", "snapshot": "git:abc", "cutoff": "2026-07-22T20:24:58+05:30",
        "expected_action": "answer", "required_facts": [], "required_evidence": [{"requirement_id": f"R{n}", "any_of": list(items)} for n, items in enumerate(requirements, start=1)],
        "prohibited_claims": [], "required_events": [], "prohibited_events": [], "expected_memory": [], "expected_rank": [], "expected_cost": None, "verification": "v",
        "provenance": {"drafted_by": "claude", "verified_by": None, "source": "s"},
    })


def _ranked(path: str, symbol: str | None, *, ranks: dict[str, int] | None = None, kind: str = "symbol", file_hash: str = "0" * 64) -> Ranked:
    hit = Hit(id=f"{path}{symbol}", kind=kind, path=path, file_hash=file_hash, symbol=symbol, signature=f"def {symbol}()" if symbol else None, start_line=1, end_line=1)
    return Ranked(hit, 1.0, ranks or {"lexical": 1})


def test_recall_counts_only_the_named_symbol_within_k_and_the_file_measure_is_separate() -> None:
    case = _case(("symbol:a.py::f",), ("symbol:b.py::g", "symbol:b.py::h"), ("path:c.py",))
    ordered = [_ranked("a.py", "other"), _ranked("b.py", "h"), _ranked("x.py", "x"), _ranked("y.py", "y"), _ranked("z.py", "z"), _ranked("c.py", None, kind="file")]
    score = ev.score_ranking(case, ordered)
    assert (score["met_at_k"], score["file_met_at_k"], score["missed_at_k"]) == (1, 2, ["R1", "R3"])  # c.py is sixth; a.py is the right file, wrong symbol


def test_a_requirement_is_found_low_in_the_order_or_by_no_channel_at_all() -> None:
    case = _case(("symbol:a.py::f",), ("symbol:b.py::g",))
    ordered = [_ranked("x.py", "x"), _ranked("b.py", "other"), _ranked("a.py", "f", ranks={"dense": 12, "lexical": 30})]
    assert ev.candidate_ranks(case, ordered) == [
        {"requirement": "R1", "fused_rank": 3, "channel_ranks": {"dense": 12, "lexical": 30}, "file_fused_rank": 3},
        {"requirement": "R2", "fused_rank": None, "channel_ranks": {}, "file_fused_rank": 2},  # the file was found, the symbol by no channel
    ]


def test_a_section_with_a_heading_is_not_a_symbol() -> None:
    case = _case(("symbol:a.md::Title",))
    assert ev.score_ranking(case, [_ranked("a.md", "Title", kind="section")])["met_at_k"] == 0


def test_a_channels_order_is_its_own_and_leaves_out_what_it_did_not_find() -> None:
    first, second, neither = _ranked("a.py", "a", ranks={"dense": 2}), _ranked("b.py", "b", ranks={"dense": 1, "lexical": 9}), _ranked("c.py", "c", ranks={"lexical": 1})
    assert [item.hit.path for item in ev.ablation_order([first, second, neither], "dense")] == ["b.py", "a.py"]
    assert [item.hit.path for item in ev.ablation_order([first, second, neither], "hybrid")] == ["a.py", "b.py", "c.py"]


def test_the_pack_score_separates_what_fits_from_what_is_about_other_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("def g():\n    return 2\n", encoding="utf-8")

    def real(name: str, symbol: str) -> Ranked:
        return _ranked(name, symbol, file_hash=hashlib.sha256((tmp_path / name).read_bytes()).hexdigest())

    score = ev.score_pack(_case(("symbol:a.py::f",)), [real("a.py", "f"), real("other.py", "g")], lambda path: (tmp_path / path).read_bytes(), 10_000)
    assert score["required_evidence_met"] == 1 and score["required_file_met"] == 1
    assert 0 < score["irrelevant_tokens"] < score["tokens"]
    assert score["stale_paths"] == 0


def _real(root: Path, name: str, symbol: str) -> Ranked:
    return _ranked(name, symbol, file_hash=hashlib.sha256((root / name).read_bytes()).hexdigest())


def test_another_symbol_in_a_gold_file_is_irrelevant_and_counts_exactly(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    other = _real(tmp_path, "a.py", "other")
    read = lambda path: (tmp_path / path).read_bytes()  # noqa: E731
    only_other = ev.score_pack(_case(("symbol:a.py::f",)), [other], read, 10_000)
    line = ev._signature_line(other.hit)
    excerpt = ev._excerpt(read("a.py"), other.hit)
    assert only_other["required_evidence_met"] == 0 and only_other["required_file_met"] == 1
    assert only_other["irrelevant_tokens"] == ev.estimate(line) + ev.estimate(f"--- {ev._where(other.hit)} ---\n{excerpt}")  # signature and body are both rendered


def test_a_signature_only_item_counts_its_line_alone(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    item = _real(tmp_path, "a.py", "g")
    line = ev._signature_line(item.hit)
    selected = ev.Selected("a.py", "symbol", "g", "0", 1, 1, "signature")
    assert ev._shown_tokens(selected, {("a.py", "g", 1): item}, lambda _path: None, {line}) == ev.estimate(line)
    assert ev._shown_tokens(selected, {("a.py", "g", 1): item}, lambda _path: None, set()) == 0


def test_off_uses_what_the_result_says_it_showed_not_headers_quoted_in_a_file(tmp_path: Path) -> None:
    files = {"a.py": "# --- b.py ---\nx\n", "b.py": "y\n"}
    read = lambda path: files[path].encode("utf-8")  # noqa: E731
    first, second = "--- a.py ---\n# --- b.py ---\nx\n", "--- b.py ---\ny\n"
    assert ev._blocks(f"{first}\n{second}", ["a.py", "b.py"], read) == [("a.py", first), ("b.py", second)]  # both shown, and a quotes b's header
    assert ev._blocks("--- a.py ---\n# --- b.py", ["a.py"], read) == [("a.py", "--- a.py ---\n# --- b.py")]  # truncated
    with pytest.raises(ValueError, match="did not show"):
        ev._blocks("something else", ["a.py"], read)


def test_off_scores_the_real_selection_when_a_file_quotes_anothers_header(tmp_path: Path) -> None:
    (tmp_path / "alpha.py").write_bytes(b"# --- beta.py ---\nvalue = 1\n")
    (tmp_path / "beta.py").write_bytes(b"value = 2\n")
    score = ev.score_off(_case(("path:beta.py",)), tmp_path, query="compare alpha.py and beta.py")
    assert score["files"] == 2 and score["met_at_k"] is None and score["pack"]["required_evidence_met"] is None and score["pack"]["required_file_met"] == 1
    shown = ev.assemble_workspace_context_for_prompt(tmp_path, task="compare alpha.py and beta.py").text
    assert score["pack"]["tokens"] == ev.estimate(shown)
    assert score["pack"]["irrelevant_tokens"] == ev.estimate(shown) - ev.estimate("--- beta.py ---\nvalue = 2\n")


def test_a_context_of_only_an_omission_list_is_all_irrelevant(tmp_path: Path) -> None:
    (tmp_path / "wanted.py").write_bytes(b"value = 1\n" * 40_000)
    score = ev.score_off(_case(("path:wanted.py",)), tmp_path, query="compare wanted.py")
    assert score["pack"]["required_file_met"] == 0 or score["pack"]["irrelevant_tokens"] < score["pack"]["tokens"]
    if score["files"] == 0:
        assert score["pack"]["irrelevant_tokens"] == score["pack"]["tokens"]


def test_records_that_do_not_describe_this_tree_are_counted(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"x")
    right = hashlib.sha256(b"x").hexdigest()
    assert ev.stale_or_missing_hits([_ranked("a.py", "f", file_hash=right)], tmp_path) == 0
    assert ev.stale_or_missing_hits([_ranked("a.py", "f"), _ranked("gone.py", "g", file_hash=right)], tmp_path) == 2


def test_each_measure_stays_separate_and_off_has_no_symbol_recall() -> None:
    row = {"requirements": 2, "met_at_k": 1, "file_met_at_k": 2, "missed_at_k": ["R2"], "pack": {"tokens": 10, "budget_tokens": 16, "required_evidence_met": 2, "required_file_met": 2, "irrelevant_tokens": 3, "stale_paths": 0}}
    off = {**row, "met_at_k": None, "missed_at_k": None, "pack": {**row["pack"], "required_evidence_met": None}}
    coverage = {"complete": False, "files_indexed": 3, "files_total": 4, "unsupported": 1, "excluded": 2}
    result = ev.aggregate([{"requirements": 2, "stale_or_missing_records": 1, "coverage": coverage, "ablations": {"off": off, "lexical": row, "dense": row, "hybrid": row}}])
    assert result["hybrid"]["recall_at_5"] == 0.5 and result["hybrid"]["file_recall_at_5"] == 1.0 and result["hybrid"]["required_evidence_in_context"] == 1.0
    assert result["off"]["recall_at_5"] is None and result["off"]["required_evidence_in_context"] is None and result["off"]["required_file_in_context"] == 1.0 and result["off"]["cases_with_all_required_evidence"] is None
    assert result["hybrid"]["cases_with_all_required_evidence"] == 1
    assert result["stale_or_missing_file_records"] == 1
    assert result["coverage"] == {"incomplete_cases": 1, "files_indexed": 3, "files_total": 4, "unsupported": 1, "excluded": 2}


def _gold(tmp_path: Path) -> Path:
    (tmp_path / "localization.json").write_text(json.dumps({"cases": []}), encoding="utf-8")
    return tmp_path


def test_held_out_is_refused_until_the_operator_approves_targets_for_this_exact_gold(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    ev.refuse_unapproved_held_out(["train", "development"], {"retrieval": "not yet"}, gold)
    with pytest.raises(ev.HeldOutRefused, match="not approved"):
        ev.refuse_unapproved_held_out(["held_out"], {"retrieval": "not yet"}, gold)
    limits = [{"metric": "hybrid recall at 5", "limit": 0.5}]
    for wrong in ({"state": "APPROVED_PENDING", "limits": limits}, {"state": "APPROVED"}, {"state": "APPROVED", "limits": []}, {"state": "APPROVED", "limits": [{"metric": "m", "limit": True}]}, {"state": "APPROVED", "limits": [{"metric": "m"}]}):
        with pytest.raises(ev.HeldOutRefused, match="not approved"):
            ev.refuse_unapproved_held_out(["held_out"], {"retrieval": {**wrong, "sealed_gold_sha256": ev.gold_digest(gold)}}, gold)
    with pytest.raises(ev.HeldOutRefused, match="not the one"):
        ev.refuse_unapproved_held_out(["held_out"], {"retrieval": {"state": "APPROVED", "limits": limits, "sealed_gold_sha256": "hex:0"}}, gold)
    ev.refuse_unapproved_held_out(["held_out"], {"retrieval": {"state": "APPROVED", "limits": limits, "sealed_gold_sha256": ev.gold_digest(gold)}}, gold)


def test_a_cutoff_tree_holds_exactly_that_commit_even_past_the_windows_path_limit(tmp_path: Path) -> None:
    source = tmp_path / "source"
    deep = "/".join(["d" * 40] * 7)
    git = ["git", "-C", str(source), "-c", "core.longpaths=true", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
    (m1_scale.long_path(source) / deep).mkdir(parents=True)
    (m1_scale.long_path(source) / deep / "old.py").write_bytes(b"old = 1\n")
    subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "first"], check=True, capture_output=True)
    first = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    (m1_scale.long_path(source) / "later.py").write_bytes(b"later = 1\n")
    subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "later"], check=True, capture_output=True)
    target = tmp_path / "tree"
    ev.materialize(source, first, target, branch="cutoff")
    # git archive applies this checkout's line-ending setting, as a real checkout here would
    assert (m1_scale.long_path(target) / deep / "old.py").read_bytes().replace(b"\r\n", b"\n") == b"old = 1\n"
    assert not (target / "later.py").exists()
    assert subprocess.run(["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"], check=True, capture_output=True, text=True).stdout.strip() == "cutoff"
    ev.materialize(source, first, target, branch="cutoff")  # a second run replaces it

