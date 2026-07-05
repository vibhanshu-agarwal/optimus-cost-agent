from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

RETENTION_MS_30_DAYS = 2_592_000_000
RETENTION_SECONDS_30_DAYS = 2_592_000


class RedisTelemetryClient(Protocol):
    async def execute_command(self, *args: object): ...
    async def hset(self, key: str, mapping: dict[str, str]): ...
    async def expire(self, key: str, ttl_seconds: int): ...


@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    execution_mode: str
    generation_scope: str
    rigor_level: str
    user_approval_id: str
    assumption_count: int


class RedisTelemetryAdapter:
    def __init__(self, *, client: RedisTelemetryClient, retention_ms: int = RETENTION_MS_30_DAYS) -> None:
        self._client = client
        self._retention_ms = retention_ms

    async def ensure_series(self, key: str) -> None:
        try:
            await self._client.execute_command("TS.CREATE", key, "RETENTION", self._retention_ms)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                raise
            await self._client.execute_command("TS.ALTER", key, "RETENTION", self._retention_ms)

    async def record_metric(self, *, run_id: str, metric_name: str, value: str) -> None:
        if not run_id:
            raise ValueError("Access constraint violation: Missing telemetry run_id key.")
        key = f"telemetry:run:{run_id}:metrics:{metric_name}"
        await self.ensure_series(key)
        await self._client.execute_command("TS.ADD", key, "*", value)

    async def write_run_metadata(self, metadata: RunMetadata) -> None:
        key = f"run:{metadata.run_id}:metadata"
        await self._client.hset(
            key,
            mapping={
                "execution_mode": metadata.execution_mode,
                "generation_scope": metadata.generation_scope,
                "rigor_level": metadata.rigor_level,
                "user_approval_id": metadata.user_approval_id,
                "assumption_count": str(metadata.assumption_count),
            },
        )
        await self._client.expire(key, RETENTION_SECONDS_30_DAYS)
