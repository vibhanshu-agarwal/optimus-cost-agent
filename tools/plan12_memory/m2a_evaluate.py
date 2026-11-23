"""Plan 12.13 M2a evaluation: `python -m tools.plan12_memory.m2a_evaluate --config reports/plan12-memory-m2a/run-config.json --phase calibration --output reports/plan12-memory-m2a/calibration.json`.

Phases: `calibration` (train and development: the path-order ambiguity baseline on real files, and every split schedule through the real
planning loop under each candidate partition), `index-check` (the frozen metadata states against a real index on the released Redis) and
`qualification` (held-out, once, after CP1). Task 3 adds `split` (train and development again, every request through the real route
fitting), `determinism` (repeated and reordered inputs) and `cache-identity` (prompt prefix, request and registry identities). Model
replies are scripted and cost nothing; no provider is reachable. Records carry counts, paths of synthetic files, hashes and codes, never
file bodies.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
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
from optimus.agent.workspace_context import (
    RankingHints,
    WorkspaceReferenceStatus,
    assemble_workspace_context_for_prompt,
    rank_ambiguity,
    verified_hints,
)
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.file_policy import FilePolicy, FilePurpose
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


PROBE_RECIPE = "own-limit-probes.v1"


def observation_text(schedule: Mapping[str, Any], size: int) -> str:
    """`size` UTF-8 bytes of observation: ASCII, or for own-limit probes U+00F6 (two bytes each) with one ASCII pad when odd."""
    if schedule.get("observation_text") == "multibyte":
        return "\u00f6" * (size // 2) + "o" * (size % 2)
    return "o" * size


def _observation_bytes(read: Mapping[str, Any], text_bytes: int, schedule: Mapping[str, Any] | None = None) -> int:
    start, size = read["start_byte"], read["range_bytes"]
    return pl.planning_observation_serialized_bytes(
        pl.PlanningObservation(
            path=read["path"],
            start_byte=start,
            end_byte=start + size,
            source_sha256=_PLACEHOLDER_SHA256,
            observation_text=observation_text(schedule or {}, text_bytes),
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
    observations = sum(
        _observation_bytes(read, round_["observation_text_bytes"], resolved) for round_ in rounds for read in round_["reads"]
    )
    return {"observations": observations, "current_reads": sum(_read_bytes(read) for read in rounds[-1]["reads"])}


def _smallest(total: Any, target: int, *, start: int) -> int:
    for value in range(start, 20_000):
        if total(value) == target:
            return value
    raise ValueError(f"target {target} is not reachable")


def boundary_targets(boundary: Mapping[str, Any]) -> dict[str, int]:
    """The template's own targets by side: observations, current_reads, or both (mixed lists observations first)."""
    if isinstance(boundary["target"], list):
        return {"observations": boundary["target"][0], "current_reads": boundary["target"][1]}
    side = "current_reads" if "current_reads" in boundary["total"] else "observations"
    return {side: boundary["target"]}


