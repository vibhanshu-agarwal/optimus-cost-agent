"""Summarizer qualification tooling for `calculator-constraints-v1` (Plan 12.2 Task 8).

Design spec 6.5-6.6 and Task 1 contracts 3. Only `run` makes paid calls. This module provides:

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
  the cost reservation.
- `run_live`: the paid qualification of the reviewed `qualification` test profile (Plan 12.2 Stage B;
  Codex Haiku Stage A review, launcher ruling). A client of the Gateway that the operator-started,
  profiled host owns: it never starts a Gateway or contacts a provider itself, and the Gateway's own
  binding check refuses any other snapshot before a provider attempt. No other model client may use
  that Gateway during the run: its route stop is not a concurrent admission barrier.

Usage:
    python tools/evaluate_context_summarizer.py envelope [--registry FILE] [--override FILE]
    python tools/evaluate_context_summarizer.py check --summary FILE --step {step1,final} [--finish-status stop]
    python tools/evaluate_context_summarizer.py run --profile qualification --host-pid PID --gateway-pid PID --out NEW_DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
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
from optimus.acp.local_gateway_secrets import resolve_shared_secret
from optimus.acp.operator_paths import resolve_config_root
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.maintenance import (
    HostMaintenance,
    MaintenanceIdentity,
    MaintenanceReceipt,
    SummarizerCall,
    SummarizerResponse,
    SummarizerRoute,
    gateway_summarizer_factory,
)
from optimus.gateway.client import GatewayClient
from optimus_model_policy import RegistrySnapshot, Role, load_registry, ordered_assignments, validate_registry
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS, disclosure_key
from optimus_model_policy.experimental import EMPIRICAL_ESTIMATOR_METHOD, experimental_route
from optimus_model_policy.registry import SummaryReceipt
from optimus_model_policy.test_profiles import compose_test_profile_snapshot

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "context_engine" / "calculator-constraints-v1.json"
MAX_FIXTURE_CALLS = 2
# The step 1 summary carried into step 2, in UTF-8 bytes: a run control selected by Codex (Haiku Stage
# A review M2), separate from the fixture's output token cap, which does not bound a summary's bytes.
# A longer summary is never truncated: the run stops with step 2 unrun.
CARRIED_SUMMARY_MAX_BYTES = 8192
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
    framing_tokens: int = 0
    """The route estimator's allowance for one message's framing (per-message plus fixed tokens)."""


class CapRefused(Exception):
    """A call whose upper cost bound would pass the authorized dollar cap is never made."""


def _prompt_upper_bound_usd(prompt: str, max_output_tokens: int, candidate: Candidate) -> Decimal:
    prompt_tokens = len(prompt.encode("utf-8")) + candidate.framing_tokens
    per_attempt = (prompt_tokens * candidate.input_usd_per_million + max_output_tokens * candidate.output_usd_per_million) / _MILLION
    return per_attempt * MAX_ROUTE_ATTEMPTS


def request_upper_bound_usd(input_text: str, max_output_tokens: int, candidate: Candidate) -> Decimal:
    """The reservation for one request: one token per UTF-8 byte of the complete summary prompt plus the
    route's framing allowance, the full output cap, and every provider attempt the route allows. It
    assumes the output cap also bounds any reasoning tokens. For an empirical route estimator this is
    an engineering estimate, not a proven bound: the Gateway checks reported usage on every call."""
    return _prompt_upper_bound_usd(build_summary_prompt(input_text), max_output_tokens, candidate)


def _framing_tokens(snapshot: RegistrySnapshot, estimator_name: str) -> tuple[int, str]:
    """The estimator's one-message framing allowance and how the input estimate should be described."""
    estimator = snapshot.policy.estimators.get(estimator_name)
    if estimator is None:
        return 0, "utf8-bytes; no route estimator"
    framing = estimator.per_message_tokens + estimator.fixed_tokens
    if estimator.method == EMPIRICAL_ESTIMATOR_METHOD:
        return framing, f"empirical: one token per UTF-8 byte plus {framing} framing tokens; not a proven bound"
    return framing, f"one token per UTF-8 byte plus {framing} framing tokens"


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
    unrun: str | None = None
    """Why step 2 was not run although step 1 passed, if so."""

    @property
    def passed(self) -> bool:
        return self.final is not None and self.step1.passed and self.final.passed


