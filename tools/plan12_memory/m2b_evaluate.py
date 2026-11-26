"""Plan 12.14 M2b evaluation: `python -m tools.plan12_memory.m2b_evaluate --config reports/plan12-memory-m2b/run-config.json --phase calibration --output ...`.

Calibration (Task 1) runs three independent real-index repetitions of the development set. Each repetition provisions the released Redis
afresh, indexes each cutoff tree with that set's poisoned file and positive control (cases.json injections), retrieves each task once and
captures what retrieval returned; every packing policy is then scored on that same capture, so the policies differ only in packing. The
budget cases are measured on main's tree: R, T, C, the chosen budget, and the B/U (legacy) and F (model-aware) packs' bytes and digests.

No generative or provider call is possible: the Gateway's upstream is an unroutable local address. The fresh set is refused here: it is opened
once, in Task 4 qualification (`--phase qualification`), which replays the four historical sets first, each on its own, then the fresh set
with its poison and control, and gates F's required coverage against U's on every set. Records carry counts, hashes and identifiers, never
source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from context_engine.context_pack import SECTION_BODIES, SECTION_REQUIRED, Pack, assemble_pack
from context_engine.file_outline import summary_target
from context_engine.pack_utility import POLICIES
from context_engine.retrieval import Ranked, Retrieval, Retriever, read_catalogue, seed_map
from optimus.context.context_budget import BudgetPolicy, legacy_budget, plan_budget
from optimus.context.memory_session import MAP_CHARS
from optimus.context.memory_workspace import FastembedEmbedder
from tools.plan12_memory import m1_evaluate, m1_scale
from tools.plan12_memory.contracts import GoldenCase

CALIBRATION_SETS = ("development",)
REPETITIONS = 3
IRRELEVANT_MAX = 16_000
D3_USABLE_INPUT = min(1_000_000, 262_144) - 32_768  # the D3 entry's endpoint window, the policy ceiling and the implementer reserve (manifest.json)
D3_TARGET_USD = Decimal("0.008192")
D3_INPUT_PRICE = Decimal("0.50")
Q_INPUT_CAP = 65_536
FRAMING_TOKENS = 2 * 16 + 256  # the D3 estimator: 16 per message (system, user) and 256 fixed
estimate = m1_evaluate.estimate


class FreshRefused(SystemExit):
    pass


@dataclass(frozen=True)
class Capture:
    """One retrieval, kept so every policy packs the same input."""

    case: GoldenCase
    query: str
    ranked: tuple[Ranked, ...]
    protected: tuple[str, ...]
    read: Callable[[str], bytes | None]


def load_set(repository: Path, cases_record: Mapping[str, Any], name: str, *, qualification: bool = False) -> list[GoldenCase]:
    if name == "fresh" and not qualification:
        raise FreshRefused("the fresh set is opened once, in Task 4 qualification, never in calibration")
    spec = cases_record["packing_sets"][name]
    out: list[GoldenCase] = []
    for fixture, splits in spec["fixtures"].items():
        path = repository / fixture
        digest = "hex:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != spec["fixture_sha256"][fixture]:
            raise SystemExit(f"{fixture} is not the frozen fixture ({digest})")
        payload = json.loads(path.read_text(encoding="utf-8"))
        out.extend(case for case in map(GoldenCase.model_validate, payload["cases"]) if case.split in splits and case.kind == "localization")
    return out


def control_case(injection: Mapping[str, Any], snapshot: str, cutoff: str) -> GoldenCase:
    control = injection["control"]["case"]
    return GoldenCase.model_validate({
        "schema": "plan12-memory-case/1", "case_id": control["case_id"], "version": 1, "family": control["case_id"].split("-")[0], "split": "development",
        "kind": "localization", "role": "control", "oracles": ["K2"], "inputs": [{"seq": 0, "actor": "user", "text": control["query"], "attempt": None}],
        "project_id": "optimus-cost-agent", "snapshot": snapshot, "cutoff": cutoff, "expected_action": "answer", "required_facts": [],
        "required_evidence": control["required_evidence"], "prohibited_claims": [], "required_events": [], "prohibited_events": [], "expected_memory": [],
        "expected_rank": [], "expected_cost": None, "verification": "positive control (cases.json injections)",
        "provenance": {"drafted_by": "claude", "verified_by": None, "source": "Plan 12.14 Task 0 cases.json injections"},
    })


def inject(tree: Path, injection: Mapping[str, Any]) -> None:
    """The set's poison and control, committed into the cutoff tree so the real policy and worker index them as ordinary files. They take
    the tree's own archive date (materialize gives every file its commit time), so recency neither favours them nor varies with the clock."""
    anchor = (m1_scale.long_path(tree) / "pyproject.toml").stat().st_mtime
    for key in ("poison", "control"):
        item = injection[key]
        data = item["text"].encode("utf-8")
        assert "hex:" + hashlib.sha256(data).hexdigest() == item["sha256"], f"{item['path']} is not the frozen text"
        target = m1_scale.long_path(tree) / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.utime(target, (anchor, anchor))
    m1_scale._git(tree, "add", "-A")
    m1_scale._git(tree, "commit", "-q", "-m", "plan 12.14 injections")


def shown(pack: Pack) -> list[Any]:
    return [item for item in pack.selected if item.disclosure in {"body", "signature"}]


