from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from optimus.runtime.modes import ExecutionMode

DEFAULT_PLAN_TTL_SECONDS = 3600


class PlanPersistenceOutcome(StrEnum):
    PERSISTED = "persisted"
    PERSISTENCE_FAILED = "persistence_failed"
    PERSISTENCE_PARTIAL = "persistence_partial"


@dataclass(frozen=True, slots=True)
class PlanPersistenceResult:
    outcome: PlanPersistenceOutcome
    completed_substeps: tuple[str, ...] = ()

    @property
    def authorizing(self) -> bool:
        return self.outcome is PlanPersistenceOutcome.PERSISTED


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

    def persist_plan(self, record: AgentPlanRecord) -> PlanPersistenceResult:
        self.save_plan(record)
        return PlanPersistenceResult(
            outcome=PlanPersistenceOutcome.PERSISTED,
            completed_substeps=("primary", "expiry", "pointer"),
        )

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
        submit: "Callable[[Callable[[], Awaitable[Any]]], Any] | None" = None,
        owned_runtime: object | None = None,
    ) -> None:
        """
        ``submit`` is the owner submission seam an async-backed store runs on (Seam 2,
        checkpoint B). It takes a zero-argument operation factory and runs it on the ONE
        loop that owns the client -- ``RedisRuntime.run_sync`` in production. It is
        required whenever ``async_store`` is given: a store that fell back to the
        process-wide shared tool loop would drive the runtime's client from a second
        owner, which is the lifetime defect this seam removes. The synchronous
        ``client`` path needs no owner and is unchanged.

        ``owned_runtime`` is set only by :meth:`from_url`, whose convenience lifetime this
        store then carries and closes; a store handed a runtime's seam by that runtime
        owns nothing and cannot close it.
        """
        if async_store is not None and client is not None:
            raise ValueError("Specify either async_store or client, not both")
        if async_store is not None and submit is None:
            raise TypeError(
                "an async-backed RedisAgentStateStore requires the owner submission seam "
                "(submit=runtime.run_sync); it never falls back to the shared tool loop"
            )
        self._async_store = async_store
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._submit = submit
        self._owned_runtime = owned_runtime

    @classmethod
    def from_url(cls, url: str, ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS) -> "RedisAgentStateStore":
        """Build a runtime AND keep custody of it.

        Before Seam 2 this discarded the runtime it built, leaving a live loop owner with
        no close handle. The returned store now retains that runtime as
        :attr:`owned_runtime`, submits through its owner, and closes it in :meth:`close`.
        """
        from optimus.redis.runtime import RedisRuntime

        runtime = RedisRuntime.from_url(url, ttl_seconds=ttl_seconds)
        async_store = AsyncRedisAgentStateStore(client=runtime.client, ttl_seconds=ttl_seconds)
        return cls(async_store=async_store, ttl_seconds=ttl_seconds, submit=runtime.run_sync, owned_runtime=runtime)

    @property
    def owned_runtime(self) -> object | None:
        return self._owned_runtime

    def submit(self, operation: "Callable[[], Awaitable[Any]]") -> Any:
        """Run an operation factory on the owner that drives this store's client.

        Tools that need raw client access (key scans, cleanup) use this instead of a
        loop of their own, so the client is never driven from a second owner.
        """
        if self._submit is None:
            raise RuntimeError("this store has no owner submission seam; it wraps a synchronous client")
        return self._submit(operation)

    def close(self, *, timeout: float | None = None):
        """Close the runtime this store owns. Only a :meth:`from_url` store owns one."""
        if self._owned_runtime is None:
            raise RuntimeError("this store owns no runtime; close the runtime that built it instead")
        return self._owned_runtime.close(timeout=timeout)

    @property
    def redis_client(self) -> object:
        if self._async_store is not None:
            return self._async_store._client
        if self._client is None:
            raise RuntimeError("redis client is not configured")
        return self._client

    def save_plan(self, record: AgentPlanRecord) -> None:
        if self._async_store is not None:
            self._submit(lambda: self._async_store.save_plan(record))
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

    def persist_plan(self, record: AgentPlanRecord) -> PlanPersistenceResult:
        if self._async_store is not None:
            try:
                self.save_plan(record)
            except Exception:
                return PlanPersistenceResult(outcome=PlanPersistenceOutcome.PERSISTENCE_FAILED)
            return PlanPersistenceResult(
                outcome=PlanPersistenceOutcome.PERSISTED,
                completed_substeps=("primary", "expiry", "pointer"),
            )
        completed: list[str] = []
        key = _plan_key(run_id=record.run_id, plan_hash=record.plan_hash)
        mapping = _record_to_mapping(record)
        try:
            try:
                self._client.hset(key, mapping=mapping)
            except TypeError:
                self._client.hset(key, mapping)
            completed.append("primary")
            self._client.expire(key, self._ttl_seconds)
            completed.append("expiry")
            latest_key = _latest_plan_key(run_id=record.run_id)
            try:
                self._client.hset(latest_key, mapping={"plan_hash": record.plan_hash})
            except TypeError:
                self._client.hset(latest_key, {"plan_hash": record.plan_hash})
            completed.append("pointer")
            self._client.expire(latest_key, self._ttl_seconds)
        except Exception:
            if completed:
                return PlanPersistenceResult(
                    outcome=PlanPersistenceOutcome.PERSISTENCE_PARTIAL,
                    completed_substeps=tuple(completed),
                )
            return PlanPersistenceResult(outcome=PlanPersistenceOutcome.PERSISTENCE_FAILED)
        return PlanPersistenceResult(
            outcome=PlanPersistenceOutcome.PERSISTED,
            completed_substeps=tuple(completed),
        )

    def load_plan(self, *, run_id: str, plan_hash: str) -> AgentPlanRecord:
        if self._async_store is not None:
            return self._submit(lambda: self._async_store.load_plan(run_id=run_id, plan_hash=plan_hash))
        key = _plan_key(run_id=run_id, plan_hash=plan_hash)
        raw = self._client.hgetall(key)
        if not raw:
            raise KeyError("stored plan not found")
        return _record_from_mapping(_decode_mapping(raw))

    def latest_plan_for_run(self, *, run_id: str) -> AgentPlanRecord | None:
        if self._async_store is not None:
            return self._submit(lambda: self._async_store.latest_plan_for_run(run_id=run_id))
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
            self._submit(lambda: self._async_store.ping())
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
