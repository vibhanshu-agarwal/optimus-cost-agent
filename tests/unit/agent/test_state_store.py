from decimal import Decimal

import pytest

from optimus.agent.state_store import AgentPlanRecord, InMemoryAgentStateStore, RedisAgentStateStore, validate_redis_url
from optimus.runtime.modes import ExecutionMode


class FakeRedis:
    def __init__(self, ping_error: Exception | None = None) -> None:
        self.ping_error = ping_error
        self.hsets: list[tuple[str, dict[str, str]]] = []
        self.hgetalls: dict[str, dict[str, str]] = {}
        self.expires: list[tuple[str, int]] = []

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
        validate_redis_url("redis://user:secret@localhost:6379/0")


def test_validate_redis_url_accepts_redis_and_rediss_without_credentials():
    assert validate_redis_url("redis://localhost:6379/0") == "redis://localhost:6379/0"
    assert validate_redis_url("rediss://cache.example.com:6380/0") == "rediss://cache.example.com:6380/0"


def test_validate_redis_url_rejects_non_redis_schemes():
    with pytest.raises(ValueError, match="must use redis:// or rediss://"):
        validate_redis_url("http://localhost:6379/0")


def test_plan_record_schema_and_persisted_mapping_are_functional_only():
    record = plan_record()

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
    }

    fake = FakeRedis()
    RedisAgentStateStore(client=fake).save_plan(record)
    persisted_fields = set(fake.hsets[0][1])
    assert persisted_fields == set(AgentPlanRecord.model_fields)


def test_redis_store_writes_hash_and_ttl():
    fake = FakeRedis()
    store = RedisAgentStateStore(client=fake, ttl_seconds=3600)
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
    store = RedisAgentStateStore(client=fake, ttl_seconds=3600)
    record = plan_record()
    store.save_plan(record)

    assert store.load_plan(run_id="run-1", plan_hash="hash-1") == record


def test_redis_store_loads_latest_plan_for_run():
    fake = FakeRedis()
    store = RedisAgentStateStore(client=fake, ttl_seconds=3600)
    record = plan_record()
    store.save_plan(record)

    assert store.latest_plan_for_run(run_id="run-1") == record


def test_redis_store_ping_fails_closed_when_redis_is_down():
    fake = FakeRedis(ping_error=ConnectionError("redis unavailable"))
    store = RedisAgentStateStore(client=fake, ttl_seconds=3600)

    with pytest.raises(ConnectionError, match="redis unavailable"):
        store.ping()


def test_in_memory_store_treats_expired_plan_as_missing():
    store = InMemoryAgentStateStore(clock_ms=lambda: 3_700_000)
    store.save_plan(plan_record())

    with pytest.raises(KeyError, match="stored plan not found"):
        store.load_plan(run_id="run-1", plan_hash="hash-1")
