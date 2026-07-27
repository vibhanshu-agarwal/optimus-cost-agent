from __future__ import annotations

import threading

import pytest
import redis

from optimus_gateway.models import ToolClass
from optimus_gateway.tool_state import (
    GatewayToolCallCapExceeded,
    GatewayToolStateUnavailable,
    InMemoryGatewayToolStateStore,
    RedisGatewayToolStateStore,
)


class _FailingRedisClient:
    """Minimal double whose every call raises a connection error, proving fail-closed behavior."""

    def sadd(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("redis down")

    def smembers(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("redis down")

    def incr(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("redis down")

    def expire(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("redis down")

    def decr(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("redis down")

    def ping(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("redis down")


# --- InMemoryGatewayToolStateStore (unit-only dependency double) ------------


def test_in_memory_store_records_and_returns_search_result_urls():
    store = InMemoryGatewayToolStateStore()

    search_id = store.record_search(run_id="run-1", source_urls=("https://python.org/a", "https://python.org/b"))

    assert search_id
    assert store.search_result_urls(run_id="run-1") == frozenset({"https://python.org/a", "https://python.org/b"})


def test_in_memory_store_accumulates_multiple_searches_for_same_run():
    store = InMemoryGatewayToolStateStore()

    store.record_search(run_id="run-1", source_urls=("https://python.org/a",))
    store.record_search(run_id="run-1", source_urls=("https://python.org/b",))

    assert store.search_result_urls(run_id="run-1") == frozenset({"https://python.org/a", "https://python.org/b"})


def test_in_memory_store_rejects_cross_run_provenance_lookup():
    store = InMemoryGatewayToolStateStore()
    store.record_search(run_id="run-1", source_urls=("https://python.org/a",))

    assert store.search_result_urls(run_id="run-2") == frozenset()
    assert store.search_result_urls(run_id="run-1") == frozenset({"https://python.org/a"})


def test_in_memory_store_returns_empty_set_for_unknown_run():
    store = InMemoryGatewayToolStateStore()

    assert store.search_result_urls(run_id="never-searched") == frozenset()


def test_in_memory_store_increments_call_counter_per_run_and_tool_class():
    store = InMemoryGatewayToolStateStore()

    assert store.increment_call(run_id="run-1", tool_class=ToolClass.WEB_SEARCH, max_calls=3) == 1
    assert store.increment_call(run_id="run-1", tool_class=ToolClass.WEB_SEARCH, max_calls=3) == 2
    # a different tool_class under the same run_id has its own independent counter.
    assert store.increment_call(run_id="run-1", tool_class=ToolClass.WEB_EXTRACT, max_calls=3) == 1
    # a different run_id has its own independent counter too.
    assert store.increment_call(run_id="run-2", tool_class=ToolClass.WEB_SEARCH, max_calls=3) == 1


def test_in_memory_store_rejects_call_after_cap_reached():
    store = InMemoryGatewayToolStateStore()
    store.increment_call(run_id="run-1", tool_class=ToolClass.WEB_SEARCH, max_calls=2)
    store.increment_call(run_id="run-1", tool_class=ToolClass.WEB_SEARCH, max_calls=2)

    with pytest.raises(GatewayToolCallCapExceeded):
        store.increment_call(run_id="run-1", tool_class=ToolClass.WEB_SEARCH, max_calls=2)

    # a rejected call must not have silently advanced the counter past the cap.
    with pytest.raises(GatewayToolCallCapExceeded):
        store.increment_call(run_id="run-1", tool_class=ToolClass.WEB_SEARCH, max_calls=2)


def test_in_memory_store_call_counter_is_atomic_under_concurrency():
    store = InMemoryGatewayToolStateStore()
    max_calls = 20
    successes: list[int] = []
    failures: list[Exception] = []
    lock = threading.Lock()

    def _call() -> None:
        try:
            count = store.increment_call(run_id="run-1", tool_class=ToolClass.WEB_SEARCH, max_calls=max_calls)
            with lock:
                successes.append(count)
        except GatewayToolCallCapExceeded as exc:
            with lock:
                failures.append(exc)

    threads = [threading.Thread(target=_call) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(successes) == max_calls
    assert len(failures) == 50 - max_calls
    assert sorted(successes) == list(range(1, max_calls + 1))


# --- RedisGatewayToolStateStore: fail-closed behavior (unit tier: fake client double) ---


def test_redis_store_fails_closed_on_search_recording_when_client_unavailable():
    store = RedisGatewayToolStateStore(client=_FailingRedisClient())

    with pytest.raises(GatewayToolStateUnavailable):
        store.record_search(run_id="run-1", source_urls=("https://python.org/a",))


def test_redis_store_fails_closed_on_provenance_lookup_when_client_unavailable():
    store = RedisGatewayToolStateStore(client=_FailingRedisClient())

    with pytest.raises(GatewayToolStateUnavailable):
        store.search_result_urls(run_id="run-1")


def test_redis_store_fails_closed_on_call_increment_when_client_unavailable():
    store = RedisGatewayToolStateStore(client=_FailingRedisClient())

    with pytest.raises(GatewayToolStateUnavailable):
        store.increment_call(run_id="run-1", tool_class=ToolClass.WEB_SEARCH, max_calls=3)


def test_redis_store_fails_closed_on_ping_when_client_unavailable():
    store = RedisGatewayToolStateStore(client=_FailingRedisClient())

    with pytest.raises(GatewayToolStateUnavailable):
        store.ping()


def test_redis_store_never_falls_back_to_in_memory_state_on_unavailability():
    store = RedisGatewayToolStateStore(client=_FailingRedisClient())

    with pytest.raises(GatewayToolStateUnavailable):
        store.record_search(run_id="run-1", source_urls=("https://python.org/a",))

    # The Redis-backed store carries no in-memory shadow state to silently
    # fall back to when the configured backend is unavailable.
    assert not hasattr(store, "_search_results")
    assert not hasattr(store, "_call_counts")


def test_redis_store_from_url_builds_a_direct_client_without_agent_side_wrapper():
    store = RedisGatewayToolStateStore.from_url("redis://localhost:6399/0")

    assert isinstance(store, RedisGatewayToolStateStore)
    assert isinstance(store.redis_client, redis.Redis)
