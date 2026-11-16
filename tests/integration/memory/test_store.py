"""Plan 12.11 Task 1: the memory store's dedicated Redis, its access control and the Gateway's start-up checks, on the released
resource. Selected with `-m requires_plan12_memory_redis`. These tests stop and recreate only the exact released container."""

from __future__ import annotations

import json
import socket
import time
import uuid
from typing import Any

import pytest
import redis
from redis.exceptions import AuthenticationError, NoPermissionError, ResponseError

from optimus.acp import local_infra
from optimus_gateway import memory_store
from optimus_security import memory_store_contract as msc
from tests.integration.memory.conftest import CONTAINER, IMAGE, PORT, Provisioned, docker, wait_for_auth

pytestmark = [pytest.mark.requires_plan12_memory_redis]

_CAPS = json.dumps({"op": "capabilities"}).encode()


def test_no_file_and_no_container_argument_holds_the_password(provisioned: Provisioned) -> None:
    for name in ("users.acl", "memory-store.json"):
        assert provisioned.password not in (provisioned.root / name).read_text(encoding="utf-8")
    view = json.loads(docker("inspect", CONTAINER, check=True).stdout)[0]
    assert provisioned.password not in json.dumps(view)
    assert view["Config"]["Image"] == IMAGE and view["Config"]["Labels"]["optimus.memory.resource"] == provisioned.config.resource
    assert view["HostConfig"]["Memory"] == 1024 * 1024 * 1024


def test_the_store_persists_and_never_evicts(provisioned: Provisioned) -> None:
    client = wait_for_auth(provisioned)
    assert client.info("persistence")["aof_enabled"] == 1
    assert client.info("memory")["maxmemory_policy"] == "noeviction"
    client.set("omem:probe", "x")
    assert memory_store.waitaof_local(client, timeout_ms=2000) == 1  # the write is on disk before this returns


def test_without_the_password_nothing_can_be_read(provisioned: Provisioned) -> None:
    anonymous = redis.Redis(host="127.0.0.1", port=PORT, socket_timeout=5)
    with pytest.raises((AuthenticationError, ResponseError)):
        anonymous.get("omem:resource")
    wrong = redis.Redis(host="127.0.0.1", port=PORT, username=provisioned.config.user, password="wrong", socket_timeout=5)
    with pytest.raises(AuthenticationError):
        wrong.ping()


@pytest.mark.parametrize("command", [("FLUSHALL",), ("FLUSHDB",), ("CONFIG", "GET", "*"), ("CONFIG", "SET", "appendonly", "no"), ("KEYS", "*"),
                                     ("EVAL", "return 1", "0"), ("ACL", "LIST"), ("SHUTDOWN",), ("DEBUG", "SLEEP", "0")])
def test_the_memory_user_cannot_run_administrative_commands(provisioned: Provisioned, command: tuple[str, ...]) -> None:
    with pytest.raises((NoPermissionError, ResponseError)):
        provisioned.connect().execute_command(*command)


def test_the_memory_user_cannot_touch_keys_outside_the_store(provisioned: Provisioned) -> None:
    client = provisioned.connect()
    for key in ("oidx:resource", "other:key"):
        with pytest.raises((NoPermissionError, ResponseError)):
            client.set(key, "x")
    client.set("omem:allowed", "x")


def test_the_gateway_verifies_and_serves_capabilities_on_the_real_store(provisioned: Provisioned) -> None:
    keyring = type("Keyring", (), {"get_password": lambda _self, _s, _n: provisioned.password})()
    service = memory_store.build_memory_store_service(provisioned.config, keyring_backend=keyring, hmac_key=b"k" * 32)
    status, reply = service.handle(_CAPS, deadline=time.monotonic() + 5)
    assert status == 200 and reply["durable"] is True and reply["admitting"] is True and reply["admission_ceiling_mb"] == 384
    stored = provisioned.connect().get("omem:resource")
    assert stored == provisioned.config.resource.encode()


def test_another_resource_on_the_port_is_refused(provisioned: Provisioned) -> None:
    client = wait_for_auth(provisioned)
    with pytest.raises(memory_store.MemoryStoreStartupError) as refused:
        memory_store.verify_resource(client, "optimus-memory-store-someone-else")
    assert refused.value.code == "MEMORY_STORE_RESOURCE_MISMATCH"


def test_data_without_the_resource_marker_is_never_claimed(provisioned: Provisioned) -> None:
    client = wait_for_auth(provisioned)
    client.delete("omem:resource")
    client.set("omem:unclaimed", "x")
    try:
        with pytest.raises(memory_store.MemoryStoreStartupError) as refused:
            memory_store.verify_resource(client, provisioned.config.resource)
        assert refused.value.code == "MEMORY_STORE_UNIDENTIFIED_DATA"
        assert client.get("omem:resource") is None  # the refusal wrote nothing
    finally:
        client.delete("omem:unclaimed")
        client.set("omem:resource", provisioned.config.resource)


