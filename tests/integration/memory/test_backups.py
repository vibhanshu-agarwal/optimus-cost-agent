"""Plan 12.12 Task 1 backups on the released memory store and the released backup folder on a separate physical disk: a real lost
volume and a lost recovery copy restored from the backup with later deletions kept, the real disk query, a withdrawal racing a
backup, and a corrupted backup refused by the Gateway. Selected with `-m requires_plan12_memory_redis`; the backup folder comes
from P1212_BACKUP_TEST_ROOT (the released `F:\\optimus-p1212-test`), else every case skips."""

from __future__ import annotations

import os
import secrets
import shutil
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import memory_commands as mc
from optimus.context import memory_backups as mb
from optimus.context import memory_recovery as mr
from optimus_gateway import memory_store
from tests.integration.memory.conftest import Provisioned
from tests.integration.memory.test_recovery import CANARY, _go, _lose_the_volume, _workspace
from tests.integration.memory.test_store import _project
from tests.integration.memory.test_user_authority import _service, _stream, host

pytestmark = [pytest.mark.requires_plan12_memory_redis]
ROOT_VARIABLE = "P1212_BACKUP_TEST_ROOT"


@pytest.fixture
def backup_root() -> Iterator[Path]:
    root = os.environ.get(ROOT_VARIABLE)
    if not root or not Path(root).is_dir():
        pytest.skip(f"UNRUN: {ROOT_VARIABLE} does not name the released backup folder")
    folder = Path(root) / f"run-{secrets.token_hex(6)}"
    yield folder
    shutil.rmtree(folder, ignore_errors=True)  # only this run's folder inside the released one


def _host(provisioned: Provisioned, tmp_path: Path, project: str, repo: Path) -> tuple[Any, mr.Recovery, mb.Backups, mc.MemoryCommands]:
    store = host(_service(provisioned, tmp_path / "journal"), project)
    recovery = mr.Recovery(store, mr.StateFile(tmp_path / "config", project))
    backups = mb.Backups(recovery, mb.BackupStateFile(tmp_path / "config", project), workspace=repo, config_root=tmp_path / "config")

    def written(action: str, item: str) -> None:
        recovery.written(action, item)
        if action in ("withdraw", "tombstone"):
            backups.withdrawn(item)
    store.guard, store.written = recovery.recovery_required, written
    commands = mc.MemoryCommands(store, trusted=True, sanitize=lambda v: v, recovery=recovery, workspace=repo, backups=backups)
    return store, recovery, backups, commands


def test_the_real_disk_query_marks_the_released_folder_as_a_separate_drive(provisioned: Provisioned, tmp_path: Path,
                                                                            backup_root: Path) -> None:
    repo, project = _workspace(tmp_path), _project()
    _store, _recovery, backups, commands = _host(provisioned, tmp_path, project, repo)
    _go(commands, "/remember Never push to main.")
    _go(commands, "/memory export")
    store_disks, folder_disks = mb.disks(mb.default_store_data() or Path("/nonexistent")), mb.disks(backup_root.parent)
    expected = "separate" if store_disks and folder_disks and not store_disks & folder_disks else None
    assessed = backups.assess(backup_root)
    if expected is None:
        pytest.skip(f"the released folder's disk ({folder_disks}) is not established as separate from the store's ({store_disks})")
    assert assessed["domain"] == expected and "disk" in assessed["reason"], assessed


def test_restore_applies_newer_deletions(provisioned: Provisioned, tmp_path: Path,
                                                                           backup_root: Path) -> None:
    repo, project = _workspace(tmp_path), _project()
    store, recovery, backups, commands = _host(provisioned, tmp_path, project, repo)
    rule = _go(commands, "/remember Never push to main.").notices[0][0]
    secret = _go(commands, f"/remember {CANARY}").notices[0][0]
    other = _go(commands, "/remember Use uv for every command.").notices[0][0]
    _go(commands, "/memory export")
    assert "Backed up" in _go(commands, f"/memory backup configure {backup_root}").text
    (generation,) = mr.generations(backup_root)
    _go(commands, f"/forget {secret.item}@1 --purge")  # after the backup: the journal outlives the volume
    _go(commands, f"/forget {other.item}@1")  # after the backup: the host's state outlives it
    shutil.rmtree(mr.location(repo))  # the recovery copy is gone too: only the other drive holds memory
    _lose_the_volume(provisioned)
    store, recovery, backups, commands = _host(provisioned, tmp_path, project, repo)
    assert recovery.recovery_required() and _stream(provisioned, project) == []
    listed = _go(commands, "/memory restore").text
    assert generation.name in listed and "backup in" in listed, listed
    answer = _go(commands, f"/memory restore {generation.name}")
    assert "Restored" in answer.text, answer.text
    assert store.read(rule.item).event.statement == "Never push to main."
    assert store.read(secret.item).event.status == "purged" and store.read(secret.item).event.statement == ""
    assert store.read(other.item).event.status == "withdrawn"
    raw = b"".join(provisioned.connect().hgetall(memory_store.MemoryStore._key(project, "payloads")).values())
    assert b"zebra-quartz" not in raw


def test_withdrawal_publishes_clean_before_retiring(provisioned: Provisioned, tmp_path: Path, backup_root: Path) -> None:
    repo, project = _workspace(tmp_path), _project()
    store, recovery, backups, commands = _host(provisioned, tmp_path, project, repo)
    items = [_go(commands, f"/remember Rule number {n} holds.").notices[0][0] for n in range(30)]
    _go(commands, "/memory export")
    _go(commands, f"/memory backup configure {backup_root}")
    gone = items[7]
    racer = threading.Thread(target=lambda: _go(commands, f"/forget {gone.item}@1"))
    racer.start()
    try:
        backups.backup()
    except mb.BackupError:
        pass  # a busy recovery copy is a transient outcome, never a published inconsistent generation
    racer.join()
    backups.backup()  # cleanup owed by the withdrawal: a clean generation, older ones removed
    state = backups.state()
    assert state.cleanup_pending == [] and len(mr.generations(backup_root)) == 1
    (generation,) = mr.generations(backup_root)
    body = b"".join((backup_root / generation.name / name).read_bytes() for name in mr.LAYOUT)
    assert b"Rule number 7 holds." not in body
    _lose_the_volume(provisioned)
    store, recovery, backups, commands = _host(provisioned, tmp_path, project, repo)
    assert "Restored" in _go(commands, f"/memory restore {generation.name}").text
    assert store.read(gone.item).event.status == "withdrawn"


def test_corrupted_generation_refuses_restore(provisioned: Provisioned, tmp_path: Path, backup_root: Path) -> None:
    repo, project = _workspace(tmp_path), _project()
    _store, recovery, _backups, commands = _host(provisioned, tmp_path, project, repo)
    _go(commands, "/remember Never push to main.")
    _go(commands, "/memory export")
    _go(commands, f"/memory backup configure {backup_root}")
    (generation,) = mr.generations(backup_root)
    entries = backup_root / generation.name / "entries.jsonl"
    entries.write_bytes(entries.read_bytes().replace(b"main", b"prod"))
    shutil.rmtree(mr.location(repo))
    _lose_the_volume(provisioned)
    _store, recovery, _backups, commands = _host(provisioned, tmp_path, project, repo)
    answer = _go(commands, f"/memory restore {generation.name}")
    assert "do not match its manifest" in answer.text and _stream(provisioned, project) == [], answer.text
