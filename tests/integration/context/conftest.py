"""Provisions the released dedicated Redis the way a real launch does: `memory-setup` writes the configuration, then
`ensure_memory_redis` creates the container from its hash-only ACL file.

Only the exact released names are ever removed or created, and only when P1210_INDEX_DOCKER_RELEASED says so; without it every
case skips before any client or Docker command runs. Never the shared test Redis.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import redis

from optimus.acp import local_infra
from optimus.acp.memory_setup import run_setup
from optimus_gateway import memory_index
from optimus_security.memory_index_config import KEYRING_SERVICE, MemoryIndexConfig, artifact_digest, memory_index_root, read
from tests.unit.acp.conftest import FakeKeyring

RELEASE_FLAG = "P1210_INDEX_DOCKER_RELEASED"
CONTAINER = "p1210-index-test-redis"
VOLUME = "p1210-index-test-data"
PORT = 6392
IMAGE = "redis@sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5"


def docker(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=120)


def remove_released_resources() -> None:
    docker("rm", "-f", CONTAINER)
    docker("volume", "rm", "-f", VOLUME)


def _fake_artifact(*, repository: str, revision: str, target: Path) -> None:
    (target / "model.onnx").write_bytes(repository.encode("utf-8") + revision.encode("utf-8"))


def settings(tmp: Path) -> dict[str, Any]:
    probe = tmp / "probe"
    probe.mkdir(exist_ok=True)
    _fake_artifact(repository="test/repository", revision="abc", target=probe)
    embedding = {"model": "test/model", "source": "test", "repository": "test/repository", "revision": "abc", "licence": "MIT",
                 "dimensions": 8, "max_input_tokens": 16, "artifact_directory": "model", "artifact_sha256": artifact_digest(probe)}
    return {"image": IMAGE, "container": CONTAINER, "volume": VOLUME, "host": "127.0.0.1", "port": PORT, "user": "optimus-index",
            "maxmemory_mb": 512, "artifact_megabytes": 1, "embedding": embedding}  # 1 GiB in all, with the container's headroom: the released cap


@dataclass
class Provisioned:
    root: Path
    config: MemoryIndexConfig
    password: str

    def endpoint(self) -> memory_index.IndexEndpoint:
        return memory_index.IndexEndpoint(self.config.host, self.config.port, self.config.user, self.password, self.config.resource)

    def connect(self) -> redis.Redis:
        return memory_index.connect(self.endpoint())


def setup_config(tmp: Path) -> tuple[Path, MemoryIndexConfig, str]:
    keyring = FakeKeyring()
    run_setup(tmp, keyring_backend=keyring, confirm=lambda _description: True, download=_fake_artifact, defaults=settings(tmp))
    root = memory_index_root(tmp)
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
    root, config, password = setup_config(tmp_path_factory.mktemp("memory-config"))
    status = local_infra.ensure_memory_redis(root)
    assert status.state == "ready", status
    yield Provisioned(root, config, password)
