"""Plan 12.11 Task 2: purge and its journal in the default run, against the in-memory stand-in. What a purge leaves in Redis's
own files is proven on the real instance in tests/integration/memory/test_lifecycle.py."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from redis.exceptions import OutOfMemoryError

from context_engine import memory_contracts as engine
from optimus_gateway import memory_store
from optimus_gateway.memory_files import Entry, Inventory, InventoryUnavailable
from optimus_gateway.memory_journal import PurgeJournal, journal_key
from optimus_security import memory_store_contract as msc
from tests.unit.optimus_gateway.test_memory_store_commit import RESOURCE, Client, Server, append, event, lease, read

ITEM = "m-0123456789abcdef"
OTHER = "m-00000000000000aa"
PAYLOADS = memory_store.MemoryStore._key("p-1", "payloads")
STREAM = memory_store.MemoryStore._key("p-1", "events")
PROJECT = memory_store.MemoryStore._project_hash("p-1")


MANIFEST = "file appendonly.aof.2.base.rdb seq 2 type b\nfile appendonly.aof.2.incr.aof seq 2 type i\n"
CURRENT = ("appendonlydir", "dump.rdb", "appendonlydir/appendonly.aof.2.base.rdb", "appendonlydir/appendonly.aof.2.incr.aof",
           "appendonlydir/appendonly.aof.manifest")


def files(*extra: str | Entry, manifest: str = MANIFEST) -> Inventory:
    """The current snapshot and AOF set, plus `extra` (a name is a regular file)."""
    entries = [Entry("d" if path == "appendonlydir" else "f", path) for path in CURRENT]
    entries += [item if isinstance(item, Entry) else Entry("f", item) for item in extra]
    return Inventory(tuple(entries), manifest)


CLEAN = files()


def store(root: Path, server: Server | None = None, *, journal: bool = True) -> tuple[memory_store.MemoryStoreService, Server, PurgeJournal]:
    server = server or Server()
    server.files = CLEAN  # type: ignore[attr-defined]  # what the data directory holds; a test may leave an old file in it
    purge_journal = PurgeJournal(root / "journal", journal_key("pw"))

    def inventory(_timeout: float) -> Inventory:
        files = server.files  # type: ignore[attr-defined]
        if files is None:
            raise InventoryUnavailable("docker not found")
        return files

    inner = memory_store.MemoryStore(Client(server, 9), Client(server), admission_ceiling_mb=384, cursor_key=b"k",  # type: ignore[arg-type]
                                     journal=purge_journal if journal else None, inventory=inventory)

    def verify(deadline: float) -> None:
        inner.verify(RESOURCE, deadline=deadline)

    return memory_store.MemoryStoreService(inner, verify=verify), server, purge_journal


def call(service: memory_store.MemoryStoreService, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    return service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 5)


def purge(service: memory_store.MemoryStoreService, token: int, item: str = ITEM, key: str = "c" * 64) -> tuple[int, dict[str, Any]]:
    return call(service, {"op": "purge", "project": "p-1", "token": token, "item": item, "idempotency_key": key})


def status(service: memory_store.MemoryStoreService, item: str = ITEM) -> dict[str, Any]:
    code, reply = call(service, {"op": "purge_status", "project": "p-1", "item": item})
    assert code == 200, reply
    return reply


def phases(journal: PurgeJournal, item: str = ITEM) -> list[str]:
    return [entry["phase"] for entry in journal.entries(PROJECT, item)]


def saved(service: memory_store.MemoryStoreService, token: int) -> None:
    for change in (event(), event(version=2, statement="second secret"), event(item=OTHER, event_id="e-00aa-1", statement="kept")):
        code, reply = append(service, token, change)
        assert code == 200 and reply["durable_state"] == "confirmed", reply


def finish_background(server: Server) -> None:
    """What Redis does when the rewrite and the snapshot it was asked for finish well."""
    server.persistence.update(aof_rewrites=server.persistence["aof_rewrites"] + 1, rdb_saves=server.persistence["rdb_saves"] + 1,
                              aof_rewrite_in_progress=0, rdb_bgsave_in_progress=0)


def test_a_purge_destroys_every_version_and_keeps_only_a_payload_free_tombstone(tmp_path: Path) -> None:
    service, server, journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    code, reply = purge(service, token)
    assert code == 200 and reply["durable_state"] == "confirmed" and reply["purge_state"] == "pending", reply
    assert set(server.hashes[PAYLOADS]) == {"e-00aa-1"}  # both versions' payloads gone, the other item's kept
    assert all(b"secret" not in fields[b"e"] for _, fields in server.streams[STREAM])  # the stream never held the text
    tombstone = read(service)
    assert (tombstone["status"], tombstone["version"], tombstone["statement"], tombstone["title"]) == ("purged", 3, "", "")
    assert read(service, OTHER)["statement"] == "kept"
    assert phases(journal) == ["intent", "tombstoned", "physical"]
    assert server.background == ["BGREWRITEAOF", "BGSAVE SCHEDULE"]


def test_the_disk_step_completes_only_after_fresh_rewrites_finish_well(tmp_path: Path) -> None:
    service, server, journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    purge(service, token)
    assert status(service)["purge_state"] == "pending"  # nothing finished yet: nothing reissued either
    assert server.background == ["BGREWRITEAOF", "BGSAVE SCHEDULE"]
    finish_background(server)
    assert status(service)["purge_state"] == memory_store.PURGE_COMPLETED
    assert phases(journal)[-1] == "completed"
    assert status(service)["purge_state"] == memory_store.PURGE_COMPLETED and len(server.background) == 2


RETAINED = files("appendonlydir/copy.aof")  # a file in the AOF directory Redis does not name
HISTORY = files("appendonlydir/appendonly.aof.1.base.rdb", manifest=MANIFEST + "file appendonly.aof.1.base.rdb seq 1 type h\n")
LEFTOVER = files("dump.rdb.bak")
SPACED = files("dump.rdb dump.rdb")  # Codex CP2 review 2, finding 3: split on whitespace, this was two allowed names
NOT_A_FILE = files(Entry("d", "appendonlydir/old"))
# Review 3, finding 4: a field without its value. The line is otherwise a whole next increment, present, so only the pairing
# check refuses it.
UNPAIRED = files("appendonlydir/appendonly.aof.3.incr.aof", manifest=MANIFEST + "file appendonly.aof.3.incr.aof seq 3 type i startoffset\n")


# Review 3, finding 2: no listing shows that Redis made a file and has retired it, so nothing is ever removed. What a Redis
# killed mid-fork leaves (its forks' working files), an increment Redis may name next, and a file anyone made under a Redis
# name alike hold the purge pending until they are gone.
@pytest.mark.parametrize(("inventory", "why"), [
    (RETAINED, "retained_files"), (HISTORY, "history_files"), (LEFTOVER, "unexpected_files"), (SPACED, "unexpected_files"),
    (NOT_A_FILE, "unexpected_files"), (UNPAIRED, "manifest_unreadable"), (None, "file_inventory_unavailable"),
    (files("temp-4242.rdb"), "unexpected_files"), (files("temp-rewriteaof-bg-31.aof"), "unexpected_files"),
    (files("temp-rewriteaof-32.aof"), "unexpected_files"), (files("appendonlydir/appendonly.aof.3.incr.aof"), "retained_files"),
    (files(Entry("l", "temp-4244.rdb")), "unexpected_files"),
])
def test_a_file_outside_the_current_set_holds_the_purge_pending_until_it_is_gone(tmp_path: Path, inventory: Inventory | None,
                                                                                  why: str) -> None:
    """Codex CP2 review 1, finding 2: Redis reports a rewrite as done even when it could not delete the old AOF file."""
    service, server, journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    purge(service, token)
    finish_background(server)
    server.files = inventory  # type: ignore[attr-defined]
    reply = status(service)
    assert (reply["purge_state"], reply["files"]) == ("pending", why) and "completed" not in phases(journal)
    # Codex CP2 review 4: the reply names what holds it and the runbook that says how to check and retire it
    assert bool(reply["blocking"]) == (why != "file_inventory_unavailable") and reply["next"] == "inspect_data_files"
    assert (Path(__file__).parents[3] / reply["runbook"]).is_file()
    assert status(service)["files"] == why  # asked again, nothing changed it: the Gateway removes nothing
    server.files = CLEAN  # type: ignore[attr-defined]  # the operator removed it: the same purge now completes
    assert status(service)["purge_state"] == memory_store.PURGE_COMPLETED


BASE, INCR = "file appendonly.aof.2.base.rdb seq 2 type b\n", "file appendonly.aof.2.incr.aof seq 2 type i\n"
OLD_BASE = "appendonlydir/appendonly.aof.1.base.rdb"


@pytest.mark.parametrize(("inventory", "blocking"), [
    # Codex CP2 review 4, finding 4: a retained old base the manifest lists as a second base is not the manifest Redis writes
    (files(OLD_BASE, manifest=MANIFEST + "file appendonly.aof.1.base.rdb seq 1 type b\n"), ["appendonlydir/appendonly.aof.manifest"]),
    (files(manifest=INCR), ["appendonlydir/appendonly.aof.manifest"]),  # no base
    (files(manifest=INCR + BASE), ["appendonlydir/appendonly.aof.manifest"]),  # the base after an increment
    (files("appendonlydir/appendonly.aof.1.incr.aof", manifest=MANIFEST + "file appendonly.aof.1.incr.aof seq 1 type i\n"),
     ["appendonlydir/appendonly.aof.manifest"]),  # increments out of sequence
    (files(manifest=MANIFEST + INCR), ["appendonlydir/appendonly.aof.manifest"]),  # a file named twice
    (files(manifest="file appendonly.aof.2.incr.aof seq 2 type b\nfile appendonly.aof.2.base.rdb seq 2 type i\n"),
     ["appendonlydir/appendonly.aof.manifest"]),  # a file named for another type
    (files(manifest="file appendonly.aof.2.base.rdb seq 3 type b\n" + INCR), ["appendonlydir/appendonly.aof.manifest"]),  # seq
    (files("appendonlydir/other.aof.2.base.rdb", manifest="file other.aof.2.base.rdb seq 2 type b\n" + INCR),
     ["appendonlydir/appendonly.aof.manifest"]),  # another prefix than the manifest's
    (files(manifest=MANIFEST + "file appendonly.aof.3.incr.aof seq 3 type i\n"), ["appendonlydir/appendonly.aof.manifest"]),  # missing
    (files(OLD_BASE), [OLD_BASE]), (files("temp-4242.rdb", "dump.rdb.bak"), ["dump.rdb.bak", "temp-4242.rdb"]),
])
def test_only_the_manifest_redis_writes_bounds_what_may_stay(inventory: Inventory, blocking: list[str]) -> None:
    """The manifest is checked whole, and a pending residue names what holds it."""
    from optimus_gateway import memory_files

    assert memory_files.residue(files()) is None  # control: the current set
    why = memory_files.residue(inventory)
    assert why is not None and list(why.entries) == blocking, why


LISTING = ("\0--optimus-inventory--\0d appendonlydir\0f dump.rdb\0f appendonlydir/appendonly.aof.2.base.rdb\0"
           "f appendonlydir/appendonly.aof.manifest\0\0--optimus-inventory--\0file appendonly.aof.2.base.rdb seq 2 type b\n")


@pytest.mark.parametrize("output", [
    LISTING.replace("manifest\0\0--", "manifest\0--", 1),  # the last record is not terminated
    LISTING.replace("f dump.rdb\0", "f dump.rdb\0d dump.rdb\0", 1),  # a path twice: a later entry would mask the first
    LISTING.replace("f dump.rdb\0", "ff dump.rdb\0", 1),  # a malformed record (" dump.rdb" with a leading space is a real name)
    LISTING.replace("f dump.rdb\0", "dump.rdb\0", 1),  # a record without its type
    LISTING.replace("f dump.rdb\0", "f /dump.rdb\0", 1),  # not a path relative to the data directory
    LISTING.replace("\0--optimus-inventory--\0", "", 1),  # the framing is incomplete
    "x" + LISTING,  # something before the listing
])
def test_a_malformed_listing_is_unavailable_never_clean(output: str) -> None:
    """Codex CP2 review 3, finding 4: a listing that is not exactly what find and the manifest produce proves nothing."""
    from optimus_gateway import memory_files

    assert memory_files.residue(memory_files.parse(LISTING)) is None  # control: the well-formed listing is clean
    with pytest.raises(memory_files.InventoryUnavailable):
        memory_files.parse(output)


def test_the_inventory_reads_only_the_provisioned_container(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from optimus.acp import local_infra
    from optimus_gateway import memory_files

    assert memory_files.RESOURCE_LABEL == local_infra._MEMORY_RESOURCE_LABEL
    config = SimpleNamespace(container="c", resource="r-1", port=6394)
    # Codex CP2 review 2, finding 3: a name with spaces or a newline is one entry, never two allowed ones
    odd = memory_files.parse(LISTING.replace("f dump.rdb\0", "f dump.rdb dump.rdb\0f a\nb\0", 1))
    assert [entry.path for entry in odd.entries][1:3] == ["dump.rdb dump.rdb", "a\nb"] and memory_files.residue(odd) == memory_files.Residue(
        "unexpected_files", ("a\nb", "dump.rdb dump.rdb"))
    inspected = {"Config": {"Labels": {"optimus.memory.resource": "r-1"}}, "HostConfig": {"PortBindings": {"6379/tcp": [{"HostPort": "6394"}]}}}
    argvs: list[list[str]] = []

    def run(argv, **_kwargs):  # type: ignore[no-untyped-def]
        argvs.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps([inspected]) if argv[1] == "inspect" else LISTING)

    monkeypatch.setattr(memory_files.shutil, "which", lambda _name: "docker")
    monkeypatch.setattr(memory_files.subprocess, "run", run)
    assert memory_files.residue(memory_files.docker_inventory(config)(5.0)) is None  # type: ignore[arg-type]
    assert [argv[1] for argv in argvs] == ["inspect", "exec"] and argvs[-1][-3:-1] == ["sh", "-c"]  # the fixed script alone
    assert "\0" not in argvs[-1][-1] and "rm " not in argvs[-1][-1]  # the NULs are the shell's printf's; nothing is removed
    inspected["Config"]["Labels"]["optimus.memory.resource"] = "someone-else"
    with pytest.raises(memory_files.InventoryUnavailable):
        memory_files.docker_inventory(config)(5.0)  # type: ignore[arg-type]


def test_a_rewrite_already_running_at_the_purge_is_never_counted(tmp_path: Path) -> None:
    """It may have forked before the deletion: the store waits for it, then asks for a fresh one."""
    service, server, _journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    server.persistence.update(aof_rewrite_in_progress=1)
    purge(service, token)
    assert server.background == ["BGSAVE SCHEDULE"]
    server.persistence.update(aof_rewrite_in_progress=0, aof_rewrites=1, rdb_saves=1, rdb_bgsave_in_progress=0)  # both end
    assert status(service)["purge_state"] == "pending"
    assert server.background == ["BGSAVE SCHEDULE", "BGREWRITEAOF"]
    server.persistence.update(aof_rewrites=2, aof_rewrite_in_progress=0)
    assert status(service)["purge_state"] == memory_store.PURGE_COMPLETED


@pytest.mark.parametrize("change", [{"aof_last_bgrewrite_status": "err"}, {"rdb_last_bgsave_status": "err"}])
def test_a_failed_rewrite_or_snapshot_is_asked_for_again(tmp_path: Path, change: dict[str, str]) -> None:
    service, server, _journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    purge(service, token)
    finish_background(server)
    server.persistence.update(change)
    assert status(service)["purge_state"] == "pending" and len(server.background) == 3


def test_a_restarted_redis_starts_the_disk_step_over(tmp_path: Path) -> None:
    """Its counters began again, and it may have loaded files that still hold the text."""
    service, server, _journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    purge(service, token)
    finish_background(server)
    server.run_id = "run-2"
    assert status(service)["purge_state"] == "pending" and server.background[2:] == ["BGREWRITEAOF", "BGSAVE SCHEDULE"]
    finish_background(server)
    assert status(service)["purge_state"] == memory_store.PURGE_COMPLETED


def test_an_unconfirmed_tombstone_is_finished_by_a_retry_under_the_same_key(tmp_path: Path) -> None:
    service, server, journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    server.fsync = 0
    code, first = purge(service, token)
    assert code == 200 and (first["durable_state"], first["purge_state"]) == ("unconfirmed", "pending")
    assert phases(journal) == ["intent"] and server.background == []
    assert status(service) == {"status": "ok", "item": ITEM, "purge_state": "pending"}  # the tombstone is there, not yet proven
    server.fsync = 1
    code, again = purge(service, token)
    assert code == 200 and again["replayed"] is not False and again["stream_id"] == first["stream_id"]
    assert again["durable_state"] == "confirmed" and phases(journal) == ["intent", "tombstoned", "physical"]
    assert len(server.streams[STREAM]) == 4  # three saves and one tombstone: nothing appended twice


def test_a_journal_that_cannot_be_written_stops_the_purge_before_anything_is_sent(tmp_path: Path) -> None:
    service, server, journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    (tmp_path / "journal").write_text("not a directory")  # the journal's root cannot be created
    assert purge(service, token) == (503, msc.error_body("MEMORY_JOURNAL_UNAVAILABLE"))
    assert len(server.streams[STREAM]) == 3 and len(server.hashes[PAYLOADS]) == 3


def test_a_record_the_gateway_did_not_write_is_refused(tmp_path: Path) -> None:
    service, _server, _journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    purge(service, token)
    forged = PurgeJournal(tmp_path / "journal", journal_key("not the password"))
    forged.record(PROJECT, ITEM, "physical", run_id="run-1", aof_target=0, rdb_target=0)
    forged.record(PROJECT, ITEM, "completed", run_id="run-1")  # two records: a dead writer's last one alone is withheld unread
    forged.close()
    code, reply = call(service, {"op": "purge_status", "project": "p-1", "item": ITEM})
    assert (code, reply) == (503, msc.error_body("MEMORY_JOURNAL_INVALID"))


def test_a_purged_item_takes_no_more_changes_and_its_old_keys_replay_nothing(tmp_path: Path) -> None:
    service, _server, _journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    purge(service, token)
    assert append(service, token, event())[1] == msc.error_body("ITEM_PURGED")  # the first save's own key: its digest is gone
    assert append(service, token, event(version=4, event_id="e-new-4")) == (409, msc.error_body("ITEM_PURGED"))
    code, again = purge(service, token, key="d" * 64)  # another key for the same purge finishes it, never refuses it
    assert code == 200 and again["already_purged"] is True and again["purge_state"] == "pending"
    assert purge(service, token, item="m-ffffffffffffffff", key="e" * 64) == (404, msc.error_body("ITEM_UNKNOWN"))
    assert purge(service, token, item=OTHER) == (409, msc.error_body("IDEMPOTENCY_CONFLICT"))  # the purge key, another item


def test_purge_needs_its_journal_and_status_starts_at_none(tmp_path: Path) -> None:
    service, _server, _journal = store(tmp_path, journal=False)
    token = lease(service)
    saved(service, token)
    assert purge(service, token) == (503, msc.error_body("MEMORY_JOURNAL_UNAVAILABLE"))
    service, _server, _journal = store(tmp_path / "with")
    assert status(service) == {"status": "ok", "item": ITEM, "purge_state": "none"}


def test_a_live_item_whose_payload_is_missing_is_damage_never_an_empty_memory(tmp_path: Path) -> None:
    service, server, _journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    server.hashes[PAYLOADS].pop("e-00aa-1")
    fresh, _server, _journal = store(tmp_path / "fresh", server)  # a new Gateway rebuilds its fold from Redis
    assert call(fresh, {"op": "read", "project": "p-1", "item": OTHER}) == (503, msc.error_body("MEMORY_STORAGE_ERROR"))


def test_a_store_at_its_memory_limit_reports_full_not_a_fault(tmp_path: Path) -> None:
    service, server, _journal = store(tmp_path)
    token = lease(service)

    def refuse() -> None:
        raise OutOfMemoryError("Command # 1 (XADD ...) of pipeline caused error: command not allowed when used memory > 'maxmemory'.")

    server.before_exec = refuse
    assert append(service, token, event()) == (507, msc.error_body("MEMORY_FULL"))
    assert STREAM not in server.streams


def test_a_purged_item_is_served_as_the_engine_s_tombstone(tmp_path: Path) -> None:
    service, _server, _journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    purge(service, token)
    stored = engine.StoredEvent.from_record("p-1", read(service))
    assert (stored.event.action, stored.event.status, stored.event.statement, stored.event.version) == ("tombstone", "purged", "", 3)


def test_a_dead_gateway_s_last_journal_record_still_counts(tmp_path: Path) -> None:
    """Fable CP2 M1: a writer that exited never wrote a stream end; its last record is kept once its HMAC verifies."""
    first = PurgeJournal(tmp_path / "journal", journal_key("pw"))
    first.record(PROJECT, ITEM, "intent", version=3, key="c" * 64)
    first.close()  # the process ends: no orderly stream end, the outbox would withhold this tail
    later = PurgeJournal(tmp_path / "journal", journal_key("pw"))
    assert [entry["phase"] for entry in later.entries(PROJECT, ITEM)] == ["intent"]


def test_a_tombstone_redis_holds_is_driven_even_when_the_journal_lost_it(tmp_path: Path) -> None:
    service, server, journal = store(tmp_path)
    token = lease(service)
    saved(service, token)
    server.fsync = 0
    purge(service, token)  # tombstoned in Redis, never proven, so never journalled past its intent
    journal.close()
    import shutil

    shutil.rmtree(tmp_path / "journal")  # and then the journal is lost too
    server.fsync = 1
    fresh, _server, fresh_journal = store(tmp_path, server)
    assert status(fresh)["purge_state"] == "pending" and server.background == ["BGREWRITEAOF", "BGSAVE SCHEDULE"]
    assert phases(fresh_journal) == ["tombstoned", "physical"]
    finish_background(server)
    assert status(fresh)["purge_state"] == memory_store.PURGE_COMPLETED


def test_off_records_over_the_cap_archive_the_oldest_and_stop_at_the_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan 12.11 Task 4: past the active cap, the oldest live off record moves to the unserved archive (still off, now
    superseded, its scanned title kept and marked) and the reply names it, so the growth is visible. Fable CP2 M5 still holds:
    at the store's ceiling a misbehaving model cannot fill it with off records; refusing one loses no knowledge."""
    monkeypatch.setattr(msc, "MAX_OFF_RECORDS", 3)
    service, server, _journal = store(tmp_path)
    token = lease(service)
    for n in range(3):
        off = event(item=f"m-{n:016x}", event_id=f"e-off-{n}", action="off", trust="off", statement="", title="(withheld)")
        assert append(service, token, off)[0] == 200
    extra = event(item="m-00000000000000ff", event_id="e-off-x", action="off", trust="off", statement="", title="(withheld)")
    code, reply = append(service, token, extra)
    assert code == 200 and reply["archived"] == f"m-{0:016x}"
    archived = read(service, f"m-{0:016x}")
    assert (archived["version"], archived["trust"], archived["status"], archived["title"]) == (2, "off", "superseded", "(withheld)")
    assert "archived:overflow" in archived["lineage"] and archived["statement"] == ""
    server.used = 400 * 1024 * 1024  # type: ignore[attr-defined]  # over the 384 MiB admission ceiling
    more = event(item="m-00000000000000fe", event_id="e-off-y", action="off", trust="off", statement="", title="(withheld)")
    assert append(service, token, more) == (507, msc.error_body("OFF_RECORDS_FULL"))
    server.used = 0  # type: ignore[attr-defined]
    assert append(service, token, event())[0] == 200  # a real memory is not an off record
