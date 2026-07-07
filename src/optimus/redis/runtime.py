from __future__ import annotations

from dataclasses import dataclass

from optimus.agent.state_store import (
    DEFAULT_PLAN_TTL_SECONDS,
    AsyncRedisAgentStateStore,
    RedisAgentStateStore,
    validate_redis_url,
)
from optimus.redis.async_bridge import sync_await
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter


@dataclass(frozen=True)
class RedisRuntime:
    """Shared redis.asyncio pool for plan state and TimeSeries telemetry (LLD §10)."""

    pool: object
    client: object
    ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS

    @classmethod
    def from_url(cls, url: str, *, ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS) -> RedisRuntime:
        validated = validate_redis_url(url)
        import redis.asyncio as aioredis

        pool = aioredis.ConnectionPool.from_url(validated, decode_responses=True, socket_connect_timeout=2)
        client = aioredis.Redis(connection_pool=pool)
        return cls(pool=pool, client=client, ttl_seconds=ttl_seconds)

    def sync_state_store(self) -> RedisAgentStateStore:
        async_store = AsyncRedisAgentStateStore(client=self.client, ttl_seconds=self.ttl_seconds)
        return RedisAgentStateStore(async_store=async_store)

    def telemetry_adapter(self) -> RedisTelemetryAdapter:
        return RedisTelemetryAdapter(client=self.client)

    def ping(self) -> None:
        sync_await(self._ping_async())

    async def _ping_async(self) -> None:
        try:
            await self.client.ping()
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

    async def aclose(self) -> None:
        await self.client.aclose()
        await self.pool.aclose()
