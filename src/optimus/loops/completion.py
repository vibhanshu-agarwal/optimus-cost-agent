from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

from optimus.gateway.client import GatewayClient
from optimus.loops.ledger import ProgressLedger
from optimus.loops.models import CompletionEvaluation, IterationState
from optimus.telemetry.redaction import redact_for_telemetry
from optimus.telemetry.subjects import sanitize_workspace_text


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
        workspace_root: str | Path | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._deterministic_predicate = deterministic_predicate
        self._workspace_root = workspace_root

    def evaluate(self, state: IterationState, ledger: ProgressLedger) -> CompletionEvaluation:
        if self._deterministic_predicate is not None:
            deterministic = self._deterministic_predicate(state, ledger)
            if not deterministic.completed:
                return deterministic
        response = self._client.create_response(
            model=self._model,
            input_text=_completion_prompt(state, ledger, workspace_root=self._workspace_root),
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


def _completion_prompt(
    state: IterationState,
    ledger: ProgressLedger,
    *,
    workspace_root: str | Path | None,
) -> str:
    recent = ledger.entries(run_id=state.run_id)[-5:]
    summaries = "\n".join(
        (
            f"- iteration {entry.iteration}: "
            f"summary={_sanitize_prompt_text(entry.summary, workspace_root=workspace_root)}; "
            f"failure_signature={_sanitize_prompt_text(entry.failure_signature or '', workspace_root=workspace_root)}; "
            f"stop_reason={entry.stop_reason}; "
            f"evidence={_sanitize_prompt_evidence(entry.evidence, workspace_root=workspace_root)}"
        )
        for entry in recent
    )
    return (
        "Evaluate whether the bounded goal loop is complete.\n"
        "Return strict JSON with keys completed, reason, and confidence.\n"
        f"Goal: {_sanitize_prompt_text(state.goal, workspace_root=workspace_root)}\n"
        f"Completion condition: {_sanitize_prompt_text(state.completion_condition, workspace_root=workspace_root)}\n"
        f"Iterations: {state.iteration}\n"
        f"Recent progress:\n{summaries}\n"
    )


def _sanitize_prompt_text(text: str, *, workspace_root: str | Path | None) -> str:
    return sanitize_workspace_text(text, workspace_root=workspace_root)


def _sanitize_prompt_evidence(evidence: dict[str, str], *, workspace_root: str | Path | None) -> dict[str, str]:
    redacted = redact_for_telemetry(evidence)
    if not isinstance(redacted, dict):
        return {}
    return {
        str(key): sanitize_workspace_text(str(value), workspace_root=workspace_root)
        for key, value in redacted.items()
    }
