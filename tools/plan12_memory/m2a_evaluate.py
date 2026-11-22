"""Plan 12.13 M2a evaluation: `python -m tools.plan12_memory.m2a_evaluate --config reports/plan12-memory-m2a/run-config.json --phase calibration --output reports/plan12-memory-m2a/calibration.json`.

Phases: `calibration` (train and development: the path-order ambiguity baseline on real files, and every split schedule through the real
planning loop under each candidate partition), `index-check` (the frozen metadata states against a real index on the released Redis) and
`qualification` (held-out, once, after CP1). Model replies are scripted and cost nothing; no provider is reachable. Records carry counts,
paths of synthetic files, hashes and codes, never file bodies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest import mock

from optimus.agent import planning_loop as pl
from optimus.agent.models import AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.agent.workspace_context import WorkspaceReferenceStatus, assemble_workspace_context_for_prompt
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode

REPORTS = Path("reports/plan12-memory-m2a")
FROZEN_FILES = ("cases.json", "ranking-policy.json", "evaluation-contract.json", "case-provenance.json")
PARTITIONS = ((2, 14), (4, 12), (6, 10), (8, 8))
BASELINE = "4/12"
_PLACEHOLDER_SHA256 = "0" * 64
_FILE_BYTES = 24 * 1024
_STATUS = {
    WorkspaceReferenceStatus.AMBIGUOUS: "ambiguous_stop",
    WorkspaceReferenceStatus.RESOLVED: "resolved",
    WorkspaceReferenceStatus.NOT_FOUND: "not_found",
}


class FrozenInputChanged(SystemExit):
    pass


class HeldOutRefused(SystemExit):
    pass


@dataclass(frozen=True)
class Frozen:
    cases: dict[str, Any]
    digests: dict[str, str]


def load_frozen(repository: Path) -> Frozen:
    """The frozen inputs, refused unless each file's bytes still match the digest Task 0 recorded."""
    recorded = {
        Path(item["path"]).name: item["sha256"]
        for item in json.loads((repository / REPORTS / "prerequisites.json").read_text(encoding="utf-8"))["frozen_inputs"]["files"]
    }
    digests: dict[str, str] = {}
    for name in FROZEN_FILES:
        actual = "hex:" + hashlib.sha256((repository / REPORTS / name).read_bytes()).hexdigest()
        if actual != recorded[name]:
            raise FrozenInputChanged(f"{name} changed since it was frozen: {actual} is not {recorded[name]}")
        digests[name] = actual
    return Frozen(json.loads((repository / REPORTS / "cases.json").read_text(encoding="utf-8")), digests)


def selected(items: Iterable[Mapping[str, Any]], *, phase: str, splits: Sequence[str]) -> list[Mapping[str, Any]]:
    if phase != "qualification" and "held_out" in splits:
        raise HeldOutRefused("held-out is consumed once, at qualification after CP1")
    return [item for item in items if item["split"] in splits]


# ---------------------------------------------------------------- #245 schedules


def _observation_bytes(read: Mapping[str, Any], text_bytes: int) -> int:
    start, size = read["start_byte"], read["range_bytes"]
    return pl.planning_observation_serialized_bytes(
        pl.PlanningObservation(
            path=read["path"], start_byte=start, end_byte=start + size, source_sha256=_PLACEHOLDER_SHA256, observation_text="o" * text_bytes
        )
    )


def _read_bytes(read: Mapping[str, Any], size: int | None = None) -> int:
    start, size = read["start_byte"], read["range_bytes"] if size is None else size
    evidence = pl.PlanningReadEvidence(
        path=read["path"],
        start_byte=start,
        end_byte=start + size,
        source_sha256=_PLACEHOLDER_SHA256,
        line_endings="lf",
        range_text="x" * size,
    )
    return len(pl._serialize_planning_read_evidence(evidence).encode("utf-8"))