def run_qualification(
    fixture: Fixture,
    candidate: Candidate,
    summarize: SummarizerCall,
    *,
    dollar_cap: Decimal,
    recorded_on: str,
    registry_hash: str | None = None,
    on_receipt: Callable[[MaintenanceReceipt], None] | None = None,
) -> QualificationResult:
    """`on_receipt` receives each attempt's receipt as it is recorded, so a caller keeps them even if
    the run then raises."""
    turns = fixture.turns
    calls = 0
    authorized = Decimal(0)
    receipts: list[MaintenanceReceipt] = []

    def record(receipt: MaintenanceReceipt) -> None:
        receipts.append(receipt)
        if on_receipt is not None:
            on_receipt(receipt)

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
            registry_hash=registry_hash,
        ),
        record_receipt=record,
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
    final, unrun = None, None
    if step1.passed:
        carried = len((first.summary_text or "").encode("utf-8"))
        if carried > CARRIED_SUMMARY_MAX_BYTES:
            unrun = f"step 2 UNRUN: the step 1 summary is {carried} UTF-8 bytes, over the {CARRIED_SUMMARY_MAX_BYTES}-byte carry ceiling"
        else:
            # Merge the step 1 summary with the newer turns, as the runtime's incremental path does.
            second = step(maintenance_input(first.summary_text, [turns[seq] for seq in fixture.step2]), fixture.step1 + fixture.step2)
            final = evaluate_summary(second.summary_text, second.finish_status, fixture.final_facts, fixture.rules)
    request_ids = tuple(r.gateway_request_id for r in receipts if r.gateway_request_id)
    costs = [r.cost_usd for r in receipts]
    reported = None if any(cost is None for cost in costs) else sum(costs, Decimal(0))  # type: ignore[arg-type]
    result = QualificationResult(candidate, step1, final, calls, request_ids, reported, None, tuple(receipts), unrun)
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
    return QualificationResult(candidate, step1, final, calls, request_ids, reported, receipt, tuple(receipts), unrun)


# --- The paid envelope ---------------------------------------------------------------------------------


def _candidate(snapshot: RegistrySnapshot, model_id: str) -> Candidate:
    entry = snapshot.policy.models[model_id]
    return Candidate(
        model_id=model_id,
        providers=entry.route.providers,
        quantizations=entry.route.quantizations,
        reasoning=entry.default_reasoning,
        input_usd_per_million=entry.prices.input_usd_per_million,
        output_usd_per_million=entry.prices.output_usd_per_million,
        framing_tokens=_framing_tokens(snapshot, entry.route.estimator)[0],
    )


RESERVATION_BASIS = (
    "empirical engineering reservation, not a universal upper bound: each request at its input estimate "
    "(step 2 carrying a summary at the byte ceiling), the full output cap and every provider attempt; "
    "a provider charge after a failed check cannot be undone"
)


