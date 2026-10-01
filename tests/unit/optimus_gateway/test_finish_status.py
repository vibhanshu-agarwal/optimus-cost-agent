"""Plan 12.2 Task 5: the provider's true finish status reaches the host through both Gateway APIs.

Before this, ``/v1/chat/completions`` always reported ``finish_reason: "stop"`` and ``/v1/responses``
reported nothing, so a reply cut off at the output limit looked complete.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from optimus.gateway.models import parse_gateway_response
from optimus_gateway.chat_completions import handle_chat_completions_request
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import ProviderMessageResult, parse_openai_chat_completion


def _completion(**choice: object) -> dict:
    first: dict = {"index": 0, "message": {"role": "assistant", "content": "partial plan"}}
    first.update(choice)
    return {
        "id": "gen-1",
        "model": "cn/alpha",
        "choices": [first],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": "0.0001"},
    }


@pytest.mark.parametrize(("raw", "parsed"), [("stop", "stop"), ("length", "length"), ("LENGTH", "length"), (None, None)])
def test_the_upstream_parser_keeps_the_finish_reason(raw, parsed) -> None:
    body = _completion(finish_reason=raw) if raw is not None else _completion()
    assert parse_openai_chat_completion(body, {}, requested_model="cn/alpha").finish_reason == parsed


@pytest.mark.parametrize("bad", [7, "", ["length"]])
def test_a_malformed_finish_reason_is_rejected(bad) -> None:
    with pytest.raises(RuntimeError, match="finish reason"):
        parse_openai_chat_completion(_completion(finish_reason=bad), {}, requested_model="cn/alpha")


class _Upstream:
    def __init__(self, finish_reason: str | None) -> None:
        self._finish_reason = finish_reason

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        return ProviderMessageResult(
            message_id="gen-1",
            output_text="partial plan",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            billing_units=15,
            cost_usd=Decimal("0.0001"),
            provider="openrouter",
            resolved_provider="Alpha",
            requested_model=model,
            resolved_model=model,
            model_version=None,
            cache_hit=False,
            finish_reason=self._finish_reason,
        )


def _config() -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        shared_secret="local-shared-secret",  # pragma: allowlist secret - synthetic test fixture
        provider="openrouter",
        provider_api_key="or-test",  # pragma: allowlist secret - synthetic test fixture
        base_url="https://openrouter.ai/api/v1",
    )


@pytest.mark.parametrize("finish_reason", ["stop", "length", None])
def test_both_gateway_apis_report_the_true_finish_reason(finish_reason) -> None:
    status, responses_body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "cn/alpha", "input": "plan"},
        config=_config(),
        upstream_client=_Upstream(finish_reason),
    )
    assert status == 200
    assert responses_body["finish_reason"] == finish_reason
    assert parse_gateway_response(responses_body).finish_reason == finish_reason

    status, chat_body = handle_chat_completions_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "cn/alpha", "messages": [{"role": "user", "content": "plan"}]},
        config=_config(),
        upstream_client=_Upstream(finish_reason),
    )
    assert status == 200
    assert chat_body["choices"][0]["finish_reason"] == finish_reason, "no longer hard-coded to stop"


def test_the_host_parser_rejects_a_malformed_finish_reason() -> None:
    from optimus.gateway.errors import GatewayResponseError

    body = {
        "id": "resp-1",
        "output_text": "x",
        "finish_reason": 3,
        "gateway_usage": {"gateway_request_id": "gw-1", "provider": "openrouter", "billing_units": 1, "cost_usd": "0.1"},
    }
    with pytest.raises(GatewayResponseError, match="finish_reason"):
        parse_gateway_response(body)