def serialized_totals(resolved: Mapping[str, Any]) -> dict[str, int]:
    """Cumulative observations at the final turn and the last round's current reads, in serialized UTF-8 bytes."""
    rounds = resolved["rounds"]
    observations = sum(_observation_bytes(read, round_["observation_text_bytes"]) for round_ in rounds for read in round_["reads"])
    return {"observations": observations, "current_reads": sum(_read_bytes(read) for read in rounds[-1]["reads"])}


def _smallest(total: Any, target: int, *, start: int) -> int:
    for value in range(start, 20_000):
        if total(value) == target:
            return value
    raise ValueError(f"target {target} is not reachable")


def resolve(schedule: Mapping[str, Any]) -> dict[str, Any]:
    """The schedule with every free length solved: reads first, then observations, so each total equals its target exactly."""
    resolved = json.loads(json.dumps(schedule))
    boundary = schedule.get("boundary")
    if boundary is None:
        return resolved
    targets = boundary["target"] if isinstance(boundary["target"], list) else None
    rounds = resolved["rounds"]
    if "current_reads" in boundary["total"]:
        last = rounds[-1]["reads"]
        fixed = sum(_read_bytes(read) for read in last[:-1])
        last[-1]["range_bytes"] = _smallest(
            lambda n: fixed + _read_bytes(last[-1], n), targets[1] if targets else boundary["target"], start=1
        )
    if "observations" in boundary["total"]:
        free = rounds[0] if targets else rounds[-1]

        def total(n: int) -> int:
            free["observation_text_bytes"] = n
            return serialized_totals(resolved)["observations"]

        free["observation_text_bytes"] = _smallest(total, targets[0] if targets else boundary["target"], start=0)
    return resolved


class _ScriptedGateway:
    """Replies in order and costs nothing; it is the only client the runner holds, so no provider can be reached."""

    def __init__(self, replies: Sequence[str]) -> None:
        self.replies = list(replies)
        self.inputs: list[str] = []

    def create_response(self, *, model: str, input_text: str, metadata: Any = None, route_binding: Any = None) -> GatewayResponse:
        self.inputs.append(input_text)
        number = len(self.inputs)
        reply = self.replies.pop(0) if self.replies else "REFUSE: script exhausted"
        usage = GatewayUsage(gateway_request_id=f"m2a-{number}", provider="local-script", billing_units=0, cost_usd=Decimal("0"))
        return GatewayResponse(response_id=f"m2a-{number}", output_text=reply, gateway_usage=usage, raw={})


def _span(text: str, start: str, end: str) -> int:
    first, last = text.find(start), text.rfind(end)
    return 0 if first < 0 or last < 0 else len(text[first : last + len(end)].encode("utf-8"))


