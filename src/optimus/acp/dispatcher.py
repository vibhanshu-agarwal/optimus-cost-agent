from __future__ import annotations

from pathlib import Path
from typing import Any

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
from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayError
from optimus.gateway.models import GatewayResponse
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools.mutation_tools import write_file


class JsonRpcDispatcher:
    def __init__(
        self,
        request_ids: RequestIdTracker | None = None,
        runtime_context: RuntimeContext | None = None,
        gateway_client: GatewayClient | None = None,
    ) -> None:
        self._request_ids = request_ids or RequestIdTracker()
        self._runtime_context = runtime_context or RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )
        self._gateway_client = gateway_client

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
        except GatewayError as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INTERNAL_ERROR, message=str(exc)),
            )

        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}"),
        )


def _gateway_response_payload(response: GatewayResponse) -> dict[str, Any]:
    return {
        "response_id": response.response_id,
        "output_text": response.output_text,
        "gateway_usage": {
            "gateway_request_id": response.gateway_usage.gateway_request_id,
            "provider": response.gateway_usage.provider,
            "provider_request_id": response.gateway_usage.provider_request_id,
            "cache_hit": response.gateway_usage.cache_hit,
            "billing_units": response.gateway_usage.billing_units,
            "cost_usd": str(response.gateway_usage.cost_usd),
        },
    }
