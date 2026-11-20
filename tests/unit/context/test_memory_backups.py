"""Plan 12.12 Task 1: configured backups of the recovery copy, against the real store on its in-memory stand-in, real Git
repositories and the real file system (frozen cases B01-B31 in reports/plan12-memory-m3-part2/cases.json). Physical disks are
injected here; the real disk query and the real store are exercised in tests/integration/memory/test_backups.py."""

from __future__ import annotations

import errno
import os
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import memory_commands as mc
from optimus.context import memory_backups as mb
from optimus.context import memory_recovery as mr
from tests.unit.context.test_memory_recovery import CANARY, _git, _Host

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
            release.wait(5)
    thread = threading.Thread(target=other_host)
    thread.start()
    held.wait(5)
    try:
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


def test_b09_a_replaced_target_is_never_written_or_pruned(tmp_path: Path, repo: Path, places: dict[str, Path]) -> None:
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

    def broken(_source: Path, _final: Path) -> None:
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
    assert host.backups.state().prior == [str(first_target.resolve())]
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
    assert host.backups.state().prior == [str((places["separate"] / "a").resolve())]
    assert "earlier backup folders still listed" in host.backups.status_line()


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


def test_b25_an_interrupted_publication_is_never_a_generation(tmp_path: Path, repo: Path, places: dict[str, Path],
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
    with pytest.raises(KeyboardInterrupt):
        host.backups.backup()
    monkeypatch.undo()
    assert len(_published(target)) == 1 and not list(target.glob(".staging-*"))
    (target / ".staging-leftover").mkdir()  # a crash that left staging behind
    host.backups.backup()
    assert len(_published(target)) == 2 and not list(target.glob(".staging-*"))


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
    host.run(f"/forget {gone[0]}@1")
    assert host.backups.state().cleanup_pending == [gone[0]]


def test_real_disk_query_names_a_disk_for_an_existing_local_folder(tmp_path: Path) -> None:
    found = mb.disks(tmp_path)
    assert found is None or (found and all(isinstance(name, str) and name for name in found))
    assert mb.failure_domain(tmp_path, {"same folder": tmp_path})[0] in ("same", "unknown")
