"""Plan 12.11 Task 2: commit, capacity and purge on the released memory store, with the released CP2 fault injection: the same
exact container recreated with variant flags, killed, paused and restarted, and its /data files searched for canaries.

Byte searches run with `--rdbcompression no`: compression hides bytes from a search without removing them, so every search has a
control that must be found in the same files. Selected with `-m requires_plan12_memory_redis`.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import local_infra
from optimus_gateway import memory_store
from optimus_security import memory_store_contract as msc
from tests.integration.memory.conftest import CONTAINER, Provisioned, docker, provisioned_variant, wait_for_auth
from tests.integration.memory.test_store import _append, _call, _event, _lease, _project

pytestmark = [pytest.mark.requires_plan12_memory_redis]

_VISIBLE = ("--rdbcompression", "no")
_SLOW_FORKS = ("--rdb-key-save-delay", "400000")  # microseconds per key, in snapshots and AOF rewrites alike: seconds per fork


def _service(provisioned: Provisioned, journal: Path) -> memory_store.MemoryStoreService:
    keyring = type("Keyring", (), {"get_password": lambda _self, _s, _n: provisioned.password})()
    return memory_store.build_memory_store_service(provisioned.config, keyring_backend=keyring, hmac_key=b"k" * 32, journal_root=journal)


def _purge(service: memory_store.MemoryStoreService, project: str, token: int, item: str, key: str) -> tuple[int, dict[str, Any]]:
    return _call(service, {"op": "purge", "project": project, "token": token, "item": item, "idempotency_key": key})


def _status(service: memory_store.MemoryStoreService, project: str, item: str) -> dict[str, Any]:
    code, reply = _call(service, {"op": "purge_status", "project": project, "item": item})
    assert code == 200, reply
    return reply


def _until_completed(service: memory_store.MemoryStoreService, project: str, item: str, seconds: float = 120) -> float:
    """Poll as the host does. After a restart the first request finds the lost connection and is refused; the next verifies."""
    started = time.monotonic()
    while True:
        code, reply = _call(service, {"op": "purge_status", "project": project, "item": item})
        assert code == 200 or reply == msc.error_body("MEMORY_UNAVAILABLE"), reply
        if reply.get("purge_state") == memory_store.PURGE_COMPLETED:
            return time.monotonic() - started
        assert time.monotonic() - started < seconds, "the disk step did not complete"
        time.sleep(0.25)


def _files_with(needle: str) -> set[str]:
    """Every file under /data holding these exact bytes. grep exits 1 when nothing matches, which is the answer, not an error."""
    found = docker("exec", CONTAINER, "grep", "-racF", "-e", needle, "/data").stdout
    return {line.rsplit(":", 1)[0] for line in found.splitlines() if line and not line.endswith(":0")}


def _stored(text: str) -> str:
    """How the store writes a statement: JSON with non-ASCII escaped."""
    return json.dumps(text, ensure_ascii=True)[1:-1]


def _restart(provisioned: Provisioned) -> None:
    docker("kill", CONTAINER, check=True)  # no clean shutdown: only what reached the AOF survives
    status = local_infra.ensure_memory_store_redis(provisioned.root)
    assert status.state == "ready", status
    wait_for_auth(provisioned)


def _persistence(provisioned: Provisioned) -> dict[str, Any]:
    return dict(provisioned.connect().info("persistence"))


def _saved_pair(service: memory_store.MemoryStoreService, project: str, token: int) -> tuple[str, str, str]:
    """An item with two versions carrying an encoded canary, and a control item that must survive everywhere."""
    canary, control = f"Zebra-Ü-{uuid.uuid4().hex}", f"Kept-é-{uuid.uuid4().hex}"
    item, other = "m-0123456789abcdef", "m-00000000000000aa"
    for event in (_event(item, statement=f"Never {canary} v1"), _event(item, 2, statement=f"Never {canary} v2", title=f"t {canary}"),
                  _event(other, statement=f"Keep {control}")):
        code, reply = _append(service, project, token, event)
        assert code == 200 and reply["durable_state"] == "confirmed", reply
    return item, _stored(canary), _stored(control)


def _assert_erased(provisioned: Provisioned, project: str, canary: str, control: str) -> None:
    client = provisioned.connect()
    stream = client.xrange(memory_store.MemoryStore._key(project, "events"))
    payloads = client.hgetall(memory_store.MemoryStore._key(project, "payloads"))
    assert all(canary.encode() not in fields[b"e"] for _, fields in stream)
    assert all(canary.encode() not in value for value in payloads.values())
    assert any(control.encode() in value for value in payloads.values())
    assert _files_with(canary) == set()  # no wait: a completed purge has seen the directory hold only the manifest's files
    holders = _files_with(control)  # the same search finds the item that was kept, in the snapshot and in the AOF base
    assert "/data/dump.rdb" in holders and any(name.startswith("/data/appendonlydir/") and name.endswith(".base.rdb") for name in holders)


@pytest.fixture(scope="module")
def visible(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Provisioned]:
    with provisioned_variant(tmp_path_factory.mktemp("memory-visible"), *_VISIBLE) as provisioned:
        yield provisioned


# --- purge ------------------------------------------------------------------------------------------------------------


def test_a_purge_leaves_the_text_in_no_key_and_no_file(visible: Provisioned, tmp_path: Path) -> None:
    service, project = _service(visible, tmp_path), _project()
    token = _lease(service, project)
    item, canary, control = _saved_pair(service, project, token)
    assert _files_with(canary)  # before: the text is on disk, so the search can see it
    started = time.monotonic()
    code, reply = _purge(service, project, token, item, "a" * 64)
    assert code == 200 and reply["durable_state"] == "confirmed", reply
    logical = time.monotonic() - started
    assert _call(service, {"op": "read", "project": project, "item": item})[1]["item"]["status"] == "purged"
    physical = _until_completed(service, project, item)
    _assert_erased(visible, project, canary, control)
    assert logical <= 1.0 and physical <= 120  # K2: logical purge <= 1 s after the confirmed tombstone; rewrite <= 120 s


def test_a_file_the_rewrite_left_behind_holds_the_purge_pending_until_it_is_gone(visible: Provisioned, tmp_path: Path) -> None:
    """Codex CP2 review 1, finding 2: Redis can report a rewrite done while an old AOF file it failed to unlink still holds the
    text. Copies of the increment stand in for such files (Codex CP2 review 2, findings 1, 3 and 4). The Gateway removes only
    the one a dead fork of the server's own user would leave; an unlisted AOF part, a Redis name someone else made and a name
    with a space all hold the purge pending until they are gone."""
    service, project = _service(visible, tmp_path), _project()
    token = _lease(service, project)
    item, canary, control = _saved_pair(service, project, token)
    names = docker("exec", CONTAINER, "ls", "-1A", "/data/appendonlydir", check=True).stdout.split()
    increment = f"/data/appendonlydir/{next(name for name in names if name.endswith('.incr.aof'))}"
    dead = "/data/temp-4242.rdb"  # no such process in the container
    kept = ["/data/appendonlydir/appendonly.aof.99.incr.aof", "/data/temp-4243.rdb", "/data/dump.rdb dump.rdb"]
    for user, copy in (("redis", dead), ("redis", kept[0]), ("root", kept[1]), ("root", kept[2])):
        docker("exec", "-u", user, CONTAINER, "cp", increment, copy, check=True)
    assert {dead, *kept} <= _files_with(canary)
    assert _purge(service, project, token, item, "f" * 64)[0] == 200
    deadline = time.monotonic() + 120
    while (reply := _status(service, project, item)).get("files") not in ("unexpected_files", "retained_files"):
        assert reply["purge_state"] == "pending" and time.monotonic() < deadline, reply
        time.sleep(0.25)
    assert _status(service, project, item)["purge_state"] == "pending"  # the rewrite and snapshot are done; the files are not
    assert dead not in _files_with(canary) and set(kept) <= _files_with(canary)  # the Gateway removed the dead fork's alone
    docker("exec", CONTAINER, "rm", *kept, check=True)
    _until_completed(service, project, item)
    _assert_erased(visible, project, canary, control)


def test_a_purge_interrupted_before_its_transaction_sends_nothing_and_a_retry_finishes_it(
        visible: Provisioned, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, project = _service(visible, tmp_path), _project()
    token = _lease(service, project)
    item, canary, control = _saved_pair(service, project, token)
    length = visible.connect().xlen(memory_store.MemoryStore._key(project, "events"))

    def lost(_pipe: Any) -> list[Any]:
        raise memory_store.RedisConnectionError("lost before EXEC")

    monkeypatch.setattr(service._store, "_execute", lost)
    assert _purge(service, project, token, item, "b" * 64) == (503, msc.error_body("MEMORY_UNAVAILABLE"))
    monkeypatch.undo()
    assert visible.connect().xlen(memory_store.MemoryStore._key(project, "events")) == length
    assert _status(service, project, item) == {"status": "ok", "item": item, "purge_state": "pending", "next": "retry_purge"}
    assert _purge(service, project, token, item, "b" * 64)[0] == 200
    _until_completed(service, project, item)
    _assert_erased(visible, project, canary, control)


def test_a_redis_killed_between_the_tombstone_and_its_fsync_proof_is_finished_by_a_retry(
        visible: Provisioned, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, project = _service(visible, tmp_path), _project()
    token = _lease(service, project)
    item, canary, control = _saved_pair(service, project, token)
    plain = memory_store.waitaof_local

    def killed(client: Any, *, timeout_ms: int) -> int:
        docker("kill", CONTAINER, check=True)
        return plain(client, timeout_ms=timeout_ms)

    monkeypatch.setattr(memory_store, "waitaof_local", killed)
    code, reply = _purge(service, project, token, item, "c" * 64)
    monkeypatch.undo()
    assert code == 200 and (reply["durable_state"], reply["purge_state"]) == ("unconfirmed", "pending"), reply
    status = local_infra.ensure_memory_store_redis(visible.root)
    assert status.state == "ready", status
    wait_for_auth(visible)
    code, again = _purge(service, project, token, item, "c" * 64)
    assert code == 200 and again["replayed"] is True and again["durable_state"] == "confirmed", again
    _until_completed(service, project, item)
    _assert_erased(visible, project, canary, control)


# --- commit and capacity ----------------------------------------------------------------------------------------------


def test_competing_gateways_lose_nothing_and_never_write_one_version_twice(visible: Provisioned, tmp_path: Path) -> None:
    first, second, project = _service(visible, tmp_path / "a"), _service(visible, tmp_path / "b"), _project()
    token = _lease(first, project)
    results: list[tuple[int, dict[str, Any]]] = []
    lock = threading.Lock()

    def write(service: memory_store.MemoryStoreService, index: int) -> None:
        outcome = _append(service, project, token, _event(f"m-{index:016x}"))
        same = _append(service, project, token, _event("m-ffffffffffffffff"))  # every writer races for version 1 of one item
        with lock:
            results.extend([outcome, same])

    threads = [threading.Thread(target=write, args=(service, index)) for index, service in enumerate([first, second] * 8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    distinct = [reply for code, reply in results[0::2] if code == 200]
    assert len(distinct) + sum(1 for code, reply in results[0::2] if reply == msc.error_body("MEMORY_CONTENDED")) == 16
    raced = [code for code, _reply in results[1::2]]
    assert raced.count(200) == 1 and set(raced) <= {200, 409}
    stream = visible.connect().xrange(memory_store.MemoryStore._key(project, "events"))
    assert len(stream) == len(distinct) + 1
    assert len({json.loads(fields[b"e"])["event"]["event_id"] for _, fields in stream}) == len(stream)


def test_an_expired_lease_is_fenced_out_by_the_next_holder(visible: Provisioned, tmp_path: Path) -> None:
    service, project = _service(visible, tmp_path), _project()
    code, reply = _call(service, {"op": "lease", "project": project, "owner": "host-1", "action": "acquire", "ttl_ms": 1_000})
    assert code == 200
    time.sleep(1.2)
    newer = _lease(service, project, owner="host-2")
    assert newer > reply["token"]
    assert _append(service, project, reply["token"], _event()) == (409, msc.error_body("LEASE_LOST"))
    assert _append(service, project, newer, _event())[1]["durable_state"] == "confirmed"


def test_a_save_whose_fsync_proof_was_cut_by_a_kill_is_reconciled_by_its_retry(
        visible: Provisioned, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, project = _service(visible, tmp_path), _project()
    token = _lease(service, project)
    plain = memory_store.waitaof_local

    def killed(client: Any, *, timeout_ms: int) -> int:
        docker("kill", CONTAINER, check=True)
        return plain(client, timeout_ms=timeout_ms)

    event = _event()
    monkeypatch.setattr(memory_store, "waitaof_local", killed)
    code, first = _append(service, project, token, event, key="e" * 64)
    monkeypatch.undo()
    assert code == 200 and first["durable_state"] == "unconfirmed", first
    status = local_infra.ensure_memory_store_redis(visible.root)
    assert status.state == "ready", status
    wait_for_auth(visible)
    code, again = _append(service, project, token, event, key="e" * 64)
    assert code == 200 and again["replayed"] is True and again["durable_state"] == "confirmed", again
    assert visible.connect().xlen(memory_store.MemoryStore._key(project, "events")) == 1


def test_a_stalled_server_leaves_a_save_unconfirmed_never_reported_durable(visible: Provisioned, tmp_path: Path) -> None:
    """A slow disk under appendfsync always stalls the whole server; a paused container is that stall, made exact."""
    service, project = _service(visible, tmp_path), _project()
    token = _lease(service, project)
    docker("pause", CONTAINER, check=True)
    try:
        started = time.monotonic()
        code, reply = _append(service, project, token, (event := _event()), key="9" * 64)
        assert time.monotonic() - started < msc.DEADLINE_SECONDS + 1  # the request's deadline holds against a silent server
        assert (code, reply) == (503, msc.error_body("MEMORY_TIMEOUT"))
    finally:
        docker("unpause", CONTAINER, check=True)
    code, again = _append(service, project, token, event, key="9" * 64)  # verified again, then the retry settles it once
    assert code == 200 and again["durable_state"] == "confirmed", again
    assert visible.connect().xlen(memory_store.MemoryStore._key(project, "events")) == 1


def test_a_kill_under_load_keeps_every_confirmed_save_and_retries_settle_the_rest(visible: Provisioned, tmp_path: Path) -> None:
    service, project = _service(visible, tmp_path), _project()
    token = _lease(service, project)
    confirmed: dict[str, str] = {}
    uncertain: list[tuple[str, dict[str, Any]]] = []
    stop = threading.Event()

    def load() -> None:
        index = 0
        while not stop.is_set():
            key, event = uuid.uuid4().hex * 2, _event(f"m-{index:016x}")
            code, reply = _append(service, project, token, event, key=key)
            if code == 200 and reply["durable_state"] == "confirmed":
                confirmed[event["item"]] = event["statement"]
            else:
                uncertain.append((key, event))
            index += 1

    thread = threading.Thread(target=load)
    thread.start()
    time.sleep(1.0)
    docker("kill", CONTAINER, check=True)
    time.sleep(0.5)
    stop.set()
    thread.join()
    status = local_infra.ensure_memory_store_redis(visible.root)
    assert status.state == "ready", status
    wait_for_auth(visible)
    fresh = _service(visible, tmp_path / "fresh")  # a new Gateway: nothing in its RAM
    for item, statement in confirmed.items():
        assert _call(fresh, {"op": "read", "project": project, "item": item})[1]["item"]["statement"] == statement
    for key, event in uncertain:
        code, reply = _append(fresh, project, token, event, key=key)
        assert code == 200 and reply["durable_state"] == "confirmed", reply
    assert visible.connect().xlen(memory_store.MemoryStore._key(project, "events")) == len(confirmed) + len(uncertain)
    assert len(confirmed) > 10


# --- variants: each recreates the released store with other flags, so they run after the shared store's tests ---------


@pytest.mark.parametrize("during", ["aof_rewrite_in_progress", "rdb_bgsave_in_progress"])
def test_a_redis_killed_during_the_rewrite_or_the_snapshot_starts_the_disk_step_over(tmp_path: Path, during: str) -> None:
    with provisioned_variant(tmp_path / "store", *_VISIBLE, *_SLOW_FORKS) as provisioned:
        service, project = _service(provisioned, tmp_path / "journal"), _project()
        token = _lease(service, project)
        item, canary, control = _saved_pair(service, project, token)
        assert _purge(service, project, token, item, "d" * 64)[0] == 200
        deadline = time.monotonic() + 60
        while not _persistence(provisioned).get(during):
            assert time.monotonic() < deadline, f"{during} never started"
            time.sleep(0.05)
        _restart(provisioned)
        _until_completed(service, project, item, seconds=180)
        runs = {entry.get("run_id") for entry in service._store._purge_journal.entries(memory_store.MemoryStore._project_hash(project), item)}
        assert len(runs - {None}) == 2  # the disk step began again under the restarted Redis
        _assert_erased(provisioned, project, canary, control)


def test_a_store_without_aof_admits_nothing(tmp_path: Path) -> None:
    with provisioned_variant(tmp_path / "store", "--appendonly", "no") as provisioned:
        service, project = _service(provisioned, tmp_path / "journal"), _project()
        code, reply = _call(service, {"op": "lease", "project": project, "owner": "host-1", "action": "acquire", "ttl_ms": 60_000})
        assert (code, reply) == (503, msc.error_body("MEMORY_STORE_CONFIGURATION_UNEXPECTED"))
        assert provisioned.connect().dbsize() == 0


def test_saves_stop_at_the_ceiling_and_the_reserve_still_takes_withdrawals_and_purges(tmp_path: Path) -> None:
    with provisioned_variant(tmp_path / "store", *_VISIBLE, admission_ceiling_mb=2) as provisioned:
        service, project = _service(provisioned, tmp_path / "journal"), _project()
        token = _lease(service, project)
        for item in ("m-0123456789abcdef", "m-00000000000000aa"):
            assert _append(service, project, token, _event(item, statement="saved while there is room"))[0] == 200
        provisioned.connect().set("omem:filler", "x" * (2 * 1024 * 1024))  # the store's own memory, past the admission ceiling
        assert _append(service, project, token, _event("m-00000000000000bb")) == (503, msc.error_body("MEMORY_NOT_ADMITTING"))
        withdrawn = _event("m-00000000000000aa", 2, action="withdraw", status="withdrawn", title="", statement="")
        assert _append(service, project, token, withdrawn)[1]["durable_state"] == "confirmed"  # from the reserve
        assert _purge(service, project, token, "m-0123456789abcdef", "f" * 64)[1]["durable_state"] == "confirmed"


def test_a_store_at_its_memory_limit_reports_full_and_writes_nothing_partial(tmp_path: Path) -> None:
    with provisioned_variant(tmp_path / "store", "--maxmemory", "3mb") as provisioned:
        service, project = _service(provisioned, tmp_path / "journal"), _project()
        token = _lease(service, project)
        filler = provisioned.connect()
        for index in range(64):
            try:
                filler.set(f"omem:filler:{index}", "x" * 65536)
            except memory_store.ResponseError:
                break
        before = provisioned.connect().xlen(memory_store.MemoryStore._key(project, "events"))
        assert _append(service, project, token, _event()) == (507, msc.error_body("MEMORY_FULL"))
        client = provisioned.connect()
        assert client.xlen(memory_store.MemoryStore._key(project, "events")) == before
        assert client.hlen(memory_store.MemoryStore._key(project, "payloads")) == 0