def score_pack(case: GoldenCase, capture: Capture, pack: Pack, *, poison_path: str | None) -> dict[str, Any]:
    """M1's pack measures, plus the poison's own tokens. An item shown as a body can also have its signature line shown."""
    items = shown(pack)
    met = [r.requirement_id for r in case.required_evidence if any(m1_evaluate.meets(e, i.path, i.symbol if i.kind == "symbol" else None) for e in r.any_of for i in items)]
    by_id = {(entry.hit.path, entry.hit.symbol, entry.hit.start_line): entry for entry in capture.ranked}
    signature_lines = set(pack.text.split(SECTION_BODIES, 1)[0].splitlines())

    def tokens(item: Any) -> int:
        return m1_evaluate._shown_tokens(item, by_id, capture.read, signature_lines)

    irrelevant = sum(tokens(i) for i in items if not m1_evaluate._accepted(case, i.path, i.symbol if i.kind == "symbol" else None))
    poison = sum(tokens(i) for i in items if i.path == poison_path)
    return {"requirements": len(case.required_evidence), "evidence_in_context": len(met), "met": met, "tokens": pack.tokens, "irrelevant_tokens": irrelevant,
            "poison_tokens": poison, "poison_shown": any(i.path == poison_path for i in items), "stale_paths": len(pack.stale_paths),
            "pack_sha256": "hex:" + hashlib.sha256(pack.text.encode("utf-8")).hexdigest()}


def score_capture(capture: Capture, *, budget: int, poison_path: str | None) -> dict[str, Any]:
    ranking = m1_evaluate.score_ranking(capture.case, capture.ranked)  # the same ranked list for every policy: recall at five cannot differ
    policies = {}
    for policy in POLICIES:
        pack = assemble_pack(required=(), ranked=capture.ranked, read=capture.read, estimate=estimate, budget_tokens=budget, policy=policy, task=capture.query, protected=capture.protected)
        policies[policy] = score_pack(capture.case, capture, pack, poison_path=poison_path)
    return {"case_id": capture.case.case_id, "role": capture.case.role, "snapshot": capture.case.snapshot, "ranking": ranking, "protected": len(capture.protected), "policies": policies}


def totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per policy over the probes of one repetition; the positive control is counted on its own."""
    probes = [row for row in rows if row["role"] == "probe"]
    controls = [row for row in rows if row["role"] == "control"]
    out: dict[str, dict[str, Any]] = {}
    for policy in POLICIES:
        packs = [row["policies"][policy] for row in probes]
        out[policy] = {
            "cases": len(packs), "requirements": sum(p["requirements"] for p in packs), "evidence_in_context": sum(p["evidence_in_context"] for p in packs),
            "irrelevant_tokens": sum(p["irrelevant_tokens"] for p in packs), "max_irrelevant_tokens": max((p["irrelevant_tokens"] for p in packs), default=0),
            "poison_tokens": sum(p["poison_tokens"] for p in packs), "poison_shown": sum(p["poison_shown"] for p in packs), "stale_paths": sum(p["stale_paths"] for p in packs),
            "control_admitted": sum(row["policies"][policy]["evidence_in_context"] for row in controls), "controls": len(controls),
            "met_at_5": sum(row["ranking"]["met_at_k"] for row in probes),
        }
    return out


def candidate_passes(candidate: str, repetitions: Sequence[Mapping[str, dict[str, Any]]]) -> dict[str, Any]:
    """The plan's development gates for one candidate against the baseline, every repetition. Incomplete repetitions are inconclusive."""
    reasons: list[str] = []
    if len(repetitions) != REPETITIONS:
        return {"passes": False, "inconclusive": True, "reasons": [f"{len(repetitions)} of {REPETITIONS} repetitions completed"]}
    for number, rep in enumerate(repetitions, start=1):
        base, cand = rep["baseline"], rep[candidate]
        if cand["evidence_in_context"] < base["evidence_in_context"]:
            reasons.append(f"repetition {number}: evidence in context below the baseline")
        if cand["irrelevant_tokens"] > base["irrelevant_tokens"]:
            reasons.append(f"repetition {number}: irrelevant tokens above the baseline")
        if cand["max_irrelevant_tokens"] > IRRELEVANT_MAX:
            reasons.append(f"repetition {number}: a case over {IRRELEVANT_MAX} irrelevant tokens")
        if cand["stale_paths"]:
            reasons.append(f"repetition {number}: stale evidence shown")
        if cand["poison_tokens"] > base["poison_tokens"]:
            reasons.append(f"repetition {number}: the poison gained tokens")
        if cand["control_admitted"] < base["control_admitted"]:
            reasons.append(f"repetition {number}: the positive control admitted less often")
        if cand["met_at_5"] != base["met_at_5"]:
            reasons.append(f"repetition {number}: recall at five changed")
    if not any(rep[candidate]["evidence_in_context"] > rep["baseline"]["evidence_in_context"] for rep in repetitions):
        reasons.append("no strict development improvement")
    return {"passes": not reasons, "inconclusive": False, "reasons": reasons}


def select_candidate(repetitions: Sequence[Mapping[str, dict[str, Any]]]) -> dict[str, Any]:
    """Frozen before any run: a passing candidate with more total evidence wins, then fewer irrelevant tokens, then the plan's order
    (density before coverage). None passing keeps the baseline (U = B)."""
    verdicts = {candidate: candidate_passes(candidate, repetitions) for candidate in POLICIES[1:]}
    passing = [c for c in POLICIES[1:] if verdicts[c]["passes"]]

    def key(candidate: str) -> tuple[int, int, int]:
        return (-sum(rep[candidate]["evidence_in_context"] for rep in repetitions), sum(rep[candidate]["irrelevant_tokens"] for rep in repetitions), POLICIES.index(candidate))

    selected = min(passing, key=key) if passing else "baseline"
    return {"selected": selected, "u_equals_b": selected == "baseline", "verdicts": verdicts}


