"""#480 against real Redis servers. Throwaway redis:8 containers on free loopback ports stand in for this setup's container
and for a foreign Redis that passes ordinary preflight. The operator's own optimus-redis is only read, never changed."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator

import pytest
import redis

from optimus.acp import local_infra
from optimus.acp.preflight import run_preflight

pytestmark = pytest.mark.requires_redis

_PREFLIGHT_ENV = {
    "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
    "OPTIMUS_API_KEY": "opt-live-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
}


def _docker() -> str:
    docker = shutil.which("docker")
    if docker is None or subprocess.run([docker, "image", "inspect", "redis:8"], capture_output=True, check=False).returncode:
        pytest.skip("needs Docker with the redis:8 image already present")
    return docker


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _running(docker: str, name: str) -> bool:
    result = subprocess.run([docker, "inspect", "-f", "{{.State.Running}}", name], capture_output=True, text=True, check=False)
    return result.stdout.strip() == "true"


@pytest.fixture
def start_redis() -> Iterator[Callable[[], tuple[str, int]]]:
    """Start a test-owned redis:8 container; every one is removed afterwards."""
    docker = _docker()
    names: list[str] = []

    def start() -> tuple[str, int]:
        name, port = f"optimus-test-480-{uuid.uuid4().hex[:8]}", _free_port()
        subprocess.run([docker, "run", "-d", "--name", name, "-p", f"127.0.0.1:{port}:6379", "redis:8"],
                       capture_output=True, check=True, timeout=60)
        names.append(name)
        deadline = time.monotonic() + 15
        while True:
            try:
                redis.Redis(host="127.0.0.1", port=port, socket_timeout=1).ping()
                return name, port
            except redis.RedisError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)

    yield start
    for name in names:
        subprocess.run([docker, "rm", "-f", name], capture_output=True, check=False, timeout=60)


def test_a_foreign_redis_that_passes_preflight_is_refused_and_left_running(start_redis, monkeypatch) -> None:
    ours, ours_port = start_redis()
    foreign, foreign_port = start_redis()
    monkeypatch.setattr(local_infra, "_REDIS_CONTAINER_NAME", ours)
    foreign_url = f"redis://127.0.0.1:{foreign_port}/0"
    assert run_preflight({**_PREFLIGHT_ENV, "OPTIMUS_REDIS_URL": foreign_url}, require_timeseries=True) == foreign_url

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_redis(foreign_url)

    assert exc_info.value.code == "REDIS_IDENTITY_UNCONFIRMED"
    with pytest.raises(local_infra.LocalInfrastructureError):
        local_infra.confirm_local_redis(foreign_url)  # a launch that starts nothing (--no-auto-start) refuses it too
    assert _running(_docker(), foreign)
    for confirm in (local_infra.ensure_local_redis, local_infra.confirm_local_redis):
        confirm(f"redis://127.0.0.1:{ours_port}/0")  # the configured container itself is reused


def test_the_default_url_reuses_the_operators_optimus_redis_by_reading_it_only() -> None:
    docker = _docker()
    if not _running(docker, "optimus-redis") or not local_infra._tcp_reachable("127.0.0.1", 6379):
        pytest.skip("the operator's optimus-redis is not running on the default port")
    local_infra.ensure_local_redis(local_infra.DEFAULT_REDIS_URL)
