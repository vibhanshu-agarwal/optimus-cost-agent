"""Plan 12.14 paid Q runner (Task 4, under its own release; zero-paid tests in Task 1). Design: optimus-handoff/p1214-task1/q-runner-design.md.

One process drives the real AgentRunner in Chat mode for each case and arm, on the real attached-turn packer, the real memory turn over a
real index of the case's snapshot, the real route binder on the staged composition, and the Gateway client it is given. The arms differ
only in configuration:

- N: no memory, so the runner takes today's context (engine absent) and the non-indexed builder.
- B (= U while the baseline is retained): the memory turn with the pack budget forced to the legacy policy.
- F: the memory turn with the route's own budget (the staged D3 target), exactly production's.

Two enumerated deltas from shipping production, frozen in the intended composition: index tools are withdrawn (MAX_INDEX_ROUNDS = 0, so
the turn is one request and zero-tool) and the output cap is Q's (2,048), bound through RoutePolicy. Before every logical request the
ceiling reserves MAX_ROUTE_ATTEMPTS physical attempts and the worst-case USD; a request it cannot reserve stops the run, with no
replacement. Every attempt the runner observes is kept, known or unknown; an unknown cost stops the run. Records hold ids, digests,
counts and each answer's digest, never source bodies or credentials; the answers themselves (a reply can quote source) go to a separate
sink kept outside the repository, archived and hashed for scoring.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
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


class CapRefused(Exception):
    """The next logical request cannot be reserved inside the release."""


@dataclass
class Ceiling:
    """The release's attempt and USD bounds, reserved before each logical request and settled from what the runner observed."""

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
    """Logical requests each (case, arm) is expected to send: zero for a predeclared forced refusal. Without Task 3's outline, F's two
    outline cases also refuse before any call."""
    expected = {}
    for case in cases:
        for arm in ("N", "B", "F") if u_equals_b else ("N", "B", "U", "F"):
            refused = case["forced_refusal"][arm] or (arm == "F" and case.get("kind") == "outline" and not outline_available)
            expected[(case["case_id"], arm)] = 0 if refused else 1
    return expected


@dataclass
class Recorder:
    """The Gateway client the runner holds: it forwards every request and records what was sent, in order. Nothing else reaches a model."""

    inner: Any
    sent: list[dict[str, Any]] = field(default_factory=list)

    def create_response(self, **kwargs: Any) -> Any:
        text = kwargs.get("input_text", "")
        started = time.time()
        try:
            return self.inner.create_response(**kwargs)
        finally:
            self.sent.append({"input_sha256": "hex:" + hashlib.sha256(text.encode("utf-8")).hexdigest(), "input_bytes": len(text.encode("utf-8")),
                              "started": round(started, 3), "seconds": round(time.time() - started, 3)})


def attempt_row(receipt: Any) -> dict[str, Any]:
    usage = getattr(receipt, "gateway_usage", None)
    return {
        "attempt_id": receipt.attempt_id, "gateway_request_id": receipt.gateway_request_id, "outcome": receipt.outcome, "stage": receipt.stage,
        "cost_usd": None if receipt.reported_cost_usd is None else str(receipt.reported_cost_usd),
        "requested_model": receipt.requested_model, "route": list(receipt.route), "reasoning": receipt.reasoning,
        "usage": None if usage is None else {name: getattr(usage, name, None) for name in ("input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens", "provider", "model")},
    }


@contextmanager
def zero_tools() -> Iterator[None]:
    """The plan's zero-tool Chat turn: the runner's own tools-withdrawn request, sent once."""
    with mock.patch.object(runner_module, "MAX_INDEX_ROUNDS", 0):
        yield


def legacy_policy(usable_input: int) -> BudgetPolicy:
    return BudgetPolicy("legacy", legacy_budget(usable_input), None)


def run_one(case: Mapping[str, Any], arm: str, *, position: int, gateway: Any, model: str, packer: Any, binder: Any, workspace: Path,
            ceiling: Ceiling) -> dict[str, Any]:
    """One logical request through the real runner. The ceiling is reserved first; the attempts observed settle it."""
    ceiling.reserve()
    recorder = Recorder(gateway)
    receipts: list[Any] = []
    request = AgentRunRequest(run_id=f"m2b-q-{case['case_id']}-{arm}", task=case["task"], execution_mode=ExecutionMode.CHAT, workspace_root=workspace,
                              max_planning_turns=1, max_cost_usd=ceiling.usd_max)
    runner = AgentRunner(gateway_client=recorder, model=model, state_store=InMemoryAgentStateStore())
    with zero_tools():
        result = runner.run(request, context_packer=packer, route_binder=binder, stage_receipts=receipts.append)
    attempts = [attempt_row(r) for r in receipts]
    ceiling.settle(attempts)
    return {"case_id": case["case_id"], "arm": arm, "position": position, "logical_requests": len(recorder.sent), "sent": recorder.sent,
            "attempts": attempts, "stop_reason": result.stop_reason, "answer": result.output_text,
            "unknown_cost": any(a["cost_usd"] is None for a in attempts)}


def run(cases: Sequence[Mapping[str, Any]], *, u_equals_b: bool, outline_available: bool, gateway: Any, model: str,
        packer_for: Callable[[Mapping[str, Any], str], Any], binder_for: Callable[[Mapping[str, Any], str], Any],
        workspace_for: Callable[[Mapping[str, Any]], Path], ceiling: Ceiling, write: Callable[[Mapping[str, Any]], None],
        write_answers: Callable[[Mapping[str, Any]], None]) -> dict[str, Any]:
    """The whole release in its frozen order. Stops at the first unreservable request, unknown cost or unexpected call count."""
    by_id = {case["case_id"]: case for case in cases}
    expected = expected_calls(cases, u_equals_b=u_equals_b, outline_available=outline_available)
    report: dict[str, Any] = {"schema": "plan12-memory-m2b.paid-attempts.v1", "u_equals_b": u_equals_b, "rows": [], "stopped": None}
    answers: dict[str, str | None] = {}
    for case_id, arm, position in schedule(cases, u_equals_b=u_equals_b):
        case = by_id[case_id]
        try:
            row = run_one(case, arm, position=position, gateway=gateway, model=model, packer=packer_for(case, arm), binder=binder_for(case, arm),
                          workspace=workspace_for(case), ceiling=ceiling)
        except CapRefused as refused:
            report["stopped"] = {"at": [case_id, arm], "reason": str(refused)}
            break
        row["expected_logical_requests"] = expected[(case_id, arm)]
        answer = row.pop("answer")
        answers[f"{case_id}/{arm}"] = answer
        row["answer_sha256"] = None if answer is None else "hex:" + hashlib.sha256(answer.encode("utf-8")).hexdigest()
        report["rows"].append(row)
        write_answers(answers)
        write(report)
        if row["unknown_cost"]:
            report["stopped"] = {"at": [case_id, arm], "reason": "an attempt's cost is unknown"}
            break
        if row["logical_requests"] != row["expected_logical_requests"]:
            report["stopped"] = {"at": [case_id, arm], "reason": f"{row['logical_requests']} logical requests, {row['expected_logical_requests']} expected"}
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
