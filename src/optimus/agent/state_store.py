from __future__ import annotations

import json
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from optimus.runtime.modes import ExecutionMode

DEFAULT_PLAN_TTL_SECONDS = 3600


class AgentPlanRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    task: str = Field(min_length=1)
    execution_mode: ExecutionMode
    workspace_root: str = Field(min_length=1)
    plan_hash: str = Field(min_length=1)
    plan_text: str = Field(min_length=1)
    gateway_request_id: str = Field(min_length=1)
    gateway_request_ids: tuple[str, ...] = ()
    planning_turns: int = Field(default=1, ge=1)
    model: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    created_at_ms: int = Field(ge=0)
    expires_at_ms: int = Field(ge=0)

    @field_serializer("cost_usd")
    def serialize_cost_usd(self, value: Decimal) -> str:
        return str(value)


class AgentRunRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    status: str = Field(min_length=1)
    created_at_ms: int = Field(ge=0)


class AgentStateStore(Protocol):
    def save_plan(self, record: AgentPlanRecord) -> None:
        ...

    def load_plan(self, *, run_id: str, plan_hash: str) -> AgentPlanRecord:
        ...

    def latest_plan_for_run(self, *, run_id: str) -> AgentPlanRecord | None:
        ...

    def ping(self) -> None:
        ...


class InMemoryAgentStateStore:
    def __init__(self, *, clock_ms: Callable[[], int] | None = None) -> None:
        self._clock_ms = clock_ms or (lambda: 0)
        self._plans: dict[tuple[str, str], AgentPlanRecord] = {}

    def save_plan(self, record: AgentPlanRecord) -> None:
        self._plans[(record.run_id, record.plan_hash)] = record

    def load_plan(self, *, run_id: str, plan_hash: str) -> AgentPlanRecord:
        record = self._plans.get((run_id, plan_hash))
        if record is None or record.expires_at_ms <= self._clock_ms():
            raise KeyError("stored plan not found")
        return record

    def latest_plan_for_run(self, *, run_id: str) -> AgentPlanRecord | None:
        records = [record for (stored_run_id, _), record in self._plans.items() if stored_run_id == run_id]
        if not records:
            return None
        active_records = [record for record in records if record.expires_at_ms > self._clock_ms()]
        if not active_records:
            return None
        return max(active_records, key=lambda record: record.created_at_ms)

    def ping(self) -> None:
        return None


class RedisAgentStateStore:
    """
    Provides an interface for storing and retrieving agent plans using Redis.

    This class is used to manage the storage and retrieval of agent plan records within a
    Redis datastore. It supports both synchronous and asynchronous Redis clients and ensures
    records are stored with a specified time-to-live (TTL).

    :ivar client: The synchronous Redis client used for connecting to the datastore if
        specified.
    :type client: object | None
    :ivar async_store: The asynchronous Redis state store used if specified instead of the synchronous client.
    :type async_store: AsyncRedisAgentStateStore | None
    :ivar ttl_seconds: The time-to-live (TTL) in seconds for the stored plans.
    :type ttl_seconds: int
    """
    def __init__(
        self,
        *,
        client: object | None = None,
        async_store: "AsyncRedisAgentStateStore | None" = None,
        ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS,
    ) -> None:
        if async_store is not None and client is not None:
            raise ValueError("Specify either async_store or client, not both")
        self._async_store = async_store
        self._client = client
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_url(cls, url: str, ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS) -> "RedisAgentStateStore":
        from optimus.redis.runtime import RedisRuntime

        return RedisRuntime.from_url(url, ttl_seconds=ttl_seconds).sync_state_store()

    @property
    def redis_client(self) -> object:
        if self._async_store is not None:
            return self._async_store._client
        if self._client is None:
            raise RuntimeError("redis client is not configured")
        return self._client

    def save_plan(self, record: AgentPlanRecord) -> None:
        if self._async_store is not None:
            from optimus.redis.async_bridge import sync_await

            sync_await(self._async_store.save_plan(record))
            return
        key = _plan_key(run_id=record.run_id, plan_hash=record.plan_hash)
        mapping = _record_to_mapping(record)
        try:
            self._client.hset(key, mapping=mapping)
        except TypeError:
            self._client.hset(key, mapping)
        self._client.expire(key, self._ttl_seconds)
        latest_key = _latest_plan_key(run_id=record.run_id)
        try:
            self._client.hset(latest_key, mapping={"plan_hash": record.plan_hash})
        except TypeError:
            self._client.hset(latest_key, {"plan_hash": record.plan_hash})
        self._client.expire(latest_key, self._ttl_seconds)

    def load_plan(self, *, run_id: str, plan_hash: str) -> AgentPlanRecord:
        if self._async_store is not None:
            from optimus.redis.async_bridge import sync_await

            return sync_await(self._async_store.load_plan(run_id=run_id, plan_hash=plan_hash))
        key = _plan_key(run_id=run_id, plan_hash=plan_hash)
        raw = self._client.hgetall(key)
        if not raw:
            raise KeyError("stored plan not found")
        return _record_from_mapping(_decode_mapping(raw))

    def latest_plan_for_run(self, *, run_id: str) -> AgentPlanRecord | None:
        if self._async_store is not None:
            from optimus.redis.async_bridge import sync_await

            return sync_await(self._async_store.latest_plan_for_run(run_id=run_id))
        raw = self._client.hgetall(_latest_plan_key(run_id=run_id))
        if not raw:
            return None
        latest = _decode_mapping(raw)
        plan_hash = latest.get("plan_hash")
        if not plan_hash:
            return None
        try:
            return self.load_plan(run_id=run_id, plan_hash=plan_hash)
        except KeyError:
            return None

    def ping(self) -> None:
        if self._async_store is not None:
            from optimus.redis.async_bridge import sync_await

            sync_await(self._async_store.ping())
            return
        try:
            self._client.ping()
        except ConnectionError:
            raise
        except OSError as exc:
            raise ConnectionError(str(exc)) from exc
        except Exception as exc:
            if type(exc).__module__.startswith("redis") and type(exc).__name__ in {
                "ConnectionError",
                "TimeoutError",
            }:
                raise ConnectionError(str(exc)) from exc
            raise


