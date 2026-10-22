from decimal import Decimal
from unittest.mock import create_autospec

import pytest
import redis
import redis.asyncio as aioredis

from optimus.agent.state_store import AgentPlanRecord, InMemoryAgentStateStore, RedisAgentStateStore, validate_redis_url
from optimus.redis.runtime import CloseablePool, RedisRuntime
from optimus.runtime.modes import ExecutionMode


def _checked_redis(script, *, asynchronous=False):
    checked = create_autospec(aioredis.Redis if asynchronous else redis.Redis, instance=True, spec_set=True)
    for name in ("hset", "hgetall", "expire", "ping", "aclose"):
        if hasattr(script, name):
            getattr(checked, name).side_effect = getattr(script, name)
    return checked


def _checked_submit(script):
    checked = create_autospec(RedisRuntime, instance=True, spec_set=True).run_sync
    checked.side_effect = script
    return checked


class FakeRedis:
    def __init__(self, ping_error: Exception | None = None) -> None:
        self.ping_error = ping_error
        self.hsets: list[tuple[str, dict[str, str]]] = []
        self.hgetalls: dict[str, dict[str, str]] = {}
        self.expires: list[tuple[str, int]] = []
        self.checked = _checked_redis(self)

    def hset(self, key: str, mapping: dict[str, str]):
        self.hsets.append((key, mapping))
        self.hgetalls[key] = mapping
        return len(mapping)

    def hgetall(self, key: str):
        return self.hgetalls.get(key, {})

    def expire(self, key: str, ttl_seconds: int):
        self.expires.append((key, ttl_seconds))
        return True

    def ping(self):
        if self.ping_error is not None:
            raise self.ping_error
        return True


def plan_record() -> AgentPlanRecord:
    return AgentPlanRecord(
        run_id="run-1",
        session_id="session-1",
        task="Add a docstring",
        execution_mode=ExecutionMode.AGENT,
        workspace_root="/repo",
        plan_hash="hash-1",
        plan_text="WRITE example.py\ncontent",
        gateway_request_id="gw-1",
        model="glm-5.2",
        provider="glm",
        cost_usd=Decimal("0.002"),
        created_at_ms=1000,
        expires_at_ms=3_601_000,
    )


def test_in_memory_store_replays_exact_plan_text():
    store = InMemoryAgentStateStore()
    record = plan_record()

    store.save_plan(record)

    loaded = store.load_plan(run_id="run-1", plan_hash="hash-1")
    assert loaded == record
    assert loaded.task == record.task
    assert loaded.workspace_root == record.workspace_root
    assert loaded.plan_text == record.plan_text


def test_in_memory_store_rejects_missing_plan_hash():
    store = InMemoryAgentStateStore()

    with pytest.raises(KeyError, match="stored plan not found"):
        store.load_plan(run_id="run-1", plan_hash="missing")


def test_validate_redis_url_rejects_passwords():
    with pytest.raises(ValueError, match="must not contain username or password"):
        validate_redis_url("redis://user:secret@localhost:6379/0")  # pragma: allowlist secret - synthetic test fixture, not a real credential


def test_validate_redis_url_accepts_redis_and_rediss_without_credentials():
    assert validate_redis_url("redis://localhost:6379/0") == "redis://localhost:6379/0"
    assert validate_redis_url("rediss://cache.example.com:6380/0") == "rediss://cache.example.com:6380/0"


def test_validate_redis_url_rejects_non_redis_schemes():
    with pytest.raises(ValueError, match="must use redis:// or rediss://"):
        validate_redis_url("http://localhost:6379/0")


