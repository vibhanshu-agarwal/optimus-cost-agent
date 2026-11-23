"""Every Redis health check classifies the same client failure the same way (#346)."""

import asyncio
from unittest.mock import create_autospec

import pytest
import redis.exceptions

from optimus.agent.state_store import AsyncRedisAgentStateStore, RedisAgentStateStore
from optimus.redis.async_bridge import RedisLoopOwner
from optimus.redis.runtime import CloseablePool, RedisRuntime, RuntimeClient


class _SyncClient:
    def __init__(self, failure: BaseException) -> None:
        self.failure = failure

    def ping(self) -> None:
        raise self.failure


class _AsyncClient(_SyncClient):
    async def ping(self) -> None:  # type: ignore[override]
        raise self.failure


def _ping_sync_store(failure: BaseException) -> None:
    RedisAgentStateStore(client=_SyncClient(failure)).ping()


def _ping_async_store(failure: BaseException) -> None:
    asyncio.run(AsyncRedisAgentStateStore(client=_AsyncClient(failure)).ping())


def _ping_runtime(failure: BaseException) -> None:
    runtime = RedisRuntime(
        owner=RedisLoopOwner(),
        pool=create_autospec(CloseablePool, instance=True),
        client=create_autospec(RuntimeClient, instance=True),
    )

    async def closed() -> None:
        return None

    async def fail() -> None:
        raise failure

    runtime.pool.aclose.side_effect = closed
    runtime.client.aclose.side_effect = closed
    runtime.client.ping.side_effect = fail
    try:
        runtime.ping(timeout=2)
    finally:
        runtime.close()


SITES = [_ping_sync_store, _ping_async_store, _ping_runtime]

NORMALIZED = [
    OSError("socket closed"),
    TimeoutError("operation timeout"),
    redis.exceptions.ConnectionError("redis refused"),
    redis.exceptions.TimeoutError("redis timed out"),
]

PROPAGATED = [
    ConnectionError("already builtin"),
    ValueError("not a connection failure"),
    redis.exceptions.ResponseError("WRONGTYPE"),
]


@pytest.mark.parametrize("site", SITES, ids=lambda site: site.__name__)
@pytest.mark.parametrize("failure", NORMALIZED, ids=repr)
def test_connection_failures_become_builtin_connection_error(site, failure):
    with pytest.raises(ConnectionError) as caught:
        site(failure)
    assert type(caught.value) is ConnectionError
    assert str(caught.value) == str(failure)
    assert caught.value.__cause__ is failure


@pytest.mark.parametrize("site", SITES, ids=lambda site: site.__name__)
@pytest.mark.parametrize("failure", PROPAGATED, ids=repr)
def test_other_failures_propagate_unchanged(site, failure):
    with pytest.raises(type(failure)) as caught:
        site(failure)
    assert caught.value is failure