def test_a_restart_keeps_what_was_confirmed(provisioned: Provisioned) -> None:
    client = wait_for_auth(provisioned)
    client.set("omem:restart-canary", "kept")
    assert memory_store.waitaof_local(client, timeout_ms=2000) == 1
    docker("kill", CONTAINER, check=True)  # no clean shutdown: only what reached the AOF survives
    status = local_infra.ensure_memory_store_redis(provisioned.root)
    assert status.state == "ready", status
    assert wait_for_auth(provisioned).get("omem:restart-canary") == b"kept"


def test_a_container_with_other_settings_is_never_adopted(provisioned: Provisioned) -> None:
    docker("rm", "-f", CONTAINER, check=True)
    docker("run", "-d", "--name", CONTAINER, "--label", f"optimus.memory.resource={provisioned.config.resource}", "-p", f"127.0.0.1:{PORT}:6379",
           "-v", f"{provisioned.config.volume}:/data", IMAGE, "redis-server", "--appendonly", "no", check=True)
    try:
        status = local_infra.ensure_memory_store_redis(provisioned.root)
        assert status.state == "conflict" and "will not change it" in status.detail
    finally:
        docker("rm", "-f", CONTAINER, check=True)
        assert local_infra.ensure_memory_store_redis(provisioned.root).state == "ready"


# --- the operations, through the service's real request path ------------------------------------------------------------


def _service(provisioned: Provisioned, hmac_key: bytes = b"k" * 32) -> memory_store.MemoryStoreService:
    keyring = type("Keyring", (), {"get_password": lambda _self, _s, _n: provisioned.password})()
    return memory_store.build_memory_store_service(provisioned.config, keyring_backend=keyring, hmac_key=hmac_key)


def _call(service: memory_store.MemoryStoreService, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    return service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 5)


def _project() -> str:
    return f"p-{uuid.uuid4().hex[:12]}"


def _lease(service: memory_store.MemoryStoreService, project: str, owner: str = "host-1") -> int:
    status, reply = _call(service, {"op": "lease", "project": project, "owner": owner, "action": "acquire", "ttl_ms": 60_000})
    assert status == 200, reply
    return int(reply["token"])


def _event(item: str = "m-0123456789abcdef", version: int = 1, **changes: Any) -> dict[str, Any]:
    action = "admit" if version == 1 else "update"
    base = {"event_id": f"e-{uuid.uuid4().hex[:12]}", "item": item, "version": version, "action": action, "trust": "user-authored",
            "status": "active", "kind": "preference", "scope": "s-1", "title": "asserts", "statement": f"Use plain asserts, v{version}.",
            "anchors": ["b-1"], "lineage": [], "valid_from_ms": 0, "valid_until_ms": 0}
    return {**base, **changes}


def _append(service: memory_store.MemoryStoreService, project: str, token: int, event: dict[str, Any], *, key: str | None = None,
            expected: int | None = None) -> tuple[int, dict[str, Any]]:
    return _call(service, {"op": "append", "project": project, "token": token, "idempotency_key": key or uuid.uuid4().hex * 2,
                           "expected_version": event["version"] - 1 if expected is None else expected, "event": event})


def _stream_length(provisioned: Provisioned, project: str) -> int:
    return int(provisioned.connect().xlen(memory_store.MemoryStore._key(project, "events")))


