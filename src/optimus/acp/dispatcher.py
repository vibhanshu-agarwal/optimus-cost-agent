from __future__ import annotations

from pathlib import Path
from typing import Any

from optimus.acp.errors import (
    DUPLICATE_REQUEST_ID,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    MUTATION_FORBIDDEN,
    JsonRpcError,
    error_response,
    success_response,
)
from optimus.acp.request_ids import DuplicateRequestId, RequestIdTracker
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools.mutation_tools import write_file


class JsonRpcDispatcher:
    def __init__(
        self,
        request_ids: RequestIdTracker | None = None,
        runtime_context: RuntimeContext | None = None,
    ) -> None:
        self._request_ids = request_ids or RequestIdTracker()
        self._runtime_context = runtime_context or RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )

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

        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}"),
        )
