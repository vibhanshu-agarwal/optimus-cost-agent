import io
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayRequest, UrllibGatewayTransport, _decode_gateway_json
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError


# Test double for GatewayTransport: records requests and returns canned JSON without I/O.
class FakeTransport:
    def __init__(self, response: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.response = response or {
            "id": "resp-1",
            "output_text": "ok",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "cache_hit": False,
                "billing_units": 7,
                "cost_usd": "0.0007",
            },
        }
        self.error = error
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def settings() -> OptimusGatewaySettings:
    return OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
    )


def test_create_response_posts_to_responses_endpoint_with_auth_and_json_headers():
    transport = FakeTransport()
    client = GatewayClient(settings=settings(), transport=transport)

    response = client.create_response(model="glm-5.2", input_text="hello", metadata={"run_id": "run-1"})

    assert response.output_text == "ok"
    assert response.gateway_usage.cost_usd == Decimal("0.0007")
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == "https://gateway.optimus.ai/v1/responses"
    assert request.headers == {
        "Authorization": "Bearer opt_live_abc",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert request.payload == {"model": "glm-5.2", "input": "hello", "metadata": {"run_id": "run-1"}}
    assert "messages" not in request.payload


def test_create_response_validates_trusted_gateway_before_transport_call():
    transport = FakeTransport()
    client = GatewayClient(
        settings=OptimusGatewaySettings(
            gateway_url="https://rogue.attacker.com",
            optimus_api_key="opt_live_abc",
        ),
        transport=transport,
    )

    with pytest.raises(ValueError, match="gateway origin not in trusted set"):
        client.create_response(model="glm-5.2", input_text="hello")

    assert transport.requests == []


def test_transport_http_error_is_typed():
    transport = FakeTransport(error=GatewayHttpError(503, "gateway unavailable"))
    client = GatewayClient(settings=settings(), transport=transport)

    with pytest.raises(GatewayHttpError) as exc_info:
        client.create_response(model="glm-5.2", input_text="hello")

    assert exc_info.value.status_code == 503


def test_malformed_gateway_response_is_typed():
    transport = FakeTransport(response={"id": "resp-1", "output_text": "ok"})
    client = GatewayClient(settings=settings(), transport=transport)

    with pytest.raises(GatewayResponseError, match="gateway_usage missing"):
        client.create_response(model="glm-5.2", input_text="hello")


def test_urllib_transport_serializes_json_without_secret_leak_in_repr():
    request = GatewayRequest(
        method="POST",
        url="https://gateway.optimus.ai/v1/responses",
        headers={"Authorization": "Bearer opt_live_abc", "Content-Type": "application/json"},
        payload={"model": "glm-5.2", "input": "hello"},
        timeout_seconds=10.0,
    )

    assert "opt_live_abc" not in repr(request)
    assert json.loads(request.body_bytes().decode("utf-8")) == {"model": "glm-5.2", "input": "hello"}
    assert isinstance(UrllibGatewayTransport(), UrllibGatewayTransport)


def test_decode_gateway_json_preserves_numeric_cost_as_decimal():
    decoded = _decode_gateway_json(
        '{"id":"resp-1","output_text":"ok","gateway_usage":'
        '{"gateway_request_id":"gw-1","provider":"glm","cache_hit":false,'
        '"billing_units":7,"cost_usd":0.0042}}'
    )

    assert decoded["gateway_usage"]["cost_usd"] == Decimal("0.0042")


class FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_urllib_transport_posts_json_and_decodes_decimal_cost(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeHttpResponse(
            b'{"id":"resp-1","output_text":"ok","gateway_usage":'
            b'{"gateway_request_id":"gw-1","provider":"glm","cache_hit":false,'
            b'"billing_units":7,"cost_usd":0.0042}}'
        )

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)
    request = GatewayRequest(
        method="POST",
        url="https://gateway.optimus.ai/v1/responses",
        headers={"Authorization": "Bearer opt_live_abc", "Content-Type": "application/json"},
        payload={"model": "glm-5.2", "input": "hello"},
        timeout_seconds=3.5,
    )

    decoded = UrllibGatewayTransport().post_json(request)

    assert captured["timeout"] == 3.5
    assert decoded["gateway_usage"]["cost_usd"] == Decimal("0.0042")


def test_urllib_transport_maps_http_error_to_gateway_http_error(monkeypatch):
    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        raise HTTPError(
            url="https://gateway.optimus.ai/v1/responses",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(b"gateway down"),
        )

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError) as exc_info:
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )

    assert exc_info.value.status_code == 503
    assert str(exc_info.value) == "gateway down"


