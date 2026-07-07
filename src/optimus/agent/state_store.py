from __future__ import annotations

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
    def __init__(self, *, client: object, ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_url(cls, url: str, ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS) -> "RedisAgentStateStore":
        validated = validate_redis_url(url)
        from redis import Redis

        return cls(client=Redis.from_url(validated, decode_responses=True), ttl_seconds=ttl_seconds)

    def save_plan(self, record: AgentPlanRecord) -> None:
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
        key = _plan_key(run_id=run_id, plan_hash=plan_hash)
        raw = self._client.hgetall(key)
        if not raw:
            raise KeyError("stored plan not found")
        return _record_from_mapping(_decode_mapping(raw))

    def latest_plan_for_run(self, *, run_id: str) -> AgentPlanRecord | None:
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
        self._client.ping()


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
    return {key: str(value) for key, value in record.model_dump(mode="json").items() if value is not None}


def _decode_mapping(raw: dict[object, object]) -> dict[str, str]:
    decoded: dict[str, str] = {}
    for key, value in raw.items():
        key_text = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        value_text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        decoded[key_text] = value_text
    return decoded


def _record_from_mapping(mapping: dict[str, str]) -> AgentPlanRecord:
    return AgentPlanRecord(
        run_id=mapping["run_id"],
        session_id=mapping.get("session_id"),
        task=mapping["task"],
        execution_mode=ExecutionMode(mapping["execution_mode"]),
        workspace_root=mapping["workspace_root"],
        plan_hash=mapping["plan_hash"],
        plan_text=mapping["plan_text"],
        gateway_request_id=mapping["gateway_request_id"],
        model=mapping["model"],
        provider=mapping["provider"],
        cost_usd=Decimal(mapping["cost_usd"]),
        created_at_ms=int(mapping["created_at_ms"]),
        expires_at_ms=int(mapping["expires_at_ms"]),
    )
