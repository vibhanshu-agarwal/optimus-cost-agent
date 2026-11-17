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
from optimus_gateway.memory_journal import PurgeJournal, journal_key
from optimus_security import memory_store_contract as msc
from tests.unit.optimus_gateway.test_memory_store_commit import RESOURCE, Client, Server, append, event, lease, read

ITEM = "m-0123456789abcdef"
OTHER = "m-00000000000000aa"
PAYLOADS = memory_store.MemoryStore._key("p-1", "payloads")
STREAM = memory_store.MemoryStore._key("p-1", "events")
PROJECT = memory_store.MemoryStore._project_hash("p-1")


def store(root: Path, server: Server | None = None, *, journal: bool = True) -> tuple[memory_store.MemoryStoreService, Server, PurgeJournal]:
    server = server or Server()
    purge_journal = PurgeJournal(root / "journal", journal_key("pw"))
    inner = memory_store.MemoryStore(Client(server, 9), Client(server), admission_ceiling_mb=384, cursor_key=b"k",  # type: ignore[arg-type]
                                     journal=purge_journal if journal else None)

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


def test_off_records_stop_at_the_cap_and_withdrawals_still_go_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fable CP2 M5: a misbehaving model cannot fill the store with off records."""
    monkeypatch.setattr(msc, "MAX_OFF_RECORDS", 3)
    service, _server, _journal = store(tmp_path)
    token = lease(service)
    for n in range(3):
        off = event(item=f"m-{n:016x}", event_id=f"e-off-{n}", action="off", trust="off", statement="", title="(withheld)")
        assert append(service, token, off)[0] == 200
    extra = event(item="m-00000000000000ff", event_id="e-off-x", action="off", trust="off", statement="", title="(withheld)")
    assert append(service, token, extra) == (507, msc.error_body("OFF_RECORDS_FULL"))
    assert append(service, token, event())[0] == 200  # a real memory is not an off record
