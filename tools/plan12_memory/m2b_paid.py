"""Plan 12.14 paid Q runner (Task 4, under its own release; zero-paid tests in Task 1). Design: optimus-handoff/p1214-task1/q-runner-design.md,
amended by Codex CP1 round 122 (findings 3-4).

One process drives the real AgentRunner in Chat mode for each case and arm, on the real attached-turn packer, the real memory turn over a
real index of the case's snapshot, the real route binder on the approved composition, and a Guard around the Gateway client. The arms differ
only in configuration:

- N: no memory, so the runner takes today's context (engine absent) and the non-indexed builder.
- B (= U while the baseline is retained): the memory turn with the pack budget forced to the legacy policy.
- F: the memory turn with the route's own budget (the staged D3 target), exactly production's.

Two enumerated deltas from shipping production: index tools are withdrawn (MAX_INDEX_ROUNDS = 0, so the turn is one zero-tool request,
keeping the runner's own limit observation: operator 2026-11-25, "Keep the line"), and the output cap is Q's (2,048), bound through
RoutePolicy.

The Guard is the only client the runner holds. Before it forwards a request it requires the row's call allowance, the released model, a
binding to the approved registry hash and output cap (the hash fixes that model's route), an input within the cap, and the ceiling's
reservation; otherwise it records why and raises before anything is sent (Codex CP1 attempts 2-3, finding 3). A row sends at most once: the
intra-row multi-send path is deleted (Fable 5.2, CP1). Physical attempts are counted from the Gateway's own route attempts. Each Gateway
attempt is matched to the host receipts of exactly the host request it served, recorded at dispatch, by attempt ordinal, Gateway request id
and disposition. Only a clean one-to-one match carries a known amount; a duplicate, unmatched, foreign or unattributed record, or a send
with no Gateway attempt, is kept, leaves the amount unknown and makes the row incomplete, which stops the run, with the Gateway ledger the
authority (finding 4; the money-only path is deleted). Answers go to a separate sink kept
outside the repository; the record keeps ids, digests and counts, never source or request bodies or credentials.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from unittest import mock

from optimus.agent import runner as runner_module
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.agent.workspace_context import WorkspaceReferenceDiagnostic, WorkspaceReferenceStatus, blocking_from_diagnostics
from optimus.context.context_budget import BudgetPolicy, legacy_budget
from optimus.runtime.modes import ExecutionMode
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS

ARM_ORDERS: Final = (("N", "B", "U", "F"), ("B", "U", "F", "N"), ("U", "F", "N", "B"), ("F", "N", "B", "U"))
CATEGORIES: Final = ("ranking", "budget", "outline")
OUTPUT_CAP: Final = 2_048
INPUT_CAP: Final = 65_536
PHYSICAL: Final = frozenset({"completed", "uncertain", "rejected"})  # left the Gateway for a provider; not_sent did not
UNCHECKED: Final = object()  # no dry-pass prefix boundary to hold the send to


class CapRefused(Exception):
    """The next request cannot be reserved inside the release."""


class GuardRefused(Exception):
    """The Guard refused to forward a request; nothing was sent."""


@dataclass
class Ceiling:
    """The release's attempt and USD bounds, reserved before each send and settled from the Gateway's attempts."""

    attempts_max: int
    usd_max: Decimal
    per_attempt_usd: Decimal
    attempts_used: int = 0
    usd_settled: Decimal = Decimal(0)
    unknown_attempts: int = 0  # attempts whose charge is unknown, priced at the worst case

    def reserve(self) -> None:
        """Reserve the next send's MAX_ROUTE_ATTEMPTS. A row sends at most once and settles before the next row, so nothing is pending."""
        bound = self.usd_settled + self.per_attempt_usd * (self.unknown_attempts + MAX_ROUTE_ATTEMPTS)
        if self.attempts_used + MAX_ROUTE_ATTEMPTS > self.attempts_max or bound > self.usd_max:
            raise CapRefused(f"cannot reserve {MAX_ROUTE_ATTEMPTS} attempts: {self.attempts_used} used of {self.attempts_max}, worst case USD {bound} of {self.usd_max}")

    def settle(self, attempts: Sequence[Mapping[str, Any]]) -> None:
        """Attempts from Gateway evidence count against the attempt bound; an unknown amount is priced at the worst case. There is no
        money-only path (Fable 5.2, CP1): a receipt on no attempt is a reconciliation problem, which stops the run."""
        self.attempts_used += len(attempts)
        for attempt in attempts:
            if attempt.get("cost_usd") is None:
                self.unknown_attempts += 1
            else:
                self.usd_settled += Decimal(attempt["cost_usd"])