class AsyncRedisAgentStateStore:
    """
    AsyncRedisAgentStateStore is responsible for managing agent state storage using
    Redis. It handles saving, loading, and retrieving the latest agent plans, and
    providing a mechanism to check the connection with the Redis client.

    This class is designed to work asynchronously and relies on an external Redis
    client for operations. It provides TTL-based expiration for stored plans and
    ensures efficient data management in a Redis datastore.

    :ivar client: Redis client used for the storage and retrieval of data.
    :type client: object
    :ivar ttl_seconds: Time-to-Live (TTL) duration in seconds for stored plans.
    :type ttl_seconds: int
    """
    def __init__(self, *, client: object, ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    async def save_plan(self, record: AgentPlanRecord) -> None:
        key = _plan_key(run_id=record.run_id, plan_hash=record.plan_hash)
        mapping = _record_to_mapping(record)
        try:
            await self._client.hset(key, mapping=mapping)
        except TypeError:
            await self._client.hset(key, mapping)
        await self._client.expire(key, self._ttl_seconds)
        latest_key = _latest_plan_key(run_id=record.run_id)
        try:
            await self._client.hset(latest_key, mapping={"plan_hash": record.plan_hash})
        except TypeError:
            await self._client.hset(latest_key, {"plan_hash": record.plan_hash})
        await self._client.expire(latest_key, self._ttl_seconds)

    async def load_plan(self, *, run_id: str, plan_hash: str) -> AgentPlanRecord:
        key = _plan_key(run_id=run_id, plan_hash=plan_hash)
        raw = await self._client.hgetall(key)
        if not raw:
            raise KeyError("stored plan not found")
        return _record_from_mapping(_decode_mapping(raw))

    async def latest_plan_for_run(self, *, run_id: str) -> AgentPlanRecord | None:
        raw = await self._client.hgetall(_latest_plan_key(run_id=run_id))
        if not raw:
            return None
        latest = _decode_mapping(raw)
        plan_hash = latest.get("plan_hash")
        if not plan_hash:
            return None
        try:
            return await self.load_plan(run_id=run_id, plan_hash=plan_hash)
        except KeyError:
            return None

    async def ping(self) -> None:
        try:
            await self._client.ping()
        except ConnectionError:
            raise
        except OSError as exc:
            raise ConnectionError(str(exc)) from exc
        except Exception as exc:
            if type(exc).__module__.startswith("redis") and type(exc).__name__ in {
                "ConnectionError",
                "TimeoutError",
            }:
                raise ConnectionError(str(exc)) from exc
            raise


def validate_redis_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"redis", "rediss"}:
        raise ValueError("OPTIMUS_REDIS_URL must use redis:// or rediss://")
    if parsed.username or parsed.password:
        raise ValueError("OPTIMUS_REDIS_URL must not contain username or password")
    return url


def _epoch_ms() -> int:
    return int(time.time() * 1000)


def _plan_key(*, run_id: str, plan_hash: str) -> str:
    return f"agent:plan:{run_id}:{plan_hash}"


def _latest_plan_key(*, run_id: str) -> str:
    return f"agent:plan:{run_id}:latest"


def _record_to_mapping(record: AgentPlanRecord) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key, value in record.model_dump(mode="json").items():
        if value is None:
            continue
        if key == "gateway_request_ids":
            mapping[key] = json.dumps(value)
        else:
            mapping[key] = str(value)
    return mapping


def _decode_mapping(raw: dict[object, object]) -> dict[str, str]:
    decoded: dict[str, str] = {}
    for key, value in raw.items():
        key_text = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        value_text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        decoded[key_text] = value_text
    return decoded


def _record_from_mapping(mapping: dict[str, str]) -> AgentPlanRecord:
    raw_gateway_request_ids = mapping.get("gateway_request_ids")
    gateway_request_ids = tuple(json.loads(raw_gateway_request_ids)) if raw_gateway_request_ids else ()
    return AgentPlanRecord(
        run_id=mapping["run_id"],
        session_id=mapping.get("session_id"),
        task=mapping["task"],
        execution_mode=ExecutionMode(mapping["execution_mode"]),
        workspace_root=mapping["workspace_root"],
        plan_hash=mapping["plan_hash"],
        plan_text=mapping["plan_text"],
        gateway_request_id=mapping["gateway_request_id"],
        gateway_request_ids=gateway_request_ids,
        planning_turns=int(mapping.get("planning_turns", "1")),
        model=mapping["model"],
        provider=mapping["provider"],
        cost_usd=Decimal(mapping["cost_usd"]),
        created_at_ms=int(mapping["created_at_ms"]),
        expires_at_ms=int(mapping["expires_at_ms"]),
    )
