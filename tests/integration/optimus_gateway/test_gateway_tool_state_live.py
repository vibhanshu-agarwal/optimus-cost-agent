"""Live-Redis evidence for the Gateway-owned tool state boundary.

Plan 11.2 (``P11-FEAT-GATEWAY-TOOLS``), Task 3. Proves atomic ``run_id +
tool_class`` call-cap enforcement and bounded-TTL search-provenance behavior
against a real Redis instance, using ``RedisGatewayToolStateStore``'s own
direct ``redis>=5`` client (no agent-side Redis wrapper).
"""
from __future__ import annotations

import concurrent.futures
import os
import uuid
from collections.abc import Iterator

import pytest
import redis

from optimus_gateway.models import ToolClass
from optimus_gateway.tool_state import (
    GatewayToolCallCapExceeded,
    GatewayToolStateUnavailable,
    RedisGatewayToolStateStore,
)

pytestmark = pytest.mark.requires_redis


@pytest.fixture
def live_redis_tool_state_store() -> Iterator[tuple[RedisGatewayToolStateStore, str]]:
    redis_url = os.environ.get("OPTIMUS_REDIS_URL", "").strip()
    if not redis_url:
        pytest.fail("OPTIMUS_REDIS_URL is required for requires_redis tests")

    store = RedisGatewayToolStateStore.from_url(redis_url)
    try:
        store.ping()
    except GatewayToolStateUnavailable as exc:
        pytest.fail(f"Redis is not reachable. Start Redis or fix OPTIMUS_REDIS_URL. ({exc})")

    run_id = f"live-tool-state-{uuid.uuid4().hex}"
    try:
        yield store, run_id
    finally:
        raw_client = store.redis_client
        for key in raw_client.scan_iter(match=f"gateway:tool:*{run_id}*"):
            raw_client.delete(key)


def test_live_redis_records_and_returns_search_provenance_for_same_run(live_redis_tool_state_store):
    store, run_id = live_redis_tool_state_store

    search_id = store.record_search(run_id=run_id, source_urls=("https://python.org/a", "https://python.org/b"))

    assert search_id
    assert store.search_result_urls(run_id=run_id) == frozenset({"https://python.org/a", "https://python.org/b"})


def test_live_redis_cross_run_provenance_lookup_is_isolated(live_redis_tool_state_store):
    store, run_id = live_redis_tool_state_store
    other_run_id = f"{run_id}-other"

    store.record_search(run_id=run_id, source_urls=("https://python.org/a",))

    try:
        assert store.search_result_urls(run_id=other_run_id) == frozenset()
        assert store.search_result_urls(run_id=run_id) == frozenset({"https://python.org/a"})
    finally:
        store.redis_client.delete(f"gateway:tool:search:{other_run_id}")


def test_live_redis_search_provenance_key_has_bounded_ttl(live_redis_tool_state_store):
    store, run_id = live_redis_tool_state_store

    store.record_search(run_id=run_id, source_urls=("https://python.org/a",))

    ttl = store.redis_client.ttl(f"gateway:tool:search:{run_id}")
    assert 0 < ttl <= 3600


def test_live_redis_call_cap_increment_is_atomic_across_concurrent_clients(live_redis_tool_state_store):
    store, run_id = live_redis_tool_state_store
    max_calls = 5

    def _call(_: int) -> int | None:
        try:
            return store.increment_call(run_id=run_id, tool_class=ToolClass.WEB_SEARCH, max_calls=max_calls)
        except GatewayToolCallCapExceeded:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(_call, range(20)))

    successes = sorted(value for value in results if value is not None)
    assert successes == list(range(1, max_calls + 1))
    assert results.count(None) == 20 - max_calls

    with pytest.raises(GatewayToolCallCapExceeded):
        store.increment_call(run_id=run_id, tool_class=ToolClass.WEB_SEARCH, max_calls=max_calls)


def test_live_redis_call_cap_counters_are_isolated_per_run_and_tool_class(live_redis_tool_state_store):
    store, run_id = live_redis_tool_state_store
    other_run_id = f"{run_id}-other"

    try:
        assert store.increment_call(run_id=run_id, tool_class=ToolClass.WEB_SEARCH, max_calls=2) == 1
        assert store.increment_call(run_id=run_id, tool_class=ToolClass.WEB_EXTRACT, max_calls=2) == 1
        assert store.increment_call(run_id=other_run_id, tool_class=ToolClass.WEB_SEARCH, max_calls=2) == 1
    finally:
        store.redis_client.delete(f"gateway:tool:callcap:{other_run_id}:{ToolClass.WEB_SEARCH}")


def test_live_redis_call_cap_key_has_bounded_ttl(live_redis_tool_state_store):
    store, run_id = live_redis_tool_state_store

    store.increment_call(run_id=run_id, tool_class=ToolClass.WEB_SEARCH, max_calls=5)

    ttl = store.redis_client.ttl(f"gateway:tool:callcap:{run_id}:{ToolClass.WEB_SEARCH}")
    assert 0 < ttl <= 3600


def test_live_redis_state_store_fails_closed_when_backend_unreachable():
    unreachable_store = RedisGatewayToolStateStore.from_url(
        "redis://127.0.0.1:1/0",
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )

    with pytest.raises(GatewayToolStateUnavailable):
        unreachable_store.ping()


def test_live_redis_store_uses_direct_redis_client_not_agent_wrapper(live_redis_tool_state_store):
    store, _run_id = live_redis_tool_state_store

    assert isinstance(store.redis_client, redis.Redis)
    assert type(store.redis_client).__module__.startswith("redis")
