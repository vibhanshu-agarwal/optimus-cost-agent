from __future__ import annotations

from typing import Any

from optimus.acp.errors import (
    DUPLICATE_REQUEST_ID,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcError,
    error_response,
    success_response,
)
from optimus.acp.request_ids import DuplicateRequestId, RequestIdTracker


class JsonRpcDispatcher:
    def __init__(self, request_ids: RequestIdTracker | None = None) -> None:
        self._request_ids = request_ids or RequestIdTracker()

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
        if method == "optimus.ping":
            return success_response(request_id=request_id, result={"message": "pong"})

        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}"),
        )