def run_schedule(resolved: Mapping[str, Any], partition: tuple[int, int], work: Path) -> dict[str, Any]:
    """One schedule through the real runner and planning loop with only the two limits substituted."""
    work.mkdir(parents=True, exist_ok=True)
    paths = sorted({read["path"] for round_ in resolved["rounds"] for read in round_["reads"]})
    for path in paths:
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x = 1\n" * (_FILE_BYTES // 6))
    replies = [
        "OBSERVE: "
        + "o" * round_["observation_text_bytes"]
        + "\n"
        + "".join(
            f"READ: {read['path']}#bytes={read['start_byte']}:{read['start_byte'] + read['range_bytes']}\n" for read in round_["reads"]
        )
        for round_ in resolved["rounds"]
    ]
    replies.append(f"READ {paths[0]}\nWRITE {paths[0]}\nchange\n")
    gateway = _ScriptedGateway(replies)
    observation, read = (kib * 1024 for kib in partition)
    request = AgentRunRequest(
        run_id=f"m2a-{resolved['id']}",
        task="Plan a change",
        execution_mode=ExecutionMode.AGENT,
        workspace_root=work.resolve(),
        max_planning_turns=3,
        max_cost_usd=Decimal("0.05"),
    )
    with mock.patch.object(pl, "PLANNING_OBSERVATION_MAX_BYTES", observation), mock.patch.object(pl, "PLANNING_NEW_READ_MAX_BYTES", read):
        runner = AgentRunner(
            gateway_client=gateway,
            model="glm-5.2",
            guard=PreToolGuard.for_workspace(workspace_root=work.resolve(), allowed_network_hosts=()),
            state_store=InMemoryAgentStateStore(),
        )
        result = runner.run(request)
    final = gateway.inputs[-1] if gateway.inputs else ""
    expected_observations = sum(len(round_["reads"]) for round_ in resolved["rounds"])
    expected_reads = len(resolved["rounds"][-1]["reads"])
    evidence_complete = (
        len(gateway.inputs) == len(resolved["rounds"]) + 1
        and final.count("OBS_RECORD path=") == expected_observations
        and final.count("READ_BLOCK path=") == expected_reads
    )
    feedback = {text: code for code, text in pl.PLANNING_PARSE_FEEDBACK.items()}
    parse_failures = sorted({code for text, code in feedback.items() for sent in gateway.inputs if text in sent})
    planned = result.status is AgentRunStatus.AWAITING_APPROVAL and result.stop_reason is None
    return {
        "id": resolved["id"],
        "partition": f"{partition[0]}/{partition[1]}",
        "completed": planned and evidence_complete and not parse_failures,
        "planned": planned,
        "evidence_complete": evidence_complete,
        "stop": result.stop_reason,
        "parse_failures": parse_failures,
        "requests": len(gateway.inputs),
        "weakened": False,
        "cost_usd": "0",
        "measured": {
            "observations": _span(final, "OBS_RECORD path=", "END_OBS_RECORD\n"),
            "current_reads": _span(final, "READ_BLOCK path=", "END_READ_BLOCK\n"),
        },
    }


def choose_partition(results: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, Any]:
    """Plan v3 #245 selection: no weakened checks, no loss on baseline-success schedules, more completions than the baseline; ties go to
    fewer budget stops, then the partition nearest 4/12. None when no replacement qualifies."""
    baseline = results[BASELINE]
    successes = sorted(sid for sid, row in baseline.items() if row["completed"])
    base_done = len(successes)
    rejected: dict[str, str] = {}
    ranked: list[tuple[int, int, int, str]] = []
    for label, rows in results.items():
        if label == BASELINE:
            continue
        weakened = sorted(sid for sid, row in rows.items() if row.get("weakened"))
        lost = [sid for sid in successes if not rows[sid]["completed"]]
        done = sum(1 for row in rows.values() if row["completed"])
        if weakened:
            rejected[label] = "weakens checks: " + ", ".join(weakened)
        elif lost:
            rejected[label] = "loses baseline-success schedules: " + ", ".join(lost)
        elif done <= base_done:
            rejected[label] = f"no completion gain over {BASELINE} ({done} vs {base_done})"
        else:
            stops = sum(1 for row in rows.values() if row["stop"] is not None)
            ranked.append((-done, stops, abs(int(label.split("/")[0]) - 4), label))
    ranked.sort()
    return {
        "chosen": ranked[0][3] if ranked else None,
        "baseline_completed": base_done,
        "rejected": rejected,
        "qualifying": [{"partition": item[3], "completed": -item[0], "budget_stops": item[1]} for item in ranked],
    }


# ---------------------------------------------------------------- #242 ambiguity


def _family(frozen: Frozen, family: str) -> list[dict[str, Any]]:
    return next(item["files"] for item in frozen.cases["ambiguity"]["workspaces"] if item["family"] == family)


def _content(entry: Mapping[str, Any]) -> bytes:
    path = entry["path"]
    if path.endswith(".py"):
        lines = [f"import {name}" for name in entry.get("imports", ())]
        for symbol in entry.get("symbols", ()):
            lines.append(f"class {symbol}:\n    pass" if symbol[:1].isupper() else f"def {symbol}():\n    return None")
        return ("\n\n".join(lines) + "\n").encode("utf-8")
    if path.endswith(".md"):
        return ("".join(f"# {symbol}\n\ntext\n\n" for symbol in entry.get("symbols", ())) or "text\n").encode("utf-8")
    return b"{}\n"


