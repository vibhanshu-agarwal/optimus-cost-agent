from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import DUPLICATE_REQUEST_ID, METHOD_NOT_FOUND


def test_dispatcher_handles_ping():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": 1, "method": "optimus.ping"})

    assert response == {"jsonrpc": "2.0", "id": 1, "result": {"message": "pong"}}


def test_dispatcher_rejects_unknown_method():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": 2, "method": "unknown"})

    assert response["id"] == 2
    assert response["error"]["code"] == METHOD_NOT_FOUND


def test_dispatcher_rejects_duplicate_id():
    dispatcher = JsonRpcDispatcher()
    dispatcher.dispatch({"jsonrpc": "2.0", "id": "x", "method": "optimus.ping"})

    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": "x", "method": "optimus.ping"})

    assert response["id"] == "x"
    assert response["error"]["code"] == DUPLICATE_REQUEST_ID
