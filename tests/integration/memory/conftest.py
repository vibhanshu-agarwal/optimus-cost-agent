"""Provisions the released dedicated memory Redis the way a real launch does: `memory-setup --store` writes the configuration,
then `ensure_memory_store_redis` creates the container from its hash-only ACL file.

Only the exact released names are ever removed or created, and only when P1211_MEMORY_DOCKER_RELEASED says so; without it every
case skips before any client or Docker command runs. Never the shared test Redis, the index's Redis or the product store.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import redis

from optimus.acp import local_infra
from optimus.acp.memory_setup import run_store_setup
from optimus_gateway import memory_store
from optimus_security.memory_store_config import KEYRING_SERVICE, MemoryStoreConfig, memory_store_root, read
from tests.unit.acp.conftest import FakeKeyring

RELEASE_FLAG = "P1211_MEMORY_DOCKER_RELEASED"
CONTAINER = "p1211-cp3-test-redis"  # the CP3 release (2026-11-18); CP1/CP2 used p1211-memory-test-redis, removed at CP2 close
VOLUME = "p1211-cp3-test-data"
PORT = 6396
IMAGE = "redis@sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5"


def docker(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=120)


def remove_released_resources() -> None:
    docker("rm", "-f", CONTAINER)
    docker("volume", "rm", "-f", VOLUME)


def settings() -> dict[str, Any]:
    # 512 MiB with the container's 512 MiB headroom: the released 1 GiB cap
    return {"image": IMAGE, "container": CONTAINER, "volume": VOLUME, "host": "127.0.0.1", "port": PORT, "user": "optimus-memory",
            "maxmemory_mb": 512, "admission_ceiling_mb": 384}


@dataclass
class Provisioned:
    root: Path
    config: MemoryStoreConfig
    password: str

    def endpoint(self) -> memory_store.MemoryStoreEndpoint:
        return memory_store.MemoryStoreEndpoint(self.config.host, self.config.port, self.config.user, self.password, self.config.resource)

    def connect(self) -> redis.Redis:
        return memory_store.connect(self.endpoint())


def setup_config(tmp: Path, **changes: Any) -> tuple[Path, MemoryStoreConfig, str]:
    keyring = FakeKeyring()
    run_store_setup(tmp, keyring_backend=keyring, confirm=lambda _description: True, defaults={**settings(), **changes})
    root = memory_store_root(tmp)
    _literal, config, _refusal = read(root)
    assert config is not None
    password = keyring.get_password(KEYRING_SERVICE, config.credential_name)
    assert password
    return root, config, password


@pytest.fixture(scope="module")
def provisioned(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Provisioned]:
    if not os.environ.get(RELEASE_FLAG) or shutil.which("docker") is None:
        pytest.skip(f"UNRUN: {RELEASE_FLAG} is not set; no Docker command or client ran")
    remove_released_resources()
    root, config, password = setup_config(tmp_path_factory.mktemp("memory-store-config"))
    status = local_infra.ensure_memory_store_redis(root)
    assert status.state == "ready", status
    provisioned = Provisioned(root, config, password)
    memory_store.verify_resource(wait_for_auth(provisioned), config.resource)  # the Gateway claims the empty store at its start
    yield provisioned


def wait_for_auth(provisioned: Provisioned) -> redis.Redis:
    client = provisioned.connect()
    deadline = time.monotonic() + 30
    while True:
        try:
            client.ping()
            return client
        except redis.RedisError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


@contextlib.contextmanager
def provisioned_variant(tmp: Path, *server_flags: str, **setting_changes: Any) -> Iterator[Provisioned]:
    """The released store recreated with extra server flags or settings (the released CP2 fault injection). The flags stay in
    force for every restart inside the block, so the launch's own settings check still matches; the plain launch returns after."""
    if not os.environ.get(RELEASE_FLAG) or shutil.which("docker") is None:
        pytest.skip(f"UNRUN: {RELEASE_FLAG} is not set; no Docker command or client ran")
    plain = local_infra._memory_store_server_args
    local_infra._memory_store_server_args = lambda config: [*plain(config), *server_flags]  # type: ignore[assignment]
    try:
        remove_released_resources()
        root, config, password = setup_config(tmp, **setting_changes)
        status = local_infra.ensure_memory_store_redis(root)
        assert status.state == "ready", status
        provisioned = Provisioned(root, config, password)
        wait_for_auth(provisioned)
        yield provisioned
    finally:
        local_infra._memory_store_server_args = plain  # type: ignore[assignment]