def paid_envelope(snapshot: RegistrySnapshot, fixture: Fixture) -> list[dict[str, Any]]:
    """Per assigned summarizer: what approving its two fixture requests would authorize."""
    issues = validate_registry(snapshot)
    step1_input = maintenance_input(None, [fixture.turns[seq] for seq in fixture.step1])
    # Step 2 carries the step 1 summary, at most the carry ceiling in bytes (a longer one is not sent).
    step2_input = maintenance_input("a" * CARRIED_SUMMARY_MAX_BYTES, [fixture.turns[seq] for seq in fixture.step2])
    envelope = []
    for model_id in ordered_assignments(snapshot, Role.SUMMARIZER):
        candidate = _candidate(snapshot, model_id)
        framing, estimate = _framing_tokens(snapshot, snapshot.policy.models[model_id].route.estimator)
        blockers = sorted(
            issue.code
            for issue in issues
            if issue.model_id == model_id and issue.role in (None, Role.SUMMARIZER) and issue.code != "SUMMARIZER_UNQUALIFIED"
        )
        step1_bound = request_upper_bound_usd(step1_input, fixture.max_output_tokens, candidate)
        step2_bound = request_upper_bound_usd(step2_input, fixture.max_output_tokens, candidate)
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
                "carried_summary_max_bytes": CARRIED_SUMMARY_MAX_BYTES,
                "input_estimate": estimate,
                "reservation_basis": RESERVATION_BASIS,
                "input_token_reservations": [
                    len(build_summary_prompt(step1_input).encode("utf-8")) + framing,
                    len(build_summary_prompt(step2_input).encode("utf-8")) + framing,
                ],
                "input_usd_per_million": str(candidate.input_usd_per_million),
                "output_usd_per_million": str(candidate.output_usd_per_million),
                "reserved_cost_usd": str(step1_bound + step2_bound),
                "fixture_digest": fixture.digest,
                "prompt_digest": PROMPT_DIGEST,
                "validator": VALIDATOR_VERSION,
                "receipt_fields": list(SummaryReceipt.model_fields),
            }
        )
    return envelope


# --- The paid run --------------------------------------------------------------------------------------

LIVE_PROFILE = "qualification"
LIVE_DOLLAR_CAP = Decimal("0.05")  # the operator's released ceiling for this qualification
LIVE_WALL_CLOCK_SECONDS = 30 * 60  # the released 30-minute limit
LIVE_REQUEST_TIMEOUT_SECONDS = 300.0  # a request starts only if it can time out inside the limit
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _gateway_settings(environ: Mapping[str, str]) -> OptimusGatewaySettings:
    """The host's own Gateway credentials: OPTIMUS_API_KEY, or else the shared secret the launch
    resolves (environment, `.env.gateway` or keyring), as the host does."""
    env = dict(environ)
    if not env.get("OPTIMUS_API_KEY", "").strip():
        secret = resolve_shared_secret(env, config_root=resolve_config_root(workspace_root=_REPO_ROOT, environ=env))
        if secret:
            env["OPTIMUS_API_KEY"] = secret
    return OptimusGatewaySettings.from_env(env)


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, default=str)
        handle.write("\n")


