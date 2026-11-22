"""Plan 12.12 Task 1: configured backups of the recovery copy, against the real store on its in-memory stand-in, real Git
repositories and the real file system (frozen cases B01-B31 in reports/plan12-memory-m3-part2/cases.json). Physical disks are
injected here; the real disk query and the real store are exercised in tests/integration/memory/test_backups.py."""

from __future__ import annotations

import errno
import json
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import memory_commands as mc
from optimus.context import memory_backups as mb
from optimus.context import memory_recovery as mr
from tests.unit.context.test_memory_recovery import CANARY, LOCK_FAULTS, _git, _Host, fault_platform_lock

DAY = 24 * 3600 * 1000


class _Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000_000

    def __call__(self) -> int:
        return self.now


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    (path / "README.md").write_text("x", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "first")
    return path


@pytest.fixture
def places(tmp_path: Path) -> dict[str, Path]:
    found = {name: tmp_path / name for name in ("store-data", "separate", "same", "nowhere")}
    for path in found.values():
        path.mkdir()
    return found


def _disks(places: dict[str, Path], repo_path: Path) -> Any:
    def disk_of(path: Path) -> frozenset[str] | None:
        text = str(path)
        if text.startswith(str(places["store-data"])) or text.startswith(str(places["same"])):
            return frozenset({"disk1"})
        if text.startswith(str(places["separate"])):
            return frozenset({"disk2"})
        if text.startswith(str(repo_path)):
            return frozenset({"disk1"})
        return None
    return disk_of


class _Backed(_Host):
    """A host with backups wired as the launch wires them: withdrawals mark backup cleanup."""

    def __init__(self, tmp_path: Path, workspace: Path, places: dict[str, Path], clock: _Clock, **kwargs: Any) -> None:
        super().__init__(tmp_path, workspace, **kwargs)
        self.clock = clock
        self.recovery._clock = clock
        self.backups = mb.Backups(self.recovery, mb.BackupStateFile(tmp_path / kwargs.get("config", "config"), self.store.project),
                                  workspace=workspace, config_root=tmp_path / kwargs.get("config", "config"),
                                  store_data=lambda: places["store-data"], disk_of=_disks(places, workspace), clock=clock,
                                  sleep=lambda _s: None)
        recovery_written = self.recovery.written

        def written(action: str, item: str) -> None:
            recovery_written(action, item)
            if action in ("withdraw", "tombstone"):
                self.backups.withdrawn(item)
        self.store.written = written
        self.commands = mc.MemoryCommands(self.store, trusted=True, sanitize=lambda v: v, recovery=self.recovery, workspace=workspace,
                                          backups=self.backups)

    def set_up(self, target: Path, *, cloud: bool = False) -> mc.MemoryAnswer:
        if self.recovery.state().destination is None:
            self.run("/memory export")
        return self.run(f"/memory backup configure {target}" + (" --cloud" if cloud else ""))


def _published(target: Path) -> list[str]:
    return sorted(g.name for g in mr.generations(target))


