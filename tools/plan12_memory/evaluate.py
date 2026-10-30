"""Offline fixture validation and per-case grading for the Plan 12.5 memory evaluation.

Grading compares structured trace facts with the case's gold; it never compares prose.
Each layer reports FAIL for an observed violation, INCONCLUSIVE when the evidence cannot
decide (judge error, unlisted alternative evidence, missing trace coverage) and PASS
otherwise. A deterministic synthetic trace tests this grader, not the production system.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from pydantic import ValidationError

from tools.plan12_memory.contracts import (
    AttemptReceipt,
    CaseVerdict,
    ExpectedMemory,
    GoldenCase,
    Layer,
    LayerVerdict,
    Measurements,
    MemoryStateObservation,
    ObservedEvidence,
    ObservedTrace,
    SplitManifest,
    Status,
    TraceEvent,
    ValidationReport,
)

FIXTURE_SCHEMA = "plan12-memory-fixtures/1"
SPLITS_SCHEMA = "plan12-memory-splits/1"
_SEVERITY: dict[Status, int] = {"PASS": 0, "INCONCLUSIVE": 1, "FAIL": 2, "UNRUN": 3}
RETRIEVAL_K = 5  # predeclared in reports/plan12-memory-evaluation/case-review.json metrics


_UNSERVABLE = frozenset({"withdrawn", "purged", "archived", "superseded"})
_DESTRUCTION_PREREQUISITES = ("generation.usable_verified", "rotation.acknowledged", "rotation.committed")


def _layer(fails: list[str], doubts: list[str], notes: Sequence[str] = ()) -> LayerVerdict:
    status: Status = "FAIL" if fails else "INCONCLUSIVE" if doubts else "PASS"
    return LayerVerdict(status=status, reasons=(*fails, *doubts, *notes))


def _matches(name: str, event: TraceEvent, case: GoldenCase) -> bool:
    """An event ID is ``type`` or ``type:key``. The keyed form matches only that item's events in the case's
    project, and at its expected version when the case expects exactly one present version of the item."""
    kind, _, key = name.partition(":")
    if event.type != kind:
        return False
    if not key:
        return True
    versions = {item.version for item in case.expected_memory if item.key == key and item.trust != "absent"}
    return (event.memory_key == key and event.project_id == case.project_id
            and (len(versions) != 1 or event.version in versions))


def _describe(item: ExpectedMemory | MemoryStateObservation) -> str:
    supersedes = f"/supersedes v{item.supersedes}" if item.supersedes else ""
    return f"{item.trust}/{item.status}{'/off' if item.off else ''}{supersedes}"


def _replaced(events: list[TraceEvent], destroyed: TraceEvent) -> bool:
    """Whether one newer generation of the same rotation was verified, acknowledged and committed, in order, first."""
    old = destroyed.version or 0
    earlier = [event for event in events if event.seq < destroyed.seq and event.rotation_id == destroyed.rotation_id]
    for new in {event.version for event in earlier if event.version is not None and event.version > old}:
        steps = iter(event.type for event in earlier if event.version == new)
        if all(step in steps for step in _DESTRUCTION_PREREQUISITES):
            return True
    return False


def _authority(case: GoldenCase, trace: ObservedTrace) -> LayerVerdict:
    events = sorted(trace.events, key=lambda event: event.seq)
    fails = [f"prohibited event {name} occurred" for name in case.prohibited_events if any(_matches(name, e, case) for e in events)]
    remaining = iter(events)
    if not all(any(_matches(name, event, case) for event in remaining) for name in case.required_events):
        fails.append(f"required events {list(case.required_events)} are missing or out of order")
    state: dict[tuple[str, str, int | None], MemoryStateObservation] = {
        (item.key, item.project_id, item.version): item for item in trace.memory_state
    }
    for memory in trace.served_memory:
        if memory.project_id != case.project_id:
            fails.append(f"served memory {memory.memory_id} belongs to project {memory.project_id}, not {case.project_id}")
            continue
        observed = state.get((memory.memory_id, memory.project_id, memory.version))
        if observed is None:
            fails.append(f"served memory {memory.memory_id} v{memory.version} has no observed state at that version")
        elif observed.off or observed.status in _UNSERVABLE:
            fails.append(f"served memory {memory.memory_id} v{memory.version} is {_describe(observed)} and may not be served")
    served_refs = {(memory.memory_id, memory.project_id, memory.version) for memory in trace.served_memory}
    serving_events = [event for event in events if event.type == "memory.served"]
    fails += [f"serving event at seq {event.seq} names no served item version" for event in serving_events
              if (event.memory_key, event.project_id, event.version) not in served_refs]
    announced = {(event.memory_key, event.project_id, event.version) for event in serving_events}
    fails += [f"served memory {key} v{version} has no serving event" for key, _, version in sorted(served_refs - announced, key=str)]
    for name in case.prohibited_events:
        kind, _, key = name.partition(":")
        if kind == "memory.served" and any(not key or memory.memory_id == key for memory in trace.served_memory):
            fails.append(f"prohibited serving {name} appears in served_memory")
    for index, event in enumerate(events):
        ref = (event.memory_key, event.project_id, event.version)
        if event.type == "memory.notice.remembered" and (None in ref or not any(
                earlier.type == "memory.committed" and (earlier.memory_key, earlier.project_id, earlier.version) == ref
                for earlier in events[:index])):
            fails.append(f"notice at seq {event.seq} has no earlier durable commit of the same item version in this project")
    if any(name.partition(":")[0] == "memory.notice.remembered" for name in case.required_events):
        noticed = {(e.memory_key, e.project_id, e.version) for e in events if e.type == "memory.notice.remembered"}
        fails += [
            f"no notice names {expected.key} v{expected.version}, the committed version"
            for expected in case.expected_memory
            if expected.status == "active" and not expected.off and (expected.key, expected.project_id, expected.version) not in noticed
        ]
    destroyed = [event for event in events if event.type == "rotation.old_root_destroyed"]
    fails += [f"old root generation {generation} was destroyed {count} times"
              for generation, count in Counter(event.version for event in destroyed).items() if count > 1]
    for event in destroyed:
        if event.rotation_id is None or event.version is None:
            fails.append(f"old root destroyed at seq {event.seq} names no rotation or old generation")
            continue
        if not _replaced(events, event):
            fails.append(f"old root generation {event.version} destroyed at seq {event.seq} before its rotation verified, "
                         "acknowledged and committed one newer generation")
    for expected in case.expected_memory:
        if expected.trust == "absent":
            if any((item.key, item.project_id) == (expected.key, expected.project_id) for item in trace.memory_state):
                fails.append(f"memory {expected.key} in {expected.project_id} exists, expected absent")
            continue
        observed = state.get((expected.key, expected.project_id, expected.version))
        found = "absent" if observed is None else _describe(observed)
        wanted = _describe(expected)
        if found != wanted:
            fails.append(f"memory {expected.key} v{expected.version} in {expected.project_id} is {found}, expected {wanted}")
    return _layer(fails, [])


def _retrieval(
    case: GoldenCase, trace: ObservedTrace,
) -> tuple[LayerVerdict, list[str], Decimal | None, Decimal | None, list[ObservedEvidence]]:
    fails: list[str] = []
    doubts: list[str] = []
    valid = {}
    for evidence in trace.evidence:
        if evidence.observed_at > case.cutoff:
            fails.append(f"evidence {evidence.evidence_id} was observed after the cutoff (future leakage)")
        elif evidence.project_id != case.project_id:
            fails.append(f"evidence {evidence.evidence_id} is out of scope (project {evidence.project_id})")
        elif evidence.revision != case.snapshot:
            fails.append(f"evidence {evidence.evidence_id} is stale (revision {evidence.revision}, snapshot {case.snapshot})")
        else:
            valid[evidence.evidence_id] = evidence
    # Leakage, scope and staleness are checked over every item; support counts only within the first k.
    ranked = trace.evidence[:RETRIEVAL_K]
    top = [item for item in ranked if item.evidence_id in valid]
    top_ids = {item.evidence_id for item in top}
    satisfied = 0
    for requirement in case.required_evidence:
        if top_ids & set(requirement.any_of):
            satisfied += 1
            continue
        offered = [item.evidence_id for item in top if requirement.requirement_id in item.supports]
        if offered:
            doubts.append(
                f"requirement {requirement.requirement_id} is supported only by unlisted evidence {offered}; "
                "a reviewer may add it as an acceptable alternative"
            )
        else:
            fails.append(f"requirement {requirement.requirement_id} has no supporting evidence in the first {RETRIEVAL_K}")
    served_order = [memory.memory_id for memory in trace.served_memory]
    unserved = [key for key in case.expected_rank if key not in served_order]
    positions = [served_order.index(key) for key in case.expected_rank if key in served_order]
    if unserved:
        fails.append(f"ranked memories {unserved} were not served")
    elif positions != sorted(positions):
        fails.append(f"served order {served_order} breaks the required rank {list(case.expected_rank)}")
    gold = {evidence_id for requirement in case.required_evidence for evidence_id in requirement.any_of}
    recall = Decimal(satisfied) / len(case.required_evidence) if case.required_evidence else None
    precision = Decimal(len(top_ids & gold)) / len(ranked) if ranked else None
    return _layer(fails, doubts), list(valid), recall, precision, top


def _loci(case: GoldenCase, claims: Sequence[str], top: list[ObservedEvidence]) -> tuple[list[str], list[str]]:
    """Each localization requirement needs an answered locus that is itself retrieved within the first k."""
    answered = {claim.removeprefix("locus:") for claim in claims if claim.startswith("locus:")}
    fails: list[str] = []
    doubts: list[str] = []
    for requirement in case.required_evidence:
        accepted = set(requirement.any_of)
        if answered & accepted & {item.evidence_id for item in top}:
            continue
        unlisted = [item.evidence_id for item in top
                    if item.evidence_id in answered - accepted and requirement.requirement_id in item.supports]
        if unlisted:
            doubts.append(f"the answer's locus for {requirement.requirement_id} is unlisted evidence {unlisted}; a reviewer may accept it")
        elif answered & accepted:
            fails.append(f"the answer's locus for {requirement.requirement_id} is not supported by the retrieved evidence")
        else:
            fails.append(f"the answer names no locus for requirement {requirement.requirement_id}")
    return fails, doubts


def _answer(case: GoldenCase, trace: ObservedTrace, top: list[ObservedEvidence]) -> LayerVerdict:
    answer = trace.answer
    fails: list[str] = []
    doubts: list[str] = []
    if answer.action != case.expected_action:
        fails.append(f"action {answer.action}, expected {case.expected_action}")
    served = {(memory.memory_id, memory.version) for memory in trace.served_memory}
    cited = {(citation.memory_id, citation.version) for citation in answer.citations}
    fails += [
        f"citation {citation.memory_id} v{citation.version} is fabricated: it was not served at that version"
        for citation in answer.citations
        if (citation.memory_id, citation.version) not in served
    ]
    fails += [
        f"memory {used.memory_id} v{used.version} supports the answer but is not cited"
        for used in answer.supported_by
        if (used.memory_id, used.version) not in cited
    ]
    if trace.served_memory and not answer.support_extracted:
        doubts.append("memory was served but no extractor attributed the answer's support; citation support is undecided")
    if answer.judge_status != "ok":
        doubts.append(f"claim judge reported {answer.judge_status}; claim checks are undecided")
    else:
        fails += [f"prohibited claim {claim} was made" for claim in case.prohibited_claims if claim in answer.claims]
        fails += [f"required fact {fact} is missing" for fact in case.required_facts if fact not in answer.claims]
        if case.kind == "localization":
            locus_fails, locus_doubts = _loci(case, answer.claims, top)
            fails += locus_fails
            doubts += locus_doubts
    return _layer(fails, doubts)


def _counted_attempts(trace: ObservedTrace, notes: list[str]) -> tuple[list[AttemptReceipt], Decimal, bool]:
    """Deduplicate replays, exclude conflicts and keep every unknown visible."""
    by_id: dict[str, AttemptReceipt] = {}
    conflicts: set[str] = set()
    for attempt in trace.attempts:
        previous = by_id.setdefault(attempt.attempt_id, attempt)
        if previous != attempt:
            conflicts.add(attempt.attempt_id)
            notes.append(f"attempt {attempt.attempt_id} has a conflicting duplicate; never counted as a new charge")
    by_gateway: defaultdict[str, list[str]] = defaultdict(list)
    for attempt in by_id.values():
        if attempt.gateway_request_id is not None:
            by_gateway[attempt.gateway_request_id].append(attempt.attempt_id)
    for gateway_id, attempt_ids in by_gateway.items():
        if len(attempt_ids) > 1:
            conflicts.update(attempt_ids)
            notes.append(f"gateway request {gateway_id} is shared by attempts {attempt_ids} (conflict)")
    counted: list[AttemptReceipt] = []
    known = Decimal(0)
    complete = trace.coverage_complete is True
    for attempt in by_id.values():
        if attempt.attempt_id in conflicts:
            complete = False
        elif attempt.gateway_request_id is None:
            complete = False
            notes.append(f"attempt {attempt.attempt_id} is unattributed; its cost stays unknown")
        elif attempt.state == "intent_only":
            complete = False
            notes.append(f"attempt {attempt.attempt_id} has an intent but no receipt (missing tail)")
        elif attempt.cost_usd is None or attempt.price_snapshot_id is None:
            complete = False
            notes.append(f"attempt {attempt.attempt_id} has no dated price; its cost stays unknown")
        else:
            counted.append(attempt)
            known += attempt.cost_usd
            if attempt.state == "late":
                complete = False
                notes.append(f"attempt {attempt.attempt_id} settled late; the epoch was not complete at close")
    return counted, known, complete


def _cost(case: GoldenCase, trace: ObservedTrace) -> tuple[LayerVerdict, Decimal, bool]:
    fails: list[str] = []
    notes: list[str] = []
    counted, known, complete = _counted_attempts(trace, notes)
    for receipt in (item.attempt for item in case.inputs if item.attempt is not None):
        if receipt not in trace.attempts:
            seen = any(attempt.attempt_id == receipt.attempt_id for attempt in trace.attempts)
            fails.append(f"receipt {receipt.attempt_id} from the case inputs is {'altered' if seen else 'missing'} in the trace")
    reported = trace.reported_cost
    if reported.complete is True and not complete:
        fails.append("reported complete, but the receipts are not complete")
    if reported.known_usd != known:
        fails.append(f"reported known cost {reported.known_usd} differs from the receipts' {known}")
    savings = reported.savings
    if savings is not None:
        if savings.basis == "same_tokens_repriced" and savings.label != "estimated":
            fails.append("same-tokens-repriced savings must be labelled estimated")
        if savings.basis == "matched_run" and savings.label != "measured":
            fails.append("matched-run savings must be labelled measured")
        if savings.reference_price_snapshot_id is None:
            fails.append("savings need a dated price snapshot")
        if savings.counterfactual_tokens_inferred:
            fails.append("counterfactual token usage was inferred from actual tokens")
        tokens = [(a.input_tokens, a.output_tokens, a.cache_tokens, a.reasoning_tokens) for a in counted]
        if savings.basis == "same_tokens_repriced" and any(None in row for row in tokens):
            fails.append("repricing is unavailable: a token category is null")
    expected = case.expected_cost
    if expected is not None:
        if known != expected.known_usd:
            fails.append(f"receipts give known cost {known}, gold expects {expected.known_usd}")
        if expected.complete is not None and expected.complete != complete:
            fails.append(f"receipts give completeness {complete}, gold expects {expected.complete}")
        claimed = None if savings is None else (savings.label, savings.basis, savings.amount_usd, savings.reference_price_snapshot_id)
        gold = expected.savings
        wanted = None if gold is None else (gold.label, gold.basis, gold.amount_usd, gold.reference_price_snapshot_id)
        if claimed != wanted:
            fails.append(f"reported savings {claimed}, gold expects {wanted}")
    return _layer(fails, [], notes), known, complete


def grade_trace(case: GoldenCase, trace: ObservedTrace | None) -> CaseVerdict:
    """Grade one trace against its case; no trace means UNRUN, never PASS."""
    if trace is None:
        return CaseVerdict(
            case_id=case.case_id, case_version=case.version, execution_status="UNRUN", layers={},
            reasons=("no trace: UNRUN",), evidence_ids=(), measurements=None,
        )
    if trace.case_id != case.case_id:
        raise ValueError(f"trace case_id {trace.case_id} does not match case {case.case_id}")
    if trace.case_version != case.version:
        raise ValueError(f"trace case version {trace.case_version} does not match case version {case.version}")
    retrieval, evidence_ids, recall, precision, top = _retrieval(case, trace)
    cost, known, complete = _cost(case, trace)
    layers: dict[Layer, LayerVerdict] = {
        "authority": _authority(case, trace), "retrieval": retrieval, "answer": _answer(case, trace, top), "cost": cost,
    }
    if trace.missing_coverage:
        gap = f"trace is missing coverage for {list(trace.missing_coverage)}; no layer can pass"
        layers = {
            name: verdict if verdict.status == "FAIL" else LayerVerdict(status="INCONCLUSIVE", reasons=(*verdict.reasons, gap))
            for name, verdict in layers.items()
        }
    status = max((verdict.status for verdict in layers.values()), key=_SEVERITY.__getitem__)
    savings = trace.reported_cost.savings
    return CaseVerdict(
        case_id=case.case_id,
        case_version=case.version,
        execution_status=status,
        layers=layers,
        reasons=tuple(f"{name}: {reason}" for name, verdict in layers.items() for reason in verdict.reasons),
        evidence_ids=tuple(evidence_ids),
        measurements=Measurements(
            known_cost_usd=known, cost_complete=complete, savings_usd=savings.amount_usd if savings else None,
            timing_ms=trace.timing_ms, retrieval_recall=recall, retrieval_precision=precision,
        ),
    )


def _invalid_fields(exc: ValidationError) -> list[str]:
    return sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})


def _manifest_errors(manifest: SplitManifest, cases: list[GoldenCase]) -> list[str]:
    errors: list[str] = []
    assigned = {family: split for split, families in manifest.families.items() for family in families}
    families_by_kind: defaultdict[str, set[str]] = defaultdict(set)
    for case in cases:
        families_by_kind[case.kind].add(case.family)
        if case.family not in assigned:
            errors.append(f"case {case.case_id}: family {case.family} is not in the split manifest")
        elif assigned[case.family] != case.split:
            errors.append(f"case {case.case_id}: split {case.split}, manifest says {assigned[case.family]}")
    present = {case.family for case in cases}
    errors += [f"manifest family {family} has no cases" for family in sorted(assigned.keys() - present)]
    for kind, expected in manifest.expected_family_counts.items():
        if len(families_by_kind[kind]) != expected:
            errors.append(f"{kind}: {len(families_by_kind[kind])} families, manifest expects {expected}")
    order = ("train", "development", "held_out")
    for kind in manifest.chronological_kinds:
        cutoffs = {split: [c.cutoff for c in cases if c.kind == kind and c.split == split] for split in order}
        for earlier, later in pairwise(order):
            if cutoffs[earlier] and cutoffs[later] and max(cutoffs[earlier]) >= min(cutoffs[later]):
                errors.append(f"{kind}: a {earlier} cutoff is not before every {later} cutoff")
    return errors


def validate_cases(path: Path) -> ValidationReport:
    """Validate every fixture file at ``path`` (a file or a directory of ``*.json``).

    A ``plan12-memory-splits/1`` file in the same directory is the split manifest: every
    case must then match its family assignment, cardinalities and chronological order.
    """
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    errors: list[str] = [] if files else [f"{path}: no fixture files"]
    cases: list[GoldenCase] = []
    manifests: list[SplitManifest] = []
    for file in files:
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{file.name}: unreadable JSON ({type(exc).__name__})")
            continue
        if isinstance(payload, dict) and payload.get("schema") == SPLITS_SCHEMA:
            try:
                manifests.append(SplitManifest.model_validate(payload))
            except ValidationError as exc:
                errors.append(f"{file.name}: invalid split manifest fields {_invalid_fields(exc)}")
            continue
        if not isinstance(payload, dict) or payload.get("schema") != FIXTURE_SCHEMA or not isinstance(payload.get("cases"), list):
            errors.append(f"{file.name}: not a {FIXTURE_SCHEMA} file")
            continue
        for index, raw in enumerate(payload["cases"], start=1):
            try:
                cases.append(GoldenCase.model_validate(raw))
            except ValidationError as exc:
                errors.append(f"{file.name} case {index}: invalid fields {_invalid_fields(exc)}")
    seen: set[tuple[str, int]] = set()
    family_splits: defaultdict[str, set[str]] = defaultdict(set)
    controlled: set[str] = set()
    for case in cases:
        key = (case.case_id, case.version)
        if key in seen:
            errors.append(f"duplicate case {case.case_id} v{case.version}")
        seen.add(key)
        family_splits[case.family].add(case.split)
        if case.role == "control":
            controlled.add(case.family)
    errors += [f"family {family} spans splits {sorted(splits)}" for family, splits in sorted(family_splits.items()) if len(splits) > 1]
    lifecycle = sorted({case.family for case in cases if case.kind == "lifecycle"})
    errors += [f"lifecycle family {family} has no control case" for family in lifecycle if family not in controlled]
    if len(manifests) > 1:
        errors.append("more than one split manifest")
    elif manifests:
        errors += _manifest_errors(manifests[0], cases)
    families = {(case.kind, case.family) for case in cases}
    return ValidationReport(
        files=tuple(file.name for file in files),
        case_count=len(cases),
        kind_counts=tuple(sorted(Counter(case.kind for case in cases).items())),
        family_counts=tuple(sorted(Counter(kind for kind, _ in families).items())),
        split_counts=tuple(sorted(Counter(case.split for case in cases).items())),
        errors=tuple(errors),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.plan12_memory.evaluate", description=__doc__)
    parser.add_argument(
        "--validate-only", action="store_true", required=True, help="validate fixtures; grading runs through grade_trace"
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    report = validate_cases(args.path)
    print(f"{report.case_count} cases in {len(report.files)} files; families {dict(report.family_counts)}; "
          f"cases by kind {dict(report.kind_counts)}; splits {dict(report.split_counts)}; {len(report.errors)} errors")
    for error in report.errors:
        print(f"error: {error}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