def test_urllib_transport_maps_url_error_to_gateway_http_error(monkeypatch):
    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        raise URLError("connection refused")

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError) as exc_info:
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )

    assert exc_info.value.status_code == 0
    assert "connection refused" in str(exc_info.value)


@pytest.mark.parametrize(
    "body, message",
    [
        (b"not-json", "gateway returned invalid JSON"),
        (b'["not", "object"]', "gateway returned non-object JSON"),
    ],
)
def test_urllib_transport_rejects_malformed_json_response(monkeypatch, body, message):
    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        return FakeHttpResponse(body)

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError, match=message):
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )


def test_post_tool_json_posts_to_gateway_tool_endpoint():
    transport = FakeTransport(response={"ok": True})
    client = GatewayClient(settings=settings(), transport=transport)

    response = client.post_tool_json(
        path="/v1/tools/web/search",
        payload={"query": "latest pytest release"},
    )

    assert response == {"ok": True}
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == "https://gateway.optimus.ai/v1/tools/web/search"
    assert request.headers == {
        "Authorization": "Bearer opt_live_abc",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert request.payload == {"query": "latest pytest release"}


def test_post_tool_json_validates_trusted_gateway_before_transport():
    transport = FakeTransport()
    client = GatewayClient(
        settings=OptimusGatewaySettings(
            gateway_url="https://rogue.attacker.com",
            optimus_api_key="opt_live_abc",
        ),
        transport=transport,
    )

    with pytest.raises(ValueError, match="gateway origin not in trusted set"):
        client.post_tool_json(path="/v1/tools/web/search", payload={"query": "current fact"})

    assert transport.requests == []


def test_post_tool_json_rejects_non_tool_path():
    client = GatewayClient(settings=settings(), transport=FakeTransport())

    with pytest.raises(ValueError, match="tool path must start with /v1/tools/"):
        client.post_tool_json(path="/v1/responses", payload={})


# --- Plan 9.95 Task 1 Step 3: transport tests for reported and unknown HTTP-error cost ---


def test_urllib_http_error_with_valid_gateway_usage_attaches_usage(monkeypatch):
    """HTTP 503 with a valid gateway_usage in the error body attaches usage to the error."""
    error_body = json.dumps(
        {
            "error": "temporary overload",
            "gateway_usage": {
                "gateway_request_id": "gw-err-1",
                "provider": "glm",
                "cache_hit": False,
                "billing_units": 5,
                "cost_usd": "0.0005",
            },
        }
    ).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        raise HTTPError(
            url="https://gateway.optimus.ai/v1/responses",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(error_body),
        )

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError) as exc_info:
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Authorization": "Bearer opt_live_secret", "Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.gateway_usage is not None
    assert exc_info.value.gateway_usage.gateway_request_id == "gw-err-1"
    assert exc_info.value.gateway_usage.cost_usd == Decimal("0.0005")
    assert "opt_live_secret" not in str(exc_info.value)


def test_urllib_http_error_without_gateway_usage_has_unknown_cost(monkeypatch):
    """HTTP 503 with no gateway_usage in the error body has gateway_usage=None."""
    error_body = json.dumps({"error": "temporary outage"}).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        raise HTTPError(
            url="https://gateway.optimus.ai/v1/responses",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(error_body),
        )

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError) as exc_info:
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Authorization": "Bearer opt_live_secret", "Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.gateway_usage is None
    assert "opt_live_secret" not in str(exc_info.value)


def test_urllib_http_error_with_malformed_gateway_usage_has_unknown_cost(monkeypatch):
    """HTTP 503 with invalid gateway_usage (empty request ID) has gateway_usage=None."""
    error_body = json.dumps(
        {
            "error": "bad request",
            "gateway_usage": {
                "gateway_request_id": "",
                "provider": "glm",
                "cache_hit": False,
                "billing_units": 5,
                "cost_usd": "0.0005",
            },
        }
    ).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        raise HTTPError(
            url="https://gateway.optimus.ai/v1/responses",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(error_body),
        )

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError) as exc_info:
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Authorization": "Bearer opt_live_secret", "Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.gateway_usage is None
    assert "opt_live_secret" not in str(exc_info.value)


def test_urllib_url_error_has_unknown_cost(monkeypatch):
    """URLError (network failure) results in gateway_usage=None."""

    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        raise URLError("connection refused")

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError) as exc_info:
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Authorization": "Bearer opt_live_secret", "Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )

    assert exc_info.value.status_code == 0
    assert exc_info.value.gateway_usage is None
    assert "opt_live_secret" not in str(exc_info.value)
