"""Plan 12.7 P3 live tier: synthetic K2 on the released dedicated Redis only.

Selected explicitly with `-m requires_plan12_probe_redis` and excluded from every default and profile
run. The config comes only from OPTIMUS_PLAN12_PROBE_CONFIG; without it the case skips as UNRUN
before any client or socket exists. No shared Redis fixture, preflight or URL variable is used.
"""

from __future__ import annotations

import json

import pytest

from tools.plan12_memory import probes

pytestmark = [pytest.mark.requires_plan12_probe_redis]


@pytest.fixture
def probe_config() -> probes.ProbeConfig:
    config = probes.config_from_environment()
    if config is None:
        pytest.skip(f"UNRUN: {probes.CONFIG_ENV} names no released probe config; no client was constructed")
    if config.redis is None:
        pytest.fail("the probe config has no released redis section")
    return config


def test_the_shared_server_is_refused_on_every_database(probe_config: probes.ProbeConfig) -> None:
    for endpoint in ("redis://127.0.0.1:6379/0", "redis://localhost:6379/15", "redis://[::1]:6379/1"):
        shared = probes.RedisResource(endpoint=endpoint, container=probe_config.redis.container,
                                      image=probe_config.redis.image, image_id=probe_config.redis.image_id,
                                      volume=probe_config.redis.volume)
        with pytest.raises(probes.AdmissionError):
            probes.admit_redis_endpoint(shared)


def test_synthetic_k2_on_the_released_instance(probe_config: probes.ProbeConfig) -> None:
    before = probes.source_identity()
    result, context = probes.run_probe("redis", probe_config)
    probes.bind_source(result, before, probes.source_identity())
    path = probes.write_attempt(result, probes.DEFAULT_OUT, context.ram_only)
    record = json.loads(path.read_text(encoding="ascii"))
    assert record["source"]["before"] == record["source"]["after"] and record["source"]["before"]["head"] != "UNKNOWN"
    assert record["observations"]["identity"]["container"] == probe_config.redis.container, record["limitations"]
    assert record["outcome"] in {"PASS", "FAIL"}, record["limitations"]
    assert record["disposition"] == "concluded"
