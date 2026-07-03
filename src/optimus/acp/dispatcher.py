from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from optimus.acp.errors import (
    DUPLICATE_REQUEST_ID,
    INTERNAL_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    MUTATION_FORBIDDEN,
    JsonRpcError,
    error_response,
    success_response,
)
from optimus.acp.request_ids import DuplicateRequestId, RequestIdTracker
from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainRejected
from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidenceRequest,
    EvidenceSearchResponse,
)
from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayError
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools.mutation_tools import write_file
from optimus.tools.registry import ToolCallRejected


class JsonRpcDispatcher:
    def __init__(
        self,
        request_ids: RequestIdTracker | None = None,
        runtime_context: RuntimeContext | None = None,
        gateway_client: GatewayClient | None = None,
        evidence_service: EvidenceAcquisitionService | None = None,
    ) -> None:
        self._request_ids = request_ids or RequestIdTracker()
        self._runtime_context = runtime_context or RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )
        self._gateway_client = gateway_client
        self._evidence_service = evidence_service

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        try:
            self._request_ids.remember(request_id)
        except DuplicateRequestId:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(
                    code=DUPLICATE_REQUEST_ID,
                    message="duplicate request id",
                    data={"id": request_id},
                ),
            )

        if request.get("jsonrpc") != "2.0" or "method" not in request:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
            )

        method = request["method"]
        try:
            if method == "optimus.ping":
                return success_response(request_id=request_id, result={"message": "pong"})
            if method == "optimus.gateway.responses":
                if self._gateway_client is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="gateway client not configured"),
                    )
                params = request.get("params")
                if (
                    not isinstance(params, dict)
                    or not isinstance(params.get("model"), str)
                    or not isinstance(params.get("input"), str)
                    or "messages" in params
                ):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                metadata = params.get("metadata")
                if metadata is not None and not isinstance(metadata, dict):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                gateway_response = self._gateway_client.create_response(
                    model=params["model"],
                    input_text=params["input"],
                    metadata=metadata,
                )
                return success_response(
                    request_id=request_id,
                    result=_gateway_response_payload(gateway_response),
                )
            if method == "optimus.evidence.search":
                if self._evidence_service is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="evidence service not configured"),
                    )
                try:
                    evidence_request = EvidenceRequest.model_validate(request.get("params"))
                except ValidationError:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                response, ledger = self._evidence_service.search(
                    evidence_request,
                    execution_mode=self._runtime_context.execution_mode,
                )
                return success_response(
                    request_id=request_id,
                    result=_evidence_search_payload(response, ledger, evidence_request.run_id),
                )
            if method == "optimus.evidence.extract":
                if self._evidence_service is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="evidence service not configured"),
                    )
                try:
                    extract_request = EvidenceExtractRequest.model_validate(request.get("params"))
                except ValidationError:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                response, ledger = self._evidence_service.extract(
                    extract_request,
                    execution_mode=self._runtime_context.execution_mode,
                )
                return success_response(
                    request_id=request_id,
                    result=_evidence_extract_payload(response, ledger, extract_request.run_id),
                )
            if method == "optimus.mutation.writeFile":
                params = request.get("params")
                if not isinstance(params, dict) or not isinstance(params.get("path"), str):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                write_file(
                    Path(params["path"]),
                    str(params.get("content", "")),
                    context=self._runtime_context,
                )
                return success_response(request_id=request_id, result={"written": params["path"]})
        except MutationForbidden as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=MUTATION_FORBIDDEN, message=str(exc)),
            )
        except ToolCallRejected as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message=str(exc)),
            )
        except EvidenceDomainRejected as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message=str(exc)),
            )
        except ValueError as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INTERNAL_ERROR, message=str(exc)),
            )
        except GatewayError as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INTERNAL_ERROR, message=str(exc)),
            )

        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}"),
        )


def _gateway_usage_payload(usage: GatewayUsage) -> dict[str, Any]:
    return {
        "gateway_request_id": usage.gateway_request_id,
        "provider": usage.provider,
        "provider_request_id": usage.provider_request_id,
        "cache_hit": usage.cache_hit,
        "billing_units": usage.billing_units,
        "cost_usd": str(usage.cost_usd),
    }


def _gateway_response_payload(response: GatewayResponse) -> dict[str, Any]:
    return {
        "response_id": response.response_id,
        "output_text": response.output_text,
        "gateway_usage": _gateway_usage_payload(response.gateway_usage),
    }


def _evidence_search_payload(
    response: EvidenceSearchResponse,
    ledger: EvidenceLedger,
    run_id: str,
) -> dict[str, Any]:
    return {
        "results": [
            {"title": result.title, "url": result.url_text, "snippet": result.snippet}
            for result in response.results
        ],
        "gateway_usage": _gateway_usage_payload(response.gateway_usage),
        "ledger_run_total_cost_usd": str(ledger.total_cost_usd(run_id=run_id)),
        "ledger_run_total_credits": ledger.total_credits(run_id=run_id),
    }


def _evidence_extract_payload(
    response: EvidenceExtractResponse,
    ledger: EvidenceLedger,
    run_id: str,
) -> dict[str, Any]:
    return {
        "url": response.url_text,
        "title": response.title,
        "content": response.content,
        "trust": response.trust,
        "gateway_usage": _gateway_usage_payload(response.gateway_usage),
        "ledger_run_total_cost_usd": str(ledger.total_cost_usd(run_id=run_id)),
        "ledger_run_total_credits": ledger.total_credits(run_id=run_id),
    }
