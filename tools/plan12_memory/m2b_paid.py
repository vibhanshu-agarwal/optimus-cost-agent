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

The Guard is the only client the runner holds. Before it forwards a request it requires the row's call allowance, a binding to the approved
registry hash and output cap, an input within the cap, the previous send reconciled, and the ceiling's reservation; otherwise it raises
before anything is sent. Physical attempts are counted from the Gateway's own route attempts and matched to the host's receipts by Gateway
request id; a sent request with no Gateway attempt or no matching receipt is UNKNOWN and stops the run. Answers go to a separate sink kept
outside the repository; the record keeps ids, digests and counts, never source or request bodies or credentials.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from unittest import mock

from optimus.agent import runner as runner_module
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.context.context_budget import BudgetPolicy, legacy_budget
from optimus.runtime.modes import ExecutionMode
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS

ARM_ORDERS: Final = (("N", "B", "U", "F"), ("B", "U", "F", "N"), ("U", "F", "N", "B"), ("F", "N", "B", "U"))
CATEGORIES: Final = ("ranking", "budget", "outline")
OUTPUT_CAP: Final = 2_048
INPUT_CAP: Final = 65_536
PHYSICAL: Final = frozenset({"completed", "uncertain", "rejected"})  # left the Gateway for a provider; not_sent did not


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
    unknown_attempts: int = 0

    def reserve(self) -> None:
        bound = self.usd_settled + self.per_attempt_usd * (self.unknown_attempts + MAX_ROUTE_ATTEMPTS)
        if self.attempts_used + MAX_ROUTE_ATTEMPTS > self.attempts_max or bound > self.usd_max:
            raise CapRefused(f"cannot reserve {MAX_ROUTE_ATTEMPTS} attempts: {self.attempts_used} used of {self.attempts_max}, worst case USD {bound} of {self.usd_max}")

    def settle(self, attempts: Sequence[Mapping[str, Any]]) -> None:
        self.attempts_used += len(attempts)
        for attempt in attempts:
            cost = attempt.get("cost_usd")
            if cost is None:
                self.unknown_attempts += 1
            else:
                self.usd_settled += Decimal(cost)


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
USAGE_FIELDS: Final = ("input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens", "cache_hit", "cache_age_seconds", "billing_units", "price_snapshot_id",
                       "service", "native_unit", "provider", "resolved_provider", "model", "model_version", "resolved_model", "route_request_id", "attempt")


