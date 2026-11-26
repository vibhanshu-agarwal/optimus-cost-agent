"""One-call coverage epochs for model calls outside any turn (Plan 12.8; Codex Checkpoint A ruling): the strict preflight
auth probe and the JSON-RPC Gateway pass-through. Each call gets its own epoch through an ordinary `TurnSettlement`
(stage `operation`), so it is begun, intended, receipted with the same attempt classifier every stage uses, and closed
exactly like a turn. Capture never changes the call: its result or exception passes through unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from optimus.gateway.attempts import AttemptIntegrityError, ProviderAttempt, attempts_from_failure, attempts_from_response
from optimus.gateway.client import CaptureIntent, capturing
from optimus.gateway.errors import GatewayError, GatewayFailureFacts, GatewayFailureReason, GatewayHttpError, PreflightProof
from optimus.gateway.models import GatewayResponse
from optimus.usage.turn_settlement import ReceiptConflictError, StageReceipt, TurnSettlement

if TYPE_CHECKING:
    from optimus.usage.durable_capture import DurableCapture


def captured_operation(
    capture: DurableCapture | None,
    *,
    kind: str,
    call: Callable[[], GatewayResponse],
    session_id: str | None = None,
    requested_model: str | None = None,
    gateway_failure_facts: GatewayFailureFacts | None = None,
) -> GatewayResponse:
    """Run ``call`` (one Gateway client request) inside its own coverage epoch."""
    if capture is None:
        return call()
    turn_id = f"op:{kind}:{uuid.uuid4().hex}"
    base = f"{turn_id}:operation:1:1"
    settlement = TurnSettlement(capture=capture, session_id=session_id)
    invocation = settlement.open_invocation(turn_id)
    invocation.start()
    response: GatewayResponse | None = None
    failure: BaseException | None = None
    try:
        intent = CaptureIntent(turn_id=turn_id, host_request_id=base, stage="operation", purpose=f"operation.{kind}", requested_model=requested_model)
        with capturing(intent):
            response = call()
    except BaseException as exc:
        failure = exc
        raise
    finally:
        reason = _settle(settlement, turn_id, base, session_id, requested_model, response, failure)
        invocation.end()
        settlement.finalize_turn(turn_id)
        if gateway_failure_facts is not None and isinstance(failure, GatewayError) and reason is not None:
            gateway_failure_facts.publish(failure, reason)
    return response


def _settle(settlement: TurnSettlement, turn_id: str, base: str, session_id: str | None, requested_model: str | None,
            response: GatewayResponse | None, failure: BaseException | None) -> GatewayFailureReason | None:
    integrity = False
    accepted_usage = False
    all_receipts_accepted = True
    try:
        attempts = attempts_from_response(response) if response is not None else attempts_from_failure(failure or RuntimeError())
    except AttemptIntegrityError as error:
        integrity = True
        settlement.record_integrity_failure(turn_id)
        attempts = error.attempts
    for attempt in attempts:
        try:
            receipt = _receipt(turn_id, base, session_id, requested_model, attempt)
        except ValueError:
            integrity = True
            settlement.record_integrity_failure(turn_id)
            continue
        try:
            settlement.record_attempt(receipt)
        except ReceiptConflictError:
            integrity = True  # the settlement already counted it as an integrity failure
        except ValueError:
            all_receipts_accepted = False
            settlement.record_integrity_failure(turn_id)
        else:
            accepted_usage |= attempt.outcome == "completed" and attempt.gateway_usage is not None
    if integrity:
        return GatewayFailureReason.ATTEMPT_INTEGRITY
    if isinstance(failure, GatewayHttpError):
        if failure.preflight_proof is PreflightProof.DIRECT_REFUSAL:
            return GatewayFailureReason.PREFLIGHT_REFUSED
        if failure.route_attempts_malformed:
            return None
    if all_receipts_accepted and accepted_usage and all(attempt.cost_usd is not None for attempt in attempts):
        return GatewayFailureReason.ACCOUNTED_FAILURE
    return None


def _receipt(turn_id: str, base: str, session_id: str | None, requested_model: str | None, attempt: ProviderAttempt) -> StageReceipt:
    return StageReceipt(
        session_id=session_id,
        turn_id=turn_id,
        stage="operation",
        attempt_id=f"{base}:{attempt.key}" if attempt.routed or attempt.outcome == "unattributed" else base,
        gateway_request_id=attempt.gateway_request_id,
        outcome=attempt.outcome,
        reported_cost_usd=attempt.cost_usd,
        recorded_at=datetime.now(tz=UTC),
        requested_model=requested_model,
        provider_request_id=attempt.provider_request_id,
        http_status=attempt.http_status,
        gateway_usage=attempt.gateway_usage,
    )