def test_plan_record_schema_and_persisted_mapping_are_functional_only():
    # Plan 12.2 Task 9: the admitted context digest is functional (it binds application to the
    # context the plan was made on). A record without one persists no such field.
    record = plan_record().model_copy(update={"context_digest": "c" * 64, "cost_complete": True})

    assert set(AgentPlanRecord.model_fields) == {
        "run_id",
        "session_id",
        "task",
        "execution_mode",
        "workspace_root",
        "plan_hash",
        "plan_text",
        "gateway_request_id",
        "gateway_request_ids",
        "planning_turns",
        "model",
        "provider",
        "cost_usd",
        "created_at_ms",
        "expires_at_ms",
        "context_digest",
        "record_version",
        "cost_complete",
    }

    fake = FakeRedis()
    RedisAgentStateStore(client=fake.checked).save_plan(record)
    persisted_fields = set(fake.hsets[0][1])
    assert persisted_fields == set(AgentPlanRecord.model_fields)


def test_redis_store_writes_hash_and_ttl():
    fake = FakeRedis()
    store = RedisAgentStateStore(client=fake.checked, ttl_seconds=3600)
    record = plan_record().model_copy(
        update={
            "gateway_request_ids": ("gw-1", "gw-2"),
            "planning_turns": 2,
            "cost_usd": Decimal("0.004"),
        }
    )

    store.save_plan(record)

    assert fake.hsets[0][0] == "agent:plan:run-1:hash-1"
    assert fake.hsets[0][1]["plan_text"] == "WRITE example.py\ncontent"
    assert fake.hsets[0][1]["cost_usd"] == "0.004"
    assert fake.hsets[0][1]["planning_turns"] == "2"
    assert fake.hsets[0][1]["gateway_request_ids"] == '["gw-1", "gw-2"]'
    assert fake.expires == [("agent:plan:run-1:hash-1", 3600), ("agent:plan:run-1:latest", 3600)]


def test_redis_store_loads_plan_from_hash():
    fake = FakeRedis()
    store = RedisAgentStateStore(client=fake.checked, ttl_seconds=3600)
    record = plan_record()
    store.save_plan(record)

    assert store.load_plan(run_id="run-1", plan_hash="hash-1") == record


def test_redis_store_loads_latest_plan_for_run():
    fake = FakeRedis()
    store = RedisAgentStateStore(client=fake.checked, ttl_seconds=3600)
    record = plan_record()
    store.save_plan(record)

    assert store.latest_plan_for_run(run_id="run-1") == record


def test_redis_store_ping_fails_closed_when_redis_is_down():
    fake = FakeRedis(ping_error=ConnectionError("redis unavailable"))
    store = RedisAgentStateStore(client=fake.checked, ttl_seconds=3600)

    with pytest.raises(ConnectionError, match="redis unavailable"):
        store.ping()


def test_in_memory_store_treats_expired_plan_as_missing():
    store = InMemoryAgentStateStore(clock_ms=lambda: 3_700_000)
    store.save_plan(plan_record())

    with pytest.raises(KeyError, match="stored plan not found"):
        store.load_plan(run_id="run-1", plan_hash="hash-1")


def test_persist_plan_reports_persisted_for_in_memory():
    from optimus.agent.state_store import PlanPersistenceOutcome

    store = InMemoryAgentStateStore(clock_ms=lambda: 1_000)
    result = store.persist_plan(plan_record())
    assert result.outcome is PlanPersistenceOutcome.PERSISTED
    assert result.authorizing is True


def test_persist_plan_partial_when_pointer_write_fails():
    from optimus.agent.state_store import PlanPersistenceOutcome

    class FlakyRedis(FakeRedis):
        def hset(self, key: str, mapping: dict[str, str]):
            if "latest" in key:
                raise RuntimeError("pointer failed")
            return super().hset(key, mapping)

    store = RedisAgentStateStore(client=FlakyRedis().checked, ttl_seconds=60)
    result = store.persist_plan(plan_record())
    assert result.outcome is PlanPersistenceOutcome.PERSISTENCE_PARTIAL
    assert "primary" in result.completed_substeps
    assert result.authorizing is False


# --- Seam 2, checkpoint B: async-backed stores submit through an injected owner ---------


