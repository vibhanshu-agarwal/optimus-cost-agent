"""Summarizer qualification tooling for `calculator-constraints-v1` (Plan 12.2 Task 8).

Design spec 6.5-6.6 and Task 1 contracts 3. Offline in CP2: no paid call is made here. This module
provides:

- `evaluate_summary`: a deterministic fact report. It checks the `context-summary-v1` format, a
  complete (`stop`) finish, every required fact, the current and superseded rounding rules, and no
  invented approval, deletion or reversed correction. With a reading of the scenario by Claude and
  Codex, it is a limited gate, not a statistical guarantee of model quality.
- `run_qualification`: the two-step run against an injected summarizer. Step 1 summarizes the early
  turns; step 2 merges that summary with the turns holding the correction. It makes at most two
  calls, checks a dollar cap before each, never retries until a pass, and yields receipt fields only
  for a pass.
- `paid_envelope`: what the operator approves before any paid call. Per assigned summarizer it gives
  structural blockers other than the missing receipt, exact input/output caps, the attempt ceiling and
  an upper cost bound.

Usage (offline):
    python tools/evaluate_context_summarizer.py envelope [--registry FILE] [--override FILE]
    python tools/evaluate_context_summarizer.py check --summary FILE --step {step1,final} [--finish-status stop]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any

from context_engine import OrdinaryTurn
from context_engine.engine import maintenance_input
from context_engine.summary import PROMPT_DIGEST, SUMMARY_FORMAT, VALIDATOR_VERSION, SummaryFormatError, build_summary_prompt, parse_summary
from optimus.context.maintenance import SummarizerCall, SummarizerResponse
from optimus_model_policy import RegistrySnapshot, Role, load_registry, ordered_assignments, validate_registry
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "context_engine" / "calculator-constraints-v1.json"
MAX_FIXTURE_CALLS = 2
_MILLION = Decimal(1_000_000)
_SENTENCE = re.compile(r"(?<=[.;!?])\s+|\n")


@dataclass(frozen=True, slots=True)
class Fixture:
    name: str
    digest: str
    turns: Mapping[int, OrdinaryTurn]
    step1: tuple[int, ...]
    step2: tuple[int, ...]
    tail: tuple[int, ...]
    max_output_tokens: int
    step1_facts: tuple[Mapping[str, Any], ...]
    final_facts: tuple[Mapping[str, Any], ...]
    markers: tuple[str, ...]
    forbidden: tuple[Mapping[str, str], ...]


def fixture_digest(raw: Mapping[str, Any]) -> str:
    """The fixture's identity: its canonical JSON, independent of key order, whitespace and line
    endings, so a receipt never depends on how a checkout stores the file."""
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_fixture(path: Path = FIXTURE_PATH) -> Fixture:
    raw = json.loads(path.read_bytes().decode("utf-8"))
    turns = {t["seq"]: OrdinaryTurn(t["seq"], t["user_prompt"], t["plan_text"], t["completion_text"]) for t in raw["turns"]}
    ev = raw["evaluation"]
    step1, step2, tail = tuple(ev["step1_turns"]), tuple(ev["step2_turns"]), tuple(ev["exact_tail_turns"])
    ordered = tuple(sorted(turns))
    if step1 + step2 + tail != ordered:
        raise ValueError("the fixture's steps and tail must partition its turns in order")
    if 1 not in step1 or not step2:
        raise ValueError("the early constraints and the correction must both lie inside summarized ranges")
    return Fixture(
        name=raw["fixture"],
        digest=fixture_digest(raw),
        turns=turns,
        step1=step1,
        step2=step2,
        tail=tail,
        max_output_tokens=int(ev["max_output_tokens"]),
        step1_facts=tuple(raw["step1_facts"]),
        final_facts=tuple(raw["final_facts"]),
        markers=tuple(raw["supersession_markers"]),
        forbidden=tuple(raw["forbidden"]),
    )


# --- The fact report -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FactCheck:
    id: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class FactReport:
    checks: tuple[FactCheck, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": [{"id": c.id, "passed": c.passed, "detail": c.detail} for c in self.checks]}


def evaluate_summary(
    text: str | None,
    finish_status: str | None,
    facts: Sequence[Mapping[str, Any]],
    *,
    markers: Sequence[str],
    forbidden: Sequence[Mapping[str, str]],
) -> FactReport:
    checks = [FactCheck("finished", finish_status == "stop", f"finish status {finish_status!r}")]
    try:
        parse_summary(text or "")
    except SummaryFormatError as exc:
        return FactReport(tuple([*checks, FactCheck("format", False, str(exc))]))
    checks.append(FactCheck("format", True, SUMMARY_FORMAT))
    lower = (text or "").lower()
    # Sentences, so a supersession marker elsewhere on a line cannot excuse a stale rule. A decimal
    # point is not a sentence end: splitting needs whitespace after the punctuation.
    sentences = [part for part in _SENTENCE.split(lower) if part.strip()]
    for fact in facts:
        if "all" in fact:
            missing = [needle for needle in fact["all"] if needle not in lower]
            checks.append(FactCheck(fact["id"], not missing, f"missing {missing}" if missing else "present"))
        elif "current" in fact:
            rule = fact["current"]
            checks.append(FactCheck(fact["id"], rule in lower, "stated" if rule in lower else f"{rule} not stated"))
        elif "superseded" in fact:
            rule = fact["superseded"]
            mentions = [sentence for sentence in sentences if rule in sentence]
            stale = [sentence for sentence in mentions if not any(marker in sentence for marker in markers)]
            passed = bool(mentions) and not stale
            detail = "stated as superseded" if passed else ("not mentioned" if not mentions else f"stated as current: {stale[0]!r}")
            checks.append(FactCheck(fact["id"], passed, detail))
        else:
            raise ValueError(f"unknown fact kind: {fact}")
    for rule in forbidden:
        found = re.search(rule["pattern"], lower)
        checks.append(FactCheck(rule["id"], found is None, f"found {found.group(0)!r}" if found else "absent"))
    return FactReport(tuple(checks))


# --- The two-step run ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Candidate:
    model_id: str
    providers: tuple[str, ...]
    reasoning: str | None
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal


class CapRefused(Exception):
    """A call whose upper cost bound would pass the authorized dollar cap is never made."""


def request_upper_bound_usd(input_text: str, max_output_tokens: int, candidate: Candidate) -> Decimal:
    """An upper bound for one request: input tokens bounded by UTF-8 bytes (no route estimator is
    verified yet), the full output cap, and every provider attempt the route allows."""
    prompt_tokens = len(build_summary_prompt(input_text).encode("utf-8"))
    per_attempt = (prompt_tokens * candidate.input_usd_per_million + max_output_tokens * candidate.output_usd_per_million) / _MILLION
    return per_attempt * MAX_ROUTE_ATTEMPTS


@dataclass(frozen=True, slots=True)
class QualificationResult:
    candidate: Candidate
    step1: FactReport
    final: FactReport | None
    calls: int
    request_ids: tuple[str, ...]
    reported_cost_usd: Decimal | None
    receipt: dict[str, Any] | None

    @property
    def passed(self) -> bool:
        return self.final is not None and self.step1.passed and self.final.passed


def run_qualification(
    fixture: Fixture, candidate: Candidate, summarize: SummarizerCall, *, dollar_cap: Decimal, recorded_on: str
) -> QualificationResult:
    turns = fixture.turns
    responses: list[SummarizerResponse] = []
    authorized = Decimal(0)

    def call(input_text: str) -> SummarizerResponse:
        nonlocal authorized
        if len(responses) >= MAX_FIXTURE_CALLS:
            raise CapRefused("the fixture allows two calls per candidate")
        bound = request_upper_bound_usd(input_text, fixture.max_output_tokens, candidate)
        if authorized + bound > dollar_cap:
            raise CapRefused(f"upper bound {authorized + bound} USD exceeds the cap {dollar_cap} USD")
        authorized += bound
        response = summarize(prompt=build_summary_prompt(input_text), max_output_tokens=fixture.max_output_tokens)
        responses.append(response)
        return response

    first = call(maintenance_input(None, [turns[seq] for seq in fixture.step1]))
    step1 = evaluate_summary(first.text, first.finish_status, fixture.step1_facts, markers=fixture.markers, forbidden=fixture.forbidden)
    final = None
    if step1.passed:
        # Merge the step 1 summary with the newer turns, as the runtime's incremental path does.
        second = call(maintenance_input(first.text, [turns[seq] for seq in fixture.step2]))
        final = evaluate_summary(second.text, second.finish_status, fixture.final_facts, markers=fixture.markers, forbidden=fixture.forbidden)
    attempts = [attempt for response in responses for attempt in response.attempts]
    request_ids = tuple(a.gateway_request_id for a in attempts if a.gateway_request_id)
    costs = [a.cost_usd for a in attempts]
    reported = None if any(cost is None for cost in costs) else sum(costs, Decimal(0))  # type: ignore[arg-type]
    result = QualificationResult(candidate, step1, final, len(responses), request_ids, reported, None)
    if not result.passed:
        return result
    receipt = {
        "model_id": candidate.model_id,
        "format": SUMMARY_FORMAT,
        "providers": list(candidate.providers),
        "reasoning": candidate.reasoning,
        "fixture_digest": fixture.digest,
        "prompt_digest": PROMPT_DIGEST,
        "validator": VALIDATOR_VERSION,
        "request_ids": list(request_ids),
        "recorded_on": recorded_on,
        "result": "pass",
    }
    return QualificationResult(candidate, step1, final, len(responses), request_ids, reported, receipt)


# --- The paid envelope ---------------------------------------------------------------------------------


def paid_envelope(snapshot: RegistrySnapshot, fixture: Fixture) -> list[dict[str, Any]]:
    """Per assigned summarizer: what approving its two fixture requests would authorize."""
    issues = validate_registry(snapshot)
    step1_input = maintenance_input(None, [fixture.turns[seq] for seq in fixture.step1])
    # Step 2 carries the step 1 summary, at most the output cap in tokens.
    step2_without_summary = maintenance_input("", [fixture.turns[seq] for seq in fixture.step2])
    envelope = []
    for model_id in ordered_assignments(snapshot, Role.SUMMARIZER):
        entry = snapshot.policy.models[model_id]
        candidate = Candidate(
            model_id=model_id,
            providers=entry.route.providers,
            reasoning=entry.default_reasoning,
            input_usd_per_million=entry.prices.input_usd_per_million,
            output_usd_per_million=entry.prices.output_usd_per_million,
        )
        blockers = sorted(
            issue.code
            for issue in issues
            if issue.model_id == model_id and issue.role in (None, Role.SUMMARIZER) and issue.code != "SUMMARIZER_UNQUALIFIED"
        )
        step1_bound = request_upper_bound_usd(step1_input, fixture.max_output_tokens, candidate)
        step2_bound = request_upper_bound_usd(step2_without_summary, fixture.max_output_tokens, candidate) + (
            fixture.max_output_tokens * candidate.input_usd_per_million * MAX_ROUTE_ATTEMPTS / _MILLION
        )
        envelope.append(
            {
                "model_id": model_id,
                "providers": list(candidate.providers),
                "reasoning": candidate.reasoning,
                "structurally_eligible": not blockers,
                "blockers": blockers,
                "requests": MAX_FIXTURE_CALLS,
                "max_provider_attempts_per_request": MAX_ROUTE_ATTEMPTS,
                "max_output_tokens": fixture.max_output_tokens,
                "input_token_upper_bounds": [
                    len(build_summary_prompt(step1_input).encode("utf-8")),
                    len(build_summary_prompt(step2_without_summary).encode("utf-8")) + fixture.max_output_tokens,
                ],
                "upper_cost_usd": str(step1_bound + step2_bound),
                "fixture_digest": fixture.digest,
                "prompt_digest": PROMPT_DIGEST,
                "validator": VALIDATOR_VERSION,
                "receipt_fields": ["model_id", "format", "providers", "reasoning", "fixture_digest", "prompt_digest", "validator", "request_ids", "recorded_on", "result"],
            }
        )
    return envelope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    env = commands.add_parser("envelope", help="print the paid-call envelope; makes no call")
    env.add_argument("--registry", type=Path)
    env.add_argument("--override", type=Path)
    check = commands.add_parser("check", help="fact-check one saved summary")
    check.add_argument("--summary", type=Path, required=True)
    check.add_argument("--step", choices=("step1", "final"), required=True)
    check.add_argument("--finish-status", default="stop")
    args = parser.parse_args(argv)
    fixture = load_fixture()
    if args.command == "envelope":
        if args.registry is None:
            with resources.as_file(resources.files("optimus_model_policy").joinpath("defaults.yaml")) as packaged:
                snapshot = load_registry(packaged, args.override)
        else:
            snapshot = load_registry(args.registry, args.override)
        print(json.dumps(paid_envelope(snapshot, fixture), indent=2))
        return 0
    facts = fixture.step1_facts if args.step == "step1" else fixture.final_facts
    report = evaluate_summary(args.summary.read_text(encoding="utf-8"), args.finish_status, facts, markers=fixture.markers, forbidden=fixture.forbidden)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