def required_tokens(paths: Sequence[str], read: Callable[[str], bytes | None], *, estimate: Callable[[str], int] = estimate) -> int | None:
    """R: the required text exactly as the pack serializes it, or None when a file cannot be read."""
    blocks = []
    for path in paths:
        data = read(path)
        if data is None:
            return None
        blocks.append(f"--- {path} ---\n{data.decode('utf-8')}")
    return estimate(f"{SECTION_REQUIRED}\n" + "\n".join(blocks)) if blocks else 0


def budget_case(case: Mapping[str, Any], retrieval: Retrieval, read: Callable[[str], bytes | None], *, policy: str, model_aware: BudgetPolicy,
                legacy: int, full_input: Callable[[str], int], pack_estimate: Callable[[str], int] = estimate, outline: bool = False) -> dict[str, Any]:
    """One paid budget/outline case's packs under the legacy budget (B/U) and the model-aware one (F), and the full input F would send.
    `pack_estimate` is the estimator the pack is given: production's route estimator in the budget phase (Codex CP1 round 122 finding 2).
    With `outline` (Task 3 delivered), F asks for the overflow outline exactly as a Chat turn does: the task's own summary target."""
    required = tuple(item["path"] for item in case["required_files"])
    r = required_tokens(required, read, estimate=pack_estimate)
    assert r is not None, case["case_id"]
    out: dict[str, Any] = {"case_id": case["case_id"], "kind": case.get("kind"), "R": r, "C": model_aware.ceiling, "T": model_aware.target, "legacy": legacy}
    arms = {}
    overview = summary_target(case["task"]) if outline else None
    for arm, ceiling, target in (("BU", legacy, None), ("F", model_aware.ceiling, model_aware.target)):  # F packs exactly as production: C and T
        pack = assemble_pack(required=required, ranked=retrieval.ranked, read=read, estimate=pack_estimate, budget_tokens=ceiling, policy=policy, task=case["task"],
                             protected=retrieval.protected, target_tokens=target, overview_path=overview)
        budget = pack.budget_tokens
        optional = [(i.path, i.symbol, i.start_line, i.disclosure) for i in shown(pack)]
        v = pack.outline["section_tokens"] if pack.outline is not None else r  # an outline row's required cost is its outline, not R (Fable CP2 finding 6)
        arms[arm] = {"budget": budget, "complete": pack.complete, "tokens": pack.tokens, "optional_room": budget - v if pack.complete else None,
                     "optional_items": len(optional), "optional_digest": "hex:" + hashlib.sha256(json.dumps(optional).encode()).hexdigest(),
                     "pack_bytes": len(pack.text.encode("utf-8")), "pack_sha256": "hex:" + hashlib.sha256(pack.text.encode("utf-8")).hexdigest(),
                     "full_input_tokens": full_input(pack.text) if pack.complete else None, "outline": pack.outline is not None,
                     "outline_section_tokens": v if pack.outline is not None else None}  # V, so item 11's optional_room = budget - V is checkable
    out["arms"] = arms
    out["substantive_change"] = arms["BU"]["pack_sha256"] != arms["F"]["pack_sha256"] and (arms["BU"]["optional_digest"] != arms["F"]["optional_digest"] or arms["BU"]["complete"] != arms["F"]["complete"])
    full = arms["F"]["full_input_tokens"]
    out["fits_q_cap"] = full is not None and full <= Q_INPUT_CAP
    out["r_in_legacy_to_ceiling"] = legacy < r <= model_aware.ceiling
    return out


BUDGET_KINDS: Final = {"QB1": "ordinary-fit", "QB2": "ordinary-fit", "QB3": "required-over-legacy", "QB4": "required-over-legacy", "QO1": "outline", "QO2": "outline",
                       "QO3": "whole-summary", "QO4": "exact-over-ceiling"}  # pinned by id: a row's own kind is never trusted (Codex CP1 attempt 3 finding 6)
BUDGET_CASES: Final = tuple(BUDGET_KINDS)
# Each kind's pack completeness in (B/U, F) before Task 3's outline: over-ceiling files are incomplete in both until then.
BUDGET_OUTCOMES: Final = {"ordinary-fit": (True, True), "required-over-legacy": (False, True), "whole-summary": (True, True), "outline": (False, False),
                          "exact-over-ceiling": (False, False)}
# Once Task 3's outline exists, F completes an outline case with it; B/U never outlines (a legacy budget has no hard ceiling to exceed).
OUTLINE_OUTCOMES: Final = {**BUDGET_OUTCOMES, "outline": (False, True)}


