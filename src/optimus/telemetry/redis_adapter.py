from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, NamedTuple, Protocol

from optimus.usage.errors import DuplicateGatewayRequestError
from optimus.usage.ledger import settled_fingerprint

if TYPE_CHECKING:
    from redis.typing import EncodableT, FieldT


RETENTION_MS_30_DAYS = 2_592_000_000
RETENTION_SECONDS_30_DAYS = 2_592_000

USAGE_KEY_PREFIX = "optimus:usage"


class RedisTelemetryClient(Protocol):
    def execute_command(self, *args: object) -> Awaitable[object]: ...
    def hset(self, name: str, /, *, mapping: Mapping[FieldT, EncodableT]) -> Awaitable[int]: ...
    def hsetnx(self, name: str, field: str, value: str, /) -> Awaitable[int]: ...
    def hget(self, name: str, field: str, /) -> Awaitable[bytes | str | None]: ...
    def hdel(self, name: str, /, *fields: str) -> Awaitable[int]: ...
    def expire(self, name: str, seconds: int, /) -> Awaitable[bool]: ...


class _Claim(NamedTuple):
    gateway_request_id: str
    provider: str
    provider_request_id: str | None
    billing_units: int
    cost_usd: Decimal


def _parse_claim(stored: bytes | str | None) -> _Claim | None:
    """Read a stored claim fingerprint; ``None`` for anything corrupt (treated as divergent)."""
    try:
        data = json.loads(stored.decode() if isinstance(stored, bytes) else stored)  # type: ignore[arg-type]
        if not isinstance(data["cost_usd"], str):
            return None
        cost = Decimal(data["cost_usd"])
        claim = _Claim(data["gateway_request_id"], data["provider"], data["provider_request_id"], data["billing_units"], cost)
    except (TypeError, ValueError, KeyError, InvalidOperation):  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        return None
    ids = (claim.gateway_request_id, claim.provider)
    valid = (
        all(isinstance(v, str) for v in ids)
        and isinstance(claim.provider_request_id, str | None)
        and type(claim.billing_units) is int
        and cost.is_finite()
    )
    return claim if valid else None


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
        self._settled_usage_lock = asyncio.Lock()

    async def ensure_series(self, key: str) -> None:
        try:
            await self._client.execute_command("TS.CREATE", key, "RETENTION", self._retention_ms)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                raise
            await self._client.execute_command("TS.ALTER", key, "RETENTION", self._retention_ms)

    async def _ensure_usage_series(self, key: str, *, run_id: str, metric_name: str) -> None:
        try:
            await self._client.execute_command(
                "TS.CREATE",
                key,
                "RETENTION",
                self._retention_ms,
                "LABELS",
                "run_id",
                run_id,
                "metric",
                metric_name,
            )
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                raise
            await self._client.execute_command("TS.ALTER", key, "RETENTION", self._retention_ms)

    async def record_settled_usage(
        self,
        *,
        run_id: str,
        gateway_request_id: str,
        provider: str,
        provider_request_id: str | None,
        billing_units: int,
        cost_usd: Decimal,
    ) -> None:
        """Persist one settled Gateway usage attempt to two run-scoped TimeSeries.

        Idempotent by ``gateway_request_id``: a fingerprint of every accounting field is
        claimed via ``HSETNX`` under the adapter lock. A replay whose fields match the
        existing claim by value (cost as a ``Decimal``: ``0.003`` equals ``0.0030``) is a no-op (no second ``TS.ADD``); a divergent
        fingerprint raises :class:`~optimus.usage.errors.DuplicateGatewayRequestError`
        without writing a second point. If the TimeSeries write itself fails after a new
        claim is made, the claim is released so a legitimate retry is not permanently
        blocked by a phantom claim.
        """
        if not run_id:
            raise ValueError("Access constraint violation: Missing telemetry run_id key.")
        claims_key = f"{USAGE_KEY_PREFIX}:{run_id}:claims"
        fingerprint = json.dumps(
            {
                "gateway_request_id": gateway_request_id,
                "provider": provider,
                "provider_request_id": provider_request_id,
                "billing_units": billing_units,
                "cost_usd": str(cost_usd),
            },
            sort_keys=True,
        )
        async with self._settled_usage_lock:
            claimed = await self._client.hsetnx(claims_key, gateway_request_id, fingerprint)
            if not claimed:
                existing = await self._client.hget(claims_key, gateway_request_id)
                stored = _parse_claim(existing)
                if stored is not None and settled_fingerprint(stored) == settled_fingerprint(
                    _Claim(gateway_request_id, provider, provider_request_id, billing_units, cost_usd)
                ):
                    return
                raise DuplicateGatewayRequestError(gateway_request_id)
            try:
                cost_key = f"{USAGE_KEY_PREFIX}:{run_id}:cost_usd"
                units_key = f"{USAGE_KEY_PREFIX}:{run_id}:billing_units"
                await self._ensure_usage_series(cost_key, run_id=run_id, metric_name="cost_usd")
                await self._ensure_usage_series(units_key, run_id=run_id, metric_name="billing_units")
                await self._client.execute_command("TS.ADD", cost_key, "*", str(cost_usd))
                await self._client.execute_command("TS.ADD", units_key, "*", str(billing_units))
            except Exception:
                await self._client.hdel(claims_key, gateway_request_id)
                raise

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
