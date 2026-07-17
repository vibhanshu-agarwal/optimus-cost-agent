from optimus.acp import errors
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


def test_error_response_sanitizes_message_and_nested_data_and_drops_data_on_failure(monkeypatch):
    error = JsonRpcError(
        code=INVALID_REQUEST,
        message="OPTIMUS_API_KEY=top-secret-canary",
        data={"nested": {"bearer": "Bearer top-secret-canary"}},
    )

    response = error_response(request_id="abc", error=error)
    assert "top-secret-canary" not in str(response)
    assert response["error"]["code"] == INVALID_REQUEST
    assert response["error"]["message"]

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError()))
    failed_response = error_response(request_id="abc", error=error)
    assert failed_response["error"]["message"] == "internal error"
    assert "data" not in failed_response["error"]


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