def test_a_confirmed_save_is_served_and_versions_move_one_at_a_time(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    token = _lease(service, project)
    status, saved = _append(service, project, token, _event())
    assert status == 200 and (saved["durable_state"], saved["projection_state"], saved["version"]) == ("confirmed", "current", 1)
    assert _call(service, {"op": "read", "project": project, "item": saved["item"]})[1]["item"]["statement"] == "Use plain asserts, v1."
    assert _append(service, project, token, _event(version=2), expected=0) == (400, msc.error_body("REQUEST_INVALID"))
    assert _append(service, project, token, _event(version=3), expected=2) == (409, msc.error_body("VERSION_CONFLICT"))
    assert _append(service, project, token, _event(version=2))[1]["durable_state"] == "confirmed"
    withdrawn = _event(version=3, action="withdraw", status="withdrawn", title="", statement="")
    assert _append(service, project, token, withdrawn)[0] == 200
    item = _call(service, {"op": "read", "project": project, "item": saved["item"]})[1]["item"]
    assert (item["version"], item["status"], item["statement"]) == (3, "withdrawn", "")


def test_a_retry_returns_the_first_result_and_appends_nothing(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    token, event, key = _lease(service, project), _event(), "c" * 64
    first = _append(service, project, token, event, key=key)[1]
    again = _append(service, project, token, event, key=key)[1]
    assert again["replayed"] is True and again["stream_id"] == first["stream_id"] and again["durable_state"] == "confirmed"
    assert _stream_length(provisioned, project) == 1
    assert _append(service, project, token, {**event, "statement": "Something else."}, key=key) == (409, msc.error_body("IDEMPOTENCY_CONFLICT"))
    assert _append(service, project, token, {**_event(item="m-00000000000000aa"), "event_id": event["event_id"]}) == (409, msc.error_body("EVENT_ID_REUSED"))
    assert _stream_length(provisioned, project) == 1


def test_a_fresh_gateway_rebuilds_the_same_view_from_the_stream(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    token, event, key = _lease(service, project), _event(), "d" * 64
    _append(service, project, token, event, key=key)
    restarted = _service(provisioned)  # no cache: everything comes from the stream
    assert _call(restarted, {"op": "read", "project": project, "item": event["item"]})[1]["item"]["event_id"] == event["event_id"]
    assert _append(restarted, project, token, event, key=key)[1]["replayed"] is True
    assert _append(restarted, project, token, _event(), expected=0) == (409, msc.error_body("VERSION_CONFLICT"))


def test_only_the_lease_holder_appends_and_a_new_holder_fences_the_old_one(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    first = _lease(service, project, "host-1")
    assert _call(service, {"op": "lease", "project": project, "owner": "host-2", "action": "acquire", "ttl_ms": 60_000}) == (409, msc.error_body("LEASE_HELD"))
    resumed = _lease(service, project, "host-1")
    assert resumed > first
    assert _append(service, project, first, _event()) == (409, msc.error_body("LEASE_LOST"))
    assert _append(service, project, resumed, _event())[0] == 200
    assert _call(service, {"op": "lease", "project": project, "owner": "host-1", "action": "release", "token": resumed})[0] == 200
    assert _append(service, project, resumed, _event(item="m-00000000000000bb")) == (409, msc.error_body("LEASE_LOST"))
    assert _lease(service, project, "host-2") > resumed


def test_an_event_whose_fsync_was_never_confirmed_is_not_served_until_a_later_one_is(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    token = _lease(service, project)
    unconfirmed = _event(item="m-00000000000000cc")
    record = {"type": "event", "key": "e" * 64, "digest": "0" * 64, "event": unconfirmed}
    provisioned.connect().xadd(memory_store.MemoryStore._key(project, "events"), {"e": json.dumps(record)})  # appended, never confirmed
    assert _call(service, {"op": "read", "project": project, "item": unconfirmed["item"]})[1]["item"] is None
    assert _append(service, project, token, _event())[1]["durable_state"] == "confirmed"
    # AOF is ordered: the later confirmation covers the earlier append too
    assert _call(service, {"op": "read", "project": project, "item": unconfirmed["item"]})[1]["item"]["event_id"] == unconfirmed["event_id"]


def test_lists_page_by_item_and_a_cursor_works_only_where_it_was_issued(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    token = _lease(service, project)
    items = [f"m-{n:016x}" for n in range(5)]
    for item in items:
        _append(service, project, token, _event(item=item))
    _append(service, project, token, _event(item="m-00000000000000ff", scope="s-2"))
    status, first = _call(service, {"op": "list", "project": project, "scope": "s-1", "limit": 3})
    assert status == 200 and [entry["item"] for entry in first["items"]] == items[:3] and first["cursor"]
    rest = _call(service, {"op": "list", "project": project, "scope": "s-1", "limit": 3, "cursor": first["cursor"]})[1]
    assert [entry["item"] for entry in rest["items"]] == items[3:] and rest["cursor"] is None
    for elsewhere in ({"project": _project(), "scope": "s-1"}, {"project": project, "scope": "s-2"}):
        assert _call(service, {"op": "list", "limit": 3, "cursor": first["cursor"], **elsewhere}) == (400, msc.error_body("CURSOR_INVALID"))
    other_key = _service(provisioned, hmac_key=b"z" * 32)
    assert _call(other_key, {"op": "list", "project": project, "scope": "s-1", "limit": 3, "cursor": first["cursor"]}) == (400, msc.error_body("CURSOR_INVALID"))


def test_projects_are_separate_but_any_holder_of_the_key_can_name_any_project(provisioned: Provisioned) -> None:
    service, mine, theirs = _service(provisioned), _project(), _project()
    _append(service, theirs, _lease(service, theirs), _event(item="m-00000000000000dd"))
    assert _call(service, {"op": "list", "project": mine, "scope": "s-1", "limit": 10})[1]["items"] == []
    # Residual (ADR-037's, kept by ADR-042): the Gateway authenticates the shared key, not the workspace. The host binds projects.
    assert _call(service, {"op": "read", "project": theirs, "item": "m-00000000000000dd"})[1]["item"] is not None


def test_checkpoints_are_kept_once_and_served_newest_first(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    token = _lease(service, project)
    point = {"session": "sess-1", "sequence": 1, "branch": "main", "worktree": "wt-1", "baseline": "", "settled_at_ms": 1,
             "outcome": "settled", "objective": "obj-1", "provenance": "turn-1", "plan_hash": "", "pending": [], "amendments": [],
             "completion": [], "verification": [], "remaining": []}
    for sequence in (1, 2, 3):
        status, reply = _call(service, {"op": "checkpoint", "project": project, "token": token, "checkpoint": {**point, "sequence": sequence}})
        assert status == 200 and reply["durable_state"] == "confirmed"
    assert _call(service, {"op": "checkpoint", "project": project, "token": token, "checkpoint": point})[1]["replayed"] is True
    assert _call(service, {"op": "checkpoint", "project": project, "token": token, "checkpoint": {**point, "outcome": "failed"}}) == (409, msc.error_body("IDEMPOTENCY_CONFLICT"))
    served = _call(service, {"op": "checkpoints", "project": project, "limit": 2})[1]["checkpoints"]
    assert [entry["sequence"] for entry in served] == [3, 2]


def test_a_connection_keeps_the_request_budget_through_a_real_command(provisioned: Provisioned) -> None:
    client = memory_store.connect(provisioned.endpoint())
    client.ping()
    memory_store.set_budget(client, 0.3)
    client.ping()  # a real checkout runs its probe, which restores the parser's cached timeout
    connection = client.optimus_link.connection
    assert connection.socket_timeout == 0.3 and connection._sock.gettimeout() == 0.3 and connection._parser._buffer.socket_timeout == 0.3
    memory_store.set_budget(client, msc.DEADLINE_SECONDS)
    client.ping()
    assert connection._sock.gettimeout() == msc.DEADLINE_SECONDS


def _drop(client: redis.Redis) -> None:
    """Close the connection's socket under redis-py, as a server restart would; the pool reconnects at the next checkout."""
    client.optimus_link.connection._sock.shutdown(socket.SHUT_RDWR)


def test_a_silent_reconnect_is_never_used_before_the_resource_is_verified_again(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    token = _lease(service, project)
    _drop(service._store._writer)
    assert _append(service, project, token, _event()) == (503, msc.error_body("MEMORY_UNAVAILABLE"))  # reconnected, then refused
    assert _append(service, project, token, _event())[1]["durable_state"] == "confirmed"  # verified again first
    assert service._store._writer.optimus_link.connects == 2


def test_a_reconnect_to_another_resource_is_refused(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    token = _lease(service, project)
    admin = provisioned.connect()
    admin.set("omem:resource", "optimus-memory-store-someone-else")
    try:
        _drop(service._store._redis)
        assert _call(service, {"op": "read", "project": project, "item": "m-0123456789abcdef"}) == (503, msc.error_body("MEMORY_UNAVAILABLE"))
        assert _append(service, project, token, _event()) == (503, msc.error_body("MEMORY_STORE_RESOURCE_MISMATCH"))
        assert _stream_length(provisioned, project) == 0
    finally:
        admin.set("omem:resource", provisioned.config.resource)


def test_the_writer_is_one_connection_without_retries(provisioned: Provisioned) -> None:
    writer = memory_store.connect(provisioned.endpoint())
    pool = writer.connection_pool
    assert isinstance(pool, redis.BlockingConnectionPool) and pool.max_connections == 1
    assert int(writer.client_id()) == int(writer.client_id())  # the same connection answers twice
    connection = pool.get_connection()
    try:
        assert connection.retry._retries == 0
    finally:
        pool.release(connection)


def test_fifty_saves_in_a_row_are_each_confirmed_within_the_commit_timeout(provisioned: Provisioned) -> None:
    service, project = _service(provisioned), _project()
    token = _lease(service, project)
    took: list[float] = []
    for n in range(50):
        started = time.perf_counter()
        status, reply = _append(service, project, token, _event(item=f"m-{n:016x}"))
        took.append(time.perf_counter() - started)
        assert status == 200 and reply["durable_state"] == "confirmed", reply
    took.sort()
    print(f"ack seconds: p50={took[24]:.4f} p95={took[47]:.4f} max={took[-1]:.4f}")
    assert took[-1] < memory_store._WAITAOF_COMMIT_MS / 1000