def resolve(schedule: Mapping[str, Any], targets: Mapping[str, int] | None = None) -> dict[str, Any]:
    """The schedule with every free length solved: reads first, then observations, so each total equals its target exactly. `targets`
    replaces the boundary's own (own-limit probes). A target unreachable at the template's lengths rescales that side's fixed records once,
    so each one's serialized bytes (headers and framing included) become floor(bytes * target / template target) (cases.json
    probe_recipe). Still unreachable raises ValueError: the probe is blocked, never skipped."""
    resolved = json.loads(json.dumps(schedule))
    boundary = schedule.get("boundary")
    if boundary is None:
        return resolved
    own = boundary_targets(boundary)
    goal = own if targets is None else dict(targets)
    rounds = resolved["rounds"]
    if "current_reads" in goal:
        last = rounds[-1]["reads"]

        def solve_reads() -> int:
            fixed = sum(_read_bytes(read) for read in last[:-1])
            return _smallest(lambda n: fixed + _read_bytes(last[-1], n), goal["current_reads"], start=1)

        try:
            last[-1]["range_bytes"] = solve_reads()
        except ValueError:
            if targets is None:
                raise
            for read in last[:-1]:
                size = _read_bytes(read)
                read["range_bytes"] = max(1, size * goal["current_reads"] // own["current_reads"] - (size - read["range_bytes"]))
            last[-1]["range_bytes"] = solve_reads()
        if any(read["start_byte"] + read["range_bytes"] > _FILE_BYTES for read in last):
            raise ValueError("a read range passes the end of its file")
    if "observations" in goal:
        free = rounds[0] if len(own) == 2 else rounds[-1]

        def total(n: int) -> int:
            free["observation_text_bytes"] = n
            return serialized_totals(resolved)["observations"]

        try:
            free["observation_text_bytes"] = _smallest(total, goal["observations"], start=0)
        except ValueError:
            if targets is None:
                raise
            for round_ in rounds:
                if round_ is not free:
                    text, count = round_["observation_text_bytes"], len(round_["reads"])
                    size = sum(_observation_bytes(read, text, resolved) for read in round_["reads"])
                    scaled = size * goal["observations"] // own["observations"]
                    round_["observation_text_bytes"] = max(0, (scaled - (size - count * text)) // count)
            free["observation_text_bytes"] = _smallest(total, goal["observations"], start=0)
    return resolved


def probe_variants(schedule: Mapping[str, Any], partition: tuple[int, int]) -> list[dict[str, Any]]:
    """The template's own-limit probes for one candidate: exact and one-over on its side; mixed: both exact, then each side one over.
    Observation text is multibyte. A variant that cannot be solved, or whose other side is over its limit, is blocked."""
    limits = {"observations": partition[0] * 1024, "current_reads": partition[1] * 1024}
    sides = list(boundary_targets(schedule["boundary"]))
    if len(sides) == 2:
        plans = {
            "exact": dict(limits),
            "one_over_observations": {**limits, "observations": limits["observations"] + 1},
            "one_over_reads": {**limits, "current_reads": limits["current_reads"] + 1},
        }
    else:
        plans = {"exact": {sides[0]: limits[sides[0]]}, "one_over": {sides[0]: limits[sides[0]] + 1}}
    variants = []
    for name, targets in plans.items():
        variant: dict[str, Any] = {"template": schedule["id"], "variant": name, "targets": targets}
        try:
            resolved = resolve({**schedule, "observation_text": "multibyte"}, targets)
        except ValueError as error:
            variants.append({**variant, "blocked": str(error)})
            continue
        totals = serialized_totals(resolved)
        over = [side for side in limits if side not in targets and totals[side] > limits[side]]
        variants.append({**variant, "totals": totals, **({"blocked": f"{over[0]} over its limit"} if over else {"resolved": resolved})})
    return variants


def probe_passed(variant: str, row: Mapping[str, Any] | None) -> bool:
    """Exact: completed. One-over: no plan, and a budget stop or the OBSERVATION_TOO_LARGE parse failure (a plan after it fails: F2).
    Either way every request the probe sent was fitted to the route (Codex CP2 review 1, finding 2)."""
    if row is None or row["route_fit"]["status"] != "passed":
        return False
    if variant == "exact":
        return bool(row["completed"])
    return not row["planned"] and (row["stop"] in BUDGET_STOPS or "OBSERVATION_TOO_LARGE" in row["parse_failures"])


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


_OBS_RECORD = re.compile(r"OBS_RECORD path=(\S+) bytes=(\d+):(\d+) sha256=([0-9a-f]{64})\n(.*?)\nEND_OBS_RECORD\n", re.DOTALL)
_READ_BLOCK = re.compile(r"READ_BLOCK path=(\S+) bytes=(\d+):(\d+) sha256=([0-9a-f]{64}) eol=(\w+)\n(.*?)\nEND_READ_BLOCK\n", re.DOTALL)
BUDGET_STOPS = frozenset({"PLANNING_OBSERVATION_BUDGET_EXHAUSTED", "PLANNING_READ_BUDGET_EXHAUSTED"})


def write_workspace(resolved: Mapping[str, Any], work: Path) -> list[str]:
    """The schedule's files: plain LF text long enough for every range."""
    work.mkdir(parents=True, exist_ok=True)
    paths = sorted({read["path"] for round_ in resolved["rounds"] for read in round_["reads"]})
    for path in paths:
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x = 1\n" * (_FILE_BYTES // 6))
    return paths


def check_evidence(final: str, resolved: Mapping[str, Any], work: Path) -> list[str]:
    """Problems with the final request's evidence, empty when it carries exactly the expected records: every round's observation and the
    last round's reads, each with its path, range, the file's current sha256 and its whole payload. Duplicates and substitutions count."""
    whole = {path: (work / path).read_bytes() for path in {read["path"] for round_ in resolved["rounds"] for read in round_["reads"]}}
    digest_of = {path: hashlib.sha256(data).hexdigest() for path, data in whole.items()}

    def span(read: Mapping[str, Any]) -> tuple[str, int, int, str]:
        start = read["start_byte"]
        return read["path"], start, start + read["range_bytes"], digest_of[read["path"]]

    expected_observations = sorted(
        (*span(read), observation_text(resolved, round_["observation_text_bytes"]))
        for round_ in resolved["rounds"]
        for read in round_["reads"]
    )
    expected_reads = sorted(
        (*span(read), "lf", whole[read["path"]][read["start_byte"] : read["start_byte"] + read["range_bytes"]].decode("utf-8"))
        for read in resolved["rounds"][-1]["reads"]
    )
    found_observations = sorted((path, int(a), int(b), sha, text) for path, a, b, sha, text in _OBS_RECORD.findall(final))
    found_reads = sorted((path, int(a), int(b), sha, eol, text) for path, a, b, sha, eol, text in _READ_BLOCK.findall(final))
    problems = []
    if found_observations != expected_observations:
        problems.append(f"observation records differ ({len(found_observations)} found, {len(expected_observations)} expected)")
    if found_reads != expected_reads:
        problems.append(f"read blocks differ ({len(found_reads)} found, {len(expected_reads)} expected)")
    return problems


@functools.cache
def _route() -> tuple[Any, str, Any]:
    """The shipped ordinary registry, and the implementer route with the smallest usable input: the tightest any ordinary launch fits
    to. Chosen by its limit, never by name (models are configuration)."""
    from optimus.acp.context_attachment import implementer_role
    from optimus.context.shipped_policy import attachment_limits
    from optimus.gateway.route_binding import RouteIdentityError
    from optimus_model_policy.binding import compose_trusted_snapshot, packaged_defaults

    snapshot = compose_trusted_snapshot(packaged_defaults())
    routes = []
    for model_id in sorted(snapshot.policy.models):
        try:
            implementer_role(snapshot, model_id)
            routes.append((attachment_limits(snapshot, model_id).usable_input_tokens, model_id))
        except KeyError, RouteIdentityError:
            continue
    _usable, model_id = min(routes)
    return snapshot, model_id, attachment_limits(snapshot, model_id)


def route_packer() -> Any:
    """The real ContextPacker on that route: an attached turn with no history and no summarizer, so fitting can make no call. Its fit()
    is the shipped one, unchanged."""
    from context_engine.engine import ContextEngine
    from optimus.acp.conversation import ConversationSanitizer, ConversationSanitizerInputs
    from optimus.context.assembly import AttachedTurn, ContextAttachment
    from optimus.context.shipped_policy import MAX_REPACKS, RECORD_RESERVATION_BYTES, SOURCE_MAX_BYTES, no_attachment_ledger

    snapshot, model_id, limits = _route()
    attachment = ContextAttachment(
        engine=ContextEngine(),
        parameters=limits.parameters,
        limits=limits.limits,
        source_max_bytes=SOURCE_MAX_BYTES,
        record_reservation_bytes=RECORD_RESERVATION_BYTES,
        usable_input_tokens=limits.usable_input_tokens,
        estimate_request=limits.estimate_request,
        registry_hash=snapshot.effective_hash,
        model_id=model_id,
        summarizer=None,
        summarizer_route=None,
        record_receipt=no_attachment_ledger,
        max_repacks=MAX_REPACKS,
    )
    turn = AttachedTurn.capture(
        attachment=attachment,
        session_key="m2a",
        records={},
        approvals={},
        generation=0,
        sanitizer=ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=(), known_pii=())),
        strategy="compaction",
        mode=ExecutionMode.AGENT,
        checkpoint=None,
        current_prompt="Plan a change",
        turn_seq=1,
        cancelled=lambda: False,
    )
    if turn.prepare().kind != "view":
        raise RuntimeError("the route packer has no view")
    return turn


