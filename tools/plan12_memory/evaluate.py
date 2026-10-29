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
from pathlib import Path

from pydantic import ValidationError

from tools.plan12_memory.contracts import (
    AttemptReceipt,
    CaseVerdict,
    GoldenCase,
    Layer,
    LayerVerdict,
    Measurements,
    ObservedTrace,
    Status,
    ValidationReport,
)

FIXTURE_SCHEMA = "plan12-memory-fixtures/1"
_SEVERITY: dict[Status, int] = {"PASS": 0, "INCONCLUSIVE": 1, "FAIL": 2, "UNRUN": 3}


def _layer(fails: list[str], doubts: list[str], notes: Sequence[str] = ()) -> LayerVerdict:
    status: Status = "FAIL" if fails else "INCONCLUSIVE" if doubts else "PASS"
    return LayerVerdict(status=status, reasons=(*fails, *doubts, *notes))


def _authority(case: GoldenCase, trace: ObservedTrace) -> LayerVerdict:
    types = [event.type for event in sorted(trace.events, key=lambda event: event.seq)]
    fails = [f"prohibited event {name} occurred" for name in case.prohibited_events if name in types]
    remaining = iter(types)
    if not all(name in remaining for name in case.required_events):
        fails.append(f"required events {list(case.required_events)} are missing or out of order")
    fails += [
        f"served memory {memory.memory_id} belongs to project {memory.project_id}, not {case.project_id}"
        for memory in trace.served_memory
        if memory.project_id != case.project_id
    ]
    return _layer(fails, [])


def _retrieval(case: GoldenCase, trace: ObservedTrace) -> tuple[LayerVerdict, list[str], Decimal | None, Decimal | None]:
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
    satisfied = 0
    for requirement in case.required_evidence:
        if valid.keys() & set(requirement.any_of):
            satisfied += 1
            continue
        offered = [item.evidence_id for item in valid.values() if requirement.requirement_id in item.supports]
        if offered:
            doubts.append(
                f"requirement {requirement.requirement_id} is supported only by unlisted evidence {offered}; "
                "a reviewer may add it as an acceptable alternative"
            )
        else:
            fails.append(f"requirement {requirement.requirement_id} has no supporting evidence")
    gold = {evidence_id for requirement in case.required_evidence for evidence_id in requirement.any_of}
    recall = Decimal(satisfied) / len(case.required_evidence) if case.required_evidence else None
    precision = Decimal(len(valid.keys() & gold)) / len(trace.evidence) if trace.evidence else None
    return _layer(fails, doubts), list(valid), recall, precision


def _answer(case: GoldenCase, trace: ObservedTrace) -> LayerVerdict:
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
    if answer.judge_status != "ok":
        doubts.append(f"claim judge reported {answer.judge_status}; claim checks are undecided")
    else:
        fails += [f"prohibited claim {claim} was made" for claim in case.prohibited_claims if claim in answer.claims]
        fails += [f"required fact {fact} is missing" for fact in case.required_facts if fact not in answer.claims]
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
    retrieval, evidence_ids, recall, precision = _retrieval(case, trace)
    cost, known, complete = _cost(case, trace)
    layers: dict[Layer, LayerVerdict] = {
        "authority": _authority(case, trace), "retrieval": retrieval, "answer": _answer(case, trace), "cost": cost,
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


def validate_cases(path: Path) -> ValidationReport:
    """Validate every fixture file at ``path`` (a file or a directory of ``*.json``)."""
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    errors: list[str] = [] if files else [f"{path}: no fixture files"]
    cases: list[GoldenCase] = []
    for file in files:
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{file.name}: unreadable JSON ({type(exc).__name__})")
            continue
        if not isinstance(payload, dict) or payload.get("schema") != FIXTURE_SCHEMA or not isinstance(payload.get("cases"), list):
            errors.append(f"{file.name}: not a {FIXTURE_SCHEMA} file")
            continue
        for index, raw in enumerate(payload["cases"], start=1):
            try:
                cases.append(GoldenCase.model_validate(raw))
            except ValidationError as exc:
                fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
                errors.append(f"{file.name} case {index}: invalid fields {fields}")
    seen: set[tuple[str, int]] = set()
    family_splits: defaultdict[str, set[str]] = defaultdict(set)
    for case in cases:
        key = (case.case_id, case.version)
        if key in seen:
            errors.append(f"duplicate case {case.case_id} v{case.version}")
        seen.add(key)
        family_splits[case.family].add(case.split)
    errors += [f"family {family} spans splits {sorted(splits)}" for family, splits in sorted(family_splits.items()) if len(splits) > 1]
    return ValidationReport(
        files=tuple(file.name for file in files),
        case_count=len(cases),
        kind_counts=tuple(sorted(Counter(case.kind for case in cases).items())),
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
    print(f"{report.case_count} cases in {len(report.files)} files; kinds {dict(report.kind_counts)}; "
          f"splits {dict(report.split_counts)}; {len(report.errors)} errors")
    for error in report.errors:
        print(f"error: {error}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
