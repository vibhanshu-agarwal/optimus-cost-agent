"""#671 (Codex round 2, High): a tool Redis URL whose query redis-py cannot parse never reaches the Gateway's startup
traceback (its stderr, kept in the ACP Gateway log) with the value. No Redis is contacted; synthetic values only."""

from __future__ import annotations

import traceback

import pytest

from optimus_gateway.providers import build_tool_dependencies
from optimus_gateway.tool_state import RedisGatewayToolStateStore
from tests.unit.optimus_gateway.test_providers import _openrouter_config

_PW = "synthpw" + "r" * 14  # synthetic
URLS = {
    "verify-flag": "redis://127.0.0.1:6379/0?ssl_include_verify_flags=" + _PW,
    "bad-int": "redis://127.0.0.1:6379/0?socket_timeout=" + _PW,
}


@pytest.mark.parametrize("url", URLS.values(), ids=URLS.keys())
def test_gateway_startup_refuses_an_unparseable_tool_redis_url_without_its_value(url: str) -> None:
    with pytest.raises(ValueError) as caught:
        build_tool_dependencies(_openrouter_config(tool_redis_url=url, tool_allowed_domains=("example.com",)))
    printed = "".join(traceback.format_exception(caught.value))  # what Gateway startup prints
    assert _PW not in printed, printed
    assert "OPTIMUS_GATEWAY_TOOL_REDIS_URL" in str(caught.value)


def test_a_usable_tool_redis_url_still_builds_without_connecting() -> None:
    store = RedisGatewayToolStateStore.from_url("redis:///0?socket_timeout=3")
    assert isinstance(store, RedisGatewayToolStateStore)
