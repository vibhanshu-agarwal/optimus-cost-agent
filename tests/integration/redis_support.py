from __future__ import annotations

import os
from decimal import Decimal

import pytest

from optimus.agent.state_store import RedisAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage

DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"


def redis_url() -> str:
    return os.environ.get("OPTIMUS_REDIS_URL", DEFAULT_REDIS_URL).strip() or DEFAULT_REDIS_URL


def redis_reachable(url: str | None = None) -> bool:
    target = url or redis_url()
    try:
        RedisAgentStateStore.from_url(target).ping()
    except Exception:
        return False
    return True


def skip_unless_redis(url: str | None = None) -> str:
    target = url or redis_url()
    if not redis_reachable(target):
        pytest.skip(
            f"Redis is not reachable at {target}. "
            "Start Redis (for example `docker run --rm -p 6379:6379 redis:7-alpine`) "
            "or set OPTIMUS_REDIS_URL."
        )
    return target


class FakeGatewayClient:
    def __init__(self, output_text: str = "Plan text") -> None:
        self.calls: list[dict[str, object]] = []
        self.output_text = output_text

    def create_response(self, *, model: str, input_text: str, metadata=None) -> GatewayResponse:
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        return GatewayResponse(
            response_id="resp-1",
            output_text=self.output_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                billing_units=5,
                cost_usd=Decimal("0.002"),
            ),
            raw={"id": "resp-1"},
        )
