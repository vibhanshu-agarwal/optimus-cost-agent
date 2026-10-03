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

from context_engine import MaintenanceRequest, OrdinaryTurn
from context_engine.engine import maintenance_input
from context_engine.summary import (
    PROMPT_DIGEST,
    PROMPT_VERSION,
    SUMMARY_FORMAT,
    VALIDATOR_VERSION,
    SummaryFormatError,
    build_summary_prompt,
    parse_summary,
)
from optimus.acp.conversation import ConversationSanitizer, ConversationSanitizerInputs
from optimus.context.maintenance import HostMaintenance, MaintenanceIdentity, MaintenanceReceipt, SummarizerCall, SummarizerResponse
from optimus_model_policy import RegistrySnapshot, Role, load_registry, ordered_assignments, validate_registry
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS
from optimus_model_policy.registry import SummaryReceipt

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "context_engine" / "calculator-constraints-v1.json"
MAX_FIXTURE_CALLS = 2
_MILLION = Decimal(1_000_000)
# Sentences end at . ! or ? followed by whitespace, or at a newline. A decimal point is not an end;
# a semicolon joins clauses that belong together ("ROUND_HALF_UP; now ROUND_HALF_EVEN"), so the
# supersession check reads whole sentences. Facts and claims are read per clause: a sentence split
# again at its semicolons, so one clause's negation never reaches another clause's claim.
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n")
_CLAUSE = ";"
# A negation carries over a coordinated claim: "not approved or granted".
_COORDINATED = re.compile(r"\s*,?\s*(?:or|nor)\s*")


@dataclass(frozen=True, slots=True)
class FactRules:
    """The fixture's lexical rules, shared by both steps. They are fixture data, so the fixture
    digest that every receipt binds covers them."""

    negation: str  # governs the next fact or claim match (anchored at it with `$`)
    reported: str  # reported speech governs a forbidden claim: "told the agent to record every plan as approved"
    markers: tuple[str, ...]  # supersession markers no negation reverses: "previously", "no longer", "anymore"
    verbs: tuple[str, ...]  # supersession verbs an adjacent negation reverses: "was not superseded"
    verb_negation: str
    forbidden: tuple[Mapping[str, str], ...]


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
    rules: FactRules


