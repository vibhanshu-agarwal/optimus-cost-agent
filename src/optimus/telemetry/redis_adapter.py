from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Protocol

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


def _claim_fields(
    gateway_request_id: str, provider: str, provider_request_id: str | None, billing_units: int, cost_text: str
) -> dict[str, object]:
    return {
        "gateway_request_id": gateway_request_id,
        "provider": provider,
        "provider_request_id": provider_request_id,
        "billing_units": billing_units,
        "cost_usd": cost_text,
    }


def _stored_cost_text(stored: str) -> str | None:
    """The ``cost_usd`` string of a stored claim object, or ``None`` if it has none."""
    try:
        cost = json.loads(stored)["cost_usd"]
    except (ValueError, TypeError, KeyError, RecursionError):
        return None
    return cost if isinstance(cost, str) else None


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
        claimed via ``HSETNX`` under the adapter lock. An identical replay's fingerprint
        matches the existing claim (cost compared by value) and is a no-op (no second ``TS.ADD``); a divergent
        fingerprint raises :class:`~optimus.usage.errors.DuplicateGatewayRequestError`
        without writing a second point. If the TimeSeries write itself fails after a new
        claim is made, the claim is released so a legitimate retry is not permanently
        blocked by a phantom claim.
        """
        # Stays deferred: optimus.usage.accounting imports optimus.telemetry at load time, so a
        # module-level import here would make a package cycle (concurrent cold imports can deadlock).
        from optimus.usage.errors import DuplicateGatewayRequestError

        if not run_id:
            raise ValueError("Access constraint violation: Missing telemetry run_id key.")
        claims_key = f"{USAGE_KEY_PREFIX}:{run_id}:claims"
        fields = (gateway_request_id, provider, provider_request_id, billing_units)
        fingerprint = json.dumps(_claim_fields(*fields, str(cost_usd)), sort_keys=True)
        async with self._settled_usage_lock:
            claimed = await self._client.hsetnx(claims_key, gateway_request_id, fingerprint)
            if not claimed:
                try:
                    existing = await self._client.hget(claims_key, gateway_request_id)
                except UnicodeDecodeError:  # a decoding client met a stored claim that is not UTF-8
                    existing = None
                if isinstance(existing, bytes):
                    try:
                        existing = existing.decode()
                    except UnicodeDecodeError:
                        existing = None
                if existing == fingerprint:
                    return
                # Same request with the cost written differently (0.003 vs 0.0030) is a replay, but only
                # when the stored claim is exactly a string this code writes: canonical JSON, str(Decimal) cost.
                cost_text = _stored_cost_text(existing) if existing is not None and cost_usd.is_finite() else None
                if cost_text is not None:
                    try:
                        stored_cost = Decimal(cost_text)
                    except InvalidOperation:
                        stored_cost = None
                    if (
                        stored_cost is not None
                        and stored_cost.is_finite()
                        and stored_cost == cost_usd
                        and str(stored_cost) == cost_text
                        and existing == json.dumps(_claim_fields(*fields, cost_text), sort_keys=True)
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
