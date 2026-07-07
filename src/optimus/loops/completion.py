from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Protocol

from optimus.gateway.client import GatewayClient
from optimus.loops.ledger import ProgressLedger
from optimus.loops.models import CompletionEvaluation, IterationState


class DeterministicCompletionPredicate(Protocol):
    def __call__(self, state: IterationState, ledger: ProgressLedger) -> CompletionEvaluation:
        raise NotImplementedError


class DeterministicCompletionEvaluator:
    def __init__(self, *, completed: bool, reason: str) -> None:
        self._completed = completed
        self._reason = reason

    def evaluate(self, state: IterationState, ledger: ProgressLedger) -> CompletionEvaluation:
        return CompletionEvaluation(completed=self._completed, reason=self._reason)


class GatewayCompletionEvaluator:
    def __init__(
        self,
        *,
        client: GatewayClient,
        model: str,
        deterministic_predicate: DeterministicCompletionPredicate | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._deterministic_predicate = deterministic_predicate

    def evaluate(self, state: IterationState, ledger: ProgressLedger) -> CompletionEvaluation:
        if self._deterministic_predicate is not None:
            deterministic = self._deterministic_predicate(state, ledger)
            if not deterministic.completed:
                return deterministic
        response = self._client.create_response(
            model=self._model,
            input_text=_completion_prompt(state, ledger),
            metadata={
                "purpose": "goal_loop_completion_evaluation",
                "run_id": state.run_id,
                "session_id": state.session_id,
            },
        )
        try:
            payload = json.loads(response.output_text, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise ValueError("completion evaluator returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("completion evaluator returned non-object JSON")
        completed = payload.get("completed")
        if not isinstance(completed, bool):
            raise ValueError("completed must be a JSON boolean")
        try:
            confidence = Decimal(str(payload.get("confidence", "1")))
        except InvalidOperation as exc:
            raise ValueError("confidence must be a decimal") from exc
        usage = response.gateway_usage
        credits = usage.optimus_credits_debited if usage.optimus_credits_debited is not None else Decimal("0")
        return CompletionEvaluation(
            completed=completed,
            reason=str(payload.get("reason") or "completion evaluator did not provide a reason"),
            confidence=confidence,
            cost_credits=credits,
            gateway_request_id=usage.gateway_request_id,
        )


def _completion_prompt(state: IterationState, ledger: ProgressLedger) -> str:
    recent = ledger.entries(run_id=state.run_id)[-5:]
    summaries = "\n".join(
        f"- iteration {entry.iteration}: summary={entry.summary}; failure_signature={entry.failure_signature}; stop_reason={entry.stop_reason}; evidence={entry.evidence}"
        for entry in recent
    )
    return (
        "Evaluate whether the bounded goal loop is complete.\n"
        "Return strict JSON with keys completed, reason, and confidence.\n"
        f"Goal: {state.goal}\n"
        f"Completion condition: {state.completion_condition}\n"
        f"Iterations: {state.iteration}\n"
        f"Recent progress:\n{summaries}\n"
    )
