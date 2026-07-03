from decimal import Decimal

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayRequest


class CapturingGatewayTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        return {
            "id": "resp-plan-1",
            "output_text": "Plan-mode advisory response.",
            "gateway_usage": {
                "gateway_request_id": "gw-plan-1",
                "provider": "glm",
                "provider_request_id": "provider-plan-1",
                "cache_hit": False,
                "billing_units": 31,
                "cost_usd": "0.0031",
            },
        }


def test_mocked_full_gateway_run_uses_only_optimus_credentials(monkeypatch):
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt_live_test")
    for key in [
        "ANTHROPIC_API_KEY",
        "GLM_API_KEY",
        "LANGSMITH_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "TAVILY_API_KEY",
        "ZHIPUAI_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = OptimusGatewaySettings.from_env()
    assert settings.validate_no_local_provider_keys() == ()

    transport = CapturingGatewayTransport()
    dispatcher = JsonRpcDispatcher(
        gateway_client=GatewayClient(settings=settings, transport=transport)
    )

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "plan-call-1",
            "method": "optimus.gateway.responses",
            "params": {
                "model": "glm-5.2",
                "input": "Create an advisory plan.",
                "metadata": {"run_id": "run-1", "session_id": "session-1"},
            },
        }
    )

    assert "error" not in response
    assert response["result"]["output_text"] == "Plan-mode advisory response."
    assert response["result"]["gateway_usage"]["cost_usd"] == str(Decimal("0.0031"))
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.url == "https://gateway.optimus.ai/v1/responses"
    assert request.headers["Authorization"] == "Bearer opt_live_test"
    assert request.payload["input"] == "Create an advisory plan."
    assert "messages" not in request.payload
