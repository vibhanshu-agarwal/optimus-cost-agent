from optimus.acp.errors import (
    DUPLICATE_REQUEST_ID,
    INVALID_REQUEST,
    JsonRpcError,
    error_response,
    success_response,
)


def test_success_response_uses_jsonrpc_2_and_preserves_id():
    response = success_response(request_id=7, result={"ok": True})

    assert response == {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {"ok": True},
    }


def test_error_response_uses_code_message_and_id():
    response = error_response(
        request_id="abc",
        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": "abc",
        "error": {"code": -32600, "message": "invalid request"},
    }


def test_error_response_includes_optional_data():
    response = error_response(
        request_id=None,
        error=JsonRpcError(
            code=DUPLICATE_REQUEST_ID,
            message="duplicate request id",
            data={"id": "abc"},
        ),
    )

    assert response["error"]["data"] == {"id": "abc"}
