"""Plan 12.10 Task 2: the dedicated Redis's lifecycle and access control, on the released resource.

Selected with `-m requires_plan12_index_redis`. These tests stop, kill and recreate only the exact released container.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest
import redis
from redis.exceptions import AuthenticationError, NoPermissionError, ResponseError

from optimus.acp import local_infra
from optimus_gateway import memory_index
from optimus_security import memory_index_contract as mic
from tests.integration.context import conftest as provision
from tests.integration.context.conftest import CONTAINER, IMAGE, PORT, Provisioned, docker, remove_released_resources

pytestmark = [pytest.mark.requires_plan12_index_redis]


def _container_id() -> str:
    return docker("inspect", "--format", "{{.Id}}", CONTAINER, check=True).stdout.strip()


def _wait_for_auth(provisioned: Provisioned) -> redis.Redis:
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


def test_the_acl_file_holds_only_the_hash(provisioned: Provisioned) -> None:
    acl = (provisioned.root / "users.acl").read_text(encoding="utf-8")
    assert provisioned.password not in acl and "user default off" in acl
    config = (provisioned.root / "memory-index.json").read_text(encoding="utf-8")
    assert provisioned.password not in config


def test_the_running_container_was_created_with_no_secret_in_its_arguments(provisioned: Provisioned) -> None:
    view = json.loads(docker("inspect", CONTAINER, check=True).stdout)[0]
    text = json.dumps(view)
    assert provisioned.password not in text
    assert view["Config"]["Image"] == IMAGE
    assert view["Config"]["Labels"]["optimus.memory.resource"] == provisioned.config.resource


def test_without_the_password_nothing_can_be_read(provisioned: Provisioned) -> None:
    anonymous = redis.Redis(host="127.0.0.1", port=PORT, socket_timeout=5)
    with pytest.raises((AuthenticationError, ResponseError)):
        anonymous.get("oidx:resource")
    wrong = redis.Redis(host="127.0.0.1", port=PORT, username=provisioned.config.user, password="wrong", socket_timeout=5)
    with pytest.raises(AuthenticationError):
        wrong.ping()


@pytest.mark.parametrize("command", [("FLUSHALL",), ("CONFIG", "GET", "*"), ("KEYS", "*"), ("EVAL", "return 1", "0"), ("ACL", "LIST"), ("SHUTDOWN",)])
def test_the_index_user_cannot_run_administrative_commands(provisioned: Provisioned, command: tuple[str, ...]) -> None:
    client = provisioned.connect()
    with pytest.raises((NoPermissionError, ResponseError)):
        client.execute_command(*command)


def test_the_index_user_cannot_touch_keys_outside_the_index(provisioned: Provisioned) -> None:
    client = provisioned.connect()
    with pytest.raises((NoPermissionError, ResponseError)):
        client.set("other:key", "x")
    client.set("oidx:allowed", "x")
    client.delete("oidx:allowed")


def test_the_resource_check_passes_under_the_real_acl(provisioned: Provisioned) -> None:
    client = provisioned.connect()
    client.delete("oidx:resource")
    memory_index.verify_resource(client, provisioned.config.resource)


def test_ensuring_again_keeps_the_same_container(provisioned: Provisioned) -> None:
    before = _container_id()
    assert local_infra.ensure_memory_redis(provisioned.root).state == "ready"
    assert _container_id() == before


def test_concurrent_launches_agree_on_one_resource(provisioned: Provisioned) -> None:
    remove_released_resources()
    results: list[str] = []
    threads = [threading.Thread(target=lambda: results.append(local_infra.ensure_memory_redis(provisioned.root).state)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(120)
    assert results == ["ready"] * 4, results
    assert docker("ps", "--filter", f"name=^/{CONTAINER}$", "--format", "{{.Names}}", check=True).stdout.split() == [CONTAINER]


def test_data_survives_a_stop_and_a_start(provisioned: Provisioned) -> None:
    client = _wait_for_auth(provisioned)
    client.set("oidx:survivor", "kept")
    time.sleep(1.5)  # appendfsync everysec
    docker("stop", CONTAINER, check=True)
    assert local_infra.ensure_memory_redis(provisioned.root, start=False).state == "unavailable"
    assert local_infra.ensure_memory_redis(provisioned.root).state == "ready"
    assert _wait_for_auth(provisioned).get("oidx:survivor") == b"kept"


def test_no_auto_start_only_checks(provisioned: Provisioned) -> None:
    docker("stop", CONTAINER, check=True)
    assert local_infra.ensure_memory_redis(provisioned.root, start=False).state == "unavailable"
    assert docker("inspect", "--format", "{{.State.Running}}", CONTAINER, check=True).stdout.strip() == "false"
    assert local_infra.ensure_memory_redis(provisioned.root).state == "ready"


def test_a_stranger_in_the_container_name_is_refused_and_left_alone(provisioned: Provisioned) -> None:
    remove_released_resources()
    docker("run", "-d", "--name", CONTAINER, IMAGE, check=True)
    stranger = _container_id()
    status = local_infra.ensure_memory_redis(provisioned.root)
    assert status.state == "conflict" and "will not change it" in status.detail
    assert _container_id() == stranger
    remove_released_resources()
    assert local_infra.ensure_memory_redis(provisioned.root).state == "ready"


def test_a_stranger_on_the_port_is_refused_and_left_alone(provisioned: Provisioned) -> None:
    remove_released_resources()
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE if hasattr(socket, "SO_EXCLUSIVEADDRUSE") else socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", PORT))
        listener.listen(1)
        status = local_infra.ensure_memory_redis(provisioned.root)
        assert status.state == "conflict" and "listening" in status.detail
    assert docker("ps", "-a", "--filter", f"name=^/{CONTAINER}$", "--format", "{{.Names}}", check=True).stdout.split() == []
    assert local_infra.ensure_memory_redis(provisioned.root).state == "ready"


def test_a_changed_acl_file_is_refused(provisioned: Provisioned, tmp_path: Path) -> None:
    root, _config, _password = provision.setup_config(tmp_path)
    (root / "users.acl").write_text("user default on nopass ~* +@all\n", encoding="utf-8")
    status = local_infra.ensure_memory_redis(root)
    assert status.state == "conflict" and "ACL" in status.detail


def test_an_outage_refuses_index_requests_and_recovery_proves_itself_again(provisioned: Provisioned) -> None:
    client = _wait_for_auth(provisioned)
    verified: list[int] = []

    def verify() -> None:
        memory_index.verify_resource(client, provisioned.config.resource)
        verified.append(1)

    service = memory_index.IndexService(memory_index.IndexStore(client, cursor_key=b"c" * 32), verify=verify)
    request = json.dumps({"op": "generation", "scope": "ab" * 32, "action": "open", "embedding": "e", "dimensions": 8, "schema_version": 1}).encode()
    assert service.handle(request, deadline=time.monotonic() + 5)[0] == 200
    docker("kill", CONTAINER, check=True)
    assert service.handle(request, deadline=time.monotonic() + 5) == (503, mic.error_body("INDEX_UNAVAILABLE"))
    assert local_infra.ensure_memory_redis(provisioned.root).state == "ready"
    _wait_for_auth(provisioned)
    assert service.handle(request, deadline=time.monotonic() + 5)[0] == 200
    assert len(verified) == 2
