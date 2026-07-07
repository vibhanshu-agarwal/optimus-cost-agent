from __future__ import annotations

from collections.abc import Iterator

import pytest

from optimus.agent.state_store import RedisAgentStateStore
from tests.integration.redis_support import skip_unless_redis


@pytest.fixture
def live_redis_store() -> Iterator[tuple[RedisAgentStateStore, str]]:
    import uuid

    url = skip_unless_redis()
    store = RedisAgentStateStore.from_url(url)
    run_id = f"live-{uuid.uuid4().hex}"
    yield store, run_id
    client = store._client
    for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
        client.delete(key)