def run_schedule(resolved: Mapping[str, Any], partition: tuple[int, int], work: Path) -> dict[str, Any]:
    """One schedule through the real runner, planning loop and route fitting (ContextPacker.fit) with only the two limits substituted.
    Completed: a plan, no parse failure, exactly the expected evidence, and every request fitted to the route unchanged."""
    paths = write_workspace(resolved, work)
    replies = [
        "OBSERVE: "
        + observation_text(resolved, round_["observation_text_bytes"])
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
    _snapshot, model_id, limits = _route()
    packer = route_packer()
    with mock.patch.object(pl, "PLANNING_OBSERVATION_MAX_BYTES", observation), mock.patch.object(pl, "PLANNING_NEW_READ_MAX_BYTES", read):
        runner = AgentRunner(
            gateway_client=gateway,
            model=model_id,
            guard=PreToolGuard.for_workspace(workspace_root=work.resolve(), allowed_network_hosts=()),
            state_store=InMemoryAgentStateStore(),
        )
        result = runner.run(request, context_packer=packer)
    readings = packer.dispatch_readings()
    fitted = (
        result.stop_reason != "CONTEXT_CAPACITY_EXCEEDED"
        and packer.repacks == 0
        and len(readings) == len(gateway.inputs)
        and all(reading.tokens <= reading.capacity for reading in readings)
    )
    route_fit = {
        "status": "passed" if fitted else "failed",
        "requests_fitted": len(readings),
        "repacks": packer.repacks,
        "max_request_tokens": max((reading.tokens for reading in readings), default=0),
        "usable_input_tokens": limits.usable_input_tokens,
    }
    final = gateway.inputs[-1] if gateway.inputs else ""
    problems = check_evidence(final, resolved, work)
    if len(gateway.inputs) != len(resolved["rounds"]) + 1:
        problems.append(f"{len(gateway.inputs)} requests, {len(resolved['rounds']) + 1} expected")
    feedback = {text: code for code, text in pl.PLANNING_PARSE_FEEDBACK.items()}
    parse_failures = sorted({code for text, code in feedback.items() for sent in gateway.inputs if text in sent})
    planned = result.status is AgentRunStatus.AWAITING_APPROVAL and result.stop_reason is None
    return {
        "id": resolved["id"],
        "partition": f"{partition[0]}/{partition[1]}",
        "completed": planned and not problems and not parse_failures and fitted,
        "planned": planned,
        "evidence_complete": not problems,
        "evidence_problems": problems,
        "stop": result.stop_reason,
        "parse_failures": parse_failures,
        "budget_stop": result.stop_reason in BUDGET_STOPS or "OBSERVATION_TOO_LARGE" in parse_failures,
        "requests": len(gateway.inputs),
        "weakened": False,
        "route_fit": route_fit,
        "cost_usd": "0",
        "measured": {
            "observations": _span(final, "OBS_RECORD path=", "END_OBS_RECORD\n"),
            "current_reads": _span(final, "READ_BLOCK path=", "END_READ_BLOCK\n"),
        },
    }


def choose_partition(
    results: Mapping[str, Mapping[str, Mapping[str, Any]]], probes: Mapping[str, Sequence[Mapping[str, Any]]] | None = None
) -> dict[str, Any]:
    """Plan v4 #245 selection on train/development. Boundary templates are left out: no-loss, completions and budget stops count
    non-boundary schedules only. A partition is dropped when it weakens a check, fails one of its own-limit probes, or loses a non-boundary
    baseline success; the baseline and the rest are ordered by most completions, fewer budget stops, then nearness to 4/12. None when the
    baseline comes first. 4/12's own probe failures are reported and it stays the fallback. The held-out improvement is qualification's
    own gate (Codex CP1 review 1, finding 3)."""

    def stops(rows: Mapping[str, Mapping[str, Any]]) -> int:
        return sum(1 for row in rows.values() if row.get("budget_stop", row["stop"] in BUDGET_STOPS))

    def failures(label: str) -> list[str]:
        return [f"{probe['template']}:{probe['variant']}" for probe in (probes or {}).get(label, ()) if not probe["passed"]]

    scored = {label: {sid: row for sid, row in rows.items() if not row.get("boundary")} for label, rows in results.items()}
    successes = sorted(sid for sid, row in scored[BASELINE].items() if row["completed"])
    rejected: dict[str, str] = {}
    ranked: list[tuple[int, int, int, str]] = []
    for label, rows in scored.items():
        weakened = sorted(sid for sid, row in results[label].items() if row.get("weakened"))
        failed = failures(label) if label != BASELINE else []
        lost = [sid for sid in successes if not rows[sid]["completed"]]
        if weakened:
            rejected[label] = "weakens checks: " + ", ".join(weakened)
        elif failed:
            rejected[label] = "fails own-limit probes: " + ", ".join(failed)
        elif lost:
            rejected[label] = "loses baseline-success schedules: " + ", ".join(lost)
        else:
            ranked.append((-sum(1 for row in rows.values() if row["completed"]), stops(rows), abs(int(label.split("/")[0]) - 4), label))
    ranked.sort()
    for _done, _stops, _distance, label in ranked[1:]:
        if label != BASELINE:
            rejected[label] = f"ranks below {ranked[0][3]} on completions, then budget stops, then nearness to {BASELINE}"
    chosen = ranked[0][3] if ranked and ranked[0][3] != BASELINE else None
    return {
        "chosen": chosen,
        "scored": "non-boundary schedules only (plan v4 #245); probe templates are diagnostics",
        "baseline_completed": len(successes),
        "baseline_probe_failures": failures(BASELINE),
        "rejected": rejected,
        "eligible": [{"partition": item[3], "completed": -item[0], "budget_stops": item[1]} for item in ranked],
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


def materialize(files: Sequence[Mapping[str, Any]], root: Path, *, skip: Iterable[str] = (), reverse: bool = False) -> None:
    """The family's synthetic workspace, with an ignore file for every denied directory that is not skipped by policy already. `reverse`
    writes the files in the opposite order (determinism)."""
    left_out = set(skip)
    ignored = sorted({entry["path"].split("/", 1)[0] + "/" for entry in files if "ignore-file" in entry.get("denied", "")})
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text("".join(f"{item}\n" for item in ignored), encoding="utf-8", newline="\n")
    for entry in reversed(files) if reverse else files:
        if entry["path"] in left_out:
            continue
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_content(entry))


HintsFor = Any  # Callable[[Sequence[str], Sequence[str]], RankingHints]


def _diagnose(root: Path, task: str, reference: str, hints_for: HintsFor = None) -> tuple[str, list[str], str | None]:
    """The ordinary assembly's stop for `reference`; with `hints_for`, its candidates re-ranked by the shared policy with those hints, as
    MemoryTurn.assemble ranks them."""
    result = assemble_workspace_context_for_prompt(root, task=task)
    diagnostics = result.diagnostics if hints_for is None else rank_ambiguity(result.diagnostics, task, hints_for)
    wanted = reference.replace("\\", "/")
    diagnostic = next((item for item in diagnostics if item.reference.replace("\\", "/") == wanted), None)
    if diagnostic is None:
        return "not_referenced", [], None
    outcome = _STATUS.get(diagnostic.status, diagnostic.status.value)
    resolved = diagnostic.candidates[0] if diagnostic.status is WorkspaceReferenceStatus.RESOLVED else None
    return outcome, list(diagnostic.candidates), resolved


def index_hints(records: Sequence[Mapping[str, Any]], files: Sequence[Mapping[str, Any]], root: Path) -> HintsFor:
    """MemorySession.hints_for over the real index's recorded metadata (index-check.json): labels and imports of every file the index
    holds, each record's hash being the bytes it indexed. Current bytes come from disk, so a stale file contributes nothing."""
    from context_engine.repo_map import MapFile

    content = {entry["path"]: _content(entry) for entry in files}
    held = [row for row in records if row["observed"] != "none" and row["frozen"] != "denied"]
    map_files = [MapFile(row["path"], tuple(row["imports"]), tuple(row["labels"])) for row in held]
    hashes = {row["path"]: hashlib.sha256(content[row["path"]]).hexdigest() for row in held}

    def read(path: str) -> bytes | None:
        target = root / path
        return target.read_bytes() if target.is_file() else None

    def hints(candidates: Sequence[str], resolved: Sequence[str]) -> RankingHints:
        return verified_hints(candidates, resolved, files=map_files, hashes=hashes, read=read)

    return hints


def ambiguity_baseline(
    frozen: Frozen, case: Mapping[str, Any], work: Path, *, records: Sequence[Mapping[str, Any]] | None = None, reverse: bool = False
) -> dict[str, Any]:
    """The case on its real files: the stop with its candidates in path order (the baseline), in the order ordinary assembly now lists
    them, and, given the family's recorded index metadata, in the index turn's order; then an exact-path retry where the case has one."""
    files = _family(frozen, case["family"])
    materialize(files, work, reverse=reverse)
    outcome, ranked, resolved = _diagnose(work, case["task"], case["reference"])
    candidates = sorted(ranked)  # the path-only baseline (ranking-policy.json): the stop now lists them ranked (Task 2)
    acceptable = set(case["acceptable"])

    def rank_in(order: Sequence[str]) -> int | None:
        if outcome != "ambiguous_stop":
            return None
        return next((number for number, path in enumerate(order, start=1) if path in acceptable), None)

    rank = rank_in(candidates)
    hinted: list[str] | None = None
    if records is not None:
        after_indexing(files, work, ())  # the index's stale files differ from their records now, as at the index check
        _outcome, hinted, _resolved = _diagnose(work, case["task"], case["reference"], index_hints(records, files, work))
    denied = {entry["path"] for entry in files if "denied" in entry}
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
        "ranked_candidates": ranked,
        "ranked_rank": rank_in(ranked) if case["decidable"] else None,
        **({"index_candidates": hinted, "index_rank": rank_in(hinted) if case["decidable"] else None} if hinted is not None else {}),
        # ranking only orders the stop's set: every order lists the same candidates, and no denied file
        "candidates_kept": sorted(ranked) == candidates and (hinted is None or sorted(hinted) == candidates),
        "denied_listed": sorted(denied & {*ranked, *(hinted or ())}),
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
    """Per split: decidable and undecidable counts apart; top-one and reciprocal rank over decidable multi-candidate stops, for each order
    over the same rows (path_only, ranked: ordinary assembly, index: with the index's hints); regret on what the system acted on (a
    visible stop 0.25 when decidable, a correct resolution 0, a wrong one 1)."""
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
            "oracle_regret": sum(losses) / len(losses) if losses else None,
            "wrong_target_selections": sum(row["wrong_target_selections"] for row in group),
            "candidates_lost": sum(1 for row in group if row.get("candidates_kept") is False),
            "denied_listed": sum(len(row.get("denied_listed", ())) for row in group),
        }
        for order in ("path_only", "ranked", "index"):
            ranks = [row.get(f"{order}_rank") for row in ranked]
            known = bool(ranks) and all(value is not None for value in ranks)
            scores[split][f"{order}_top_one"] = sum(1 for value in ranks if value == 1) / len(ranks) if known else None
            scores[split][f"{order}_reciprocal_rank"] = sum(1 / value for value in ranks if value) / len(ranks) if known else None
    return scores