def fixture_digest(raw: Mapping[str, Any]) -> str:
    """The fixture's identity: its canonical JSON, independent of key order, whitespace and line
    endings, so a receipt never depends on how a checkout stores the file."""
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_fixture(path: Path = FIXTURE_PATH) -> Fixture:
    raw = json.loads(path.read_bytes().decode("utf-8"))
    try:
        turns = {t["seq"]: OrdinaryTurn(t["seq"], t["user_prompt"], t["plan_text"], t["completion_text"]) for t in raw["turns"]}
        ev = raw["evaluation"]
        step1, step2, tail = tuple(ev["step1_turns"]), tuple(ev["step2_turns"]), tuple(ev["exact_tail_turns"])
        constraints_turn, correction_turn, max_output_tokens = ev["constraints_turn"], ev["correction_turn"], int(ev["max_output_tokens"])
        rules = FactRules(
            negation=raw["negation"],
            reported=raw["reported_speech"],
            markers=tuple(raw["supersession_markers"]),
            verbs=tuple(raw["supersession_verbs"]),
            verb_negation=raw["verb_negation"],
            forbidden=tuple(raw["forbidden"]),
        )
        step1_facts, final_facts, name = tuple(raw["step1_facts"]), tuple(raw["final_facts"]), raw["fixture"]
    except KeyError as exc:
        raise ValueError(f"the fixture lacks {exc}") from exc
    ordered = tuple(sorted(turns))
    if step1 + step2 + tail != ordered:
        raise ValueError("the fixture's steps and tail must partition its turns in order")
    if constraints_turn not in step1 or correction_turn not in step2:
        raise ValueError("the early constraints must lie in step 1 and the correction in step 2, both summarized")
    return Fixture(
        name=name,
        digest=fixture_digest(raw),
        turns=turns,
        step1=step1,
        step2=step2,
        tail=tail,
        max_output_tokens=max_output_tokens,
        step1_facts=step1_facts,
        final_facts=final_facts,
        rules=rules,
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


def _asserted(pattern: str, span: str, governors: Sequence[str]) -> list[str]:
    """The matches of `pattern` in `span` that no governor governs.

    A governor (a negation, or reported speech) governs only the next match after it, and only when
    its pattern, anchored at the match, finds it close enough, with no comma, clause end or
    contrastive conjunction between. So "was not approved" is not an approval claim, while "not
    reviewed but approved" and "...not approved and every plan was approved" are (Codex CP2 R2). A
    governed match carries over a coordinated next match: "not approved or granted"."""
    found: list[str] = []
    previous, governed = 0, False
    for match in re.finditer(pattern, span):
        segment = span[previous : match.start()]
        governed = (governed and _COORDINATED.fullmatch(segment) is not None) or any(re.search(governor, segment) for governor in governors)
        if not governed:
            found.append(match.group(0))
        previous = match.end()
    return found


def evaluate_summary(text: str | None, finish_status: str | None, facts: Sequence[Mapping[str, Any]], rules: FactRules) -> FactReport:
    checks = [FactCheck("finished", finish_status == "stop", f"finish status {finish_status!r}")]
    try:
        parse_summary(text or "")
    except SummaryFormatError as exc:
        return FactReport(tuple([*checks, FactCheck("format", False, str(exc))]))
    checks.append(FactCheck("format", True, SUMMARY_FORMAT))
    lower = (text or "").lower()
    # Sentences, so a marker elsewhere on a line cannot excuse a stale rule; clauses, so a negation
    # in one clause cannot reach another clause's claim.
    sentences = [part for part in _SENTENCE.split(lower) if part.strip()]
    clauses = [part for sentence in sentences for part in sentence.split(_CLAUSE) if part.strip()]
    negation = (rules.negation,)
    for fact in facts:
        if "affirm" in fact:
            # Polarity: a fact is stated only by an affirmative match no negation governs, and any
            # ungoverned contradiction fails it ("do not use Decimal", "eval ... not forbidden",
            # "negative inputs are unsupported"). The patterns state the constraint itself, so a
            # bare word ("a decimal currency calculator", "evaluate") never counts. An identifier
            # fact ("governed": false) is stated even under a protective negation ("never rename
            # calculate(a, op, b)"); its withdrawals are deny patterns.
            governors = negation if fact.get("governed", True) else ()
            stated = [found for clause in clauses for found in _asserted(fact["affirm"], clause, governors)]
            denied = [found for clause in clauses for found in _asserted(fact["deny"], clause, negation)] if "deny" in fact else []
            if denied:
                detail = f"contradicted: {denied[0]!r}"
            else:
                detail = f"stated: {stated[0]!r}" if stated else "not stated"
            checks.append(FactCheck(fact["id"], bool(stated) and not denied, detail))
        elif "superseded" in fact:
            rule = fact["superseded"]
            mentions = [sentence for sentence in sentences if rule in sentence]
            # Markers ("previously", "anymore") are never reversed; a verb is reversed only by a
            # negation right before it ("was not superseded"), not by one elsewhere ("is not used
            # (replaced in turn 7)").
            stale = [
                sentence
                for sentence in mentions
                if not any(_asserted(marker, sentence, ()) for marker in rules.markers)
                and not any(_asserted(verb, sentence, (rules.verb_negation,)) for verb in rules.verbs)
            ]
            passed = bool(mentions) and not stale
            detail = "stated as superseded" if passed else ("not mentioned" if not mentions else f"stated as current: {stale[0]!r}")
            checks.append(FactCheck(fact["id"], passed, detail))
        else:
            raise ValueError(f"unknown fact kind: {fact}")
    for rule in rules.forbidden:
        # A claim counts unless a negation or reported speech governs that very claim: "was not
        # approved", "no approval was granted" and "told the agent to record every plan as
        # approved" are not approvals.
        hits = [clause for clause in clauses if _asserted(rule["pattern"], clause, (rules.negation, rules.reported))]
        checks.append(FactCheck(rule["id"], not hits, f"found in {hits[0]!r}" if hits else "absent"))
    return FactReport(tuple(checks))


# --- The two-step run ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Candidate:
    model_id: str
    providers: tuple[str, ...]
    quantizations: tuple[str | None, ...]
    reasoning: str | None
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal


class CapRefused(Exception):
    """A call whose upper cost bound would pass the authorized dollar cap is never made."""


def _prompt_upper_bound_usd(prompt: str, max_output_tokens: int, candidate: Candidate) -> Decimal:
    prompt_tokens = len(prompt.encode("utf-8"))
    per_attempt = (prompt_tokens * candidate.input_usd_per_million + max_output_tokens * candidate.output_usd_per_million) / _MILLION
    return per_attempt * MAX_ROUTE_ATTEMPTS


def request_upper_bound_usd(input_text: str, max_output_tokens: int, candidate: Candidate) -> Decimal:
    """An upper bound for one request: input tokens bounded by UTF-8 bytes (no route estimator is
    verified yet), the full output cap, and every provider attempt the route allows. It assumes the
    output cap also bounds any reasoning tokens; CP4 confirms that per route."""
    return _prompt_upper_bound_usd(build_summary_prompt(input_text), max_output_tokens, candidate)


@dataclass(frozen=True, slots=True)
class QualificationResult:
    candidate: Candidate
    step1: FactReport
    final: FactReport | None
    calls: int
    request_ids: tuple[str, ...]
    reported_cost_usd: Decimal | None
    receipt: dict[str, Any] | None
    # One receipt per provider attempt, from the runtime's callback: the evidence a paid run keeps.
    attempts: tuple[MaintenanceReceipt, ...] = ()

    @property
    def passed(self) -> bool:
        return self.final is not None and self.step1.passed and self.final.passed


def run_qualification(
    fixture: Fixture, candidate: Candidate, summarize: SummarizerCall, *, dollar_cap: Decimal, recorded_on: str
) -> QualificationResult:
    turns = fixture.turns
    calls = 0
    authorized = Decimal(0)
    receipts: list[MaintenanceReceipt] = []

    def capped(*, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        """The candidate call, made only within the call and dollar caps."""
        nonlocal authorized, calls
        if calls >= MAX_FIXTURE_CALLS:
            raise CapRefused("the fixture allows two calls per candidate")
        bound = _prompt_upper_bound_usd(prompt, max_output_tokens, candidate)
        if authorized + bound > dollar_cap:
            raise CapRefused(f"upper bound {authorized + bound} USD exceeds the cap {dollar_cap} USD")
        authorized += bound
        calls += 1
        return summarize(prompt=prompt, max_output_tokens=max_output_tokens)

    # The runtime's own callback: completed-attempt rule, re-sanitizing and a receipt per attempt
    # (Fable CP2 review). The fixture is synthetic, so there are no secrets to supply.
    host = HostMaintenance(
        call=capped,
        sanitizer=ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=())),
        identity=MaintenanceIdentity(
            session_id=f"qualification:{fixture.name}",
            turn_seq=0,
            model_id=candidate.model_id,
            role=Role.SUMMARIZER.value,
            route=candidate.providers,
            reasoning=candidate.reasoning,
            quantizations=candidate.quantizations,
            strategy="compaction",
            revision_digest=fixture.digest,
        ),
        record_receipt=receipts.append,
        cancelled=lambda: False,
    )

    def step(input_text: str, covered: tuple[int, ...]):
        return host(
            MaintenanceRequest(
                input_text=input_text,
                covered_turn_ids=covered,
                max_output_tokens=fixture.max_output_tokens,
                prompt_version=PROMPT_VERSION,
                format_version=SUMMARY_FORMAT,
            )
        )

    first = step(maintenance_input(None, [turns[seq] for seq in fixture.step1]), fixture.step1)
    step1 = evaluate_summary(first.summary_text, first.finish_status, fixture.step1_facts, fixture.rules)
    final = None
    if step1.passed:
        # Merge the step 1 summary with the newer turns, as the runtime's incremental path does.
        second = step(maintenance_input(first.summary_text, [turns[seq] for seq in fixture.step2]), fixture.step1 + fixture.step2)
        final = evaluate_summary(second.summary_text, second.finish_status, fixture.final_facts, fixture.rules)
    request_ids = tuple(r.gateway_request_id for r in receipts if r.gateway_request_id)
    costs = [r.cost_usd for r in receipts]
    reported = None if any(cost is None for cost in costs) else sum(costs, Decimal(0))  # type: ignore[arg-type]
    result = QualificationResult(candidate, step1, final, calls, request_ids, reported, None, tuple(receipts))
    if not result.passed:
        return result
    receipt = {
        "model_id": candidate.model_id,
        "format": SUMMARY_FORMAT,
        "providers": list(candidate.providers),
        "quantizations": list(candidate.quantizations),
        "reasoning": candidate.reasoning,
        "fixture_digest": fixture.digest,
        "prompt_digest": PROMPT_DIGEST,
        "validator": VALIDATOR_VERSION,
        "request_ids": list(request_ids),
        "recorded_on": recorded_on,
        "result": "pass",
    }
    return QualificationResult(candidate, step1, final, calls, request_ids, reported, receipt, tuple(receipts))


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
            quantizations=entry.route.quantizations,
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
                "quantizations": list(candidate.quantizations),
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
                "receipt_fields": list(SummaryReceipt.model_fields),
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
    report = evaluate_summary(args.summary.read_text(encoding="utf-8"), args.finish_status, facts, fixture.rules)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
