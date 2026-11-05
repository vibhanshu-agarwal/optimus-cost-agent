"""Plan 12.10 M1 retrieval evaluation: `python -m tools.plan12_memory.m1_evaluate --config reports/plan12-memory-m1/run-config-eval.json --splits train,development`.

Each localization case is asked of a real index of its own cutoff tree, on the released Redis through the real route, and scored for four
ablations at a fixed budget: today's context (off), lexical, dense and the hybrid production ranking. No generative or provider call is possible:
the Gateway's upstream is an unroutable local address. The held-out split is refused until the operator has approved retrieval targets for
exactly this gold (targets.json `retrieval`). Records carry counts, hashes and identifiers from the gold, never source text.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sqlite3
import subprocess
import tarfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from context_engine.context_pack import SECTION_BODIES, Selected, _excerpt, _signature_line, _where, assemble_pack
from context_engine.retrieval import Ranked, Retriever
from optimus.agent.workspace_context import assemble_workspace_context_for_prompt
from optimus.context.memory_session import PACK_MAX_TOKENS, PACK_SHARE
from optimus.context.memory_workspace import FastembedEmbedder
from optimus_model_policy.registry import load_registry
from tools.plan12_memory import m1_scale
from tools.plan12_memory.contracts import GoldenCase

K = 5
ABLATIONS = ("off", "lexical", "dense", "hybrid")
RETRIEVED = ("lexical", "dense", "hybrid")


class HeldOutRefused(SystemExit):
    pass


def estimate(text: str) -> int:
    """The qualified route's configured estimator: one token per UTF-8 byte."""
    return len(text.encode("utf-8"))


def parse_evidence(evidence: str) -> tuple[str, str | None]:
    """`symbol:path::Name` or `path:path`, as (path, symbol or None)."""
    kind, _, rest = evidence.partition(":")
    if kind == "symbol":
        path, _, symbol = rest.partition("::")
        return path, symbol
    if kind == "path":
        return rest, None
    raise ValueError(f"unknown evidence id {evidence!r}")


def meets(evidence: str, path: str, symbol: str | None) -> bool:
    wanted_path, wanted_symbol = parse_evidence(evidence)
    return path == wanted_path and (wanted_symbol is None or symbol == wanted_symbol)


def gold_paths(case: GoldenCase) -> set[str]:
    return {parse_evidence(evidence)[0] for requirement in case.required_evidence for evidence in requirement.any_of}


def _accepted(case: GoldenCase, path: str, symbol: str | None) -> bool:
    """An accepted locus. Another symbol in a gold file is not one, so it counts as irrelevant."""
    return any(meets(evidence, path, symbol) for requirement in case.required_evidence for evidence in requirement.any_of)


def ablation_order(ranked: Sequence[Ranked], ablation: str) -> list[Ranked]:
    """The hybrid order is production's. A single channel's order is the position that channel itself reported, so no extra query can differ."""
    if ablation == "hybrid":
        return list(ranked)
    return sorted((item for item in ranked if ablation in item.ranks), key=lambda item: item.ranks[ablation])


def score_ranking(case: GoldenCase, ordered: Sequence[Ranked]) -> dict[str, Any]:
    """Recall at k: a requirement counts when one of its items is in the first k. The file measure is what a reader could open from those k."""
    top = [(item.hit.path, item.hit.symbol if item.hit.kind == "symbol" else None) for item in ordered[:K]]
    top_paths = {path for path, _symbol in top}
    met = [requirement.requirement_id for requirement in case.required_evidence if any(meets(evidence, path, symbol) for evidence in requirement.any_of for path, symbol in top)]
    files = [requirement.requirement_id for requirement in case.required_evidence if any(parse_evidence(evidence)[0] in top_paths for evidence in requirement.any_of)]
    return {"requirements": len(case.required_evidence), "met_at_k": len(met), "file_met_at_k": len(files), "missed_at_k": [requirement.requirement_id for requirement in case.required_evidence if requirement.requirement_id not in met]}


def _shown_tokens(item: Selected, ranked_by_id: Mapping[tuple[str, str | None, int | None], Ranked], contents: Callable[[str], bytes | None], signature_lines: set[str]) -> int:
    """Everything rendered for this item. An item shown as a body can also have its signature line shown."""
    source = ranked_by_id.get((item.path, item.symbol, item.start_line))
    if source is None:
        return 0
    line = _signature_line(source.hit)
    tokens = estimate(line) if line in signature_lines else 0
    if item.disclosure == "body":
        excerpt = _excerpt(contents(item.path) or b"", source.hit)
        tokens += estimate(f"--- {_where(source.hit)} ---\n{excerpt}") if excerpt else 0
    return tokens


