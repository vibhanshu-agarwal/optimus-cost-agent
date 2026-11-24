"""Plan 12.14 M2b evaluation: `python -m tools.plan12_memory.m2b_evaluate --config reports/plan12-memory-m2b/run-config.json --phase calibration --output ...`.

Calibration (Task 1) runs three independent real-index repetitions of the development set. Each repetition provisions the released Redis
afresh, indexes each cutoff tree with that set's poisoned file and positive control (cases.json injections), retrieves each task once and
captures what retrieval returned; every packing policy is then scored on that same capture, so the policies differ only in packing. The
budget cases are measured on main's tree: R, T, C, the chosen budget, and the B/U (legacy) and F (model-aware) packs' bytes and digests.

No generative or provider call is possible: the Gateway's upstream is an unroutable local address. The fresh set is refused here: it is opened
once, in Task 4 qualification. Records carry counts, hashes and identifiers, never source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from context_engine.context_pack import SECTION_BODIES, SECTION_REQUIRED, Pack, assemble_pack, chosen_budget
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


def load_set(repository: Path, cases_record: Mapping[str, Any], name: str) -> list[GoldenCase]:
    if name == "fresh":
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
    """The set's poison and control, committed into the cutoff tree so the real policy and worker index them as ordinary files."""
    for key in ("poison", "control"):
        item = injection[key]
        data = item["text"].encode("utf-8")
        assert "hex:" + hashlib.sha256(data).hexdigest() == item["sha256"], f"{item['path']} is not the frozen text"
        target = m1_scale.long_path(tree) / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
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


def required_tokens(paths: Sequence[str], read: Callable[[str], bytes | None]) -> int | None:
    """R: the required text exactly as the pack serializes it, or None when a file cannot be read."""
    blocks = []
    for path in paths:
        data = read(path)
        if data is None:
            return None
        blocks.append(f"--- {path} ---\n{data.decode('utf-8')}")
    return estimate(f"{SECTION_REQUIRED}\n" + "\n".join(blocks)) if blocks else 0


def budget_case(case: Mapping[str, Any], retrieval: Retrieval, read: Callable[[str], bytes | None], *, policy: str, model_aware: BudgetPolicy,
                legacy: int, full_input: Callable[[str], int]) -> dict[str, Any]:
    """One paid budget/outline case's packs under the legacy budget (B/U) and the model-aware one (F), and the full input F would send."""
    required = tuple(item["path"] for item in case["required_files"])
    r = required_tokens(required, read)
    assert r is not None, case["case_id"]
    out: dict[str, Any] = {"case_id": case["case_id"], "kind": case.get("kind"), "R": r, "C": model_aware.ceiling, "T": model_aware.target, "legacy": legacy}
    arms = {}
    for arm, budget in (("BU", legacy), ("F", chosen_budget(model_aware.ceiling, model_aware.target or model_aware.ceiling, r) if r <= model_aware.ceiling else model_aware.ceiling)):
        pack = assemble_pack(required=required, ranked=retrieval.ranked, read=read, estimate=estimate, budget_tokens=budget, policy=policy, task=case["task"], protected=retrieval.protected)
        optional = [(i.path, i.symbol, i.start_line, i.disclosure) for i in shown(pack)]
        arms[arm] = {"budget": budget, "complete": pack.complete, "tokens": pack.tokens, "optional_room": budget - r if pack.complete else None,
                     "optional_items": len(optional), "optional_digest": "hex:" + hashlib.sha256(json.dumps(optional).encode()).hexdigest(),
                     "pack_bytes": len(pack.text.encode("utf-8")), "pack_sha256": "hex:" + hashlib.sha256(pack.text.encode("utf-8")).hexdigest(),
                     "full_input_tokens": full_input(pack.text) if pack.complete else None}
    out["arms"] = arms
    out["substantive_change"] = arms["BU"]["pack_sha256"] != arms["F"]["pack_sha256"] and (arms["BU"]["optional_digest"] != arms["F"]["optional_digest"] or arms["BU"]["complete"] != arms["F"]["complete"])
    full = arms["F"]["full_input_tokens"]
    out["fits_q_cap"] = full is not None and full <= Q_INPUT_CAP
    out["r_in_legacy_to_ceiling"] = legacy < r <= model_aware.ceiling
    return out