class FakeAsyncRedis:
    """Async fake client: records which thread each operation ran on."""

    def __init__(self) -> None:
        import threading

        self.hsets: list[tuple[str, dict[str, str]]] = []
        self.hgetalls: dict[str, dict[str, str]] = {}
        self.threads: list[int] = []
        self._threading = threading
        self.checked = _checked_redis(self, asynchronous=True)

    async def hset(self, key: str, mapping: dict[str, str]):
        self.threads.append(self._threading.get_ident())
        self.hsets.append((key, mapping))
        self.hgetalls[key] = mapping
        return len(mapping)

    async def hgetall(self, key: str):
        self.threads.append(self._threading.get_ident())
        return self.hgetalls.get(key, {})

    async def expire(self, key: str, ttl_seconds: int):
        return True

    async def ping(self):
        return True

    async def aclose(self):
        return None


class _Pool:
    def __init__(self):
        self.checked = create_autospec(CloseablePool, instance=True, spec_set=True)
        self.checked.aclose.side_effect = self.aclose

    async def aclose(self):
        return None


def _async_store(client: FakeAsyncRedis):
    from optimus.agent.state_store import AsyncRedisAgentStateStore

    return AsyncRedisAgentStateStore(client=client.checked, ttl_seconds=60)


def test_an_async_backed_store_requires_an_injected_submission_seam():
    """MUTATION: a serving store that silently falls back to the shared tool owner."""
    with pytest.raises(TypeError, match="submit"):
        RedisAgentStateStore(async_store=_async_store(FakeAsyncRedis()))


def test_an_async_backed_store_submits_every_operation_through_the_injected_seam():
    import asyncio

    client = FakeAsyncRedis()
    submissions: list[str] = []

    def submit(operation):
        submissions.append(type(operation).__name__)
        return asyncio.run(operation())

    store = RedisAgentStateStore(async_store=_async_store(client), submit=_checked_submit(submit))
    store.save_plan(plan_record())
    loaded = store.load_plan(run_id="run-1", plan_hash="hash-1")
    latest = store.latest_plan_for_run(run_id="run-1")
    store.ping()

    assert loaded.plan_hash == "hash-1"
    assert latest is not None and latest.plan_hash == "hash-1"
    assert len(submissions) == 4, submissions  # save, load, latest, ping
    assert all(name == "function" for name in submissions)


def test_a_runtime_built_store_runs_on_the_runtime_owner_loop_not_a_shared_one():
    """MUTATION: cleanup on the caller's loop -- here, operations on a second owner."""
    from optimus.redis import async_bridge
    from optimus.redis.async_bridge import RedisLoopOwner
    from optimus.redis.runtime import RedisRuntime

    client = FakeAsyncRedis()
    owner = RedisLoopOwner(name="seam2b-store-owner")
    runtime = RedisRuntime(pool=_Pool().checked, client=client.checked, owner=owner)
    try:
        store = runtime.sync_state_store()
        store.save_plan(plan_record())
        assert store.load_plan(run_id="run-1", plan_hash="hash-1").plan_hash == "hash-1"
    finally:
        record = runtime.close(timeout=5.0)
    assert set(client.threads) == {owner.thread.ident}
    assert async_bridge._shared_tool_owner is None, "a serving store reached the shared tool owner"
    assert record.owner_terminated


def test_a_late_submission_after_close_receives_a_stable_closed_error_and_reopens_nothing():
    """MUTATION: replacement owner after admission closes."""
    from optimus.redis import async_bridge
    from optimus.redis.async_bridge import RedisLoopOwner, RedisLoopOwnerClosed
    from optimus.redis.runtime import RedisRuntime

    client = FakeAsyncRedis()
    owner = RedisLoopOwner(name="seam2b-late-owner")
    runtime = RedisRuntime(pool=_Pool().checked, client=client.checked, owner=owner)
    store = runtime.sync_state_store()
    runtime.close(timeout=5.0)

    result = store.persist_plan(plan_record())
    assert result.outcome.value == "persistence_failed"
    with pytest.raises(RedisLoopOwnerClosed):
        store.load_plan(run_id="run-1", plan_hash="hash-1")
    assert runtime.owner is owner and owner.is_terminated
    assert async_bridge._shared_tool_owner is None
    assert client.threads == []