def materialize(files: Sequence[Mapping[str, Any]], root: Path, *, skip: Iterable[str] = ()) -> None:
    """The family's synthetic workspace, with an ignore file for every denied directory that is not skipped by policy already."""
    left_out = set(skip)
    ignored = sorted({entry["path"].split("/", 1)[0] + "/" for entry in files if "ignore-file" in entry.get("denied", "")})
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text("".join(f"{item}\n" for item in ignored), encoding="utf-8", newline="\n")
    for entry in files:
        if entry["path"] in left_out:
            continue
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_content(entry))


def _diagnose(root: Path, task: str, reference: str) -> tuple[str, list[str], str | None]:
    result = assemble_workspace_context_for_prompt(root, task=task)
    wanted = reference.replace("\\", "/")
    diagnostic = next((item for item in result.diagnostics if item.reference.replace("\\", "/") == wanted), None)
    if diagnostic is None:
        return "not_referenced", [], None
    outcome = _STATUS.get(diagnostic.status, diagnostic.status.value)
    resolved = diagnostic.candidates[0] if diagnostic.status is WorkspaceReferenceStatus.RESOLVED else None
    return outcome, list(diagnostic.candidates), resolved


def ambiguity_baseline(frozen: Frozen, case: Mapping[str, Any], work: Path) -> dict[str, Any]:
    """Today's behavior on the case's real files: the stop, its candidate order (path order) and an exact-path retry where the case has one."""
    materialize(_family(frozen, case["family"]), work)
    outcome, candidates, resolved = _diagnose(work, case["task"], case["reference"])
    acceptable = set(case["acceptable"])
    rank = (
        next((number for number, path in enumerate(candidates, start=1) if path in acceptable), None)
        if outcome == "ambiguous_stop"
        else None
    )
    wrong = 1 if resolved is not None and resolved not in acceptable else 0
    row: dict[str, Any] = {
        "id": case["id"],
        "family": case["family"],
        "split": case["split"],
        "decidable": case["decidable"],
        "outcome": outcome,
        "expected": case["expected"],
        "candidates": candidates,
        "resolved": resolved,
        "resolved_correct": resolved in acceptable if resolved else None,
        "path_only_rank": rank if case["decidable"] else None,
        "wrong_target_selections": wrong,
    }
    retry = case.get("retry")
    if retry:
        mutation = retry.get("mutation_before_retry", "")
        if mutation.startswith("delete "):
            (work / mutation.removeprefix("delete ")).unlink()
        task = case["task"].replace(case["reference"], retry["input"], 1)
        retried, _candidates, retried_to = _diagnose(work, task, retry["input"])
        row["retry"] = {"outcome": retried, "resolved": retried_to}
        row["wrong_target_selections"] += 1 if retried_to is not None and retried_to not in acceptable else 0
    return row