# ---------------------------------------------------------------- phases


def _head(repository: Path) -> str:
    return subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def calibration(
    frozen: Frozen,
    work: Path,
    splits: Sequence[str],
    *,
    phase: str,
    partitions: Sequence[tuple[int, int]] = PARTITIONS,
    index: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    if work.exists():
        shutil.rmtree(work)
    ambiguity = [
        ambiguity_baseline(frozen, case, work / "ambiguity" / case["id"], records=None if index is None else index[case["family"]])
        for case in selected(frozen.cases["ambiguity"]["cases"], phase=phase, splits=splits)
    ]
    recipe = frozen.cases["split_schedules"]["probe_recipe"]["version"]
    if recipe != PROBE_RECIPE:
        raise FrozenInputChanged(f"cases.json probe recipe {recipe} is not the {PROBE_RECIPE} this evaluator implements")
    schedules = selected(frozen.cases["split_schedules"]["schedules"], phase=phase, splits=splits)
    runs: dict[str, dict[str, dict[str, Any]]] = {}
    probes: dict[str, list[dict[str, Any]]] = {}
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
        for partition in partitions:
            label = f"{partition[0]}/{partition[1]}"
            row = run_schedule(resolved, partition, work / "schedules" / schedule["id"] / label.replace("/", "-"))
            boundary = "boundary" in schedule
            runs.setdefault(label, {})[schedule["id"]] = {
                **row,
                "split": schedule["split"],
                "shape": schedule["shape"],
                "boundary": boundary,
            }
            if boundary:
                for variant in probe_variants(schedule, partition):
                    probe_row = None
                    if "resolved" in variant:
                        probe_row = run_schedule(
                            variant.pop("resolved"),
                            partition,
                            work / "probes" / schedule["id"] / label.replace("/", "-") / variant["variant"],
                        )
                    probes.setdefault(label, []).append(
                        {
                            **variant,
                            "split": schedule["split"],
                            "passed": probe_passed(variant["variant"], probe_row),
                            **(
                                {
                                    key: probe_row[key]
                                    for key in (
                                        "completed",
                                        "planned",
                                        "stop",
                                        "parse_failures",
                                        "evidence_problems",
                                        "requests",
                                        "route_fit",
                                    )
                                }
                                if probe_row
                                else {}
                            ),
                        }
                    )
    summary = {
        label: {
            split: {
                "completed": sum(1 for row in rows.values() if row["split"] == split and row["completed"]),
                "of": sum(1 for row in rows.values() if row["split"] == split),
                "budget_stops": sum(1 for row in rows.values() if row["split"] == split and row["budget_stop"]),
                "other_stops": sum(
                    1 for row in rows.values() if row["split"] == split and row["stop"] is not None and not row["budget_stop"]
                ),
                "parse_failures": sum(1 for row in rows.values() if row["split"] == split and row["parse_failures"]),
                "non_boundary_completed": sum(
                    1 for row in rows.values() if row["split"] == split and not row["boundary"] and row["completed"]
                ),
                "non_boundary_of": sum(1 for row in rows.values() if row["split"] == split and not row["boundary"]),
                "non_boundary_budget_stops": sum(
                    1 for row in rows.values() if row["split"] == split and not row["boundary"] and row["budget_stop"]
                ),
                "probes_passed": sum(1 for probe in probes.get(label, ()) if probe["split"] == split and probe["passed"]),
                "probes_of": sum(1 for probe in probes.get(label, ()) if probe["split"] == split),
            }
            for split in splits
        }
        for label, rows in runs.items()
    }
    shutil.rmtree(work)
    return {
        "ambiguity": {"rows": ambiguity, "scores": score_ambiguity(ambiguity)},
        "split": {
            "completion_scope": "a plan, no parse failure, exactly the expected evidence records (path, range, file sha256, whole payload), "
            "and every request fitted by the shipped ContextPacker.fit to the ordinary implementer route with the smallest usable input",
            "probe_recipe": recipe,
            "boundaries": resolved_lengths,
            "runs": runs,
            "probes": probes,
            "summary": summary,
            "choice": choose_partition(runs, probes) if phase in ("calibration", "split") else None,
        },
    }


# ---------------------------------------------------------------- Task 3: qualification, capacity, F2, determinism, identities


F2 = {
    "finding": "CP1 (round 117): a plan accepted after OBSERVATION_TOO_LARGE carries none of the rejected turn's reads",
    "established": "no production-required evidence is dropped. The rejected turn reads nothing; the correction request carries every "
    "earlier observation and current read unchanged; a plan binds only the evidence it was shown (PlanningLoopResult.evidence_sha256s); "
    "an EDIT of a file it was never shown is refused EDIT_SOURCE_UNSEEN before any write",
    "disposition": "no parse-recovery change. The evaluator never counts such a plan as a completion or as a one-over probe pass",
    "tests": [
        "tests/unit/agent/test_planning_loop_recovery.py::test_observation_too_large_keeps_the_earlier_evidence_and_reads_nothing",
        "tests/unit/agent/test_planning_loop_recovery.py::test_a_plan_after_observation_too_large_cannot_edit_a_file_it_was_never_shown",
        "tests/unit/tools/test_plan12_memory_m2a.py::test_a_one_over_probe_needs_a_typed_stop_and_a_plan_after_observation_too_large_fails",
    ],
}


def chosen_partition(repository: Path, frozen: Frozen) -> tuple[int, int]:
    """The partition calibration.json chose under these frozen inputs; refused when its inputs differ or it chose none."""
    calibration_report = json.loads((repository / REPORTS / "calibration.json").read_text(encoding="utf-8"))
    if calibration_report["inputs"] != frozen.digests:
        raise FrozenInputChanged("calibration.json ran on other frozen inputs")
    chosen = calibration_report["split"]["choice"]["chosen"]
    if chosen is None:
        raise SystemExit("calibration chose no partition: 4/12 stays and the plan stops for disposition")
    observation, read = (int(part) for part in chosen.split("/"))
    return observation, read


def index_records(repository: Path, frozen: Frozen) -> dict[str, list[dict[str, Any]]]:
    """index-check.json's real-index rows per family, refused unless they cover exactly the frozen files and matched every state."""
    report = json.loads((repository / REPORTS / "index-check.json").read_text(encoding="utf-8"))
    if report["mismatches"]:
        raise FrozenInputChanged("index-check.json has mismatches")
    rows = {family["family"]: family["candidates"] for family in report["families"]}
    for workspace in frozen.cases["ambiguity"]["workspaces"]:
        if [row["path"] for row in rows[workspace["family"]]] != [entry["path"] for entry in workspace["files"]]:
            raise FrozenInputChanged(f"index-check.json does not cover {workspace['family']}'s frozen files")
    return rows


def capacity_trade(runs: Mapping[str, Mapping[str, Mapping[str, Any]]], chosen: str) -> dict[str, Any]:
    """What one turn's current reads give up: every schedule, probe templates included, that 4/12 completes and the chosen one does not."""
    observation, read = (int(part) * 1024 for part in chosen.split("/"))
    return {
        "current_read_bytes": {"4/12": 12 * 1024, chosen: read},
        "observation_bytes": {"4/12": 4 * 1024, chosen: observation},
        "current_read_bytes_lost": 12 * 1024 - read,
        "lost_completions": sorted(sid for sid, row in runs[BASELINE].items() if row["completed"] and not runs[chosen][sid]["completed"]),
        "claim": "no capacity-preservation claim: a current read over the chosen limit is a typed read-budget stop within one turn",
    }


def qualify(
    ambiguity_scores: Mapping[str, Any], ambiguity_rows: Sequence[Mapping[str, Any]], split_report: Mapping[str, Any], chosen: str
) -> dict[str, Any]:
    """Plan v4 held-out gates, judged once. #242, per order: top-one and reciprocal rank both at least path-only and one strictly higher,
    on the same rows, with zero wrong targets, no candidate lost and no denied file listed. #245: every held-out probe of the chosen
    partition passes, it completes at least one more held-out non-boundary schedule than 4/12, and loses none 4/12 completes."""
    held = ambiguity_scores["held_out"]
    safe = held["wrong_target_selections"] == 0 and held["candidates_lost"] == 0 and held["denied_listed"] == 0
    stops_visible = all(row["outcome"] == "ambiguous_stop" for row in ambiguity_rows if row["expected"] == "ambiguous_stop")
    verdicts: dict[str, Any] = {}
    for order in ("ranked", "index"):
        top, rr = held[f"{order}_top_one"], held[f"{order}_reciprocal_rank"]
        base_top, base_rr = held["path_only_top_one"], held["path_only_reciprocal_rank"]
        if top is None or rr is None or base_top is None or base_rr is None:
            verdicts[order] = {"passed": False, "reason": "unmeasured"}
            continue
        better = top >= base_top and rr >= base_rr and (top > base_top or rr > base_rr)
        verdicts[order] = {"passed": better and safe and stops_visible, "top_one": [base_top, top], "reciprocal_rank": [base_rr, rr]}
    runs = split_report["runs"]

    def done(label: str) -> set[str]:
        return {sid for sid, row in runs[label].items() if not row["boundary"] and row["completed"]}

    failed_probes = [f"{probe['template']}:{probe['variant']}" for probe in split_report["probes"].get(chosen, ()) if not probe["passed"]]
    lost = sorted(done(BASELINE) - done(chosen))
    gained = sorted(done(chosen) - done(BASELINE))
    return {
        "ambiguity_242": {
            **verdicts,
            "safety": {"zero_wrong_targets_no_loss_no_denied": safe, "every_expected_stop_visible": stops_visible},
        },
        "split_245": {
            "passed": not failed_probes and not lost and bool(gained),
            "chosen": chosen,
            "failed_probes": failed_probes,
            "baseline_successes_lost": lost,
            "non_boundary_completions_gained": gained,
        },
    }


def determinism(frozen: Frozen, work: Path, chosen: tuple[int, int]) -> dict[str, Any]:
    """Train and development only: every ambiguity case twice, its files written in opposite orders, and every schedule twice at the
    chosen partition. Byte-identical rows, or the differing ids."""
    if work.exists():
        shutil.rmtree(work)
    cases = selected(frozen.cases["ambiguity"]["cases"], phase="determinism", splits=("train", "development"))
    differing_cases = [
        case["id"]
        for case in cases
        if json.dumps(ambiguity_baseline(frozen, case, work / "a" / case["id"]), sort_keys=True)
        != json.dumps(ambiguity_baseline(frozen, case, work / "b" / case["id"], reverse=True), sort_keys=True)
    ]
    schedules = selected(frozen.cases["split_schedules"]["schedules"], phase="determinism", splits=("train", "development"))
    differing_schedules = [
        item["id"]
        for item in schedules
        if json.dumps(run_schedule(resolve(item), chosen, work / "s1" / item["id"]), sort_keys=True)
        != json.dumps(run_schedule(resolve(item), chosen, work / "s2" / item["id"]), sort_keys=True)
    ]
    shutil.rmtree(work)
    return {
        "ambiguity": {"cases": len(cases), "reordered": "files written in opposite orders", "differing": differing_cases},
        "schedules": {"runs": len(schedules), "partition": f"{chosen[0]}/{chosen[1]}", "differing": differing_schedules},
        "why_pages": "tests/unit/context/test_context_why.py (unit): pages are rendered from one immutable snapshot",
        "identical": not differing_cases and not differing_schedules,
    }


# main merged into the branch, before Task 2's code
PRE_TASK2 = "e0ece334e5f394544ff723aca7184715ea74b8f9"  # pragma: allowlist secret (a git commit)


def cache_identity(repository: Path) -> dict[str, Any]:
    """The planner prompt's versions, and its cacheable prefix and one fixed request digested under 4/12 and under the production limits;
    the registry's ordinary, Auto and test-profile hashes, and whether any registry file changed since before Task 2."""
    from optimus.agent import prompts
    from optimus.agent.workspace_context import DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES
    from optimus_model_policy import binding
    from optimus_model_policy.registry import load_registry
    from optimus_model_policy.test_profiles import TEST_PROFILES, compose_test_profile_snapshot

    def sha(text: str) -> str:
        return "hex:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

    limits = {
        "4/12": (4 * 1024, 12 * 1024, DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES),
        "production": (pl.PLANNING_OBSERVATION_MAX_BYTES, pl.PLANNING_NEW_READ_MAX_BYTES, DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES),
    }
    digests = {
        label: {
            "limits": list(value),
            "prefix_tools_on": sha(prompts.indexed_planner_prefix(repo_map="", tools_enabled=True, evidence_limits=value)),
            "prefix_tools_off": sha(prompts.indexed_planner_prefix(repo_map="", tools_enabled=False, evidence_limits=value)),
            "request": sha(
                prompts.build_multi_turn_planner_input(
                    "Plan a change", planning_turn=1, max_planning_turns=3, remaining_wall_clock_minutes=30, evidence_limits=value
                )
            ),
        }
        for label, value in limits.items()
    }
    changed = subprocess.run(
        ["git", "-C", str(repository), "diff", "--name-only", PRE_TASK2, "HEAD", "--", "src/optimus_model_policy"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    auto = load_registry(binding.packaged_defaults(), Path(binding.__file__).with_name(binding.AUTO_OVERLAY_FILENAME))
    return {
        "prompt_versions": {
            "multi_turn_planner": prompts.MULTI_TURN_PLANNER_PROMPT_VERSION,
            "indexed_planner": prompts.INDEXED_PLANNER_PROMPT_VERSION,
            "unchanged": "the templates are unchanged; only the rendered limit values differ",
        },
        "digests": digests,
        "prefix_changed": digests["4/12"]["prefix_tools_on"] != digests["production"]["prefix_tools_on"],
        "registry": {
            "ordinary": "hex:" + binding.compose_trusted_snapshot(binding.packaged_defaults()).effective_hash,
            "auto": "hex:" + auto.effective_hash,
            # each composition is checked against its pinned hash and raises on a difference
            "test_profiles": {
                name: "hex:" + compose_test_profile_snapshot(name).effective_hash
                for name, profile in TEST_PROFILES.items()
                if profile.override is not None and profile.effective_hash is not None
            },
            "files_changed_since": f"git:{PRE_TASK2}",
            "files_changed": changed,
        },
    }


def after_indexing(files: Sequence[Mapping[str, Any]], tree: Path, later: Iterable[str]) -> None:
    """After publication: files never indexed appear, and stale files now differ from their records. Files are written directly, so the
    family's frozen ignore file is left as it was (Codex CP1 review 1, finding 5)."""
    added = set(later)
    for entry in files:
        target = tree / entry["path"]
        if entry["path"] in added:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_content(entry))
        elif entry.get("metadata") == "stale":
            target.write_bytes(_content(entry) + b"# edited after indexing\n")


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
    workspace_split = {case["family"]: case["split"] for case in frozen.cases["ambiguity"]["cases"]}
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
            after_indexing(files, tree, later)
            policy = FilePolicy(tree)
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
                decision = policy.decide(entry["path"], purpose=FilePurpose.AUTOMATIC)
                denied = "denied" in entry
                rows.append(
                    {
                        "path": entry["path"],
                        "frozen": "denied" if denied else entry.get("metadata"),
                        "observed": state,
                        "policy_allowed": decision.allowed,
                        "policy_reason": decision.reason,
                        "imports": list(imports_of(record.description)) if record else [],
                        "labels": labels,
                        # a denied file must be refused by the real policy and absent from the index; anything else must show its frozen state
                        "matches": (record is None and not decision.allowed)
                        if denied
                        else (decision.allowed and state == entry.get("metadata")),
                    }
                )
            family = {
                "family": workspace["family"],
                "split": workspace_split[workspace["family"]],
                "files_written": outcome.files_written,
                "records": outcome.records_written,
                "coverage": outcome.coverage,
                "candidates": rows,
            }
            if family["split"] != "held_out":  # task text is read only for train/development before qualification (CP1 finding 6)
                resolved_paths = sorted(
                    {
                        path
                        for case in frozen.cases["ambiguity"]["cases"]
                        if case["family"] == workspace["family"]
                        for path in (entry["path"] for entry in files)
                        if path in case["task"]
                    }
                )
                family["neighbours_of_resolved_task_paths"] = {path: neighbours(map_files, [path]) for path in resolved_paths}
            families.append(family)
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
        "later_files": "files marked none were written after publication, leaving the frozen ignore file unchanged; files marked stale were "
        "edited after it; denied files must be refused by the real FilePolicy and absent from the index",
        "task_text": "read only for train/development families (neighbours of resolved task paths); held-out families report metadata states only",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m2a_evaluate")
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--phase", required=True, choices=("calibration", "index-check", "qualification", "split", "determinism", "cache-identity")
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    repository = Path(__file__).resolve().parents[2]
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    frozen = load_frozen(repository)
    report: dict[str, Any] = {
        "schema": f"plan12-memory-m2a.{args.phase}.v{1 if args.phase in ('index-check', 'split', 'determinism', 'cache-identity') else 2}",
        "head": f"git:{_head(repository)}",
        "phase": args.phase,
        "inputs": frozen.digests,
        "paid_attempts": 0,
        "provider_cost_usd": "0",
    }
    work = repository / config["work_dir"] / args.phase
    if args.phase == "index-check":
        report.update(index_check(frozen, config, repository))
    elif args.phase == "cache-identity":
        report.update(cache_identity(repository))
    elif args.phase == "determinism":
        report.update(determinism(frozen, work, chosen_partition(repository, frozen)))
    elif args.phase == "qualification":
        chosen = chosen_partition(repository, frozen)
        label = f"{chosen[0]}/{chosen[1]}"
        report["splits"] = ["held_out"]
        report.update(
            calibration(
                frozen, work, ("held_out",), phase="qualification", partitions=((4, 12), chosen), index=index_records(repository, frozen)
            )
        )
        report["gates"] = qualify(report["ambiguity"]["scores"], report["ambiguity"]["rows"], report["split"], label)
        report["held_out_custody"] = (
            "consumed once at this head; no tuning against these results; a second use needs a successor disposition"
        )
    else:
        splits = ("train", "development")
        report["splits"] = list(splits)
        index = index_records(repository, frozen) if args.phase == "split" else None
        report.update(calibration(frozen, work, splits, phase=args.phase, index=index))
        if args.phase == "split":
            chosen = report["split"]["choice"]["chosen"]
            report["capacity_trade"] = None if chosen is None else capacity_trade(report["split"]["runs"], chosen)
            report["f2"] = F2
    Path(args.output).write_text(json.dumps(report, indent=1, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