def test_b01_backups_are_off_until_configured_and_write_nothing(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    assert host.backups.run_if_due() is None
    assert not any(any(places[name].iterdir()) for name in ("separate", "same"))
    assert "Backups: off (not configured)" in host.run("/memory backup").text


def test_b02_b22_a_separate_disk_target_holds_the_exact_generation_bytes(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.run("/memory export")
    question = host.commands.run(mc.MemoryCommand("backup_configure", target=str(places["separate"] / "b")), block="c").confirm
    assert question is not None and "separate physical disk" in question.text and mb.ENCRYPTION_UNAVAILABLE in question.text
    assert not (places["separate"] / "b").exists()  # nothing before the user confirms
    answer = host.commands.confirmed(question)
    assert "Backed up" in answer.text
    (name,) = _published(places["separate"] / "b")
    source = Path(host.recovery.state().destination or "") / name
    for file in mr.LAYOUT:  # byte-identical to the exact generation it copies, nothing rewritten
        assert (places["separate"] / "b" / name / file).read_bytes() == (source / file).read_bytes()
    state = host.backups.state()
    assert state.domain == "separate" and state.last_success and state.last_success["name"] == name


def test_b03_after_downtime_exactly_one_catch_up_snapshot(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    assert host.backups.run_if_due() is None  # just backed up: not due
    clock.now += 3 * DAY
    host.remember("Tests run with pytest -q.")
    assert "overdue since" in host.backups.status_line()
    assert host.backups.run_if_due() is not None
    assert host.backups.run_if_due() is None  # one catch-up, never a backlog
    assert len(_published(places["separate"] / "b")) == 2


def test_b04_one_publisher_per_project(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    clock.now += 2 * DAY
    lock = host.backups._state.path.with_name(host.backups._state.path.name + ".publish.lock")
    held, release = threading.Event(), threading.Event()

    def other_host() -> None:
        with mr._file_lock(lock):
            held.set()
            release.wait()  # held until the test releases it: the two 2 s lock waits never outlast it
    thread = threading.Thread(target=other_host)
    thread.start()
    try:
        assert held.wait(5), "publisher lock holder did not signal acquisition"
        assert host.backups.run_if_due() is None  # the other publisher holds it
        with pytest.raises(mb.BackupError) as busy:
            host.backups.backup()
        assert busy.value.code == "BACKUP_BUSY"
    finally:
        release.set()
        thread.join()
    assert len(_published(places["separate"] / "b")) == 1


def test_b05_b06_same_disk_warns_and_unknown_stays_unknown(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.run("/memory export")
    same = host.commands.run(mc.MemoryCommand("backup_configure", target=str(places["same"] / "b")), block="c").confirm
    assert same is not None and "WARNING" in same.text and "same physical disk" in same.text
    unknown = host.commands.run(mc.MemoryCommand("backup_configure", target=str(places["nowhere"] / "b")), block="c").confirm
    assert unknown is not None and "unknown" in unknown.text
    host.commands.confirmed(same)
    assert host.backups.state().domain == "same" and "no protection against losing that drive" in host.backups.status_line()


def test_b07_b08_a_synced_target_needs_consent_and_only_the_users_command_writes_it(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    monkeypatch.setenv("OneDrive", str(places["separate"]))
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.run("/memory export")
    assessed = host.backups.assess(places["separate"] / "b")
    assert assessed["synced"] == "OneDrive"
    with pytest.raises(mb.BackupError, match="BACKUP_SYNC_CONSENT"):
        host.backups.configure(assessed, consent=False)
    question = host.commands.run(mc.MemoryCommand("backup_configure", target=str(places["separate"] / "b")), block="c").confirm
    assert question is not None and "synced (OneDrive)" in question.text
    assert "Take each one with" in host.commands.confirmed(question).text
    clock.now += 2 * DAY
    assert host.backups.run_if_due() is None and _published(places["separate"] / "b") == []
    assert "held:" in host.backups.status_line()
    assert "Backed up" in host.run("/memory backup now").text and len(_published(places["separate"] / "b")) == 1


def test_changed_target_identity_refuses_write_and_prune(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    (old,) = _published(target)
    moved = places["separate"] / "elsewhere"
    target.rename(moved)
    target.mkdir()  # a different folder now answers to the same path
    clock.now += 40 * DAY
    with pytest.raises(mb.BackupError) as changed:
        host.backups.backup()
    assert changed.value.code == "BACKUP_TARGET_CHANGED" and not any(target.iterdir()) and _published(moved) == [old]
    assert host.backups.state().last_success["name"] == old  # type: ignore[index]


def test_sync_target_without_consent_refused(tmp_path: Path, repo: Path, places: dict[str, Path],
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """B07: a synced folder is never configured without consent bound to it."""
    monkeypatch.setenv("OneDrive", str(places["separate"]))
    host = _Backed(tmp_path, repo, places, _Clock())
    host.run("/memory export")
    assessed = host.backups.assess(places["separate"] / "b")
    with pytest.raises(mb.BackupError) as refused:
        host.backups.configure(assessed, consent=False)
    assert refused.value.code == "BACKUP_SYNC_CONSENT" and host.backups.state().target is None
    assert not (places["separate"] / "b").exists()


def test_b09_a_link_in_the_target_path_is_refused(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    link = places["separate"] / "link"
    try:
        os.symlink(places["nowhere"], link, target_is_directory=True)
    except OSError:
        pytest.skip("this account cannot create symbolic links")
    with pytest.raises(mb.BackupError) as linked:
        host.backups.assess(link / "b")
    assert linked.value.code == "BACKUP_TARGET_LINKED"


def test_b10_targets_overlapping_the_workspace_config_recovery_or_a_repository_are_refused(tmp_path: Path, repo: Path,
                                                                                           places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.run("/memory export")
    for target, code in ((repo / "backups", "BACKUP_TARGET_OVERLAP"), (tmp_path / "config" / "b", "BACKUP_TARGET_OVERLAP"),
                         (Path(host.recovery.state().destination or "") / "b", "BACKUP_TARGET_OVERLAP")):
        with pytest.raises(mb.BackupError) as refused:
            host.backups.assess(target)
        assert refused.value.code == code, target
    other = tmp_path / "other-repo"
    other.mkdir()
    _git(other, "init", "-q")
    with pytest.raises(mb.BackupError) as in_git:
        host.backups.assess(other / "b")
    assert in_git.value.code == "BACKUP_TARGET_IN_GIT"
    with pytest.raises(mb.BackupError) as relative:
        host.backups.assess(Path("relative/b"))
    assert relative.value.code == "BACKUP_TARGET_RELATIVE"


@pytest.mark.parametrize(("error", "attempts"), [(errno.EBUSY, 3), (errno.EACCES, 1)])
def test_b11_a_failed_write_keeps_the_last_good_backup_and_retries_only_transients(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                                    monkeypatch: pytest.MonkeyPatch, error: int,
                                                                                    attempts: int) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    good = host.backups.state().last_success
    host.remember("Tests run with pytest -q.")
    clock.now += 2 * DAY
    calls = []

    def failing(path: Path, data: bytes) -> None:
        if str(places["separate"]) in str(path):
            calls.append(path)
            raise OSError(error, os.strerror(error))
        original(path, data)
    original = mr._write
    monkeypatch.setattr(mr, "_write", failing)
    with pytest.raises(mb.BackupError) as failed:
        host.backups.backup()
    state = host.backups.state()
    assert failed.value.code == "BACKUP_WRITE_FAILED" and state.last_success == good
    assert state.failure is not None and state.failure["attempts"] == attempts and len(calls) == attempts
    assert "last attempt failed" in host.backups.status_line() and len(_published(places["separate"] / "b")) == 1
    assert not list((places["separate"] / "b").glob(".staging-*"))


def test_b11_b30_a_target_the_os_cannot_create_is_a_readable_answer(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """CP3 platform probe P4: a target the OS refuses to create (on Windows a path past 260 characters without long-path support;
    also a denied parent or a read-only drive) answers readably through the confirmed set-up, never a failed turn; nothing is set up."""
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.run("/memory export")
    target = places["separate"] / "b"
    real_mkdir = Path.mkdir

    def refusing(self: Path, *args: Any, **kwargs: Any) -> None:
        if str(self).startswith(str(target)):
            raise FileNotFoundError(errno.ENOENT, "The system cannot find the path specified")
        real_mkdir(self, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", refusing)
    answer = host.run(f"/memory backup configure {target}")
    assert "could not be created (The system cannot find the path specified" in answer.text, answer.text
    assert "Nothing was changed." in answer.text and host.backups.state().target is None and not target.exists()


def test_b11_a_target_reported_missing_while_written_is_a_recorded_write_failure(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """Fable CP3 review 1, finding 1: a FileNotFoundError while the target is written (a Windows path the folder fit but its files
    do not, or the folder removed mid-write) is the target's failure, never "the source moved": it is answered and recorded."""
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    good = host.backups.state().last_success
    host.remember("Tests run with pytest -q.")
    clock.now += 2 * DAY

    def missing(_captured: dict[str, bytes], final: Path, _prefix: str) -> None:
        raise FileNotFoundError(errno.ENOENT, "The system cannot find the path specified", str(final / "entries.jsonl"))
    monkeypatch.setattr(mb.Backups, "_publish", staticmethod(missing))
    answer = host.run("/memory backup now")
    assert f"could not be written to {target} (The system cannot find the path specified" in answer.text, answer.text
    state = host.backups.state()
    assert state.failure is not None and state.failure["code"] == "BACKUP_WRITE_FAILED" and state.last_success == good
    assert "last attempt failed" in host.backups.status_line() and len(_published(target)) == 1


def test_memory_moving_on_from_a_clean_copy_is_read_again_never_a_recorded_failure(tmp_path: Path, repo: Path,
                                                                                    places: dict[str, Path],
                                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """Fable CP3 review 1, finding 3: this host's copy is clean, but memory moved on through another config root and the kept
    generation lapsed. The backup exports the copy again and succeeds; nothing is recorded as a failed attempt."""
    from optimus_gateway import memory_store

    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    _Host(tmp_path, repo, host.server, config="other-config").remember("Written through another config root.")
    monkeypatch.setattr(memory_store, "_PINNED_SECONDS", -1.0)  # the copy's own generation is no longer kept anywhere
    clock.now += 2 * DAY
    generation = host.backups.backup()
    state = host.backups.state()
    assert generation.count == 2 and state.failure is None and state.last_success["name"] == generation.name  # type: ignore[index]


def test_b11_a_full_disk_that_also_refuses_the_failure_record_is_still_a_readable_answer(tmp_path: Path, repo: Path,
                                                                                         places: dict[str, Path],
                                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex CP3 review 1, finding 2, the backup's side: the write fails and recording the failure fails too (the backup
    settings share the full disk); `/memory backup now` still answers with the write failure, and says the record is missing."""
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    host.remember("Tests run with pytest -q.")  # a new generation to publish
    clock.now += 2 * DAY
    settings = host.backups._state.path
    real = mr._durable_json
    filled: list[int] = []  # the disk fills while the backup is written: every later settings write is refused too

    def full(path: Path, value: Any) -> None:
        if path == settings and filled:
            raise OSError(errno.ENOSPC, "No space left on device")
        real(path, value)

    def no_space(_captured: dict[str, bytes], _final: Path, _prefix: str) -> None:
        filled.append(1)
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(mr, "_durable_json", full)
    monkeypatch.setattr(mb.Backups, "_publish", staticmethod(no_space))
    answer = host.run("/memory backup now")
    assert "could not be written to" in answer.text and "It could not be recorded either: The backup settings could not be " \
        "saved (No space left on device)" in answer.text, answer.text


def test_b11_a_publisher_lock_the_config_folder_refuses_is_a_readable_answer(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex CP3 review 2, finding 1: the backup's publisher lock file cannot be opened (the config folder is read-only):
    `/memory backup now` answers readably and nothing is written."""
    import builtins

    import optimus_file_lock

    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    host.remember("Tests run with pytest -q.")
    clock.now += 2 * DAY
    publisher = host.backups._state.path.name + ".publish.lock"

    def opening(path: Any, *args: Any, **kwargs: Any) -> Any:
        if Path(path).name == publisher:
            raise PermissionError(errno.EACCES, "Access is denied", str(path))
        return builtins.open(path, *args, **kwargs)
    monkeypatch.setattr(optimus_file_lock, "open", opening, raising=False)
    answer = host.run("/memory backup now")
    assert "The backup's lock file could not be opened (Access is denied); nothing was written." in answer.text, answer.text
    assert len(_published(places["separate"] / "b")) == 1


def test_b12_b13_retention_removes_only_old_managed_generations_after_a_verified_new_one(tmp_path: Path, repo: Path,
                                                                                          places: dict[str, Path],
                                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    (first,) = _published(target)
    (target / "my-notes").mkdir()  # not a generation: never touched
    clock.now += 31 * DAY
    host.remember("Tests run with pytest -q.")

    def broken(_source: Path, _final: Path, _prefix: str) -> None:
        raise mb.BackupError("BACKUP_VERIFY_FAILED", "does not match")
    monkeypatch.setattr(mb.Backups, "_publish", staticmethod(broken))
    with pytest.raises(mb.BackupError):
        host.backups.backup()
    assert _published(target) == [first]  # a failed replacement never prunes the last usable one
    monkeypatch.undo()
    host.backups.backup()
    (second,) = _published(target)
    assert second != first and (target / "my-notes").is_dir()


def test_b14_withdrawal_publishes_clean_then_retires_older_copies_here_and_in_earlier_targets(tmp_path: Path, repo: Path,
                                                                                              places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    gone = host.remember(CANARY)
    first_target, second_target = places["separate"] / "a", places["separate"] / "b"
    host.set_up(first_target)
    clock.now += 1000
    host.set_up(second_target)  # the first target stays listed
    assert [prior["path"] for prior in host.backups.state().prior] == [str(first_target.resolve())]
    host.run(f"/forget {gone[0]}@1")
    assert host.backups.state().cleanup_pending == [gone[0]] and host.backups.due()
    assert "cleanup pending" in host.backups.status_line()
    host.backups.backup()
    (clean,) = _published(second_target)
    body = b"".join((second_target / clean / name).read_bytes() for name in mr.LAYOUT)
    assert b"zebra-quartz" not in body
    assert _published(first_target) == [] and host.backups.state().prior == [] and host.backups.state().cleanup_pending == []


def test_b14_an_offline_earlier_target_keeps_cleanup_pending(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    gone = host.remember(CANARY)
    host.set_up(places["separate"] / "a")
    host.set_up(places["separate"] / "b")
    shutil.move(str(places["separate"] / "a"), str(places["nowhere"] / "unplugged"))  # the drive is gone for now
    host.run(f"/forget {gone[0]}@1")
    host.backups.backup()
    (prior,) = host.backups.state().prior
    assert prior["path"] == str((places["separate"] / "a").resolve()) and prior["owes_cleanup"] and prior["unreachable"]
    assert "cleanup pending, folder unreachable or changed" in host.backups.status_line()
    clock.now += 2 * DAY
    host.backups.run_if_due()  # the drive is still away: the obligation survives the daily backup
    assert host.backups.state().prior and host.backups.state().prior[0]["owes_cleanup"]
    shutil.move(str(places["nowhere"] / "unplugged"), str(places["separate"] / "a"))  # the drive is back, same folder
    host.backups.run_if_due()
    assert _published(places["separate"] / "a") == [] and host.backups.state().prior == []


def test_b16_b23_restore_from_a_backup_into_an_empty_store_only(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    keep = host.remember("Never push to main.")
    gone = host.remember(CANARY)
    host.set_up(places["separate"] / "b")
    (name,) = _published(places["separate"] / "b")
    shutil.rmtree(host.recovery.state().destination or "")  # the recovery copy is lost too
    refused = host.run(f"/memory restore {name}")  # the store still holds memory
    assert "Restored" not in refused.text
    host.run(f"/forget {gone[0]}@1")
    fresh = _Backed(tmp_path / "lost", repo, places, clock)  # the volume was lost: a new, empty store
    host.rebind(fresh.service)
    listed = host.run("/memory restore").text
    assert name in listed and "backup in" in listed
    restored = host.run(f"/memory restore {name}")
    assert "Restored" in restored.text
    items = host.items()
    assert items[keep[0]][2] == "active" and items.get(gone[0], (0, "", "withdrawn"))[2] != "active"  # the later withdrawal holds


def test_b20_an_encrypted_backup_is_refused_and_writes_nothing(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.run("/memory export")
    answer = host.run(f"/memory backup configure {places['separate'] / 'b'} --encrypted")
    assert mb.ENCRYPTION_UNAVAILABLE in answer.text and not (places["separate"] / "b").exists()
    assert host.backups.state().target is None


def test_b21_a_corrupted_backup_is_not_restored(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    (name,) = _published(places["separate"] / "b")
    entries = places["separate"] / "b" / name / "entries.jsonl"
    entries.write_bytes(entries.read_bytes().replace(b"main", b"prod"))
    with pytest.raises(mr.RecoveryError) as damaged:
        mr.read_generation(places["separate"] / "b" / name, host.store.project)
    assert damaged.value.code == "RECOVERY_GENERATION_DAMAGED"


def test_interrupted_publication_never_counts_staging(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    host.remember("Tests run with pytest -q.")
    clock.now += 2 * DAY
    real_replace = os.replace

    def crash(source: Any, destination: Any) -> None:
        if str(target) in str(destination):
            raise KeyboardInterrupt  # the process stops at the atomic rename
        real_replace(source, destination)
    monkeypatch.setattr(os, "replace", crash)
    monkeypatch.setattr(mb.shutil, "rmtree", lambda *_a, **_k: None)  # killed: no cleanup runs after the crash
    with pytest.raises(KeyboardInterrupt):
        host.backups.backup()
    monkeypatch.undo()
    assert len(_published(target)) == 1  # whatever the crash left is not a generation
    leftovers = list(target.glob(".staging-*"))
    assert leftovers and all((leftover / "manifest.json").exists() for leftover in leftovers)  # it got as far as the rename
    host.backups.backup()
    assert len(_published(target)) == 2 and not list(target.glob(".staging-*"))  # the next run removes it


def test_b28_disabling_or_moving_keeps_every_copy_listed(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "a")
    answer = host.run("/memory backup disable").text
    assert "Backups are off" in answer and str((places["separate"] / "a").resolve()) in answer
    assert len(_published(places["separate"] / "a")) == 1 and host.backups.run_if_due() is None
    host.set_up(places["separate"] / "b")
    assert str((places["separate"] / "a").resolve()) in host.backups.status_line()


def test_b29_a_relocated_synced_target_loses_its_consent(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OneDrive", str(places["separate"]))
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    host.backups._state.update(lambda s: setattr(s, "consent", None))  # the consent was bound to another place
    with pytest.raises(mb.BackupError) as refused:
        host.backups.backup()
    assert refused.value.code == "BACKUP_SYNC_CONSENT"


def test_b30_backup_commands_send_no_folder_to_the_gateway_and_call_no_model(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    sent: list[str] = []
    service = host.service
    def post(body: Any) -> Any:
        sent.append(repr(body))
        return service.handle(body, deadline=_deadline())
    host.store._post = post  # type: ignore[assignment]
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    host.run("/memory backup now")
    host.run("/memory backup")
    assert sent and not any(str(places["separate"]) in body or "separate" in body for body in sent)


def _deadline() -> float:
    import time

    return time.monotonic() + 5


def test_b31_status_separates_boundaries_and_never_claims_external_erasure(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OneDrive", str(places["separate"]))
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    listing = host.run("/memory").text
    assert "Recovery copy:" in listing and "Backups: on" in listing and mb.ENCRYPTION_UNAVAILABLE in listing
    assert "Optimus cannot erase" in listing and "erased" not in listing.replace("cannot be erased", "")


def test_the_launch_factory_wires_backups_and_withdrawal_cleanup(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    gone = host.remember(CANARY)
    host.set_up(places["separate"] / "b")
    host.run(f"/forget {gone[0]}@1")
    assert host.backups.state().cleanup_pending == [gone[0]]


def test_real_disk_query_names_a_disk_for_an_existing_local_folder(tmp_path: Path) -> None:
    found = mb.disks(tmp_path)
    if sys.platform == "win32":
        assert found and all(name.startswith("disk") for name in found)  # a local NTFS temp folder is on a named physical disk
    else:
        assert found is None or (found and all(isinstance(name, str) and name for name in found))
    assert mb.failure_domain(tmp_path, {"same folder": tmp_path})[0] in ("same", "unknown")


# --- Fable CP1 review findings ------------------------------------------------------------------------------------------


def test_f1_projects_sharing_a_folder_never_touch_each_others_backups(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    folder = places["separate"] / "shared"
    from tests.unit.context.test_memory_recovery import _snapshot

    one = _Backed(tmp_path / "one", repo, places, clock, project="p-1", registry=_snapshot({"git:one": "p-1"}))
    two = _Backed(tmp_path / "two", repo, places, clock, project="p-2", registry=_snapshot({"git:two": "p-2"}))
    two.remember("Use uv for every command.")
    two.set_up(folder)
    (theirs,) = [g.name for g in mr.generations(folder) if g.project == "p-2"]
    gone = one.remember(CANARY)
    one.set_up(folder)
    one.run(f"/forget {gone[0]}@1")
    one.backups.backup()  # withdrawal cleanup: every older generation of p-1 only
    clock.now += 40 * 24 * 3600 * 1000
    one.remember("Tests run with pytest -q.")
    one.backups.backup()  # retention: only p-1's old generations
    assert theirs in [g.name for g in mr.generations(folder)]
    assert all(g.project == "p-1" for g in one.backups.generations()) and theirs not in one.run("/memory restore").text


def test_f2_returning_to_an_earlier_folder_keeps_its_newest_generation(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    gone = host.remember(CANARY)
    a, b = places["separate"] / "a", places["separate"] / "b"
    host.set_up(a)
    host.set_up(b)
    host.set_up(a)  # back to A: A is the target again, never also an earlier one
    assert [prior["path"] for prior in host.backups.state().prior] == [str(b.resolve())]
    host.run(f"/forget {gone[0]}@1")
    generation = host.backups.backup()
    assert _published(a) == [generation.name] and host.backups.state().last_success["name"] == generation.name  # type: ignore[index]


def test_f4_a_failure_is_not_retried_every_minute(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    shutil.rmtree(places["separate"] / "b")
    clock.now += 2 * DAY
    for _minute in range(10):
        host.backups.run_if_due()
        clock.now += 60_000
    state = host.backups.state()
    assert state.failure is not None and state.failure["code"] == "BACKUP_TARGET_MISSING"
    assert state.last_attempt_ms is not None and clock.now - state.last_attempt_ms >= 9 * 60_000  # only the first tick tried
    assert "not retried until `/memory backup now`" in host.backups.status_line()  # a missing folder is permanent


def test_f5_an_earlier_folder_that_changed_is_never_cleaned_through(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    gone = host.remember(CANARY)
    a = places["separate"] / "a"
    host.set_up(a)
    host.set_up(places["separate"] / "b")
    (old,) = _published(a)
    a.rename(places["nowhere"] / "moved-a")
    a.mkdir()  # another folder answers to A's path now
    shutil.copytree(places["nowhere"] / "moved-a" / old, a / old)  # and holds a copy of the generation
    host.run(f"/forget {gone[0]}@1")
    host.backups.backup()
    assert _published(a) == [old] and host.backups.state().prior[0]["unreachable"]


def test_f6_f7_placement_and_sync_are_checked_again_before_every_write(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "parent" / "b")
    clock.now += 2 * DAY
    monkeypatch.setenv("OneDrive", str(places["separate"]))  # a sync root now covers the folder
    with pytest.raises(mb.BackupError) as synced:
        host.backups.backup()
    assert synced.value.code == "BACKUP_SYNC_CONSENT"
    monkeypatch.delenv("OneDrive")
    _git(places["separate"] / "parent", "init", "-q")  # a repository now holds it
    with pytest.raises(mb.BackupError) as in_git:
        host.backups.backup()
    assert in_git.value.code == "BACKUP_TARGET_IN_GIT" and len(_published(places["separate"] / "parent" / "b")) == 1


def test_f8_a_git_entry_refuses_even_when_git_itself_fails(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.backups._git = lambda *_a, **_k: None  # Git missing, timing out or refusing a dubious owner
    (places["separate"] / "repo-ish").mkdir()
    (places["separate"] / "repo-ish" / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    with pytest.raises(mb.BackupError) as refused:
        host.backups.assess(places["separate"] / "repo-ish" / "b")
    assert refused.value.code == "BACKUP_TARGET_IN_GIT"


def test_f9_the_store_location_is_used_only_when_found_and_the_domain_is_refreshed(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "no-docker"))
        assert mb.docker_data_location() is None
        image = tmp_path / "no-docker" / "Docker" / "wsl" / "disk" / "docker_data.vhdx"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"")
        assert mb.docker_data_location() == image
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    assert host.backups.state().domain == "separate"
    host.backups._disk_of = lambda path: frozenset({"disk1"})  # the store's image moved onto the backup's disk
    host.remember("Tests run with pytest -q.")
    host.backups.backup()
    assert host.backups.state().domain == "same"


def test_f10_an_unreadable_generation_folder_keeps_cleanup_pending(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    gone = host.remember(CANARY)
    target = places["separate"] / "b"
    host.set_up(target)
    (old,) = _published(target)
    (target / old / "manifest.json").write_text("{damaged", encoding="utf-8")
    host.run(f"/forget {gone[0]}@1")
    host.backups.backup()
    state = host.backups.state()
    assert state.cleanup_pending == [gone[0]] and state.unreadable == [old]
    assert "unreadable folders in the backup folder may hold withdrawn text" in host.backups.status_line()


def test_f11_damaged_backup_settings_never_break_restore_and_a_damaged_recovery_generation_offers_its_backup(
        tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    (name,) = _published(places["separate"] / "b")
    recovery_entries = Path(host.recovery.state().destination or "") / name / "entries.jsonl"
    recovery_entries.write_bytes(recovery_entries.read_bytes().replace(b"main", b"prod"))
    question = host.commands.run(mc.MemoryCommand("restore", generation=name), block="c").confirm
    assert question is not None and "read from the backup" in question.text and question.meta.get("backup")
    host.backups._state.path.write_text("[1, 2]", encoding="utf-8")
    listed = host.run("/memory restore").text
    assert "Backups unavailable" in listed and name in listed


def test_f12_a_damaged_source_generation_is_never_published(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.run("/memory export")
    name = (host.recovery.state().exported or {})["name"]
    entries = Path(host.recovery.state().destination or "") / name / "entries.jsonl"
    entries.write_bytes(entries.read_bytes().replace(b"main", b"prod"))
    answer = host.run(f"/memory backup configure {places['separate'] / 'b'}")
    assert "Backed up" not in answer.text and _published(places["separate"] / "b") == []


def test_f14_a_second_host_waits_and_both_show_the_same_status(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    other = mb.Backups(host.recovery, mb.BackupStateFile(tmp_path / "config", host.store.project), workspace=repo,
                       config_root=tmp_path / "config", store_data=lambda: places["store-data"], disk_of=_disks(places, repo),
                       clock=clock, sleep=lambda _s: None)  # a second host process: its own objects, the same files
    assert other.status_line() == host.backups.status_line()
    host.remember("Tests run with pytest -q.")
    clock.now += 2 * DAY
    assert other.run_if_due() is not None and host.backups.run_if_due() is None  # the second one finds it already done
    assert other.status_line() == host.backups.status_line() and len(_published(places["separate"] / "b")) == 2


def test_f14_verification_catches_bytes_that_did_not_reach_the_disk(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    host.remember("Tests run with pytest -q.")
    clock.now += 40 * DAY
    original = mr._write

    def short(path: Path, data: bytes) -> None:
        original(path, data[:-1] if path.name == "entries.jsonl" and str(target) in str(path) else data)
    monkeypatch.setattr(mr, "_write", short)
    with pytest.raises(mb.BackupError) as failed:
        host.backups.backup()
    assert failed.value.code == "BACKUP_VERIFY_FAILED" and len(_published(target)) == 1  # the old one survives retention


def test_f14_a_crash_while_writing_a_file_leaves_no_generation(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    host.remember("Tests run with pytest -q.")
    clock.now += 2 * DAY
    original = mr._write

    def crash(path: Path, data: bytes) -> None:
        if path.name == "MEMORY.md" and str(target) in str(path):
            raise KeyboardInterrupt
        original(path, data)
    monkeypatch.setattr(mr, "_write", crash)
    monkeypatch.setattr(mb.shutil, "rmtree", lambda *_a, **_k: None)
    with pytest.raises(KeyboardInterrupt):
        host.backups.backup()
    monkeypatch.undo()
    assert len(_published(target)) == 1 and list(target.glob(".staging-*"))
    host.backups.backup()
    assert len(_published(target)) == 2 and not list(target.glob(".staging-*"))


def test_b17_with_backups_off_a_lost_store_has_only_the_recovery_copy(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.run("/memory export")
    assert "Backups: off (not configured)" in host.run("/memory").text  # the risk is shown before any loss
    fresh = _Backed(tmp_path / "lost", repo, places, _Clock())
    host.rebind(fresh.service)
    listed = host.run("/memory restore").text
    assert "backup in" not in listed  # expected loss: no other drive holds a copy


def test_b24_an_earlier_registrations_backup_restores_only_through_a_confirmed_mapping(tmp_path: Path, repo: Path,
                                                                                      places: dict[str, Path]) -> None:
    from tests.unit.context.test_memory_recovery import _snapshot
    from tests.unit.optimus_gateway.test_memory_store_commit import Server

    clock = _Clock()
    folder = places["separate"] / "shared"
    old = _Backed(tmp_path / "old", repo, places, clock, project="u-alpha-old", registry=_snapshot({"git:x": "u-alpha-old"}))
    rule = old.remember("Never push to main.")
    old.set_up(folder)
    (name,) = _published(folder)
    stranger = _Backed(tmp_path / "other", repo, places, clock, project="p-other", registry=_snapshot({"git:other": "p-other"}))
    stranger.remember("Use poetry.")
    stranger.set_up(folder)  # another workspace's project shares the folder: never offered for mapping
    shutil.rmtree(old.recovery.state().destination or "")
    new = _Backed(tmp_path / "new", repo, places, clock, project="proj-alpha", registry=_snapshot({"git:x": "proj-alpha"}),
                  server=Server())
    new.run("/memory export")
    new.run(f"/memory backup configure {folder}")
    listed = new.run("/memory restore").text
    assert name in listed and "written for project `u-alpha-old`" in listed and "p-other" not in listed
    plain = new.run(f"/memory restore {name}").text
    assert "--map" in plain
    question = new.commands.run(mc.parse_command(f"/memory restore {name} --map", attachments=False), block="b").confirm
    assert question is not None and question.meta["place"] == str(folder.resolve())
    answer = new.commands.confirmed(question)
    assert "into this project" in answer.text, answer.text
    assert new.items()[rule[0]][3] == "Never push to main."
    (theirs,) = [g.name for g in mr.generations(folder) if g.project == "p-other"]
    refused = new.run(f"/memory restore {theirs} --map").text
    assert "Restored" not in refused and "There is no recovery copy" in refused


def test_f17_withdrawals_before_any_backup_target_record_nothing(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    gone = host.remember(CANARY)
    host.run(f"/forget {gone[0]}@1")
    assert host.backups.state().cleanup_pending == []


def test_f21_a_folder_without_a_stable_identity_is_refused(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.run("/memory export")
    assessed = host.backups.assess(places["separate"] / "b")
    real = mb.identity
    target = places["separate"] / "b"
    monkeypatch.setattr(mb, "identity", lambda path: {**real(path), "folder": 0} if Path(path) == target else real(path))
    with pytest.raises(mb.BackupError) as refused:
        host.backups.configure(assessed, consent=False)
    assert refused.value.code == "BACKUP_TARGET_NO_IDENTITY"


def test_status_says_scheduling_pauses_while_no_session_is_open(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    clock.now += 3 * DAY
    assert "pause while none is" in host.backups.status_line()


# --- Codex CP1 review 1 findings ----------------------------------------------------------------------------------------


def test_c1_a_withdrawal_during_the_backup_stays_pending_for_the_next(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    gone = host.remember(CANARY)
    host.set_up(places["separate"] / "b")
    clock.now += 2 * DAY
    original = mb.Backups._source

    raced: list[bool] = []

    def racing(self: mb.Backups, project: str) -> Any:
        found = original(self, project)  # the generation is chosen, still holding the text
        if not raced:
            raced.append(True)
            host.run(f"/forget {gone[0]}@1")  # the withdrawal lands now
        return found
    monkeypatch.setattr(mb.Backups, "_source", racing)
    host.backups.backup()
    monkeypatch.undo()
    if not host.backups.state().cleanup_pending:  # marked clean only when every remaining generation provably lacks the text
        for name in _published(places["separate"] / "b"):
            assert b"zebra-quartz" not in (places["separate"] / "b" / name / "entries.jsonl").read_bytes()
    host.backups.backup()
    assert host.backups.state().cleanup_pending == []
    for name in _published(places["separate"] / "b"):
        assert b"zebra-quartz" not in (places["separate"] / "b" / name / "entries.jsonl").read_bytes()


def test_c2_unknown_staging_folders_are_never_removed(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    target.mkdir()
    (target / ".staging-family-photos").mkdir()
    (target / ".staging-family-photos" / "a.jpg").write_bytes(b"x")
    host.set_up(target)
    assert (target / ".staging-family-photos" / "a.jpg").is_file()


def test_c3_a_copy_whose_seal_the_store_does_not_confirm_is_not_counted_and_retires_nothing(tmp_path: Path, repo: Path,
                                                                                            places: dict[str, Path]) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    (old,) = _published(target)
    host.remember("Tests run with pytest -q.")
    host.run("/memory export")
    clock.now += 40 * DAY
    name = (host.recovery.state().exported or {})["name"]
    manifest_path = Path(host.recovery.state().destination or "") / name / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["seal"] = "0" * 64  # only the seal: digests and metadata still match
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=True), encoding="utf-8")
    with pytest.raises(mb.BackupError) as unauthentic:
        host.backups.backup()
    assert unauthentic.value.code == "BACKUP_GENERATION_UNAUTHENTIC"
    assert _published(target) == [old] and host.backups.state().last_success["name"] == old  # type: ignore[index]


def test_c4_an_earlier_synced_folder_is_cleaned_only_by_the_users_own_backup(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    monkeypatch.setenv("OneDrive", str(places["same"]))
    host = _Backed(tmp_path, repo, places, clock)
    gone = host.remember(CANARY)
    host.set_up(places["same"] / "cloud")
    host.run("/memory backup now")
    host.set_up(places["separate"] / "local")
    host.run(f"/forget {gone[0]}@1")
    host.backups.backup()  # scheduled-equivalent: not the user's own command
    assert _published(places["same"] / "cloud") and "cleaned only by `/memory backup now`" in host.backups.status_line()
    host.run("/memory backup now")
    assert _published(places["same"] / "cloud") == [] and host.backups.state().prior == []


def test_c5_an_earlier_folder_now_inside_a_repository_is_not_cleaned(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    gone = host.remember(CANARY)
    a = places["separate"] / "parent" / "a"
    host.set_up(a)
    host.set_up(places["separate"] / "b")
    _git(places["separate"] / "parent", "init", "-q")
    host.run(f"/forget {gone[0]}@1")
    host.backups.backup()
    assert len(_published(a)) == 1 and host.backups.state().prior[0]["unreachable"]


def test_c6_an_unreadable_folder_in_an_earlier_target_keeps_its_obligation(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    gone = host.remember(CANARY)
    a = places["separate"] / "a"
    host.set_up(a)
    (old,) = _published(a)
    host.set_up(places["separate"] / "b")
    (a / old / "manifest.json").write_text("{damaged", encoding="utf-8")
    host.run(f"/forget {gone[0]}@1")
    host.backups.backup()
    (prior,) = host.backups.state().prior
    assert prior["owes_cleanup"] and not prior["unreachable"] and "cleanup pending" in host.backups.status_line()


def test_c8_a_sync_root_chosen_exactly_needs_consent(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    root = places["separate"] / "CompanyData"
    root.mkdir()
    monkeypatch.setenv("OneDriveCommercial", str(root))
    host = _Backed(tmp_path, repo, places, _Clock())
    host.run("/memory export")
    assert host.backups.assess(root)["synced"] == "OneDriveCommercial"


def test_c9_a_folder_replaced_while_the_confirmation_is_open_is_refused(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.run("/memory export")
    target = places["separate"] / "b"
    target.mkdir()
    question = host.commands.run(mc.MemoryCommand("backup_configure", target=str(target)), block="c").confirm
    assert question is not None
    target.rename(places["separate"] / "b-old")
    target.mkdir()
    answer = host.commands.confirmed(question)
    assert "changed while you confirmed" in answer.text and host.backups.state().target is None


def test_c10_malformed_backup_settings_are_corrupt_and_never_break_restore(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    project = host.store.project
    for bad in ({"project": project, "prior": None}, {"project": project, "enabled": "yes"},
                {"project": project, "last_success": {"at_ms": "soon"}}, {"project": project, "domain": []},
                {"project": project, "last_success": []}, {"project": project, "failure": []},
                {"project": project, "last_success": {"at_ms": 1}}, {"project": project, "prior": [{"path": "x"}]},
                {"project": project, "identity": {"path": "x"}}):
        host.backups._state.path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(mb.BackupError) as corrupt:
            host.backups.state()
        assert corrupt.value.code == "BACKUP_STATE_CORRUPT"
        assert "Backups unavailable" in host.run("/memory restore").text


def test_c11_a_permanent_failure_is_held_until_the_user_acts(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    host.remember("Tests run with pytest -q.")
    clock.now += 2 * DAY
    original = mr._write

    def denied(path: Path, data: bytes) -> None:
        if str(places["separate"]) in str(path):
            raise OSError(errno.EACCES, "denied")
        original(path, data)
    monkeypatch.setattr(mr, "_write", denied)
    assert host.backups.run_if_due() is None
    first = host.backups.state().last_attempt_ms
    clock.now += 3 * DAY
    assert host.backups.run_if_due() is None and host.backups.state().last_attempt_ms == first  # not retried by the schedule
    assert "not retried until `/memory backup now`" in host.backups.status_line()
    monkeypatch.undo()
    assert "Backed up" in host.run("/memory backup now").text


def test_c12_the_memory_store_data_overlap_is_refused_both_ways(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    with pytest.raises(mb.BackupError) as inside:
        host.backups.assess(places["store-data"] / "b")
    assert inside.value.code == "BACKUP_TARGET_OVERLAP" and "memory store's data" in inside.value.message
    host.backups._store_data = lambda: places["separate"] / "docker" / "data"
    with pytest.raises(mb.BackupError) as around:
        host.backups.assess(places["separate"] / "docker")
    assert around.value.code == "BACKUP_TARGET_OVERLAP"


def test_c13_a_moved_docker_disk_image_never_counts_the_stale_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform != "win32":
        pytest.skip("Docker Desktop's settings exist on Windows only")
    default = tmp_path / "local" / "Docker" / "wsl" / "disk" / "docker_data.vhdx"
    default.parent.mkdir(parents=True)
    default.write_bytes(b"")
    settings = tmp_path / "roaming" / "Docker" / "settings-store.json"
    settings.parent.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    settings.write_text(json.dumps({"CustomWslDistroDir": str(tmp_path / "moved")}), encoding="utf-8")
    assert mb.docker_data_location() is None  # moved, and not found where it was moved to: unknown, never the stale default
    moved = tmp_path / "moved" / "disk" / "docker_data.vhdx"
    moved.parent.mkdir(parents=True)
    moved.write_bytes(b"")
    assert mb.docker_data_location() == moved


# --- Codex CP1 review 2 findings ----------------------------------------------------------------------------------------


def _tamper_source(host: _Backed, change: Any) -> None:
    name = (host.recovery.state().exported or {})["name"]
    path = Path(host.recovery.state().destination or "") / name / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    change(manifest)
    path.write_text(json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=True), encoding="utf-8")


@pytest.mark.parametrize("field", ["frontier", "count"])
def test_r1_a_changed_deletion_frontier_or_count_is_never_counted(tmp_path: Path, repo: Path, places: dict[str, Path], field: str) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    (old,) = _published(target)
    host.remember("Tests run with pytest -q.")
    host.run("/memory export")
    clock.now += 40 * DAY
    if field == "frontier":
        _tamper_source(host, lambda m: m["frontier"].__setitem__("deletions", m["frontier"]["deletions"] + 3))  # seal unchanged
    else:
        _tamper_source(host, lambda m: m.__setitem__("count", m["count"] + 1))
    with pytest.raises(mb.BackupError) as refused:
        host.backups.backup()
    assert refused.value.code == "BACKUP_GENERATION_UNAUTHENTIC"
    assert _published(target) == [old] and host.backups.state().last_success["name"] == old  # type: ignore[index]


def test_r2_a_withdrawal_during_an_earlier_targets_scan_keeps_its_obligation(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    gone = host.remember(CANARY)
    host.set_up(places["separate"] / "a")
    host.set_up(places["separate"] / "b")
    assert not host.backups.state().prior[0]["owes_cleanup"]
    clock.now += 2 * DAY
    host.remember("Tests run with pytest -q.")
    original = mb.Backups._prior_usable

    def scanning(self: mb.Backups, prior: dict[str, Any], folder: Path) -> bool:
        usable = original(self, prior, folder)
        self.withdrawn(gone[0])  # the withdrawal lands between the scan and its state update
        return usable
    monkeypatch.setattr(mb.Backups, "_prior_usable", scanning)
    host.backups.backup()
    monkeypatch.undo()
    (prior,) = host.backups.state().prior
    assert prior["owes_cleanup"] and _published(places["separate"] / "a")


def test_r4_a_journal_moving_on_is_source_movement_not_a_failure(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    host.remember("Tests run with pytest -q.")
    clock.now += 2 * DAY
    real = host.recovery._read_generation
    calls: list[int] = []

    def purge_in_flight(bind: str, **kwargs: Any) -> Any:
        entries, final = real(bind, **kwargs)
        calls.append(1)
        if "pin" not in kwargs:
            return entries, final  # an export: each retry exports again (Fable CP3 review 1, finding 3)
        return entries, {**final, "journal": final["journal"] + 1, "seal": "f" * 64}  # a purge's intent journalled, head unchanged
    monkeypatch.setattr(host.recovery, "_read_generation", purge_in_flight)
    with pytest.raises(mb.BackupError) as moved:
        host.backups.backup()
    assert moved.value.code == "BACKUP_SOURCE_MOVED" and moved.value.transient and host.backups.state().failure is None
    monkeypatch.undo()
    assert host.backups.run_if_due() is not None  # the next scheduled check simply takes it


def test_r5_only_authenticated_bytes_are_published_and_a_crash_after_publication_is_reconciled(
        tmp_path: Path, repo: Path, places: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    host.remember("Tests run with pytest -q.")
    clock.now += 2 * DAY
    order: list[str] = []
    authenticate, replace = mb.Backups._authenticate, os.replace
    monkeypatch.setattr(mb.Backups, "_authenticate",
                        lambda self, c, n, p: order.append("authenticated") or authenticate(self, c, n, p))

    def renamed(source: Any, destination: Any) -> None:
        replace(source, destination)
        if str(target) in str(destination):
            order.append("published")
            raise KeyboardInterrupt  # killed right after the rename, before anything is recorded
    monkeypatch.setattr(os, "replace", renamed)
    with pytest.raises(KeyboardInterrupt):
        host.backups.backup()
    monkeypatch.undo()
    assert order == ["authenticated", "published"]
    newest = max(_published(target))
    assert host.backups.state().last_success["name"] != newest  # type: ignore[index]  # not counted yet
    generation = host.backups.backup()  # the restart reconciles: the published copy is checked against the source, then counted
    assert generation.name == newest and host.backups.state().last_success["name"] == newest  # type: ignore[index]


def test_r6_docker_storage_counts_only_for_the_default_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path / "docker-config"))
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    assert mb._default_engine_selected()
    monkeypatch.setenv("DOCKER_HOST", "tcp://elsewhere:2375")
    assert not mb._default_engine_selected() and mb.docker_data_location() is None
    monkeypatch.delenv("DOCKER_HOST")
    (tmp_path / "docker-config").mkdir()
    (tmp_path / "docker-config" / "config.json").write_text(json.dumps({"currentContext": "remote-box"}), encoding="utf-8")
    assert not mb._default_engine_selected() and mb.docker_data_location() is None
    if sys.platform == "win32":
        (tmp_path / "docker-config" / "config.json").write_text(json.dumps({"currentContext": "desktop-linux"}), encoding="utf-8")
        monkeypatch.setenv("APPDATA", str(tmp_path / "no-roaming"))
        default = tmp_path / "local" / "Docker" / "wsl" / "disk" / "docker_data.vhdx"
        default.parent.mkdir(parents=True)
        default.write_bytes(b"")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
        assert mb.docker_data_location() is None  # unreadable Docker Desktop settings: never the default image


def _restart(tmp_path: Path, repo: Path, places: dict[str, Path], service: Any) -> _Backed:
    """A new host process for the same project: fresh objects over the same config folder, bound to `service` (the store)."""
    host = _Backed(tmp_path, repo, places, _Clock())
    host.rebind(service)
    return host


def test_b18_a_lost_verification_key_refuses_restore_from_the_backup_readably(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    """Unit fault injection: the store's recovery key is replaced in process (a new password after keyring loss)."""
    from optimus_gateway import memory_store

    host = _Backed(tmp_path, repo, places, _Clock())
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    (name,) = _published(places["separate"] / "b")
    shutil.rmtree(host.recovery.state().destination or "")  # only the backup holds the generation
    fresh = _Backed(tmp_path / "lost", repo, places, _Clock())
    fresh.service._store._recovery_key = memory_store.recovery_key("a new password after the keyring was lost")  # type: ignore[attr-defined]
    host.rebind(fresh.service)
    question = host.commands.run(mc.MemoryCommand("restore", generation=name), block="c").confirm
    assert question is not None and question.meta.get("backup") == str((places["separate"] / "b").resolve())  # the backup is used
    answer = host.commands.confirmed(question)
    assert "Not restored" in answer.text and host.items() == {}, answer.text


def test_b26_an_interrupted_restore_from_a_backup_publishes_nothing_and_a_restart_reconciles(
        tmp_path: Path, repo: Path, places: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit fault injection: an interruption is raised inside the restore, and each restart is a new host object set over the
    same config folder. A real process kill and a kill inside the store's fenced publication transaction are not exercised."""
    host = _Backed(tmp_path, repo, places, _Clock())
    for n in range(12):
        host.remember(f"Rule number {n} holds.")
    host.set_up(places["separate"] / "b")
    (name,) = _published(places["separate"] / "b")
    expected = host.items()
    shutil.rmtree(host.recovery.state().destination or "")  # only the backup holds the generation
    fresh = _Backed(tmp_path / "lost", repo, places, _Clock())
    first = _restart(tmp_path, repo, places, fresh.service)
    call = first.store.call

    def killed(op: str, **body: Any) -> Any:
        if op == "restore" and body.get("batch") == 1:
            raise KeyboardInterrupt  # interrupted between batches: staged, never published
        return call(op, **body)
    monkeypatch.setattr(first.store, "call", killed)
    question = first.commands.run(mc.MemoryCommand("restore", generation=name), block="c").confirm
    assert question is not None and question.meta.get("backup")
    with pytest.raises(KeyboardInterrupt):
        first.commands.confirmed(question)
    monkeypatch.undo()
    second = _restart(tmp_path, repo, places, fresh.service)
    assert second.items() == {} and second.recovery.recovery_required(fresh=True)  # nothing staged is served

    def crash_after_publication(change: Any) -> Any:
        raise KeyboardInterrupt  # the store published; the host stopped before recording it
    monkeypatch.setattr(second.recovery._state, "update", crash_after_publication)
    question = second.commands.run(mc.MemoryCommand("restore", generation=name), block="c").confirm
    assert question is not None and question.meta.get("backup")
    with pytest.raises(KeyboardInterrupt):
        second.commands.confirmed(question)
    monkeypatch.undo()
    third = _restart(tmp_path, repo, places, fresh.service)
    assert third.items() == expected  # published whole, exactly once
    again = third.run(f"/memory restore {name}").text
    assert "Restored" not in again and third.items() == expected  # the restart's retry finds it done and changes nothing


def test_r7_only_the_captured_authenticated_bytes_are_published(tmp_path: Path, repo: Path, places: dict[str, Path],
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    (old,) = _published(target)
    host.remember("Tests run with pytest -q.")
    clock.now += 40 * DAY
    authenticate = mb.Backups._authenticate
    sealed: list[str] = []

    def then_tamper(self: mb.Backups, captured: dict[str, bytes], name: str, project: str) -> Any:
        entries = authenticate(self, captured, name, project)
        sealed.append(json.loads(captured["manifest.json"])["seal"])
        _tamper_source(host, lambda m: m.__setitem__("seal", "0" * 64))  # the source changes right after authentication
        return entries
    monkeypatch.setattr(mb.Backups, "_authenticate", then_tamper)
    generation = host.backups.backup()
    monkeypatch.undo()
    published = json.loads((target / generation.name / "manifest.json").read_text(encoding="utf-8"))
    assert published["seal"] == sealed[0] != "0" * 64  # the authenticated bytes, never the changed source
    assert old not in _published(target)  # retention ran on an authentic replacement only


def test_product_default_reports_drive_independence_unknown(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    host = _Backed(tmp_path, repo, places, _Clock())
    host.run("/memory export")
    product = mb.Backups(host.recovery, mb.BackupStateFile(tmp_path / "config", host.store.project), workspace=repo,
                         config_root=tmp_path / "config", disk_of=_disks(places, repo))  # the launch's store reference
    assessed = product.assess(places["separate"] / "b")  # a different disk from the recovery copy's
    assert assessed["domain"] == "unknown" and "memory store" in assessed["reason"]  # never "separate" without the store bound


def test_a_backup_is_taken_and_authenticated_while_writes_keep_landing(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    """Plan 12.12 CP3 (the CP2 contention miss): with another host writing after every store request, the export is still one
    generation and the backup authenticates it at its own head, so one production backup succeeds and verifies."""
    host = _Backed(tmp_path, repo, places, _Clock())
    for n in range(mr.PAGE + 20):
        host.remember(f"Rule number {n} for this project.")
    host.set_up(places["separate"] / "b")
    host.remember("One more rule, so the copy must be exported again.")
    other = _Host(tmp_path, repo, host.server)
    call = host.store.call
    written: list[int] = []

    def busy(op: str, **fields: Any) -> dict[str, Any]:
        reply = call(op, **fields)
        if op == "export":
            written.append(1)
            other.remember(f"Written during the backup, number {len(written)}.")
        return reply

    host.store.call = busy  # type: ignore[method-assign]
    generation = host.backups.backup(explicit=True)
    assert len(written) >= 4  # the export's pages and the authenticating re-read, each followed by a write
    published = places["separate"] / "b" / generation.name
    manifest, entries = mr.read_generation(published, host.store.project)
    assert manifest["head"] == generation.head and len(entries) == generation.count
    assert host.backups.state().failure is None and host.backups.state().last_success["name"] == generation.name


def test_a_backup_due_for_cleanup_says_so_and_never_names_a_future_overdue_date(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
    """Plan 12.12 CP3, seen in real Zed: right after a withdrawal the backup is due to finish cleanup, not overdue since tomorrow."""
    host = _Backed(tmp_path, repo, places, _Clock())
    item, _version = host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    host.run(f"/forget {item}@1")
    status = host.backups.status_line()
    assert "a backup is due now, to finish cleanup" in status and "overdue since" not in status
    assert "backup cleanup pending for 1 withdrawn item(s)" in status and "withdrawn;" not in status


@pytest.mark.parametrize("number", LOCK_FAULTS)
def test_a_lock_fault_stops_a_backup_with_its_own_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path, places: dict[str, Path],
                                                         number: int) -> None:
    """#529 review 2: the publisher lock refused for a reason other than another publisher is not "busy", and says its errno."""
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    host.set_up(places["separate"] / "b")
    clock.now += 2 * DAY
    before = _published(places["separate"] / "b")  # setting up took the first backup
    fault_platform_lock(monkeypatch, number)
    with pytest.raises(mb.BackupError) as refused:
        host.backups.backup()
    assert refused.value.code == "BACKUP_LOCK_FAILED" and f"errno {number}" in refused.value.message
    assert _published(places["separate"] / "b") == before
    with pytest.raises(mb.BackupError) as state_refused:  # the state file's own lock, which every backup step updates
        host.backups._state.update(lambda _state: None)
    assert state_refused.value.code == "BACKUP_LOCK_FAILED"



def test_a_backup_target_whose_writer_lock_cannot_be_opened_is_a_write_failure(tmp_path: Path, repo: Path,
                                                                                places: dict[str, Path]) -> None:
    """#532: the target's writer lock failing to open is still the backup's own write failure, read from its errno, as
    before the lock moved to optimus_file_lock; it is not a lock fault code."""
    clock = _Clock()
    host = _Backed(tmp_path, repo, places, clock)
    host.remember("Never push to main.")
    target = places["separate"] / "b"
    host.set_up(target)
    clock.now += 2 * DAY
    before = _published(target)
    (target / ".lock").unlink()
    (target / ".lock").mkdir()  # a folder where the writer's lock file belongs
    with pytest.raises(mb.BackupError) as refused:
        host.backups.backup()
    assert refused.value.code == "BACKUP_WRITE_FAILED" and _published(target) == before