@dataclass(frozen=True)
class Approved:
    """What every send must be bound to: the approved effective hash and Q's caps, with the route's own request estimator."""

    registry_hash: str
    estimate_request: Callable[[str], int]
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
    sent: list[dict[str, Any]] = field(default_factory=list)
    refusal: str | None = None

    def _refuse(self, reason: str) -> None:
        self.refusal = reason
        raise GuardRefused(reason)

    def create_response(self, **kwargs: Any) -> Any:
        text = kwargs.get("input_text", "")
        binding = kwargs.get("route_binding")
        if len(self.sent) >= self.allowance:
            self._refuse(f"row allowance of {self.allowance} request(s) reached")
        if binding is None:
            self._refuse("an unbound request")
        if binding.registry_hash != self.approved.registry_hash or binding.output_cap != self.approved.output_cap:
            self._refuse("the binding is not the approved composition and output cap")
        tokens = self.approved.estimate_request(text)
        if tokens > self.approved.input_cap:
            self._refuse(f"input of {tokens} estimated tokens over the cap of {self.approved.input_cap}")
        if self.sent and not self.sent[-1]["gateway_attempts"]:
            self._refuse("the previous send is not reconciled with Gateway attempts")
        self.ceiling.reserve()
        prefix_chars = binding.cache_prefix_chars
        entry: dict[str, Any] = {"route_request_id": binding.request_id, "input_sha256": _sha(text), "input_tokens_estimated": tokens,
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


def _gateway_attempt(item: Any) -> dict[str, Any]:
    return {"attempt": item.attempt, "gateway_request_id": item.gateway_request_id, "outcome": item.outcome, "http_status": item.http_status,
            "provider_request_id": item.provider_request_id, "physical": item.outcome in PHYSICAL}


def receipt_row(receipt: Any, *, tariff: Tariff = D3_TARIFF) -> dict[str, Any]:
    """One host receipt, every reported field kept; the cache-write token count is never reported, so it is UNKNOWN."""
    usage = getattr(receipt, "gateway_usage", None)
    recorded = receipt.recorded_at
    return {
        "attempt_id": receipt.attempt_id, "gateway_request_id": receipt.gateway_request_id, "provider_request_id": receipt.provider_request_id,
        "http_status": receipt.http_status, "outcome": receipt.outcome, "stage": receipt.stage, "recorded_at": recorded.isoformat() if isinstance(recorded, datetime) else str(recorded),
        "post_teardown": receipt.post_teardown, "cost_usd": None if receipt.reported_cost_usd is None else str(receipt.reported_cost_usd),
        "repriced_uncached_usd": tariff.reprice(usage), "tariff_id": tariff.id, "requested_model": receipt.requested_model, "route": list(receipt.route),
        "reasoning": receipt.reasoning, "registry_hash": receipt.registry_hash,
        "usage": None if usage is None else {name: getattr(usage, name, None) for name in USAGE_FIELDS}, "cache_write_tokens": "UNKNOWN",
    }


def physical_attempts(sent: Sequence[Mapping[str, Any]], receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Physical attempts from the Gateway's own report, each matched to the host receipt with its Gateway request id; a send the Gateway
    reported nothing for counts as MAX_ROUTE_ATTEMPTS unknown attempts. Each charge is counted once."""
    by_id = {r["gateway_request_id"]: r for r in receipts if r["gateway_request_id"]}
    out: list[dict[str, Any]] = []
    for entry in sent:
        reported = [a for a in entry["gateway_attempts"] if a["physical"]]
        if not entry["gateway_attempts"]:
            out.extend({"route_request_id": entry["route_request_id"], "gateway_request_id": None, "cost_usd": None, "reason": "no Gateway attempt reported"}
                       for _ in range(MAX_ROUTE_ATTEMPTS))
        for attempt in reported:
            receipt = by_id.get(attempt["gateway_request_id"])
            out.append({"route_request_id": entry["route_request_id"], "gateway_request_id": attempt["gateway_request_id"], "outcome": attempt["outcome"],
                        "cost_usd": None if receipt is None else receipt["cost_usd"], "reason": None if receipt is not None else "no matching host receipt"})
    return out


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


def terminal(row: Mapping[str, Any]) -> tuple[str, str | None]:
    """expected_zero_call, settled, failed or incomplete, with the reason."""
    if row["guard_refusal"] is not None:
        return "incomplete", f"guard refused: {row['guard_refusal']}"
    if row["logical_requests"] != row["expected_logical_requests"]:
        return "incomplete", f"{row['logical_requests']} logical requests, {row['expected_logical_requests']} expected"
    if row["expected_logical_requests"] == 0:
        return "expected_zero_call", row["stop_reason"]
    if any(a["cost_usd"] is None for a in row["attempts"]):
        return "incomplete", "an attempt's cost is unknown"
    if row["stop_reason"] is not None:
        return "failed", row["stop_reason"]
    return "settled", None


def run_one(case: Mapping[str, Any], arm: str, *, position: int, gateway: Any, approved: Approved, model: str, packer: Any, binder: Any, workspace: Path,
            ceiling: Ceiling, allowance: int, release: str = "Q") -> dict[str, Any]:
    """One logical request through the real runner, its Gateway client wrapped in the Guard."""
    guard = Guard(gateway, approved, ceiling, allowance)
    receipts: list[Any] = []
    run_id = f"m2b-q-{case['case_id']}-{arm}"
    request = AgentRunRequest(run_id=run_id, task=case["task"], execution_mode=ExecutionMode.CHAT, workspace_root=workspace,
                              max_planning_turns=1, max_cost_usd=ceiling.usd_max)
    runner = AgentRunner(gateway_client=guard, model=model, state_store=InMemoryAgentStateStore())
    stop_reason: str | None
    answer: str | None
    try:
        with zero_tools():
            result = runner.run(request, context_packer=packer, route_binder=binder, stage_receipts=receipts.append)
        stop_reason, answer = result.stop_reason, result.output_text
    except (GuardRefused, CapRefused) as refused:
        stop_reason, answer = type(refused).__name__, None
    host = [receipt_row(r) for r in receipts]
    attempts = physical_attempts(guard.sent, host)
    ceiling.settle(attempts)
    return {"release": release, "case_id": case["case_id"], "arm": arm, "position": position, "logical_request_id": run_id,
            "logical_requests": len(guard.sent), "sent": guard.sent, "host_receipts": host, "attempts": attempts, "guard_refusal": guard.refusal,
            "stop_reason": stop_reason, "answer": answer}


def run(cases: Sequence[Mapping[str, Any]], *, u_equals_b: bool, outline_available: bool, gateway: Any, approved: Approved, model: str,
        packer_for: Callable[[Mapping[str, Any], str], Any], binder_for: Callable[[Mapping[str, Any], str], Any],
        workspace_for: Callable[[Mapping[str, Any]], Path], ceiling: Ceiling, write: Callable[[Mapping[str, Any]], None],
        write_answers: Callable[[Mapping[str, Any]], None], release: str = "Q") -> dict[str, Any]:
    """The whole release in its frozen order. Stops at the first row that is not settled or an expected zero call."""
    by_id = {case["case_id"]: case for case in cases}
    expected = expected_calls(cases, u_equals_b=u_equals_b, outline_available=outline_available)
    report: dict[str, Any] = {"schema": "plan12-memory-m2b.paid-attempts.v2", "release": release, "u_equals_b": u_equals_b, "rows": [], "stopped": None}
    answers: dict[str, str | None] = {}
    for case_id, arm, position in schedule(cases, u_equals_b=u_equals_b):
        case = by_id[case_id]
        row = run_one(case, arm, position=position, gateway=gateway, approved=approved, model=model, packer=packer_for(case, arm), binder=binder_for(case, arm),
                      workspace=workspace_for(case), ceiling=ceiling, allowance=expected[(case_id, arm)], release=release)
        row["expected_logical_requests"] = expected[(case_id, arm)]
        answer = row.pop("answer")
        answers[f"{case_id}/{arm}"] = answer
        row["answer_sha256"] = None if answer is None else _sha(answer)
        row["terminal"], row["terminal_reason"] = terminal(row)
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