def score_pack(case: GoldenCase, ordered: Sequence[Ranked], read: Callable[[str], bytes | None], budget: int) -> dict[str, Any]:
    """What the model would actually be given at this budget: which required evidence fits, and how much of the rest is about other files."""
    pack = assemble_pack(required=(), ranked=ordered, read=read, estimate=estimate, budget_tokens=budget)
    shown = [item for item in pack.selected if item.disclosure in {"body", "signature"}]
    met = [requirement.requirement_id for requirement in case.required_evidence if any(meets(evidence, item.path, item.symbol if item.kind == "symbol" else None) for evidence in requirement.any_of for item in shown)]
    files = {item.path for item in shown}
    file_met = [requirement.requirement_id for requirement in case.required_evidence if any(parse_evidence(evidence)[0] in files for evidence in requirement.any_of)]
    by_id = {(entry.hit.path, entry.hit.symbol, entry.hit.start_line): entry for entry in ordered}
    signature_lines = set(pack.text.split(SECTION_BODIES, 1)[0].splitlines())
    irrelevant = sum(_shown_tokens(item, by_id, read, signature_lines) for item in shown if not _accepted(case, item.path, item.symbol if item.kind == "symbol" else None))
    return {"tokens": pack.tokens, "budget_tokens": budget, "required_evidence_met": len(met), "required_file_met": len(file_met), "irrelevant_tokens": irrelevant, "stale_paths": len(pack.stale_paths)}


def score_off(case: GoldenCase, root: Path, *, query: str) -> dict[str, Any]:
    """Today's context, with the same question. It shows files, some truncated, and says which, so its measures are file-level only."""
    result = assemble_workspace_context_for_prompt(root, task=query)
    files = list(result.file_sha256s)
    relevant = gold_paths(case)
    met = [requirement.requirement_id for requirement in case.required_evidence if any(parse_evidence(evidence)[0] in files for evidence in requirement.any_of)]
    irrelevant = sum(estimate(block) for path, block in _blocks(result.text, files, lambda path: (m1_scale.long_path(root) / path).read_bytes()) if path not in relevant)
    first = set(files[:K])
    file_met = [requirement.requirement_id for requirement in case.required_evidence if any(parse_evidence(evidence)[0] in first for evidence in requirement.any_of)]
    return {"requirements": len(case.required_evidence), "met_at_k": None, "file_met_at_k": len(file_met), "missed_at_k": None,
            "pack": {"tokens": estimate(result.text), "budget_tokens": None, "required_evidence_met": None, "required_file_met": len(met), "irrelevant_tokens": irrelevant, "stale_paths": 0}, "files": len(files)}


def _blocks(text: str, files: Sequence[str], read: Callable[[str], bytes]) -> list[tuple[str, str]]:
    """Each shown file's text, stepped by its real length, so a header quoted inside one file cannot start another's block. Only the last can be truncated."""
    blocks: list[tuple[str, str]] = []
    position = 0
    for path in files:
        header = f"--- {path} ---\n"
        if not text.startswith(header, position):
            raise ValueError(f"the context did not show {path} where its result said")
        whole = header + read(path).decode("utf-8")
        end = position + len(whole) if text.startswith(whole, position) else len(text)
        blocks.append((path, text[position:end]))
        position = end + 1
    return blocks


def stale_or_missing_hits(ranked: Sequence[Ranked], root: Path) -> int:
    """Records whose file is gone or has other bytes in this tree. Zero tolerance in targets.json. Equal bytes on another branch would pass here,
    so wrong-branch evidence has its own control, `wrong_branch_control`."""
    wrong = 0
    known: dict[str, str | None] = {}
    for item in ranked:
        path = item.hit.path
        if path not in known:
            file = m1_scale.long_path(root) / path
            known[path] = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
        wrong += known[path] != item.hit.file_hash
    return wrong