def test_the_convenience_factory_retains_the_runtime_it_builds(monkeypatch):
    """The discarded convenience-factory handle was a real custody gap (architecture v2)."""
    from optimus.redis.async_bridge import RedisLoopOwner
    from optimus.redis.runtime import RedisRuntime

    client = FakeAsyncRedis()
    built: list[RedisRuntime] = []

    def fake_from_url(url, *, ttl_seconds):
        runtime = RedisRuntime(
            pool=_Pool().checked, client=client.checked, owner=RedisLoopOwner(name="seam2b-factory"), ttl_seconds=ttl_seconds
        )
        built.append(runtime)
        return runtime

    monkeypatch.setattr(RedisRuntime, "from_url", create_autospec(RedisRuntime.from_url, side_effect=fake_from_url))
    store = RedisAgentStateStore.from_url("redis://127.0.0.1:6379/0", ttl_seconds=60)
    assert store.owned_runtime is built[0]
    store.save_plan(plan_record())
    keys = store.submit(lambda: _collect_keys(client))
    assert keys == {"agent:plan:run-1:hash-1", "agent:plan:run-1:latest"}
    record = store.close(timeout=5.0)
    assert record.owner_terminated
    assert built[0].state.value == "CLOSED"


async def _collect_keys(client: FakeAsyncRedis) -> set[str]:
    return set(client.hgetalls)


def test_a_store_that_owns_no_runtime_cannot_be_closed():
    store = RedisAgentStateStore(client=FakeRedis().checked)
    assert store.owned_runtime is None
    with pytest.raises(RuntimeError, match="owns no runtime"):
        store.close()


@pytest.mark.parametrize("operation", ["save", "load", "latest", "ping"])
def test_typing_missing_client_has_explicit_refusal(operation):
    store = RedisAgentStateStore()
    with pytest.raises(RuntimeError, match="^redis client is not configured$"):
        if operation == "save":
            store.save_plan(plan_record())
        elif operation == "load":
            store.load_plan(run_id="run-1", plan_hash="hash-1")
        elif operation == "latest":
            store.latest_plan_for_run(run_id="run-1")
        else:
            store.ping()


def test_typing_missing_client_persistence_stays_failed_result():
    result = RedisAgentStateStore().persist_plan(plan_record())
    assert result.outcome.value == "persistence_failed"
    assert result.completed_substeps == ()