def score_ambiguity(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per split: decidable and undecidable counts apart; top-one and reciprocal rank over decidable multi-candidate stops; regret on what
    the system acted on (a visible stop 0.25 when decidable, a correct resolution 0, a wrong one 1)."""
    scores: dict[str, dict[str, Any]] = {}
    for split in sorted({row["split"] for row in rows}):
        group = [row for row in rows if row["split"] == split]
        decidable = [row for row in group if row["decidable"]]
        ranked = [row for row in decidable if row["path_only_rank"] is not None]
        losses = [0.25 if row["outcome"] == "ambiguous_stop" else (0.0 if row.get("resolved_correct") else 1.0) for row in decidable]
        scores[split] = {
            "decidable": len(decidable),
            "undecidable": len(group) - len(decidable),
            "ranked_cases": len(ranked),
            "path_only_top_one": sum(1 for row in ranked if row["path_only_rank"] == 1) / len(ranked) if ranked else None,
            "path_only_reciprocal_rank": sum(1 / row["path_only_rank"] for row in ranked) / len(ranked) if ranked else None,
            "oracle_regret": sum(losses) / len(losses) if losses else None,
            "wrong_target_selections": sum(row["wrong_target_selections"] for row in group),
        }
    return scores


# ---------------------------------------------------------------- phases


def _head(repository: Path) -> str:
    return subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def calibration(frozen: Frozen, work: Path, splits: Sequence[str], *, phase: str) -> dict[str, Any]:
    if work.exists():
        shutil.rmtree(work)
    ambiguity = [
        ambiguity_baseline(frozen, case, work / "ambiguity" / case["id"])
        for case in selected(frozen.cases["ambiguity"]["cases"], phase=phase, splits=splits)
    ]
    schedules = selected(frozen.cases["split_schedules"]["schedules"], phase=phase, splits=splits)
    runs: dict[str, dict[str, dict[str, Any]]] = {}
    resolved_lengths: dict[str, Any] = {}
    for schedule in schedules:
        resolved = resolve(schedule)
        if "boundary" in schedule:
            resolved_lengths[schedule["id"]] = {
                "totals": serialized_totals(resolved),
                "rounds": [
                    {
                        "observation_text_bytes": round_["observation_text_bytes"],
                        "range_bytes": [read["range_bytes"] for read in round_["reads"]],
                    }
                    for round_ in resolved["rounds"]
                ],
            }
        for partition in PARTITIONS:
            label = f"{partition[0]}/{partition[1]}"
            row = run_schedule(resolved, partition, work / "schedules" / schedule["id"] / label.replace("/", "-"))
            runs.setdefault(label, {})[schedule["id"]] = {**row, "split": schedule["split"], "shape": schedule["shape"]}
    summary = {
        label: {
            split: {
                "completed": sum(1 for row in rows.values() if row["split"] == split and row["completed"]),
                "of": sum(1 for row in rows.values() if row["split"] == split),
                "budget_stops": sum(1 for row in rows.values() if row["split"] == split and row["stop"] is not None),
                "parse_failures": sum(1 for row in rows.values() if row["split"] == split and row["parse_failures"]),
            }
            for split in splits
        }
        for label, rows in runs.items()
    }
    shutil.rmtree(work)
    return {
        "ambiguity": {"rows": ambiguity, "scores": score_ambiguity(ambiguity)},
        "split": {
            "boundaries": resolved_lengths,
            "runs": runs,
            "summary": summary,
            "choice": choose_partition(runs) if phase == "calibration" else None,
        },
    }


def index_check(frozen: Frozen, config: Mapping[str, Any], repository: Path) -> dict[str, Any]:
    """Each ambiguity workspace indexed on the released Redis with the configured embedding artifact; files marked 'none' are added after
    the pass and files marked 'stale' are edited after it, then every candidate's state is read back from the published catalogue."""
    from context_engine.code_index import digest
    from context_engine.repo_map import MapFile, imports_of, neighbours
    from context_engine.retrieval import path_id, read_catalogue
    from optimus.context.memory_workspace import FastembedEmbedder
    from tools.plan12_memory import m1_scale

    work = repository / config["work_dir"] / "index-check"
    if work.exists():  # Git leaves read-only objects on Windows
        shutil.rmtree(m1_scale.long_path(work), onexc=m1_scale._clear_read_only)
    root, memory, _password, client, gateway, settings, settings_file = m1_scale._provision(dict(config), repository, work)
    families: list[dict[str, Any]] = []
    try:
        embedder = m1_scale._TimedEmbedder(
            FastembedEmbedder(
                root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"]
            )
        )
        for workspace in frozen.cases["ambiguity"]["workspaces"]:
            files = workspace["files"]
            tree = work / "trees" / workspace["family"]
            later = {entry["path"] for entry in files if entry.get("metadata") == "none" and "denied" not in entry}
            materialize(files, tree, skip=later)
            for command in (
                ["init", "-q", "-b", "main"],
                ["add", "-A"],
                ["-c", "user.name=m2a", "-c", "user.email=m2a@invalid", "commit", "-q", "-m", "m2a"],
            ):
                subprocess.run(["git", "-C", str(tree), *command], capture_output=True, check=True)
            index = m1_scale._Index(
                tree, settings, embedder, project=f"m2a-{workspace['family'].lower()}", parser_version="m2a-index-check"
            )
            outcome = m1_scale._required(index.worker().run(threading.Event()))
            for entry in files:  # after publication: new files never indexed, edited files now differ from their records
                if entry["path"] in later:
                    materialize([entry], tree)
                elif entry.get("metadata") == "stale":
                    (tree / entry["path"]).write_bytes(_content(entry) + b"# edited after indexing\n")
            current = index.storage.call("coverage")["current"]
            catalogue = {item.path: item for item in read_catalogue(index.storage, current["epoch"])}
            map_files = [MapFile(item.path, imports_of(item.description)) for item in catalogue.values()]
            rows = []
            for entry in files:
                record = catalogue.get(entry["path"])
                on_disk = tree / entry["path"]
                if record is None:
                    state = "none"
                else:
                    state = "verified" if on_disk.is_file() and record.file_hash == digest(on_disk.read_bytes()) else "stale"
                labels: list[str] = []
                if record is not None:
                    reply = index.storage.call(
                        "query", mode="path", epoch=current["epoch"], path_id=path_id(entry["path"]), k=20, kinds=["symbol", "section"]
                    )
                    labels = sorted({item.get("symbol") or item.get("label") or "" for item in reply["records"]} - {""})
                rows.append(
                    {
                        "path": entry["path"],
                        "frozen": "denied" if "denied" in entry else entry.get("metadata"),
                        "observed": state,
                        "imports": list(imports_of(record.description)) if record else [],
                        "labels": labels,
                        "matches": ("denied" in entry and record is None) or ("denied" not in entry and state == entry.get("metadata")),
                    }
                )
            resolved_paths = sorted(
                {
                    path
                    for case in frozen.cases["ambiguity"]["cases"]
                    if case["family"] == workspace["family"]
                    for path in (entry["path"] for entry in files)
                    if path in case["task"]
                }
            )
            families.append(
                {
                    "family": workspace["family"],
                    "files_written": outcome.files_written,
                    "records": outcome.records_written,
                    "coverage": outcome.coverage,
                    "candidates": rows,
                    "neighbours_of_resolved_task_paths": {path: neighbours(map_files, [path]) for path in resolved_paths},
                }
            )
        redis_facts = m1_scale._redis_facts(client, config["container"])
    finally:
        client.close()
        gateway.kill()
        gateway.wait(10)
        subprocess.run(["docker", "rm", "-f", config["container"]], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", "-f", config["volume"]], capture_output=True, check=False)
        shutil.rmtree(m1_scale.long_path(work), onexc=m1_scale._clear_read_only)
    return {
        "families": families,
        "mismatches": [f"{family['family']}:{row['path']}" for family in families for row in family["candidates"] if not row["matches"]],
        "redis": redis_facts,
        "release": {"container": memory.container, "image": memory.image, "port": memory.port},
        "embedding": {
            "model": memory.embedding.model,
            "revision": f"git:{memory.embedding.revision}",
            "artifact_sha256": f"hex:{memory.embedding.artifact_sha256}",
        },
        "later_files": "files marked none were written after publication; files marked stale were edited after it; denied files are never indexed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m2a_evaluate")
    parser.add_argument("--config", required=True)
    parser.add_argument("--phase", required=True, choices=("calibration", "index-check", "qualification"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    repository = Path(__file__).resolve().parents[2]
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    frozen = load_frozen(repository)
    report: dict[str, Any] = {
        "schema": f"plan12-memory-m2a.{args.phase}.v1",
        "head": f"git:{_head(repository)}",
        "phase": args.phase,
        "inputs": frozen.digests,
        "paid_attempts": 0,
        "provider_cost_usd": "0",
    }
    if args.phase == "index-check":
        report.update(index_check(frozen, config, repository))
    else:
        splits = ("held_out",) if args.phase == "qualification" else ("train", "development")
        report["splits"] = list(splits)
        report.update(calibration(frozen, repository / config["work_dir"] / args.phase, splits, phase=args.phase))
    Path(args.output).write_text(json.dumps(report, indent=1, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