def aggregate(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Each measure on its own, by ablation. No combined score, so one can never hide another."""
    out: dict[str, Any] = {"cases": len(cases), "requirements": sum(case["requirements"] for case in cases)}
    for ablation in ABLATIONS:
        rows = [case["ablations"][ablation] for case in cases]
        total = sum(row["requirements"] for row in rows)
        met = [row["met_at_k"] for row in rows if row["met_at_k"] is not None]
        packs = [row["pack"] for row in rows]
        evidence = [pack["required_evidence_met"] for pack in packs if pack["required_evidence_met"] is not None]
        out[ablation] = {
            "recall_at_5": round(sum(met) / total, 4) if len(met) == len(rows) and total else None,
            "file_recall_at_5": round(sum(row["file_met_at_k"] for row in rows) / total, 4) if total else None,
            "required_evidence_in_context": round(sum(evidence) / total, 4) if len(evidence) == len(rows) and total else None,
            "required_file_in_context": round(sum(pack["required_file_met"] for pack in packs) / total, 4) if total else None,
            "cases_with_all_required_evidence": sum(pack["required_evidence_met"] == row["requirements"] for pack, row in zip(packs, rows, strict=True)) if len(evidence) == len(rows) else None,
            "mean_context_tokens": round(sum(pack["tokens"] for pack in packs) / len(packs), 1) if packs else None,
            "mean_irrelevant_tokens": round(sum(pack["irrelevant_tokens"] for pack in packs) / len(packs), 1) if packs else None,
            "stale_paths": sum(pack["stale_paths"] for pack in packs),
        }
    out["stale_or_missing_file_records"] = sum(case["stale_or_missing_records"] for case in cases)
    coverage = [case["coverage"] for case in cases]
    out["coverage"] = {"incomplete_cases": sum(not item.get("complete") for item in coverage), "files_indexed": sum(item.get("files_indexed", 0) for item in coverage), "files_total": sum(item.get("files_total", 0) for item in coverage),
                       "unsupported": sum(item.get("unsupported", 0) for item in coverage), "excluded": sum(item.get("excluded", 0) for item in coverage)}
    return out


def load_cases(directory: Path, splits: Sequence[str]) -> list[GoldenCase]:
    payload = json.loads((directory / "localization.json").read_text(encoding="utf-8"))
    return [case for case in map(GoldenCase.model_validate, payload["cases"]) if case.split in splits]


def gold_digest(directory: Path) -> str:
    return "hex:" + hashlib.sha256((directory / "localization.json").read_bytes()).hexdigest()


def _numeric_limits(limits: Any) -> bool:
    return isinstance(limits, list) and bool(limits) and all(isinstance(item, dict) and isinstance(item.get("metric"), str) and isinstance(item.get("limit"), int | float) and not isinstance(item.get("limit"), bool) for item in limits)


def refuse_unapproved_held_out(splits: Sequence[str], targets: Mapping[str, Any], m1_gold: Path) -> None:
    """Targets are set from the baselines before the held-out set is opened, and they bind the exact gold the operator sealed."""
    if "held_out" not in splits:
        return
    retrieval = targets.get("retrieval")
    if not isinstance(retrieval, dict) or retrieval.get("state") != "APPROVED" or not _numeric_limits(retrieval.get("limits")):
        raise HeldOutRefused("held-out refused: the operator has not approved retrieval targets")
    if retrieval.get("sealed_gold_sha256") != gold_digest(m1_gold):
        raise HeldOutRefused("held-out refused: the gold is not the one the operator sealed")


class CachedEmbedder:
    """Consecutive cutoff trees share most of their text, so each text is embedded once. Keeps vectors keyed by a text hash, never the text."""

    def __init__(self, inner: FastembedEmbedder, path: Path) -> None:
        self._inner = inner
        self.identity = inner.identity
        self.dimensions = inner.dimensions
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("create table if not exists vectors (digest text primary key, vector blob not null)")
        self.embedded = 0
        self.reused = 0

    def embed(self, texts: Sequence[str]) -> list[bytes]:
        digests = [hashlib.sha256(f"{self.identity}\0{text}".encode()).hexdigest() for text in texts]
        with self._lock:
            found: dict[str, bytes] = {}
            for digest in dict.fromkeys(digests):
                row = self._db.execute("select vector from vectors where digest = ?", (digest,)).fetchone()
                if row is not None:
                    found[digest] = row[0]
        wanted = [position for position, digest in enumerate(digests) if digest not in found]
        if wanted:
            vectors = self._inner.embed([texts[position] for position in wanted])
            with self._lock:
                for position, vector in zip(wanted, vectors, strict=True):
                    found[digests[position]] = vector
                    self._db.execute("insert or replace into vectors values (?, ?)", (digests[position], vector))
                self._db.commit()
        self.embedded += len(wanted)
        self.reused += len(texts) - len(wanted)
        return [found[digest] for digest in digests]


def materialize(repository: Path, revision: str, target: Path, *, branch: str) -> None:
    """Exactly the cutoff tree, as its own repository, so a later commit cannot leak in and the real policy and worker see an ordinary checkout."""
    if target.exists():
        shutil.rmtree(m1_scale.long_path(target), onexc=m1_scale._clear_read_only)
    target.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(repository), "archive", "--format=tar", revision], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        archive.extractall(m1_scale.long_path(target), filter="data")
    m1_scale._git(target, "init", "-q", "-b", branch)
    m1_scale._git(target, "add", "-A")
    m1_scale._git(target, "commit", "-q", "-m", f"cutoff tree {revision[:12]}")


def _drop(index: m1_scale._Index) -> None:
    token = index.storage.call("lease", action="acquire", owner=index.owner, ttl_ms=60000, kind="scope")["token"]
    cursor = None
    while True:
        reply = index.storage.call("cleanup", action="drop", token=token, **({} if cursor is None else {"cursor": cursor}))
        cursor = reply.get("cursor")
        if cursor is None:
            return


def wrong_branch_control(work: Path, settings: Any, embedder: Any) -> dict[str, Any]:
    """The real route and worker on one checkout and two branches: a symbol only on the other branch must not reach this branch's line, and must reach its own, or the control proved nothing."""
    root = work / "wrong-branch-control"
    if root.exists():
        shutil.rmtree(root, onexc=m1_scale._clear_read_only)
    root.mkdir(parents=True)
    (root / "base.py").write_text("def base_function():\n    return 1\n", encoding="utf-8")
    m1_scale._git(root, "init", "-q", "-b", "evaluated")
    m1_scale._git(root, "add", "-A")
    m1_scale._git(root, "commit", "-q", "-m", "base")
    evaluated = m1_scale._Index(root, settings, embedder, project="m1-control", parser_version="m1-eval")
    m1_scale._required(evaluated.worker().run(threading.Event()))
    m1_scale._git(root, "checkout", "-q", "-b", "other")
    (root / "base.py").write_text("def base_function():\n    return 1\n\n\ndef m1otherbranchcanary():\n    return 2\n", encoding="utf-8")
    m1_scale._git(root, "add", "-A")
    m1_scale._git(root, "commit", "-q", "-m", "other")
    other = m1_scale._Index(root, settings, embedder, project="m1-control", parser_version="m1-eval")
    m1_scale._required(other.worker().run(threading.Event()))
    assert other.scope != evaluated.scope
    terms = ["m1otherbranchcanary"]
    result = {"hits_on_the_evaluated_branch": len(evaluated.storage.call("query", mode="lexical", terms=terms, k=5)["records"]), "hits_on_its_own_branch": len(other.storage.call("query", mode="lexical", terms=terms, k=5)["records"])}
    _drop(evaluated)
    _drop(other)
    return {**result, "wrong_branch_records": result["hits_on_the_evaluated_branch"], "positive_control_found_it": result["hits_on_its_own_branch"] > 0}


def evaluate_case(case: GoldenCase, index: m1_scale._Index, retriever: Retriever, root: Path, *, budget: int) -> dict[str, Any]:
    query = next(item.text for item in case.inputs if item.actor == "user" and item.text)

    def read(path: str) -> bytes | None:
        file = m1_scale.long_path(root) / path
        return file.read_bytes() if file.is_file() else None

    started = time.perf_counter()
    retrieval = retriever.retrieve(query)
    seconds = time.perf_counter() - started
    assert retrieval.state == "ok", retrieval.state
    ablations: dict[str, Any] = {"off": score_off(case, root, query=query)}
    for ablation in RETRIEVED:
        ordered = ablation_order(retrieval.ranked, ablation)
        ablations[ablation] = {**score_ranking(case, ordered), "pack": score_pack(case, ordered, read, budget)}
    return {"case_id": case.case_id, "version": case.version, "split": case.split, "snapshot": f"hex:{case.snapshot.removeprefix('git:')}", "cutoff": case.cutoff.isoformat(), "requirements": len(case.required_evidence),
            "retrieve_seconds": round(seconds, 3), "channels": dict(retrieval.channels), "coverage": dict(retrieval.coverage), "stale_or_missing_records": stale_or_missing_hits(retrieval.ranked, root), "ablations": ablations}


def run(config: Mapping[str, Any], repository: Path, splits: Sequence[str]) -> dict[str, Any]:
    gold = {name: repository / path for name, path in config["gold"].items()}
    targets = json.loads((repository / "reports/plan12-memory-m1/targets.json").read_text(encoding="utf-8"))
    refuse_unapproved_held_out(splits, targets, gold["m1"])
    work = repository / config["work_dir"]
    root, memory, _password, client, gateway, settings, settings_file = m1_scale._provision(dict(config), repository, work)
    head = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    cases = [(name, case) for name, directory in gold.items() for case in load_cases(directory, splits)]
    cases.sort(key=lambda pair: pair[1].cutoff)
    embedder = CachedEmbedder(FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"]), work / "embedding-cache.sqlite")
    route = load_registry(repository / "src/optimus_model_policy/defaults.yaml").policy.models[config["fixed_route"]].route
    budget = min(int(route.endpoints[0].context_window_tokens * PACK_SHARE), PACK_MAX_TOKENS)
    report: dict[str, Any] = {"schema": "plan12-memory-m1.retrieval.v1", "head": f"hex:{head}", "splits": list(splits), "k": K, "estimator": "one token per UTF-8 byte", "budget_tokens": budget, "fixed_route": config["fixed_route"],
                              "gold": {name: {"directory": str(directory.relative_to(repository)).replace("\\", "/"), "sha256": gold_digest(directory)} for name, directory in gold.items()},
                              "limits": ["Recency sees commit-time file dates in these copies, so it is noise here, not evidence of its value.", "A cutoff tree's index holds only that tree, so future leakage is excluded by construction."], "cases": {}, "trees": []}
    previous: m1_scale._Index | None = None
    try:
        report["wrong_branch_control"] = wrong_branch_control(work, settings, embedder)
        snapshots: dict[str, list[tuple[str, GoldenCase]]] = {}
        for name, case in cases:
            snapshots.setdefault(case.snapshot.removeprefix("git:"), []).append((name, case))
        for number, (revision, group) in enumerate(snapshots.items(), start=1):
            tree = work / "trees" / revision[:12]
            materialize(repository, revision, tree, branch=f"cutoff-{revision[:12]}")
            index = m1_scale._Index(tree, settings, embedder, project="m1-eval", parser_version="m1-eval")
            before = embedder.embedded
            started = time.perf_counter()
            m1_scale._note(f"tree {number}/{len(snapshots)} {revision[:12]}: indexing")
            outcome = m1_scale._required(index.worker().run(threading.Event()))
            report["trees"].append({"revision": f"hex:{revision}", "seconds": round(time.perf_counter() - started, 1), "records": outcome.records_written, "files": outcome.files_written, "embedded_now": embedder.embedded - before, "coverage": outcome.coverage})
            retriever = Retriever(index.storage, embedder)
            for name, case in group:
                report["cases"].setdefault(name, []).append(evaluate_case(case, index, retriever, tree, budget=budget))
            if previous is not None:  # the previous line stays until now, so a stale record had somewhere to come from
                _drop(previous)
            previous = index
            old = work / "trees"
            for leftover in old.iterdir():
                if leftover != tree:
                    shutil.rmtree(m1_scale.long_path(leftover), onexc=m1_scale._clear_read_only)
            report["redis"] = m1_scale._redis_facts(client, config["container"])
            write_report(report, repository, config)  # kept current: a stopped run still shows what it measured
        report["results"] = {name: {split: aggregate([row for row in rows if row["split"] == split]) for split in splits} for name, rows in report["cases"].items()}
        report["embedding"] = {"embedded": embedder.embedded, "reused": embedder.reused}
    finally:
        client.close()
        gateway.kill()
        gateway.wait(10)
        subprocess.run(["docker", "rm", "-f", config["container"]], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", "-f", config["volume"]], capture_output=True, check=False)
    return report


def write_report(report: Mapping[str, Any], repository: Path, config: Mapping[str, Any]) -> None:
    out = repository / config["out"]
    out.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m1_evaluate")
    parser.add_argument("--config", required=True)
    parser.add_argument("--splits", required=True, help="comma-separated: train, development, held_out")
    args = parser.parse_args(argv)
    repository = Path(__file__).resolve().parents[2]
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    splits = args.splits.split(",")
    if config.get("out") is None:
        config["out"] = "reports/plan12-memory-m1/retrieval.json"
    report = run(config, repository, splits)
    write_report(report, repository, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