def budget_gates(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    budget = [row for row in rows if row["case_id"].startswith("QB")]
    ordinary = [row for row in budget if row["kind"] == "ordinary-fit"]
    over = [row for row in budget if row["kind"] == "required-over-legacy"]
    checks = {
        "all_four_change": len(budget) == 4 and all(row["substantive_change"] for row in budget),
        "two_ordinary_allocation_changes": len(ordinary) == 2 and all(row["substantive_change"] and row["arms"]["F"]["complete"] for row in ordinary),
        "two_r_in_legacy_to_ceiling": len(over) == 2 and all(row["r_in_legacy_to_ceiling"] and row["arms"]["F"]["complete"] for row in over),
        "every_complete_f_fits_q_cap": all(row["fits_q_cap"] for row in rows if row["arms"]["F"]["complete"]),
    }
    return {"checks": checks, "passes": all(checks.values())}


def full_input(prefix: str, task: str) -> Callable[[str], int]:
    """The request F would send, as the D3 estimator counts it: the indexed Chat prefix with its map, the pack and the task, plus framing.
    Task 2 proves the production builder's bytes; this bounds the input against Q's cap before any paid prompt."""
    return lambda pack_text: estimate(f"{prefix}\n{pack_text}\n{task}") + FRAMING_TOKENS


def retrieve(retriever: Retriever, query: str, *, named: Sequence[str] = ()) -> Retrieval:
    retrieval = retriever.retrieve(query, named_paths=named)
    assert retrieval.state == "ok", retrieval.state
    return retrieval


def _reader(root: Path) -> Callable[[str], bytes | None]:
    def read(path: str) -> bytes | None:
        file = m1_scale.long_path(root) / path
        return file.read_bytes() if file.is_file() else None

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
    _write(report, out)
    return report


def _repetition(config: Mapping[str, Any], repository: Path, snapshots: Mapping[str, Sequence[GoldenCase]], injection: Mapping[str, Any], *, number: int, legacy: int,
                model_aware: BudgetPolicy, cases_record: Mapping[str, Any], report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    work = repository / config["work_dir"] / f"rep-{number}"
    root, memory, _password, client, gateway, settings, settings_file = m1_scale._provision(dict(config), repository, work)
    rows: list[dict[str, Any]] = []
    trees: list[dict[str, Any]] = []
    try:
        embedder = m1_evaluate.CachedEmbedder(FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"]), work / "embedding-cache.sqlite")
        if number == 1:
            report["wrong_branch_control"] = m1_evaluate.wrong_branch_control(work, settings, embedder)
        previous = None
        poison = injection["poison"]["path"]
        for revision, group in snapshots.items():
            tree = work / "trees" / revision[:12]
            m1_evaluate.materialize(repository, revision, tree, branch=f"cutoff-{revision[:12]}")
            inject(tree, injection)
            index = _index(tree, settings, embedder, trees, revision)
            retriever, read = Retriever(index.storage, embedder), _reader(tree)
            for case in [*group, control_case(injection, f"git:{revision}", group[0].cutoff.isoformat())]:
                query = next(item.text for item in case.inputs if item.actor == "user" and item.text)
                retrieval = retrieve(retriever, query)
                capture = Capture(case, query, retrieval.ranked, retrieval.protected, read)
                row = score_capture(capture, budget=legacy, poison_path=poison)
                row["stale_or_missing_records"] = m1_evaluate.stale_or_missing_hits(retrieval.ranked, tree)
                rows.append({**row, "case_id": row["case_id"] if case.role == "probe" else f"{row['case_id']}@{revision[:12]}"})
            previous = _rotate(previous, index, work, tree)
        rows.extend(_budget_cases(config, repository, work, settings, embedder, cases_record, trees, legacy=legacy, model_aware=model_aware))
    finally:
        client.close()
        gateway.kill()
        gateway.wait(10)
        subprocess.run(["docker", "rm", "-f", config["container"]], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", "-f", config["volume"]], capture_output=True, check=False)
    return rows, trees


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
                  legacy: int, model_aware: BudgetPolicy) -> list[dict[str, Any]]:
    from optimus.agent.prompts import indexed_chat_prefix

    paid = [c for c in cases_record["paid_q"]["cases"] if c["category"] in {"budget", "outline"}]
    revision = paid[0]["snapshot"].removeprefix("git:")
    assert all(c["snapshot"] == f"git:{revision}" for c in paid)
    tree = work / "trees" / f"main-{revision[:12]}"
    m1_evaluate.materialize(repository, revision, tree, branch=f"main-{revision[:12]}")
    index = _index(tree, settings, embedder, trees, revision)
    read = _reader(tree)
    retriever = Retriever(index.storage, embedder)
    epoch = index.storage.call("coverage")["current"]["epoch"]
    prefix = indexed_chat_prefix(repo_map=seed_map(index.storage, epoch, read_catalogue(index.storage, epoch), budget_chars=MAP_CHARS).text, tools_enabled=False)
    rows = []
    for case in paid:
        retrieval = retrieve(retriever, case["task"], named=[item["path"] for item in case["required_files"]])
        rows.append(budget_case(case, retrieval, read, policy="baseline", model_aware=model_aware, legacy=legacy, full_input=full_input(prefix, case["task"])))
    return rows


def _write(report: Mapping[str, Any], out: Path) -> None:
    out.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("calibration", "qualification"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    repository = Path.cwd()
    config = json.loads((repository / args.config).read_text(encoding="utf-8"))
    if args.phase == "qualification":
        raise FreshRefused("qualification opens in Task 4, after CP1")
    report = run_calibration(config, repository, repository / args.output)
    print(json.dumps({"selection": report["selection"]["selected"], "repetitions": len(report["repetitions"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
