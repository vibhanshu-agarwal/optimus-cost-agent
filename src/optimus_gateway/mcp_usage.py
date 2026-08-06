"""Gateway-owned MCP usage records and persistence boundaries."""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any, Literal, Protocol

import redis
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from optimus_gateway.mcp_models import parse_namespaced_tool_name


class MCPUsagePersistenceError(RuntimeError):
    """Base class for failures that withhold a result from release."""


class MCPUsageUnavailableError(MCPUsagePersistenceError):
    """Raised when the authoritative Gateway usage backend is unavailable."""


class MCPUsageConflictError(MCPUsagePersistenceError):
    """Raised when a gateway_request_id is reused for a different record."""


class MCPUsageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gateway_request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    request_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    profile_revision: str = Field(min_length=1)
    namespaced_tool_name: str = Field(min_length=1)
    upstream_tool_name: str = Field(min_length=1)
    transport: Literal["http", "stdio"]
    disposition: str = Field(min_length=1)
    attribution: Literal["settled", "explicit_zero", "unavailable"]
    duration_ms: int = Field(ge=0)
    request_bytes: int = Field(ge=0)
    response_bytes: int = Field(ge=0)
    provider_request_id: str | None = None
    billing_units: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=Decimal("0"))

    @field_validator("cost_usd")
    @classmethod
    def validate_finite_cost(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("cost_usd must be finite")
        return value

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        try:
            parse_namespaced_tool_name(f"{value}.placeholder", expected_profile_id=value)
        except ValueError as exc:
            raise ValueError("profile_id is invalid") from exc
        return value

    @model_validator(mode="after")
    def validate_tool_binding(self) -> MCPUsageRecord:
        parse_namespaced_tool_name(self.namespaced_tool_name, expected_profile_id=self.profile_id)
        if self.namespaced_tool_name.split(".", 1)[1] != self.upstream_tool_name:
            raise ValueError("upstream_tool_name must match namespaced_tool_name")
        if self.attribution == "settled" and (self.billing_units is None or self.cost_usd is None):
            raise ValueError("settled attribution requires billing_units and cost_usd")
        if self.attribution == "explicit_zero" and (
            self.billing_units != 0 or self.cost_usd != Decimal("0")
        ):
            raise ValueError("explicit_zero attribution requires zero billing_units and cost_usd")
        if self.attribution == "unavailable" and (self.billing_units is not None or self.cost_usd is not None):
            raise ValueError("unavailable attribution must not carry monetary values")
        return self


class MCPUsageWriter(Protocol):
    def persist(self, record: MCPUsageRecord) -> None: ...


class InMemoryMCPUsageWriter:
    """Unit-test-only writer with the same immutable-ID semantics as Redis."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, MCPUsageRecord] = {}

    def persist(self, record: MCPUsageRecord) -> None:
        with self._lock:
            existing = self._records.get(record.gateway_request_id)
            if existing is None:
                self._records[record.gateway_request_id] = record
                return
            if existing != record:
                raise MCPUsageConflictError("gateway_request_id already contains a different usage record")

    def record_for(self, gateway_request_id: str) -> MCPUsageRecord | None:
        with self._lock:
            return self._records.get(gateway_request_id)


class RedisMCPUsageWriter:
    """Direct Gateway Redis writer; no agent-side Redis runtime is reused."""

    def __init__(self, *, client: Any, retention_seconds: int = 2_592_000) -> None:
        if retention_seconds <= 0:
            raise ValueError("retention_seconds must be positive")
        self._client = client
        self._retention_seconds = retention_seconds

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        retention_seconds: int = 2_592_000,
        socket_connect_timeout: float = 2.0,
        socket_timeout: float = 2.0,
    ) -> RedisMCPUsageWriter:
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
        )
        return cls(client=client, retention_seconds=retention_seconds)

    @property
    def redis_client(self) -> Any:
        return self._client

    def persist(self, record: MCPUsageRecord) -> None:
        key = _usage_key(record.gateway_request_id)
        payload = record.model_dump_json()
        try:
            created = self._client.set(key, payload, nx=True, ex=self._retention_seconds)
            if created:
                return
            existing = self._client.get(key)
        except _REDIS_UNAVAILABLE_ERRORS as exc:
            raise MCPUsageUnavailableError("MCP usage backend is unavailable") from exc
        if existing is None:
            raise MCPUsagePersistenceError("MCP usage record disappeared during idempotent persistence")
        try:
            if isinstance(existing, bytes):
                existing = existing.decode("utf-8")
            existing_record = MCPUsageRecord.model_validate_json(existing)
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise MCPUsagePersistenceError("MCP usage backend returned an invalid record") from exc
        if existing_record != record:
            raise MCPUsageConflictError("gateway_request_id already contains a different usage record")

    def record_for(self, gateway_request_id: str) -> MCPUsageRecord | None:
        try:
            payload = self._client.get(_usage_key(gateway_request_id))
        except _REDIS_UNAVAILABLE_ERRORS as exc:
            raise MCPUsageUnavailableError("MCP usage backend is unavailable") from exc
        if payload is None:
            return None
        try:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            return MCPUsageRecord.model_validate_json(payload)
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise MCPUsagePersistenceError("MCP usage backend returned an invalid record") from exc


_REDIS_UNAVAILABLE_ERRORS: tuple[type[Exception], ...] = (
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
    OSError,
)


def _usage_key(gateway_request_id: str) -> str:
    return f"gateway:mcp:usage:{gateway_request_id}"


__all__ = [
    "InMemoryMCPUsageWriter",
    "MCPUsageConflictError",
    "MCPUsagePersistenceError",
    "MCPUsageRecord",
    "MCPUsageUnavailableError",
    "MCPUsageWriter",
    "RedisMCPUsageWriter",
]