def budget_gates(rows: Sequence[Mapping[str, Any]], *, outline_available: bool = False) -> dict[str, Any]:
    """One measurement's eight budget/outline rows, each exactly once with both arms and its kind's own outcome (Codex CP1 round 122
    finding 6; attempt 2 finding 6); apply it per repetition. With `outline_available` an outline case also needs F's pack to carry the
    outline, and nothing else may (Plan 12.14 Task 3)."""
    outcomes = OUTLINE_OUTCOMES if outline_available else BUDGET_OUTCOMES
    ids = sorted(row["case_id"] for row in rows)
    if ids != sorted(BUDGET_CASES):
        return {"checks": {"exact_case_set": False}, "passes": False, "case_ids": ids}
    if any(set(row.get("arms", {})) != {"BU", "F"} for row in rows):
        return {"checks": {"exact_case_set": True, "both_arms": False}, "passes": False}
    if any(row.get("kind") != BUDGET_KINDS[row["case_id"]] for row in rows):
        return {"checks": {"exact_case_set": True, "both_arms": True, "kinds_pinned": False}, "passes": False}
    budget = [row for row in rows if row["case_id"].startswith("QB")]
    ordinary = [row for row in budget if row["kind"] == "ordinary-fit"]
    over = [row for row in budget if row["kind"] == "required-over-legacy"]
    beyond = [row for row in rows if row["kind"] in {"outline", "exact-over-ceiling"}]
    checks = {
        "all_four_change": len(budget) == 4 and all(row["substantive_change"] for row in budget),
        "two_ordinary_allocation_changes": len(ordinary) == 2 and all(row["substantive_change"] for row in ordinary),
        "two_r_in_legacy_to_ceiling": len(over) == 2 and all(row["r_in_legacy_to_ceiling"] for row in over),
        "three_r_over_ceiling": len(beyond) == 3 and all(row["R"] > row["C"] for row in beyond),
        "each_kinds_outcome": all((row["arms"]["BU"]["complete"], row["arms"]["F"]["complete"]) == outcomes[row["kind"]] for row in rows),
        "outline_only_where_asked": all(row["arms"]["BU"].get("outline") is not True and row["arms"]["F"].get("outline", False) == (outline_available and row["kind"] == "outline")
                                        for row in rows),
        "every_complete_f_fits_q_cap": all(row["fits_q_cap"] for row in rows if row["arms"]["F"]["complete"]),
        "exact_case_set": True,
        "both_arms": True,
        "kinds_pinned": True,
    }
    return {"checks": checks, "passes": all(checks.values())}


COVERAGE_LINE_ALLOWANCE: Final = "x" * 600  # an upper bound on the memory turn's scope line, which this proxy does not render


def full_input(prefix: str, task: str, estimate_request: Callable[[str], int] | None = None) -> Callable[[str], int]:
    """The request F would send: the indexed Chat prefix with its map, the pack, the scope-line allowance, the runner's limit observation and
    the task. With the route's estimator its framing is its own; without one, the byte count plus FRAMING_TOKENS. Task 2 proves the
    production builder's bytes; this bounds the input against Q's cap before any paid prompt."""
    from optimus.agent.index_turn import LIMIT_OBSERVATION

    def tokens(pack_text: str) -> int:
        text = f"{prefix}\n{pack_text}\n{COVERAGE_LINE_ALLOWANCE}\n{LIMIT_OBSERVATION}\n{task}"
        return estimate_request(text) if estimate_request is not None else estimate(text) + FRAMING_TOKENS

    return tokens


def retrieve(retriever: Retriever, query: str, *, named: Sequence[str] = ()) -> Retrieval:
    """Calibration's call, frozen with its released evidence. The budget pass uses production_retrieve."""
    retrieval = retriever.retrieve(query, named_paths=named)
    assert retrieval.state == "ok", retrieval.state
    return retrieval


def production_retrieve(retriever: Retriever, task: str, *, named: Sequence[str]) -> Retrieval:
    """A Chat turn's own call (MemoryTurn._retrieve, whose selection text is the task): the task's first _QUERY_CHARS, the named files and
    the symbols the task names, so the budget pass packs what production packs (Codex CP1 attempt 3 finding 2)."""
    from optimus.context.memory_session import _QUERY_CHARS, named_symbols

    retrieval = retriever.retrieve(task[:_QUERY_CHARS], named_paths=named, named_symbols=named_symbols(task))
    assert retrieval.state == "ok", retrieval.state
    return retrieval


def policy_reader(root: Path) -> Callable[[str], bytes | None]:
    """Production's admitted reader (MemoryTurn._read): the includable-files policy decides, so a denied or ignored file is never read."""
    from optimus.guardrails.file_policy import FilePolicy, FilePurpose

    policy = FilePolicy(root)  # the plain root, as a launch has it: a long-path prefix fails its identity check

    def read(path: str) -> bytes | None:
        decision, data = policy.read(path, purpose=FilePurpose.AUTOMATIC)
        return data if decision.allowed else None

    return read


