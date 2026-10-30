"""Health observation includes owner lock, scheduling and operation completion."""

import asyncio
import threading
import time
from unittest.mock import create_autospec

import pytest

from optimus.redis.async_bridge import RedisLoopOwner
from optimus.redis.runtime import CloseablePool, RedisRuntime, RuntimeClient


@pytest.fixture
def runtime():
    owner = RedisLoopOwner()
    value = RedisRuntime(owner=owner, pool=create_autospec(CloseablePool, instance=True), client=create_autospec(RuntimeClient, instance=True))
    async def closed():
        return None
    value.pool.aclose.side_effect = closed
    value.client.aclose.side_effect = closed
    value.client.ping.side_effect = closed
    try:
        yield value
    finally:
        value.close()


def test_health_deadline_includes_owner_admission_lock(runtime):
    from optimus.redis.runtime import RedisHealthDeadlineExceeded

    runtime.owner._state_lock.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(RedisHealthDeadlineExceeded):
            runtime.ping(timeout=0.02)
        assert time.monotonic() - started < 0.5
        runtime.client.ping.assert_not_called()
    finally:
        runtime.owner._state_lock.release()


def test_health_deadline_includes_runtime_guard_lock(runtime):
    from optimus.redis.runtime import RedisHealthDeadlineExceeded
    runtime.lifecycle._lock.acquire()
    try:
        with pytest.raises(RedisHealthDeadlineExceeded):
            runtime.ping(timeout=0.02)
        runtime.client.ping.assert_not_called()
    finally:
        runtime.lifecycle._lock.release()


def test_expired_scheduled_health_never_enters_factory(runtime):
    from optimus.redis.runtime import RedisHealthDeadlineExceeded

    entered, release = threading.Event(), threading.Event()
    def hold():
        entered.set()
        release.wait(2)
    runtime.owner._loop.call_soon_threadsafe(hold)
    assert entered.wait(2)
    try:
        with pytest.raises(RedisHealthDeadlineExceeded):
            runtime.ping(timeout=0.02)
        assert len(runtime.owner._live) == 1
    finally:
        release.set()
    runtime.owner.run_sync(lambda: asyncio.sleep(0))
    runtime.client.ping.assert_not_called()


def test_operation_timeout_is_not_observation_expiry(runtime):
    failure = TimeoutError("operation timeout")
    runtime.client.ping.side_effect = failure
    with pytest.raises(ConnectionError) as caught:
        runtime.ping(timeout=1)
    assert type(caught.value) is ConnectionError
    assert caught.value.__cause__ is failure


def test_completed_health_observed_after_deadline_cannot_pass(runtime, monkeypatch):
    from optimus.redis.runtime import RedisHealthDeadlineExceeded
    submit = runtime.owner.submit
    def delayed_observation(*args, **kwargs):
        handle = submit(*args, **kwargs)
        handle.future.result(1)
        time.sleep(0.04)
        return handle
    monkeypatch.setattr(runtime.owner, "submit", delayed_observation)
    with pytest.raises(RedisHealthDeadlineExceeded):
        runtime.ping(timeout=0.02)


@pytest.mark.parametrize("late_failure", [False, True])
def test_health_retains_cancel_resistant_operation(runtime, late_failure, monkeypatch):
    from optimus.redis.runtime import RedisHealthDeadlineExceeded

    release = threading.Event()
    cancelled = threading.Event()
    async def ping():
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.set()
        while not release.is_set():
            await asyncio.sleep(0.001)
        if late_failure:
            raise ValueError("late failure")
    runtime.client.ping.side_effect = ping
    try:
        with pytest.raises(RedisHealthDeadlineExceeded):
            runtime.ping(timeout=0.02)
        assert cancelled.wait(2)
        assert len(runtime.owner._live) == 1
        operation = next(iter(runtime.owner._live))
        retrieved = threading.Event()
        exception = operation.future.exception
        def observe_exception(*args, **kwargs):
            result = exception(*args, **kwargs)
            retrieved.set()
            return result
        monkeypatch.setattr(operation.future, "exception", observe_exception)
        release.set()
        assert retrieved.wait(2)
        deadline = time.monotonic() + 2
        while runtime.owner._live and time.monotonic() < deadline:
            time.sleep(0.001)
        assert not runtime.owner._live
    finally:
        release.set()
