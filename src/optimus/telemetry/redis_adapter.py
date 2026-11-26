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
    def hget(self, name: str, field: str, /) -> Awaitable[bytes | str | None]: ...
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


# KEYS: claims hash, cost series, units series. ARGV: gateway_request_id, fingerprint, cost, units.
# Redis runs a script atomically, so the claim exists exactly when both points do. Both points share one
# timestamp, later than the last sample of either series: `TS.ADD *` reads the clock per call, and under the
# BLOCK duplicate policy a units point landing on an earlier request's millisecond would fail after its cost
# point was written, which a script cannot roll back. ON_DUPLICATE BLOCK keeps a series' LAST/IGNORE filter
# from skipping a point while still answering with a timestamp; each reply is checked against the chosen one.
_SETTLE_SCRIPT = """
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 1 then return 0 end
local now = redis.call('TIME')
local ts = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
for i = 2, 3 do
  local last = redis.call('TS.GET', KEYS[i])
  if last[1] and tonumber(last[1]) >= ts then ts = tonumber(last[1]) + 1 end
end
ts = string.format('%d', ts)
for i = 2, 3 do
  local added = redis.call('TS.ADD', KEYS[i], ts, ARGV[i + 1], 'ON_DUPLICATE', 'BLOCK')
  if string.format('%d', added) ~= ts then return redis.error_reply('settled point not stored at ' .. ts) end
end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
return 1
"""


def _is_replay(existing: str, fields: tuple[str, str, str | None, int], fingerprint: str, cost_usd: Decimal) -> bool:
    """Whether a stored claim records the same settled facts (#586: cost compared by value)."""
    if existing == fingerprint:
        return True
    # Same request with the cost written differently (0.003 vs 0.0030) is a replay, but only
    # when the stored claim is exactly a string this code writes: canonical JSON, str(Decimal) cost.
    cost_text = _stored_cost_text(existing) if cost_usd.is_finite() else None
    if cost_text is None:
        return False
    try:
        stored_cost = Decimal(cost_text)
    except InvalidOperation:
        return False
    return (
        stored_cost.is_finite()
        and stored_cost == cost_usd
        and str(stored_cost) == cost_text
        and existing == json.dumps(_claim_fields(*fields, cost_text), sort_keys=True)
    )


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

        Follows the settled-facts rule of ``optimus.usage.ledger.append_settled``: a
        ``gateway_request_id`` is unique across runs, so its claim is global (one hash,
        ``{USAGE_KEY_PREFIX}:claims``), not per run. A replay with the same facts (cost compared
        by value), under this run or another, is a no-op: the cost is counted once, in the run
        that claimed it first. Different facts raise
        :class:`~optimus.usage.errors.DuplicateGatewayRequestError` without writing a point.

        The claim and both points are written by one script, which Redis runs whole or not at
        all (#646). An attempt interrupted at any point, a lost reply included, has therefore
        written either everything or nothing: a retry finds the claim and stops, or writes all
        three. Concurrent replays serialise on the script, and the loser compares the winner's
        claim. No claim is ever released, so no cleanup failure can replace the original error.
        """
        # Stays deferred: optimus.usage.accounting imports optimus.telemetry at load time, so a
        # module-level import here would make a package cycle (concurrent cold imports can deadlock).
        from optimus.usage.errors import DuplicateGatewayRequestError

        if not run_id:
            raise ValueError("Access constraint violation: Missing telemetry run_id key.")
        claims_key = f"{USAGE_KEY_PREFIX}:claims"
        fields = (gateway_request_id, provider, provider_request_id, billing_units)
        fingerprint = json.dumps(_claim_fields(*fields, str(cost_usd)), sort_keys=True)
        async with self._settled_usage_lock:
            existing = await self._read_claim(claims_key, gateway_request_id)
            if existing is not None:
                if _is_replay(existing, fields, fingerprint, cost_usd):
                    return
                raise DuplicateGatewayRequestError(gateway_request_id)
            cost_key = f"{USAGE_KEY_PREFIX}:{run_id}:cost_usd"
            units_key = f"{USAGE_KEY_PREFIX}:{run_id}:billing_units"
            await self._ensure_usage_series(cost_key, run_id=run_id, metric_name="cost_usd")
            await self._ensure_usage_series(units_key, run_id=run_id, metric_name="billing_units")
            claimed = await self._client.execute_command(
                "EVAL", _SETTLE_SCRIPT, 3, claims_key, cost_key, units_key,
                gateway_request_id, fingerprint, str(cost_usd), str(billing_units),
            )  # fmt: skip
            if not claimed:  # another writer claimed it between the read and the script
                existing = await self._read_claim(claims_key, gateway_request_id)
                if existing is None or not _is_replay(existing, fields, fingerprint, cost_usd):
                    raise DuplicateGatewayRequestError(gateway_request_id)

    async def _read_claim(self, claims_key: str, gateway_request_id: str) -> str | None:
        """The stored claim, ``None`` when there is none, ``""`` when one exists but is not UTF-8."""
        try:
            stored = await self._client.hget(claims_key, gateway_request_id)
        except UnicodeDecodeError:  # a decoding client met a stored claim that is not UTF-8
            return ""
        if isinstance(stored, bytes):
            try:
                return stored.decode()
            except UnicodeDecodeError:
                return ""
        return stored

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