def run_calibration(config: Mapping[str, Any], repository: Path, out: Path) -> dict[str, Any]:
    cases_record = json.loads((repository / config["cases"]).read_text(encoding="utf-8"))
    development = load_set(repository, cases_record, "development")
    injection = cases_record["injections"]["sets"]["development"]
    head = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    legacy = legacy_budget(D3_USABLE_INPUT)
    model_aware = plan_budget(D3_USABLE_INPUT, input_target_usd=D3_TARGET_USD, input_usd_per_million=D3_INPUT_PRICE, cache_write=True)
    report: dict[str, Any] = {"schema": "plan12-memory-m2b.calibration.v1", "head": f"git:{head}", "label": config["label"], "estimator": "one token per UTF-8 byte (pack); framing 16 per message + 256 fixed",
                              "budget": {"legacy": legacy, "C": model_aware.ceiling, "T": model_aware.target}, "cases_sha256": "hex:" + hashlib.sha256((repository / config["cases"]).read_bytes()).hexdigest(),
                              "repetitions": [], "limits": ["Recency sees commit-time file dates in these copies, so it is noise here.", "One development set; selection, not qualification."]}
    snapshots: dict[str, list[GoldenCase]] = {}
    for case in sorted(development, key=lambda c: c.cutoff):
        snapshots.setdefault(case.snapshot.removeprefix("git:"), []).append(case)
    for number in range(1, REPETITIONS + 1):
        rows, trees = _repetition(config, repository, snapshots, injection, number=number, legacy=legacy, model_aware=model_aware, cases_record=cases_record, report=report)
        report["repetitions"].append({"number": number, "trees": trees, "cases": rows, "totals": totals([r for r in rows if not r["case_id"].startswith("Q")])})
        _write(report, out)
    report["selection"] = select_candidate([rep["totals"] for rep in report["repetitions"]])
    report["budget_gates"] = [{"repetition": rep["number"], **budget_gates([r for r in rep["cases"] if r["case_id"].startswith("Q")])}
                              for rep in report["repetitions"] if any(r["case_id"].startswith("Q") for r in rep["cases"])]
    _write(report, out)
    return report


