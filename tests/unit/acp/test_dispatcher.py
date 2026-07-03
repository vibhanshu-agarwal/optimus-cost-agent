from decimal import Decimal

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import DUPLICATE_REQUEST_ID, METHOD_NOT_FOUND, MUTATION_FORBIDDEN
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


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


def test_dispatcher_maps_forbidden_runtime_mutation_to_32002():
    dispatcher = JsonRpcDispatcher(
        runtime_context=RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )
    )

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "write-1",
            "method": "optimus.mutation.writeFile",
            "params": {"path": "blocked.txt", "content": "blocked"},
        }
    )

    assert response["id"] == "write-1"
    assert response["error"]["code"] == MUTATION_FORBIDDEN
    assert response["error"]["message"] == "mutation forbidden in Plan/Chat mode"


class FakeGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, object] | None = None) -> GatewayResponse:
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        return GatewayResponse(
            response_id="resp-1",
            output_text="planned",
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                cache_hit=False,
                billing_units=12,
                cost_usd=Decimal("0.0012"),
            ),
            raw={"id": "resp-1"},
        )


def test_dispatcher_routes_gateway_responses_method_to_gateway_client():
    gateway_client = FakeGatewayClient()
    dispatcher = JsonRpcDispatcher(gateway_client=gateway_client)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "gw-call-1",
            "method": "optimus.gateway.responses",
            "params": {
                "model": "glm-5.2",
                "input": "Write a plan.",
                "metadata": {"run_id": "run-1"},
            },
        }
    )

    assert response["id"] == "gw-call-1"
    assert response["result"] == {
        "response_id": "resp-1",
        "output_text": "planned",
        "gateway_usage": {
            "gateway_request_id": "gw-1",
            "provider": "glm",
            "provider_request_id": None,
            "cache_hit": False,
            "billing_units": 12,
            "cost_usd": "0.0012",
        },
    }
    assert gateway_client.calls == [
        {"model": "glm-5.2", "input_text": "Write a plan.", "metadata": {"run_id": "run-1"}}
    ]


def test_gateway_responses_are_allowed_in_plan_chat_mode_by_design():
    gateway_client = FakeGatewayClient()
    dispatcher = JsonRpcDispatcher(
        gateway_client=gateway_client,
        runtime_context=RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        ),
    )

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "gw-plan-chat-1",
            "method": "optimus.gateway.responses",
            "params": {"model": "glm-5.2", "input": "Draft an advisory answer."},
        }
    )

    assert "error" not in response
    assert response["result"]["output_text"] == "planned"
    assert gateway_client.calls == [
        {"model": "glm-5.2", "input_text": "Draft an advisory answer.", "metadata": None}
    ]


def test_dispatcher_rejects_gateway_responses_messages_shape():
    dispatcher = JsonRpcDispatcher(gateway_client=FakeGatewayClient())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "gw-call-2",
            "method": "optimus.gateway.responses",
            "params": {"model": "glm-5.2", "messages": [{"role": "user", "content": "wrong"}]},
        }
    )

    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "invalid request"