def _append_json(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _receipt_record(receipt: MaintenanceReceipt) -> dict[str, Any]:
    usage = receipt.gateway_usage
    return {
        "attempt_id": receipt.attempt_id,
        "gateway_request_id": receipt.gateway_request_id,
        "outcome": receipt.outcome,
        "cost_usd": None if receipt.cost_usd is None else str(receipt.cost_usd),
        "finish_status": receipt.finish_status,
        "covered_turn_ids": list(receipt.covered_turn_ids),
        "recorded_at": receipt.recorded_at.isoformat(),
        "provider_request_id": receipt.provider_request_id,
        "http_status": receipt.http_status,
        "provider": receipt.provider,
        "resolved_provider": receipt.resolved_provider,
        "resolved_model": receipt.resolved_model,
        "usage": None if usage is None else usage.model_dump(mode="json"),
    }


def _evidence_sanitizer(*known_secrets: str) -> ConversationSanitizer:
    """The runtime's evidence-redaction sanitizer (the one maintenance summaries pass through), for
    every free text the run persists."""
    return ConversationSanitizer(ConversationSanitizerInputs(known_secrets=known_secrets, path_aliases=()))


def _error_text(exc: BaseException, sanitizer: ConversationSanitizer) -> str:
    text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    return sanitizer.sanitize(text)


def _refuse(reason: str) -> int:
    print(f"evaluate_context_summarizer run: REFUSED before any request: {reason}", file=sys.stderr)
    return 2


def run_live(
    *,
    out: Path,
    host_pid: int,
    gateway_pid: int,
    environ: Mapping[str, str],
    recorded_on: str,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """The paid two-request qualification of the reviewed profile through the operator-started host's
    Gateway. Exit 0: both steps passed and a receipt candidate was written; 1: the run failed or
    stopped (its evidence is kept); 2: refused before any request.

    `out` is a new directory: `run.json` (identity, written before the first dispatch),
    `attempts.jsonl` and `responses.jsonl` (appended as they arrive), `outcome.json` (always, last) and
    `receipt-candidate.json` (a pass only; it qualifies nothing until reviewed)."""
    if out.exists():
        return _refuse(f"{out} exists; every run gets a new directory")
    fixture = load_fixture()
    snapshot = compose_test_profile_snapshot(LIVE_PROFILE)
    envelope = paid_envelope(snapshot, fixture)
    if len(envelope) != 1:
        return _refuse("the profile must assign exactly one summarizer")
    [row] = envelope
    model_id = row["model_id"]
    route = experimental_route(snapshot, model_id)
    if route is None:
        return _refuse("the composed profile is not the reviewed experimental route")
    if not row["structurally_eligible"]:
        return _refuse(f"the summarizer is not structurally eligible: {row['blockers']}")
    if Decimal(row["reserved_cost_usd"]) > LIVE_DOLLAR_CAP:
        return _refuse(f"the reservation {row['reserved_cost_usd']} USD exceeds the {LIVE_DOLLAR_CAP} USD cap")
    try:
        settings = _gateway_settings(environ)
    except ValueError as exc:
        return _refuse(f"no usable Gateway credentials ({_error_text(exc, _evidence_sanitizer())})")
    shared_secret = settings.optimus_api_key.get_secret_value()
    evidence = _evidence_sanitizer(shared_secret)

    candidate = _candidate(snapshot, model_id)
    run_id = uuid.uuid4().hex
    identity = MaintenanceIdentity(
        session_id=f"qualification:{fixture.name}:{run_id}",
        turn_seq=0,
        model_id=model_id,
        role=Role.SUMMARIZER.value,
        route=candidate.providers,
        reasoning=candidate.reasoning,
        quantizations=candidate.quantizations,
        strategy="compaction",
        revision_digest=fixture.digest,
        registry_hash=snapshot.effective_hash,
    )
    bind_turn = gateway_summarizer_factory(
        gateway_client=GatewayClient(settings=settings, timeout_seconds=LIVE_REQUEST_TIMEOUT_SECONDS),
        route=SummarizerRoute(model_id, identity.role, identity.route, identity.reasoning, identity.quantizations),
        snapshot=snapshot,
        disclosure_key=disclosure_key(shared_secret),
    )
    summarize = bind_turn(identity, lambda _notice: False)  # a route needing a notice sends nothing

    out.mkdir(parents=True)
    deadline = clock() + LIVE_WALL_CLOCK_SECONDS
    sent = {"dispatched": 0, "returned": 0}

    def call(*, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        if deadline - clock() < LIVE_REQUEST_TIMEOUT_SECONDS:
            raise CapRefused("the 30-minute wall clock leaves too little time for another request")
        sent["dispatched"] += 1
        response = summarize(prompt=prompt, max_output_tokens=max_output_tokens)
        # The response and its attempts' billing reach disk before the runtime records receipts; until
        # then the request counts as in flight, at unknown cost.
        _append_json(
            out / "responses.jsonl",
            {
                "request": sent["dispatched"],
                "text": None if response.text is None else evidence.sanitize(response.text),
                "finish_status": response.finish_status,
                "attempts": [
                    {
                        "attempt_id": attempt.attempt_id,
                        "gateway_request_id": attempt.gateway_request_id,
                        "outcome": attempt.outcome,
                        "cost_usd": None if attempt.cost_usd is None else str(attempt.cost_usd),
                    }
                    for attempt in response.attempts
                ],
            },
        )
        sent["returned"] += 1
        return response

    _write_json(
        out / "run.json",
        {
            "run_id": run_id,
            "started_at": datetime.now(UTC).isoformat(),
            "profile": LIVE_PROFILE,
            "registry_hash": snapshot.effective_hash,
            "experimental_route": {"provider_family": route.provider_family, "provider_name": route.provider_name},
            "model_id": model_id,
            "providers": list(candidate.providers),
            "quantizations": list(candidate.quantizations),
            "reasoning": candidate.reasoning,
            "envelope": row,
            "dollar_cap_usd": str(LIVE_DOLLAR_CAP),
            "wall_clock_seconds": LIVE_WALL_CLOCK_SECONDS,
            "request_timeout_seconds": LIVE_REQUEST_TIMEOUT_SECONDS,
            "max_requests": MAX_FIXTURE_CALLS,
            "max_provider_attempts": MAX_FIXTURE_CALLS * MAX_ROUTE_ATTEMPTS,
            "gateway_url": settings.gateway_url,
            "host_pid": host_pid,
            "gateway_pid": gateway_pid,
            "process_identity": "operator-stated; the Gateway's binding check refuses any other approved snapshot",
            "exclusive_use": "no other model client may use this Gateway during the run",
            "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    )
    try:
        result = run_qualification(
            fixture,
            candidate,
            call,
            dollar_cap=LIVE_DOLLAR_CAP,
            recorded_on=recorded_on,
            registry_hash=snapshot.effective_hash,
            on_receipt=lambda receipt: _append_json(out / "attempts.jsonl", _receipt_record(receipt)),
        )
    except BaseException as exc:
        # Every attempt already recorded stays on disk; an interrupted request's cost is unknown.
        _write_json(
            out / "outcome.json",
            {
                "status": "stopped",
                "error": _error_text(exc, evidence),
                "requests_dispatched": sent["dispatched"],
                "in_flight": sent["dispatched"] > sent["returned"],
                "receipt": None,
            },
        )
        if isinstance(exc, Exception):
            return 1
        raise

    passed = result.passed and result.reported_cost_usd is not None and len(result.attempts) <= MAX_FIXTURE_CALLS * MAX_ROUTE_ATTEMPTS
    if passed:
        usages = [r.gateway_usage for r in result.attempts if r.outcome == "completed" and r.gateway_usage is not None]
        _write_json(
            out / "receipt-candidate.json",
            {
                "receipt": result.receipt,
                "observed": {
                    "resolved_providers": [usage.resolved_provider for usage in usages],
                    "resolved_models": [usage.resolved_model for usage in usages],
                    "reasoning_tokens": [usage.reasoning_tokens for usage in usages],
                },
                "note": "a candidate for review: it qualifies nothing and enables no attached engine by itself",
            },
        )
    _write_json(
        out / "outcome.json",
        {
            "status": "pass" if passed else "fail",
            "step1": result.step1.to_dict(),
            "final": None if result.final is None else result.final.to_dict(),
            "unrun": result.unrun,
            "calls": result.calls,
            "provider_attempts": len(result.attempts),
            "reported_cost_usd": None if result.reported_cost_usd is None else str(result.reported_cost_usd),
            "request_ids": list(result.request_ids),
        },
    )
    return 0 if passed else 1


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
    live = commands.add_parser("run", help="PAID: qualify the reviewed profile through the operator-started host's Gateway")
    live.add_argument("--profile", choices=(LIVE_PROFILE,), required=True)
    live.add_argument("--host-pid", type=int, required=True)
    live.add_argument("--gateway-pid", type=int, required=True)
    live.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        recorded_on = datetime.now(UTC).date().isoformat()
        return run_live(out=args.out, host_pid=args.host_pid, gateway_pid=args.gateway_pid, environ=os.environ, recorded_on=recorded_on)
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