def _repetition(config: Mapping[str, Any], repository: Path, snapshots: Mapping[str, Sequence[GoldenCase]], injection: Mapping[str, Any], *, number: int, legacy: int,
                model_aware: BudgetPolicy, cases_record: Mapping[str, Any], report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    work = repository / config["work_dir"] / f"rep-{number}"
    root, memory, _password, client, gateway, settings, settings_file = m1_scale._provision(dict(config), repository, work)
    rows: list[dict[str, Any]] = []
    trees: list[dict[str, Any]] = []
    try:
        embedder = m1_evaluate.CachedEmbedder(FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"]), embedding_cache(config, repository))
        if number == 1:
            report["wrong_branch_control"] = m1_evaluate.wrong_branch_control(work, settings, embedder)
        previous = None
        poison = injection["poison"]["path"]
        for revision, group in snapshots.items():
            tree = work / "trees" / revision[:12]
            m1_evaluate.materialize(repository, revision, tree, branch=f"cutoff-{revision[:12]}")
            inject(tree, injection)
            index = _index(tree, settings, embedder, trees, revision)
            retriever, read = Retriever(index.storage, embedder), policy_reader(tree)  # production's admitted reader (Codex CP1 attempt 2 finding 6)
            for case in [*group, control_case(injection, f"git:{revision}", group[0].cutoff.isoformat())]:
                query = next(item.text for item in case.inputs if item.actor == "user" and item.text)
                retrieval = retrieve(retriever, query)
                capture = Capture(case, query, retrieval.ranked, retrieval.protected, read)
                row = score_capture(capture, budget=legacy, poison_path=poison)
                row["stale_or_missing_records"] = m1_evaluate.stale_or_missing_hits(retrieval.ranked, tree)
                rows.append({**row, "case_id": row["case_id"] if case.role == "probe" else f"{row['case_id']}@{revision[:12]}"})
                rows[-1]["capture_sha256"] = save_capture(work / "captures" / f"{rows[-1]['case_id'].replace('@', '_')}.json", capture)
            previous = _rotate(previous, index, work, tree)
        if number == 1:  # main's tree and the baseline policy only: identical in every repetition (run 1, d7f060d), so measured once
            rows.extend(_budget_cases(config, repository, work, settings, embedder, cases_record, trees, legacy=legacy, model_aware=model_aware))
    finally:
        client.close()
        gateway.kill()
        gateway.wait(10)
        subprocess.run(["docker", "rm", "-f", config["container"]], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", "-f", config["volume"]], capture_output=True, check=False)
    return rows, trees


def embedding_cache(config: Mapping[str, Any], repository: Path) -> Path:
    """One content-keyed vector cache for every repetition and run: vectors are keyed by embedder identity and text hash, so a cached
    vector is the one the embedder returns. Each repetition still provisions a fresh store and builds its index with the real worker."""
    path = repository / config.get("embedding_cache", f"{config['work_dir']}/embedding-cache.sqlite")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_capture(path: Path, capture: Capture) -> str:
    """What retrieval returned, so any later policy can be re-scored offline. Ids, paths, lines, hashes and ranks only, never text."""
    record = {"case_id": capture.case.case_id, "query_sha256": "hex:" + hashlib.sha256(capture.query.encode("utf-8")).hexdigest(), "protected": list(capture.protected),
              "ranked": [{"id": r.hit.id, "kind": r.hit.kind, "path": r.hit.path, "symbol": r.hit.symbol, "file_hash": r.hit.file_hash, "start_line": r.hit.start_line,
                          "end_line": r.hit.end_line, "score": r.score, "ranks": dict(r.ranks)} for r in capture.ranked]}
    data = (json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return "hex:" + hashlib.sha256(data).hexdigest()


def _index(tree: Path, settings: Any, embedder: Any, trees: list[dict[str, Any]], revision: str) -> m1_scale._Index:
    index = m1_scale._Index(tree, settings, embedder, project="m2b-eval", parser_version="m2b-eval")
    started = time.perf_counter()
    outcome = m1_scale._required(index.worker().run(threading.Event()))
    trees.append({"revision": f"git:{revision}", "seconds": round(time.perf_counter() - started, 1), "records": outcome.records_written, "coverage": outcome.coverage})
    return index


def _rotate(previous: Any, index: Any, work: Path, tree: Path) -> Any:
    if previous is not None:  # the previous line stays until now, so a stale record had somewhere to come from
        m1_evaluate._drop(previous)
    for leftover in (work / "trees").iterdir():
        if leftover != tree:
            shutil.rmtree(m1_scale.long_path(leftover), onexc=m1_scale._clear_read_only)
    return index


def _budget_cases(config: Mapping[str, Any], repository: Path, work: Path, settings: Any, embedder: Any, cases_record: Mapping[str, Any], trees: list[dict[str, Any]], *,
                  legacy: int, model_aware: BudgetPolicy, outline: bool = False, turn: Any = None) -> list[dict[str, Any]]:
    """With `turn` (the Q launcher's memory turn on the paid rows' own session, Fable gate consult), the cases are measured through that
    turn's retriever, catalogue, admitted reader and map, so the budget report's packs are the ones the rows send (gate item 8)."""
    from optimus.agent.prompts import indexed_chat_prefix

    paid = [c for c in cases_record["paid_q"]["cases"] if c["category"] in {"budget", "outline"}]
    revision = paid[0]["snapshot"].removeprefix("git:")
    assert all(c["snapshot"] == f"git:{revision}" for c in paid)
    estimate_request = production_estimator()
    if turn is None:
        tree = work / "trees" / f"main-{revision[:12]}"
        m1_evaluate.materialize(repository, revision, tree, branch=f"main-{revision[:12]}")
        index = _index(tree, settings, embedder, trees, revision)
        read = policy_reader(tree)  # production's admitted reader (Codex CP1 round 122 finding 6)
        retriever = Retriever(index.storage, embedder)
        epoch = index.storage.call("coverage")["current"]["epoch"]
        repo_map = seed_map(index.storage, epoch, read_catalogue(index.storage, epoch), budget_chars=MAP_CHARS).text
    else:
        read, retriever, repo_map = turn._read, turn._retriever, turn.repo_map()  # noqa: SLF001 - the turn's own, exactly
    prefix = indexed_chat_prefix(repo_map=repo_map, tools_enabled=False)
    rows = []
    for case in paid:
        retrieval = production_retrieve(retriever, case["task"], named=[item["path"] for item in case["required_files"]])
        rows.append(budget_case(case, retrieval, read, policy="baseline", model_aware=model_aware, legacy=legacy, pack_estimate=estimate_request, outline=outline,
                                full_input=full_input(prefix, case["task"], estimate_request)))
    return rows


D3_MODEL: Final = "anthropic/claude-haiku-5.5"
D3_FIELD_LINE: Final = f'    context_budget: {{input_target_usd: "{D3_TARGET_USD}"}}\n'


def production_routes(work: Path) -> tuple[BudgetPolicy, BudgetPolicy, Callable[[str], int]]:
    """The legacy budget of the composition before Task 2 (the shipped defaults with only the D3 field line removed), the shipped
    route's model-aware budget and the route's own request estimator, all from attachment_limits exactly as a launch computes them."""
    from optimus.context.shipped_policy import attachment_limits
    from optimus_model_policy.binding import packaged_defaults, trusted_snapshot
    from optimus_model_policy.registry import load_registry

    text = packaged_defaults().read_text(encoding="utf-8")
    if text.count(D3_FIELD_LINE) != 1:
        raise ValueError("the packaged defaults do not carry the D3 field line exactly once")
    before = work / "defaults-without-d3.yaml"
    before.parent.mkdir(parents=True, exist_ok=True)
    before.write_text(text.replace(D3_FIELD_LINE, ""), encoding="utf-8")
    shipped = attachment_limits(trusted_snapshot(), D3_MODEL)
    legacy = attachment_limits(load_registry(before), D3_MODEL)
    return legacy.pack_budget, shipped.pack_budget, shipped.estimate_request


def production_estimator() -> Callable[[str], int]:
    from optimus.context.shipped_policy import attachment_limits
    from optimus_model_policy.binding import trusted_snapshot

    return attachment_limits(trusted_snapshot(), D3_MODEL).estimate_request


def run_budget(config: Mapping[str, Any], repository: Path, out: Path) -> dict[str, Any]:
    """One measurement of the eight budget/outline cases on main's tree with production's estimator, budgets and admitted reader."""
    cases_record = json.loads((repository / config["cases"]).read_text(encoding="utf-8"))
    head = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    work = repository / config["work_dir"] / "budget"
    legacy_policy, model_aware, _estimate = production_routes(work)
    assert legacy_policy.name == "legacy" and model_aware.name == "model-aware"
    report: dict[str, Any] = {"schema": "plan12-memory-m2b.budget.v1", "head": f"git:{head}", "label": config["label"], "estimator": "the D3 route's request estimator (attachment_limits)",
                              "reader": "FilePolicy, purpose AUTOMATIC", "budget": {"legacy": legacy_policy.ceiling, "C": model_aware.ceiling, "T": model_aware.target},
                              "cases_sha256": "hex:" + hashlib.sha256((repository / config["cases"]).read_bytes()).hexdigest(), "trees": []}
    root, memory, _password, client, gateway, settings, settings_file = m1_scale._provision(dict(config), repository, work)
    try:
        embedder = m1_evaluate.CachedEmbedder(FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"]),
                                              embedding_cache(config, repository))
        outline = bool(config.get("outline_available", False))
        report["outline_available"] = outline
        report["rows"] = _budget_cases(config, repository, work, settings, embedder, cases_record, report["trees"], legacy=legacy_policy.ceiling, model_aware=model_aware,
                                       outline=outline)
        report["budget_gates"] = budget_gates(report["rows"], outline_available=outline)
        report["embedding"] = {"embedded": embedder.embedded, "reused": embedder.reused}
        _write(report, out)
    finally:
        client.close()
        gateway.kill()
        gateway.wait(10)
        subprocess.run(["docker", "rm", "-f", config["container"]], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", "-f", config["volume"]], capture_output=True, check=False)
    return report


QUALIFICATION_SETS: Final = ("replay_seed_held_out", "replay_m1_held_out", "replay_fresh", "replay_fresh2", "fresh")  # fresh last: an earlier failure spends no opening
FRESH_REQUIREMENTS: Final = 40


def frozen_selection(repository: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Calibration's choice, read from its released report and never recomputed: no replacement or tuning against qualification."""
    data = (repository / config["calibration"]).read_bytes()
    digest = "hex:" + hashlib.sha256(data).hexdigest()
    if digest != config["calibration_sha256"]:
        raise FreshRefused(f"{config['calibration']} is not the released calibration ({digest})")
    selection = json.loads(data)["selection"]
    if selection["selected"] != "baseline":  # shortcut: only U = B is qualified here; a selected candidate needs the utility gates on every set first
        raise FreshRefused(f"calibration selected {selection['selected']}; its utility gates on the qualification sets are not built")
    return {"selected": selection["selected"], "u_equals_b": selection["u_equals_b"], "calibration_sha256": digest}


def budget_arms(capture: Capture, *, policy: str, legacy: int, model_aware: BudgetPolicy, pack_estimate: Callable[[str], int], poison_path: str | None) -> dict[str, Any]:
    """U: the selected policy at the legacy budget; F: the same policy at the model-aware ceiling and target. Both with the route's estimator,
    as a Chat turn packs; a localization task names no required file, so required coverage is the case's own requirements."""
    arms = {}
    for arm, ceiling, target in (("U", legacy, None), ("F", model_aware.ceiling, model_aware.target)):
        pack = assemble_pack(required=(), ranked=capture.ranked, read=capture.read, estimate=pack_estimate, budget_tokens=ceiling, policy=policy, task=capture.query,
                             protected=capture.protected, target_tokens=target)
        arms[arm] = {**score_pack(capture.case, capture, pack, poison_path=poison_path), "budget": pack.budget_tokens}
    return arms


def arm_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Per arm over one set's probes; its positive control is counted on its own."""
    probes = [row for row in rows if row["role"] == "probe"]
    controls = [row for row in rows if row["role"] == "control"]
    return {arm: {"cases": len(probes), "requirements": sum(r["arms"][arm]["requirements"] for r in probes),
                  "evidence_in_context": sum(r["arms"][arm]["evidence_in_context"] for r in probes),
                  "irrelevant_tokens": sum(r["arms"][arm]["irrelevant_tokens"] for r in probes), "stale_paths": sum(r["arms"][arm]["stale_paths"] for r in probes),
                  "poison_tokens": sum(r["arms"][arm]["poison_tokens"] for r in probes), "controls": len(controls),
                  "control_admitted": sum(r["arms"][arm]["evidence_in_context"] for r in controls)} for arm in ("U", "F")}


def qualification_gates(sets: Mapping[str, Mapping[str, Any]], cases_record: Mapping[str, Any]) -> dict[str, Any]:
    """Plan 12.14 Task 4's deterministic gates: every set measured with each frozen case and requirement, the fresh set's >= 40 requirements,
    and F's required coverage >= U's on every set (adoption gate: budgets). The utility gate is moot while U = B."""
    if sorted(sets) != sorted(QUALIFICATION_SETS):
        return {"checks": {"every_set_measured": False}, "passes": False, "sets": sorted(sets)}
    checks: dict[str, bool] = {"every_set_measured": True}
    for name in QUALIFICATION_SETS:
        spec, arms = cases_record["packing_sets"][name], sets[name]["arms"]
        checks[f"{name}: every frozen case and requirement"] = (arms["U"]["cases"], arms["U"]["requirements"]) == (spec["cases"], spec["requirements"])
        checks[f"{name}: F required coverage >= U"] = arms["F"]["evidence_in_context"] >= arms["U"]["evidence_in_context"]
    checks["fresh: at least 40 requirements"] = sets["fresh"]["arms"]["U"]["requirements"] >= FRESH_REQUIREMENTS
    checks["fresh: its positive control measured"] = sets["fresh"]["arms"]["U"]["controls"] > 0
    return {"checks": checks, "passes": all(checks.values()), "utility": "not applicable: calibration kept the baseline (U = B); every policy's packs are recorded per row"}


def run_qualification(config: Mapping[str, Any], repository: Path, out: Path) -> dict[str, Any]:
    """Task 4: one provisioned index store, the historical sets replayed first, each on its own, then the fresh set opened once. The report
    records the opening before the fresh fixture is read, so a second use is refused until a successor disposition is recorded."""
    if not config.get("authorization"):
        raise FreshRefused("no recorded release for the qualification run")
    if out.exists() and json.loads(out.read_text(encoding="utf-8")).get("fresh_opened"):
        raise FreshRefused(f"{out} records the fresh set opened; a second use needs a recorded successor disposition")
    cases_record = json.loads((repository / config["cases"]).read_text(encoding="utf-8"))
    selection = frozen_selection(repository, config)
    head = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    work = repository / config["work_dir"] / "qualification"
    legacy_policy, model_aware, pack_estimate = production_routes(work)
    assert legacy_policy.ceiling == legacy_budget(D3_USABLE_INPUT), "the utility record packs at calibration's legacy budget"
    report: dict[str, Any] = {"schema": "plan12-memory-m2b.qualification.v1", "head": f"git:{head}", "label": config["label"], "authorization": config["authorization"],
                              "selection": selection, "estimator": "utility record: one token per UTF-8 byte (calibration's); U and F arms: the D3 route's request estimator",
                              "retrieval": "production_retrieve (MemoryTurn._retrieve's call); reader FilePolicy, purpose AUTOMATIC",
                              "budget": {"legacy": legacy_policy.ceiling, "C": model_aware.ceiling, "T": model_aware.target},
                              "cases_sha256": "hex:" + hashlib.sha256((repository / config["cases"]).read_bytes()).hexdigest(), "fresh_opened": False, "sets": {}, "trees": []}
    root, memory, _password, client, gateway, settings, settings_file = m1_scale._provision(dict(config), repository, work)
    try:
        embedder = m1_evaluate.CachedEmbedder(FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"]),
                                              embedding_cache(config, repository))
        report["wrong_branch_control"] = m1_evaluate.wrong_branch_control(work, settings, embedder)
        previous = None
        for name in QUALIFICATION_SETS:
            if name == "fresh":
                report["fresh_opened"] = True
                _write(report, out)
            cases = load_set(repository, cases_record, name, qualification=True)
            rows, previous = _qualify_set(name, cases, cases_record["injections"]["sets"].get(name), repository, work, settings, embedder, report["trees"], previous,
                                          policy=selection["selected"], legacy=legacy_policy.ceiling, model_aware=model_aware, pack_estimate=pack_estimate)
            report["sets"][name] = {"rows": rows, "totals": totals(rows), "arms": arm_totals(rows)}
            _write(report, out)
        report["gates"] = qualification_gates(report["sets"], cases_record)
        report["embedding"] = {"embedded": embedder.embedded, "reused": embedder.reused}
        _write(report, out)
    finally:
        client.close()
        gateway.kill()
        gateway.wait(10)
        subprocess.run(["docker", "rm", "-f", config["container"]], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", "-f", config["volume"]], capture_output=True, check=False)
    return report


def _qualify_set(name: str, cases: Sequence[GoldenCase], injection: Mapping[str, Any] | None, repository: Path, work: Path, settings: Any, embedder: Any,
                 trees: list[dict[str, Any]], previous: Any, *, policy: str, legacy: int, model_aware: BudgetPolicy, pack_estimate: Callable[[str], int]) -> tuple[list[dict[str, Any]], Any]:
    """One set, each cutoff tree indexed by the real worker (with the set's poison and control when it has them), each case retrieved once by
    production's call; every policy's legacy pack is recorded (calibration's scoring) beside the selected policy's U and F packs."""
    snapshots: dict[str, list[GoldenCase]] = {}
    for case in sorted(cases, key=lambda c: c.cutoff):
        snapshots.setdefault(case.snapshot.removeprefix("git:"), []).append(case)
    poison = injection["poison"]["path"] if injection else None
    rows: list[dict[str, Any]] = []
    for revision, group in snapshots.items():
        tree = work / "trees" / f"{name}-{revision[:12]}"
        m1_evaluate.materialize(repository, revision, tree, branch=f"{name}-{revision[:12]}")
        if injection:
            inject(tree, injection)
        index = _index(tree, settings, embedder, trees, revision)
        trees[-1]["set"] = name
        retriever, read = Retriever(index.storage, embedder), policy_reader(tree)
        controls = [control_case(injection, f"git:{revision}", group[0].cutoff.isoformat())] if injection else []
        for case in [*group, *controls]:
            query = next(item.text for item in case.inputs if item.actor == "user" and item.text)
            retrieval = production_retrieve(retriever, query, named=())
            capture = Capture(case, query, retrieval.ranked, retrieval.protected, read)
            row = score_capture(capture, budget=legacy, poison_path=poison)
            row["arms"] = budget_arms(capture, policy=policy, legacy=legacy, model_aware=model_aware, pack_estimate=pack_estimate, poison_path=poison)
            row["stale_or_missing_records"] = m1_evaluate.stale_or_missing_hits(retrieval.ranked, tree)
            row["case_id"] = row["case_id"] if case.role == "probe" else f"{row['case_id']}@{revision[:12]}"
            row["capture_sha256"] = save_capture(work / "captures" / name / f"{row['case_id'].replace('@', '_')}.json", capture)
            rows.append(row)
        previous = _rotate(previous, index, work, tree)
    return rows, previous


def _write(report: Mapping[str, Any], out: Path) -> None:
    out.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("calibration", "budget", "qualification"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    repository = Path.cwd()
    config = json.loads((repository / args.config).read_text(encoding="utf-8"))
    if args.phase == "qualification":
        report = run_qualification(config, repository, repository / args.output)
        print(json.dumps({"qualification_gates": report["gates"]["passes"]}))
        return 0
    if args.phase == "budget":
        report = run_budget(config, repository, repository / args.output)
        print(json.dumps({"budget_gates": report["budget_gates"]["passes"]}))
        return 0
    report = run_calibration(config, repository, repository / args.output)
    print(json.dumps({"selection": report["selection"]["selected"], "repetitions": len(report["repetitions"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