def test_typing_async_client_requires_async_store_without_submission():
    from optimus.agent.state_store import AsyncRedisAgentStateStore

    with pytest.raises(RuntimeError, match="^this store has no owner submission seam; it wraps a synchronous client$"):
        _ = RedisAgentStateStore(client=FakeRedis().checked).async_redis_client
    client = object()

    def never_submit(_operation):
        pytest.fail("client lookup must not submit work")

    store = RedisAgentStateStore(async_store=AsyncRedisAgentStateStore(client=client), submit=never_submit)
    assert store.async_redis_client is client


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("legacy", [False, True], ids=["keyword", "legacy-positional"])
def test_hset_compatibility_preserves_call_order(asynchronous, legacy):
    import asyncio

    from optimus.agent.state_store import _async_hset, _sync_hset

    calls = []
    mapping = {"plan_hash": "bound-hash"}

    def invoke(*args, **kwargs):
        calls.append((args, kwargs))
        if kwargs and legacy:
            raise TypeError("legacy fake accepts positional mapping only")
        return 7

    async def async_invoke(*args, **kwargs):
        return invoke(*args, **kwargs)

    client = create_autospec(aioredis.Redis if asynchronous else redis.Redis, instance=True, spec_set=True)
    client.hset.side_effect = async_invoke if asynchronous else invoke
    result = asyncio.run(_async_hset(client, "plan-key", mapping, lambda native, name, values: native.hset(name, mapping=values))) if asynchronous else _sync_hset(client, "plan-key", mapping, lambda native, name, values: native.hset(name, mapping=values))
    assert result is None
    expected = [(("plan-key",), {"mapping": mapping})]
    if legacy:
        expected.append((("plan-key", mapping), {}))
    assert calls == expected


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
def test_hset_native_failure_preserves_second_exception_identity(asynchronous):
    import asyncio

    from optimus.agent.state_store import _async_hset, _sync_hset

    calls = []
    failure = ValueError("native SDK positional mapping is not supported")

    def invoke(*args, **kwargs):
        calls.append((args, kwargs))
        if kwargs:
            raise TypeError("original keyword failure")
        raise failure

    async def async_invoke(*args, **kwargs):
        return invoke(*args, **kwargs)

    client = create_autospec(aioredis.Redis if asynchronous else redis.Redis, instance=True, spec_set=True)
    client.hset.side_effect = async_invoke if asynchronous else invoke
    with pytest.raises(ValueError) as error:
        if asynchronous:
            asyncio.run(_async_hset(client, "key", {}, lambda native, name, values: native.hset(name, mapping=values)))
        else:
            _sync_hset(client, "key", {}, lambda native, name, values: native.hset(name, mapping=values))
    assert error.value is failure
    assert calls == [(("key",), {"mapping": {}}), (("key", {}), {})]


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("operation", ["save", "persist"])
def test_store_legacy_hset_preserves_primary_expiry_pointer_order(asynchronous, operation):
    import asyncio

    from optimus.agent.state_store import AsyncRedisAgentStateStore, PlanPersistenceOutcome

    trace = []
    mappings = []
    submissions = []

    def hset(*args, **kwargs):
        key = args[0]
        trace.append(("hset", "keyword" if kwargs else "positional", key))
        if kwargs:
            raise TypeError("legacy client requires positional mapping")
        mappings.append(args[1])
        return len(args[1])

    def expire(key, ttl):
        trace.append(("expire", key, ttl))
        return True

    class LegacySync:
        def hset(self, *args, **kwargs):
            return hset(*args, **kwargs)

        def expire(self, key, ttl):
            return expire(key, ttl)

    class LegacyAsync:
        async def hset(self, *args, **kwargs):
            return hset(*args, **kwargs)

        async def expire(self, key, ttl):
            return expire(key, ttl)

    def submit(factory):
        submissions.append("owner")
        return asyncio.run(factory())

    store = (RedisAgentStateStore(async_store=AsyncRedisAgentStateStore(client=_checked_redis(LegacyAsync(), asynchronous=True), ttl_seconds=60), submit=_checked_submit(submit))
             if asynchronous else RedisAgentStateStore(client=_checked_redis(LegacySync()), ttl_seconds=60))
    if operation == "save":
        store.save_plan(plan_record())
    else:
        result = store.persist_plan(plan_record())
        assert result.outcome is PlanPersistenceOutcome.PERSISTED
        assert result.completed_substeps == ("primary", "expiry", "pointer")
    assert trace == [
        ("hset", "keyword", "agent:plan:run-1:hash-1"),
        ("hset", "positional", "agent:plan:run-1:hash-1"),
        ("expire", "agent:plan:run-1:hash-1", 60),
        ("hset", "keyword", "agent:plan:run-1:latest"),
        ("hset", "positional", "agent:plan:run-1:latest"),
        ("expire", "agent:plan:run-1:latest", 60),
    ]
    assert mappings[0]["plan_text"] == "WRITE example.py\ncontent"
    assert mappings[0]["cost_usd"] == "0.002"
    assert mappings[1] == {"plan_hash": "hash-1"}
    assert submissions == (["owner"] if asynchronous else [])


def test_contract_redis_store_boundary_rejects_unknown_attributes():
    script = FakeRedis()
    boundary = getattr(script, "checked", script)
    with pytest.raises(AttributeError):
        boundary.unknown_redis_operation = True
    with pytest.raises(TypeError):
        boundary.hset("key", obsolete_mapping={})
