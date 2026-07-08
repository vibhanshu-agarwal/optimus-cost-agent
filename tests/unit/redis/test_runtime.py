from optimus.agent.state_store import RedisAgentStateStore
from optimus.redis.runtime import RedisRuntime
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter


def test_redis_runtime_shares_pool_between_state_store_and_telemetry():
    runtime = RedisRuntime.from_url("redis://127.0.0.1:6379/0")
    state_store = runtime.sync_state_store()
    adapter = runtime.telemetry_adapter()

    assert isinstance(state_store, RedisAgentStateStore)
    assert isinstance(adapter, RedisTelemetryAdapter)
    assert state_store.redis_client.connection_pool is runtime.pool
    assert adapter._client.connection_pool is runtime.pool