@dataclass(frozen=True)
class Tariff:
    """One dated uncached tariff (evaluation-contract task1_freezes.tariff): cached input repriced at ordinary input, reasoning as output."""

    id: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal

    def reprice(self, usage: Any) -> str | None:
        tokens = (getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
        if usage is None or None in tokens:
            return None
        return str((Decimal(tokens[0]) * self.input_usd_per_million + Decimal(tokens[1]) * self.output_usd_per_million) / Decimal(1_000_000))


D3_TARIFF: Final = Tariff("d3-haiku-5.5-uncached-2026-09-30", Decimal("0.50"), Decimal("2.50"))


@dataclass(frozen=True)
class Approved:
    """What every send must be bound to: the released model, the approved effective hash and Q's caps, with the route's own request estimator."""

    registry_hash: str
    estimate_request: Callable[[str], int]
    model_id: str
    output_cap: int = OUTPUT_CAP
    input_cap: int = INPUT_CAP


def _sha(text: str) -> str:
    return "hex:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Guard:
    """The Gateway client the runner holds for one row. It refuses before forwarding unless every pre-dispatch condition holds."""

    inner: Any
    approved: Approved
    ceiling: Ceiling
    allowance: int
    receipts: list[Any] = field(default_factory=list)  # the row's host receipt sink, as the runner reports them
    run_id: str | None = None  # the run whose host request identities the sends record
    sent: list[dict[str, Any]] = field(default_factory=list)
    refusal: str | None = None
    receipts_at_refusal: int | None = None  # receipts after this index are the host's own records of a request never forwarded
    expected_input_sha256: str | None = None  # the row's input from the launcher's dry preparation pass; anything else is refused (gate item 14)
    write_input: Callable[[str, str], None] | None = None  # (input_sha256, text) to the sink outside the repository, before forwarding (item 15)
    expected_cache_prefix_chars: Any = UNCHECKED  # the dry pass's cached-prefix boundary: the same text split elsewhere is refused (Codex round 124 B2)

    def __post_init__(self) -> None:
        if self.allowance not in (0, 1):  # Fable 5.2, CP1: the intra-row multi-send path is deleted
            raise ValueError(f"the frozen Q schedule allows at most one send per row, not {self.allowance}")

    def _refused(self, reason: str) -> None:
        self.refusal = reason
        self.receipts_at_refusal = len(self.receipts)

    def _refuse(self, reason: str) -> None:
        self._refused(reason)
        raise GuardRefused(reason)

    def create_response(self, **kwargs: Any) -> Any:
        text = kwargs.get("input_text", "")
        binding = kwargs.get("route_binding")
        if len(self.sent) >= self.allowance:
            self._refuse(f"row allowance of {self.allowance} request(s) reached")
        if kwargs.get("model") != self.approved.model_id:
            self._refuse("the requested model is not the released one")
        if binding is None:
            self._refuse("an unbound request")
        if binding.registry_hash != self.approved.registry_hash or binding.output_cap != self.approved.output_cap:
            self._refuse("the binding is not the approved composition and output cap")
        if self.expected_input_sha256 is not None and _sha(text) != self.expected_input_sha256:
            self._refuse("the input is not the one the dry preparation pass prepared")
        if self.expected_cache_prefix_chars is not UNCHECKED and binding.cache_prefix_chars != self.expected_cache_prefix_chars:
            self._refuse("the cached prefix is not the one the dry preparation pass bound")
        tokens = self.approved.estimate_request(text)
        if tokens > self.approved.input_cap:
            self._refuse(f"input of {tokens} estimated tokens over the cap of {self.approved.input_cap}")
        try:
            self.ceiling.reserve()
        except CapRefused as refused:
            self._refused(f"reservation refused: {refused}")
            raise
        if self.write_input is not None:  # the support audit reads what the model received; kept before the send, never in `sent`
            self.write_input(_sha(text), text)
        prefix_chars = binding.cache_prefix_chars
        dispatch = len(self.sent) + 1
        # The host request identity the runner gives this send's receipts: the Q turn is one Chat request, so turn 1, wire attempt = dispatch
        # (AgentRunner._report_receipts; Codex CP1 attempt 4 finding 4).
        receipt_base = None if self.run_id is None else f"{self.run_id}:answer:1:{dispatch}"
        entry: dict[str, Any] = {"dispatch": dispatch, "receipt_base": receipt_base, "route_request_id": binding.request_id, "input_sha256": _sha(text), "input_tokens_estimated": tokens,
                                 "cache_prefix_chars": prefix_chars, "prefix_sha256": None if prefix_chars is None else _sha(text[:prefix_chars]),
                                 "started": round(time.time(), 3), "finish_reason": None, "gateway_attempts": [], "error": None}
        self.sent.append(entry)
        started = time.perf_counter()
        try:
            response = self.inner.create_response(**kwargs)
            entry["finish_reason"] = response.finish_reason
            entry["gateway_attempts"] = [_gateway_attempt(item) for item in response.route_attempts]
            return response
        except Exception as error:
            entry["error"] = type(error).__name__
            entry["gateway_attempts"] = [_gateway_attempt(item) for item in getattr(error, "route_attempts", ())]
            raise
        finally:
            entry["seconds"] = round(time.perf_counter() - started, 3)


class NoSummaries:
    """The Gateway client a Q row's attachment summarizes through: it refuses every call. A Q turn has no history, so production's
    summarizer never runs; this makes that impossible rather than assumed, since the D3 model is also the first eligible summarizer and the
    Guard could not tell its call from the answer (Fable gate consult recommendation 2). `calls` lets the rehearsal assert none."""

    def __init__(self) -> None:
        self.calls = 0

    def create_response(self, **kwargs: Any) -> Any:
        self.calls += 1
        raise GuardRefused("a Q row never summarizes")


def _gateway_attempt(item: Any) -> dict[str, Any]:
    return {"attempt": item.attempt, "gateway_request_id": item.gateway_request_id, "outcome": item.outcome, "http_status": item.http_status,
            "provider_request_id": item.provider_request_id, "physical": item.outcome in PHYSICAL}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def receipt_row(receipt: Any, *, tariff: Tariff = D3_TARIFF) -> dict[str, Any]:
    """One host receipt with every field it carries (Codex CP1 attempt 3 finding 4): each StageReceipt field under its own name, the
    reported cost as `cost_usd`, the Gateway's normalized usage whole; plus the uncached repricing and its tariff. The cache-write token
    count is never reported, so it is UNKNOWN."""
    usage = getattr(receipt, "gateway_usage", None)
    row = {item.name: _jsonable(getattr(receipt, item.name)) for item in fields(receipt) if item.name != "gateway_usage"}
    row["cost_usd"] = row.pop("reported_cost_usd")
    row["usage"] = None if usage is None else usage.model_dump(mode="json")
    row.update({"repriced_uncached_usd": tariff.reprice(usage), "tariff_id": tariff.id, "cache_write_tokens": "UNKNOWN"})
    return row


def _base(attempt_id: str) -> str:
    return attempt_id.rsplit(":", 1)[0]  # a routed receipt's id is `<run>:<stage>:<turn>:<wire attempt>:<route attempt>`


def _ordinal(attempt_id: str) -> str:
    return attempt_id.rsplit(":", 1)[-1]


def _disposition_matches(gateway: str, host: str) -> bool:
    """The host keeps the Gateway's disposition, except a completed attempt whose usage is missing, which it records as uncertain."""
    return host == gateway or (gateway == "completed" and host == "uncertain")


def _identity(receipt: Mapping[str, Any]) -> tuple[Any, ...]:
    return (receipt["attempt_id"], receipt["gateway_request_id"])


def _of_send(receipt: Mapping[str, Any], base: str) -> bool:
    """The receipt belongs to the host request this send dispatched: its routed id, or the unrouted id the host gives a request whose
    attempts it could not attribute to the Gateway's route attempts."""
    return receipt["attempt_id"] == base or _base(receipt["attempt_id"]) == base


def reconcile(sent: Sequence[Mapping[str, Any]], receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Each Gateway attempt matched to the host receipts of exactly the host request it served (Codex CP1 attempts 2-5, finding 4).

    Each send must record its host request identity at dispatch (`receipt_base`); a send without one matches nothing. A receipt matches
    an attempt when its id is that request's with the attempt's ordinal, its Gateway id and disposition agree (a completed attempt the
    host records as uncertain keeps both, its charge unknown), and any route request id or attempt number its usage names agrees.

    Only a clean one-to-one match carries a known amount (Fable 5.2's simplification, CP1, accepted by Codex attempt 7). Anything else, a
    missing, duplicate, conflicting, foreign or unattributed record, or a send with no Gateway attempt, is kept, flagged, and leaves the
    amount unknown; a flagged row is incomplete and stops the run, and the Gateway ledger is the authority for what it cost. Attempts come
    only from Gateway evidence; a send the Gateway reported nothing for is MAX_ROUTE_ATTEMPTS unknown attempts, its own records kept."""
    claimed: set[int] = set()
    attempts: list[dict[str, Any]] = []
    problems: list[str] = []
    for entry in sent:
        rid, base = entry["route_request_id"], entry.get("receipt_base")
        if base is None:
            problems.append(f"{rid}: no host request identity recorded at dispatch")
        if not entry["gateway_attempts"]:
            own = [i for i, r in enumerate(receipts) if i not in claimed and base is not None and _of_send(r, base)]
            claimed.update(own)
            problems.append(f"{rid}: no Gateway attempt reported")
            attempts.extend({"route_request_id": rid, "attempt": None, "gateway_request_id": None, "outcome": None, "receipt_attempt_ids": [receipts[i]["attempt_id"] for i in own],
                             "cost_usd": None, "reason": "no Gateway attempt reported"} for _ in range(MAX_ROUTE_ATTEMPTS))
            continue
        for attempt in entry["gateway_attempts"]:

            def fits(r: Mapping[str, Any], attempt: Mapping[str, Any] = attempt, base: str | None = base, rid: str = rid) -> bool:
                usage = r.get("usage") or {}
                return _base(r["attempt_id"]) == base and _ordinal(r["attempt_id"]) == str(attempt["attempt"]) \
                    and r["gateway_request_id"] == attempt["gateway_request_id"] and _disposition_matches(attempt["outcome"], r["outcome"]) \
                    and usage.get("route_request_id") in (None, rid) and usage.get("attempt") in (None, attempt["attempt"])

            matches = [i for i, r in enumerate(receipts) if i not in claimed and fits(r)]
            claimed.update(matches)
            cost = receipts[matches[0]]["cost_usd"] if len(matches) == 1 else None
            reason = None if len(matches) == 1 else "no matching host receipt" if not matches else f"{len(matches)} host receipts match (charge unknown)"
            if reason:
                problems.append(f"{rid} attempt {attempt['attempt']}: {reason}")
            if attempt["physical"]:
                attempts.append({"route_request_id": rid, "attempt": attempt["attempt"], "gateway_request_id": attempt["gateway_request_id"], "outcome": attempt["outcome"],
                                 "receipt_attempt_ids": [receipts[i]["attempt_id"] for i in matches], "receipt_outcomes": [receipts[i]["outcome"] for i in matches],
                                 "cost_usd": cost, "reason": reason})
    unclaimed = [r for i, r in enumerate(receipts) if i not in claimed]
    problems.extend(f"host receipt {r['attempt_id']} ({r['outcome']}) matches no Gateway attempt" for r in unclaimed)
    return {"attempts": attempts, "unclaimed_receipts": unclaimed, "problems": problems}


def settlement(attempts: Sequence[Mapping[str, Any]], problems: Sequence[str]) -> dict[str, Any]:
    """What one row settles against the ceiling. Its actual USD is known only for a clean one-to-one reconciliation with every attempt
    priced; otherwise it is UNKNOWN and the Gateway ledger is the authority (the #463 producer contract, as amended at the gate)."""
    unknown = sum(1 for a in attempts if a.get("cost_usd") is None)
    actual = "UNKNOWN" if problems or unknown else str(sum((Decimal(a["cost_usd"]) for a in attempts), Decimal(0)))
    return {"attempts": len(attempts), "attempts_unknown_cost": unknown, "usd_actual": actual}


def schedule(cases: Sequence[Mapping[str, Any]], *, u_equals_b: bool) -> list[tuple[str, str, int]]:
    """(case_id, arm, position) in run order: each category's cases in id order take ARM_ORDERS once. With U = B, U is an alias of B's
    row (one request), so it is dropped from the run order and recorded as an alias."""
    order: list[tuple[str, str, int]] = []
    position = 0
    for category in CATEGORIES:
        chosen = sorted((c for c in cases if c["category"] == category), key=lambda c: c["case_id"])
        assert len(chosen) == len(ARM_ORDERS), category
        for case, arms in zip(chosen, ARM_ORDERS, strict=True):
            for arm in arms:
                if u_equals_b and arm == "U":
                    continue
                position += 1
                order.append((case["case_id"], arm, position))
    return order


def expected_calls(cases: Sequence[Mapping[str, Any]], *, u_equals_b: bool, outline_available: bool) -> dict[tuple[str, str], int]:
    """Logical requests each (case, arm) may send: zero for a predeclared forced refusal. Without Task 3's outline, F's two outline cases
    also refuse before any call."""
    expected = {}
    for case in cases:
        for arm in ("N", "B", "F") if u_equals_b else ("N", "B", "U", "F"):
            refused = case["forced_refusal"][arm] or (arm == "F" and case.get("kind") == "outline" and not outline_available)
            expected[(case["case_id"], arm)] = 0 if refused else 1
    return expected


@contextmanager
def zero_tools() -> Iterator[None]:
    """The plan's zero-tool Chat turn: the runner's own tools-withdrawn request, sent once."""
    with mock.patch.object(runner_module, "MAX_INDEX_ROUNDS", 0):
        yield


def legacy_policy(usable_input: int) -> BudgetPolicy:
    return BudgetPolicy("legacy", legacy_budget(usable_input), None)


def emitted_answer(stop_reason: str | None, text: str | None, required: Sequence[str]) -> bool:
    """Whether the row delivered anything beyond the host's own stop notice. A refusal delivers exactly production's too-large notice
    for one of the case's required files (workspace_context.blocking_from_diagnostics); any other text, a quote or an outline included,
    is an emitted answer."""
    if not text:
        return False
    notices = {blocking_from_diagnostics((WorkspaceReferenceDiagnostic(path, WorkspaceReferenceStatus.TOO_LARGE, (path,)),)) for path in required}
    return (stop_reason, text.strip()) not in notices


def terminal(row: Mapping[str, Any], *, expected_stop: str | None = None) -> tuple[str, str | None]:
    """expected_zero_call, settled, failed or incomplete, with the reason. A zero-call row is expected only with its case's declared stop
    reason and no emitted answer (Codex CP1 attempt 2, finding 3); any reconciliation problem is incomplete."""
    if row["guard_refusal"] is not None:
        return "incomplete", f"guard refused: {row['guard_refusal']}"
    if row.get("error"):
        return "incomplete", f"the run raised {row['error']}"
    if row["reconciliation"]["problems"]:
        return "incomplete", row["reconciliation"]["problems"][0]
    if row["logical_requests"] != row["expected_logical_requests"]:
        return "incomplete", f"{row['logical_requests']} logical requests, {row['expected_logical_requests']} expected"
    if row["expected_logical_requests"] == 0:
        if row["stop_reason"] != expected_stop or row["emitted_answer"]:
            return "incomplete", f"zero calls with stop {row['stop_reason']!r} and emitted answer {row['emitted_answer']}; expected {expected_stop!r} and none"
        return "expected_zero_call", row["stop_reason"]
    if any(a["cost_usd"] is None for a in row["attempts"]):
        return "incomplete", "an attempt's cost is unknown"
    if row["stop_reason"] is not None:
        return "failed", row["stop_reason"]
    return "settled", None


def run_one(case: Mapping[str, Any], arm: str, *, position: int, gateway: Any, approved: Approved, model: str, packer: Any, binder: Any, workspace: Path,
            ceiling: Ceiling, allowance: int, release: str = "Q", expected_input_sha256: str | None = None,
            write_input: Callable[[str, str], None] | None = None, observe_context: Callable[[Any, Any], None] | None = None,
            expected_cache_prefix_chars: Any = UNCHECKED) -> dict[str, Any]:
    """One logical request through the real runner, its Gateway client wrapped in the Guard. The frozen schedule allows at most one send
    per row, enforced by the Guard (Codex CP1 attempt 3 finding 3). Any failure of the run, an accounting integrity error included, still yields
    its row with every receipt the host reported, so the sink keeps it before the run stops (finding 4). `observe_context` is the runner's
    own workspace-context observer, through which the launcher takes the row's pack."""
    receipts: list[Any] = []  # the Guard refuses any allowance but 0 or 1 at construction
    run_id = f"m2b-q-{case['case_id']}-{arm}"
    guard = Guard(gateway, approved, ceiling, allowance, receipts, run_id, expected_input_sha256=expected_input_sha256, write_input=write_input,
                  expected_cache_prefix_chars=expected_cache_prefix_chars)
    request = AgentRunRequest(run_id=run_id, task=case["task"], execution_mode=ExecutionMode.CHAT, workspace_root=workspace,
                              max_planning_turns=1, max_cost_usd=ceiling.usd_max)
    runner = AgentRunner(gateway_client=guard, model=model, state_store=InMemoryAgentStateStore(), workspace_context_observer=observe_context)
    stop_reason: str | None
    answer: str | None
    error: str | None = None
    try:
        with zero_tools():
            result = runner.run(request, context_packer=packer, route_binder=binder, stage_receipts=receipts.append)
        stop_reason, answer = result.stop_reason, result.output_text
    except (GuardRefused, CapRefused) as refused:
        stop_reason, answer = type(refused).__name__, None
    except Exception as failure:  # noqa: BLE001 - kept on the row, which is incomplete and stops the run
        stop_reason, answer, error = None, None, type(failure).__name__
    host = [receipt_row(r) for r in receipts]
    cut = guard.receipts_at_refusal
    forwarded, unforwarded = (host, []) if cut is None else (host[:cut], host[cut:])  # the host's own record of a refused request is no charge
    reconciled = reconcile(guard.sent, forwarded)
    ceiling.settle(reconciled["attempts"])  # attempts from Gateway evidence only
    return {"release": release, "case_id": case["case_id"], "arm": arm, "position": position, "logical_request_id": run_id,
            "logical_requests": len(guard.sent), "sent": guard.sent, "host_receipts": host, "attempts": reconciled["attempts"],
            "reconciliation": {"unclaimed_receipt_ids": [r["attempt_id"] for r in reconciled["unclaimed_receipts"]], "problems": reconciled["problems"],
                               "unforwarded_receipt_ids": [r["attempt_id"] for r in unforwarded]},
            "settlement": settlement(reconciled["attempts"], reconciled["problems"]),
            "guard_refusal": guard.refusal, "error": error, "stop_reason": stop_reason, "answer": answer}


def run(cases: Sequence[Mapping[str, Any]], *, u_equals_b: bool, outline_available: bool, gateway: Any, approved: Approved, model: str,
        packer_for: Callable[[Mapping[str, Any], str], Any], binder_for: Callable[[Mapping[str, Any], str], Any],
        workspace_for: Callable[[Mapping[str, Any]], Path], ceiling: Ceiling, write: Callable[[Mapping[str, Any]], None],
        write_answers: Callable[[Mapping[str, Any]], None], release: str = "Q", write_input: Callable[[str, str], None] | None = None,
        expected_inputs: Mapping[tuple[str, str], Mapping[str, Any]] | None = None, observe_context: Callable[[Any, Any], None] | None = None,
        row_evidence: Callable[[Mapping[str, Any], str, Mapping[str, Any]], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """The whole release in its frozen order. Stops at the first row that is not settled or an expected zero call. With `expected_inputs`
    (the launcher's dry preparation pass, gate item 14), each row's Guard forwards only that row's input with that row's prefix boundary;
    a row the pass did not prepare has none, so it is refused. `row_evidence` adds the launcher's observation (pack, epoch, tree) to each
    row before it is written."""
    by_id = {case["case_id"]: case for case in cases}
    expected = expected_calls(cases, u_equals_b=u_equals_b, outline_available=outline_available)
    report: dict[str, Any] = {"schema": "plan12-memory-m2b.paid-attempts.v2", "release": release, "u_equals_b": u_equals_b, "rows": [], "stopped": None}
    answers: dict[str, str | None] = {}
    for case_id, arm, position in schedule(cases, u_equals_b=u_equals_b):
        case = by_id[case_id]
        prepared = None if expected_inputs is None else expected_inputs.get((case_id, arm))
        row = run_one(case, arm, position=position, gateway=gateway, approved=approved, model=model, packer=packer_for(case, arm), binder=binder_for(case, arm),
                      workspace=workspace_for(case), ceiling=ceiling, allowance=expected[(case_id, arm)], release=release, write_input=write_input,
                      expected_input_sha256=None if expected_inputs is None else (prepared or {}).get("input_sha256", "not prepared by the dry pass"),
                      expected_cache_prefix_chars=UNCHECKED if prepared is None else prepared["cache_prefix_chars"], observe_context=observe_context)
        row["expected_logical_requests"] = expected[(case_id, arm)]
        answer = row.pop("answer")
        answers[f"{case_id}/{arm}"] = answer
        row["emitted_answer"] = emitted_answer(row["stop_reason"], answer, [item["path"] for item in case.get("required_files", [])])
        row["answer_sha256"] = None if answer is None else _sha(answer)
        row["terminal"], row["terminal_reason"] = terminal(row, expected_stop=(case.get("boundary") or {}).get("stop_reason"))
        if row_evidence is not None:
            row.update(row_evidence(case, arm, row))
        report["rows"].append(row)
        write_answers(answers)
        write(report)
        if row["terminal"] not in {"settled", "expected_zero_call", "failed"} or (row["terminal"] == "failed" and row["logical_requests"]):
            report["stopped"] = {"at": [case_id, arm], "reason": row["terminal_reason"]}
            break
    if u_equals_b:
        report["aliases"] = {"U": "B"}
    report["ceiling"] = {"attempts_used": ceiling.attempts_used, "usd_settled": str(ceiling.usd_settled), "unknown_attempts": ceiling.unknown_attempts}
    write(report)
    return report


def write_json(path: Path) -> Callable[[Mapping[str, Any]], None]:
    def write(report: Mapping[str, Any]) -> None:
        path.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")

    return write
