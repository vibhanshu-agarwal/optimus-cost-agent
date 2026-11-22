"""Plan 12.11 Task 4 (D5, D8): the plaintext recovery copy and restore, against the real store on its in-memory stand-in, real Git
repositories and the real file guards. The same on real Redis, with a killed store and a lost volume, is in
tests/integration/memory/test_recovery.py."""

from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import optimus_file_lock
from optimus.acp import memory_commands as mc
from optimus.context import memory_recovery as mr
from optimus.context.authored_memory import GatewayMemoryStore, MemoryStoreRefused
from optimus.guardrails.path_safety import PathSafetyValidator, ValidationVerdict
from tests.unit.optimus_gateway.test_memory_store_commit import Server
from tests.unit.optimus_gateway.test_memory_store_purge import store as purge_store

CANARY = "Remember the canary phrase zebra-quartz-7731."


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", "-c", "init.defaultBranch=main", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    (path / "README.md").write_text("x", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "first")
    return path


class _Host:
    """One host's view of a project: its store client, recovery copy and memory commands, on a given stand-in server."""

    def __init__(self, tmp_path: Path, workspace: Path, server: Server | None = None, *, config: str = "config", project: str = "p-1",
                 registry: dict[str, Any] | None = None) -> None:
        self.service, self.server, _journal = purge_store(tmp_path, server)
        service = self.service
        self.store: GatewayMemoryStore = GatewayMemoryStore(object(), project=project, owner="host-1",  # type: ignore[arg-type]
                                                            post=lambda *_a, **_k: (lambda body: service.handle(body, deadline=_deadline())))
        snapshot = registry if registry is not None else _snapshot({"git:x": project})
        self.recovery = mr.Recovery(self.store, mr.StateFile(tmp_path / config, project),
                                    registry=snapshot if callable(snapshot) else (lambda: snapshot))
        self.store.guard, self.store.written = self.recovery.recovery_required, self.recovery.written
        self.commands = mc.MemoryCommands(self.store, trusted=True, sanitize=lambda v: v, recovery=self.recovery, workspace=workspace)

    def run(self, text: str) -> mc.MemoryAnswer:
        command = mc.parse_command(text, attachments=False)
        assert isinstance(command, mc.MemoryCommand), command
        answer = self.commands.run(command, block="command:1")
        if answer.confirm is not None:
            answer = self.commands.confirmed(answer.confirm)  # the user chose "Go ahead"
        if answer.purge is not None:
            answer = self.commands.purge(answer.purge)
        return answer

    def remember(self, text: str) -> tuple[str, int]:
        ((notice, _label),) = self.run(f"/remember {text}").notices
        assert notice.saved
        return notice.item, notice.version

    def rebind(self, service: Any) -> None:
        """Point this host's store client at another Gateway service (the same host after its store was replaced)."""
        self.store._post = lambda body: service.handle(body, deadline=_deadline())  # type: ignore[assignment]

    def items(self) -> dict[str, tuple[int, str, str, str]]:
        rows, _cursor = self.store.items("project", limit=100)
        return {r.event.item: (r.event.version, r.event.trust, r.event.status, r.event.statement) for r in rows}


def _snapshot(keys: dict[str, str]) -> dict[str, Any]:
    """A registry snapshot mapping each key to its project id."""
    return {"registry_version": 1, "projects": {key: {"project_id": project, "worktrees": []} for key, project in keys.items()}}


def _deadline() -> float:
    import time

    return time.monotonic() + 5


def _files(destination: Path) -> bytes:
    return b"".join(path.read_bytes() for path in sorted(destination.rglob("*")) if path.is_file())


def test_the_first_export_asks_where_and_writes_one_ignored_generation_of_active_payloads_only(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    keep = host.remember("Never push to main.")
    gone = host.remember(CANARY)
    host.run(f"/forget {gone[0]}@1")
    question = host.commands.run(mc.MemoryCommand("export"), block="command:1").confirm
    assert question is not None and question.kind == "location" and str(mr.location(repo)) in question.text
    assert not mr.location(repo).exists()  # nothing is written before the user confirms
    answer = host.commands.confirmed(question)
    assert "Saved" in answer.text
    destination = mr.location(repo)
    (generation,) = mr.generations(destination)
    assert generation.count == 2 and generation.deletions == 1
    body = _files(destination)
    assert b"Never push to main." in body and b"zebra-quartz" not in body  # the withdrawn item's text is not exported
    assert (destination / ".gitignore").read_bytes() == b"*\n"
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == ""  # nothing of it shows to Git
    assert _git(repo, "check-ignore", str(destination / generation.name / "entries.jsonl")).strip()
    assert keep[0] in host.recovery.status_line() or "last saved" in host.recovery.status_line()


def test_a_user_gitignore_that_does_not_ignore_and_tracked_content_refuse_before_any_payload(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    host.remember(CANARY)
    destination = mr.location(repo)
    destination.mkdir(parents=True)
    (destination / ".gitignore").write_text("# mine\n", encoding="utf-8")
    host.recovery.confirm(destination, sync_consent=False)
    with pytest.raises(mr.RecoveryError) as refused:
        host.recovery.export()
    assert refused.value.code == "RECOVERY_NOT_IGNORED" and (destination / ".gitignore").read_text(encoding="utf-8") == "# mine\n"
    assert b"zebra" not in _files(destination) and not mr.generations(destination)
    (destination / ".gitignore").write_text("*\n", encoding="utf-8")
    (destination / "forced.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "-f", str(destination / "forced.txt"))
    with pytest.raises(mr.RecoveryError) as refused:
        host.recovery.export()
    assert refused.value.code == "RECOVERY_TRACKED" and not mr.generations(destination)
    _git(repo, "rm", "-q", "--cached", str(destination / "forced.txt"))
    assert host.recovery.export().count == 1  # the normal ignored publication


def test_outside_git_no_git_check_is_needed(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    host = _Host(tmp_path, plain)
    host.remember("Never push to main.")
    host.run("/memory export")
    assert len(mr.generations(mr.location(plain))) == 1


def test_a_withdrawal_retires_every_older_generation_and_cleanup_is_shown_until_then(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    item, _version = host.remember(CANARY)
    host.run("/memory export")
    destination = mr.location(repo)
    assert b"zebra-quartz" in _files(destination)  # an authorized reader (this test) can read the plaintext: no confidentiality
    host.run(f"/forget {item}@1")
    assert "cleanup pending for 1 item" in host.recovery.status_line()
    host.run("/memory export")
    assert b"zebra-quartz" not in _files(destination) and len(mr.generations(destination)) == 1
    assert "cleanup pending" not in host.recovery.status_line()


def test_only_the_newest_generations_are_kept(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    clock = iter(range(1, 100))
    host.recovery._clock = lambda: next(clock) * 1000
    for n in range(5):
        host.remember(f"Rule number {n} holds.")
        host.run("/memory export")
    assert len(mr.generations(mr.location(repo))) == mr.KEEP_GENERATIONS


def test_a_location_or_copy_the_os_cannot_write_is_a_readable_answer(tmp_path: Path, repo: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """CP3 platform probe P4: a recovery location the OS refuses to create, and a copy it refuses to write (a full or read-only
    drive), answer readably through `/memory export`, never a failed turn; the failure is recorded and nothing is published."""
    host = _Host(tmp_path, repo)
    host.remember("Never push to main.")
    place = mr.location(repo)
    real_mkdir = Path.mkdir

    def refusing(self: Path, *args: Any, **kwargs: Any) -> None:
        if str(self).startswith(str(place)):
            raise PermissionError(errno.EACCES, "Access is denied")
        real_mkdir(self, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", refusing)
    answer = host.run("/memory export")
    assert "could not be created (Access is denied). Nothing was changed." in answer.text, answer.text
    assert host.recovery.state().destination is None
    monkeypatch.setattr(Path, "mkdir", real_mkdir)
    assert "Saved" in host.run("/memory export").text
    host.remember("Tests run with pytest -q.")

    def full(_path: Path, _data: bytes) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(mr, "_write", full)
    answer = host.run("/memory export")
    assert f"could not be written to {place} (No space left on device). The last copy is kept." in answer.text, answer.text
    assert host.recovery.state().failure == "RECOVERY_WRITE_FAILED"
    assert len(mr.generations(place)) == 1 and not list(place.glob(".staging-*"))


def test_a_synced_location_needs_consent_bound_to_it(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OneDrive", str(tmp_path))
    host = _Host(tmp_path, repo)
    host.remember("Never push to main.")
    question = host.commands.run(mc.MemoryCommand("export"), block="command:1").confirm
    assert question is not None and "synced (OneDrive)" in question.text and question.meta["synced"] == "OneDrive"
    host.recovery.confirm(mr.location(repo), sync_consent=False)  # a location recorded without consent
    with pytest.raises(mr.RecoveryError) as refused:
        host.recovery.export()
    assert refused.value.code == "RECOVERY_SYNC_CONSENT" and not mr.generations(mr.location(repo))
    host.commands.confirmed(question)  # consent bound to this location
    assert len(mr.generations(mr.location(repo))) == 1


def test_a_lost_store_is_recovery_required_refuses_writes_keeps_the_copy_and_restores(tmp_path: Path, repo: Path) -> None:
    """Q3 and the volume-loss path: the host knows the project held memory, so an emptied store is recovery-required; no write
    lands, no empty export replaces the copy; restore brings back every active item at its version and keeps deletions."""
    host = _Host(tmp_path, repo)
    rule = host.remember("Never push to main.")
    host.run(f"/memory edit {rule[0]}@1 Never push to main or release.")
    gone = host.remember(CANARY)
    host.run("/memory export")
    host.run(f"/forget {gone[0]}@1")  # withdrawn after the copy was written: the copy still holds it
    before = host.items()
    lost = _Host(tmp_path, repo, Server())  # the volume is lost; the host's config and the deletion journal survive
    assert lost.recovery.recovery_required()
    assert "Recovery required" in lost.run("/memory").text
    refused = lost.run("/remember Use uv.")
    assert refused.notices == () and "Restore it first" in refused.text and lost.items() == {}
    with pytest.raises(mr.RecoveryError) as empty:
        lost.recovery.export()
    assert empty.value.code == "RECOVERY_REQUIRED" and len(mr.generations(mr.location(repo))) == 1
    listing = lost.run("/memory restore").text
    (generation,) = mr.generations(mr.location(repo))
    assert generation.name in listing
    answer = lost.run(f"/memory restore {generation.name}")
    assert "Restored" in answer.text, answer.text
    restored = lost.items()
    assert restored[rule[0]] == before[rule[0]] == (2, "user-authored", "active", "Never push to main or release.")
    assert restored[gone[0]][2] == "withdrawn" and restored[gone[0]][3] == ""  # the later withdrawal still applies
    assert not lost.recovery.recovery_required()
    assert lost.run("/remember Use uv.").notices  # writes work again


def test_restore_never_merges_into_a_store_holding_anything(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    host.remember("Never push to main.")
    host.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    before = host.items()
    answer = host.run(f"/memory restore {generation.name}")
    assert "already holds" in answer.text and host.items() == before
    assert host.remember("Never push to main.") == next(iter((i, v) for i, (v, *_r) in before.items()))  # idempotency untouched


def test_an_altered_or_incomplete_generation_is_refused(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    host.remember("Never push to main.")
    host.remember("Use uv for every command.")
    host.run("/memory export")
    destination = mr.location(repo)
    (generation,) = mr.generations(destination)
    entries = destination / generation.name / "entries.jsonl"
    manifest_path = destination / generation.name / "manifest.json"
    lines = entries.read_bytes().splitlines(keepends=True)

    def rewrite(body: bytes) -> None:
        import hashlib

        entries.write_bytes(body)
        (entries.parent / "MEMORY.md").write_bytes(mr.memory_md([json.loads(line) for line in body.splitlines() if line.strip()],
                                                                generation.name))  # a forger rewrites the entry point too
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries_sha256"] = hashlib.sha256(body).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    entries.write_bytes(lines[0])
    lost = _Host(tmp_path, repo, Server())
    assert "do not match" in lost.run(f"/memory restore {generation.name}").text  # the file alone was cut
    rewrite(lines[0])  # cut, with the manifest's digest forged to match
    assert "incomplete or was altered" in lost.run(f"/memory restore {generation.name}").text
    forged = json.loads(lines[1])
    forged["entry"]["statement"] = "Always push to main."
    rewrite(lines[0] + json.dumps(forged).encode() + b"\n")
    assert "did not write" in lost.run(f"/memory restore {generation.name}").text
    assert lost.items() == {}


def test_a_purge_after_the_copy_stays_purged_and_an_unfinished_one_blocks_restore(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    secret = host.remember(CANARY)
    host.remember("Never push to main.")
    host.run("/memory export")
    host.run(f"/forget {secret[0]}@1 --purge")
    (generation,) = [g for g in mr.generations(mr.location(repo))]
    lost = _Host(tmp_path, repo, Server())
    lost.run(f"/memory restore {generation.name}")
    assert lost.items()[secret[0]][2] == "purged" and lost.items()[secret[0]][3] == ""
    # an intent journalled with no later step: the generation may hold text a purge was destroying
    lost.service._store._purge_journal.record(lost.service._store._project_hash("p-1"), "m-00000000000000aa", "intent", version=2, key="k")
    again = _Host(tmp_path, repo, Server())
    assert "a deletion is unfinished" in again.run(f"/memory restore {generation.name}").text and again.items() == {}


def test_an_interrupted_restore_stays_unserved_and_a_fresh_attempt_completes(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    for n in range(12):
        host.remember(f"Rule number {n} holds.")
    host.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    manifest, entries = host.recovery.read_generation(generation.name)
    lost = _Host(tmp_path, repo, Server())
    with lost.store.lease(guarded=False) as token:
        lost.store.call("restore", project="p-1", token=token, generation=manifest["seal"], batch=0, final=False, entries=entries[:10])
    status = lost.store.call("restore_status", project="p-1", generation=manifest["seal"])
    assert status["state"] == "staged" and status["target_empty"] and lost.items() == {}  # staged is never served
    lost.run(f"/memory restore {generation.name}")
    assert len(lost.items()) == 12
    assert lost.store.call("restore_status", project="p-1", generation=manifest["seal"])["state"] == "published"


def test_a_write_landing_before_publication_aborts_the_restore(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    for n in range(11):
        host.remember(f"Rule number {n} holds.")
    host.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    manifest, entries = host.recovery.read_generation(generation.name)
    lost = _Host(tmp_path, repo, Server())
    with lost.store.lease(guarded=False) as token:
        lost.store.call("restore", project="p-1", token=token, generation=manifest["seal"], batch=0, final=False, entries=entries[:10])
    other = _Host(tmp_path, repo, lost.server, config="other-config")  # a host that never knew the project held memory
    other.remember("A concurrent rule.")
    with lost.store.lease(guarded=False) as token, pytest.raises(MemoryStoreRefused) as refused:
        lost.store.call("restore", project="p-1", token=token, generation=manifest["seal"], batch=1, final=True, entries=entries[10:],
                        head=manifest["head"], frontier=manifest["frontier"], withdrawn=[], bind=manifest["bind"],
                        journal=manifest["journal"], purged=[])
    assert refused.value.code == "RESTORE_TARGET_NOT_EMPTY" and list(lost.items()) == list(other.items())


def test_divergent_generations_are_listed_and_none_is_chosen_for_the_user(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo)
    clock = iter(range(1, 100))
    host.recovery._clock = lambda: next(clock) * 1000
    host.remember("Never push to main.")
    host.run("/memory export")
    host.remember("Use uv for every command.")
    host.run("/memory export")
    listing = host.run("/memory restore").text
    names = [g.name for g in mr.generations(mr.location(repo))]
    assert len(names) == 2 and all(name in listing for name in names) and "nothing chooses for you" in listing


def test_the_model_cannot_read_write_or_be_given_the_recovery_copy(tmp_path: Path, repo: Path) -> None:
    """`.optimus/` is the reserved runtime tree: model READ and WRITE are blocked, under other casings on Windows and through an
    alias; an ordinary file stays readable. No bytes are opened."""
    from optimus.guardrails.command_safety import CommandSafetyValidator

    host = _Host(tmp_path, repo)
    host.remember(CANARY)
    host.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    target = mr.location(repo) / generation.name / "entries.jsonl"
    guard = PathSafetyValidator(workspace_root=repo)
    for path in (target, Path(str(target).replace(".optimus", ".OPTIMUS")) if sys.platform == "win32" else target):
        assert guard.validate_read(path).verdict is ValidationVerdict.BLOCK
        assert guard.validate_write(path).verdict is ValidationVerdict.BLOCK
    assert guard.validate_read(repo / "README.md").verdict is ValidationVerdict.ALLOW
    alias = repo / "notes"
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(mr.location(repo)), str(alias))
    else:
        alias.symlink_to(mr.location(repo), target_is_directory=True)
    try:
        assert guard.validate_read(alias / generation.name / "entries.jsonl").verdict is ValidationVerdict.BLOCK
    finally:
        os.rmdir(alias) if sys.platform == "win32" else alias.unlink()
    command = CommandSafetyValidator(workspace_root=repo, allowed_network_hosts=()).validate(("pytest", f".optimus/memory-recovery/{generation.name}/entries.jsonl"))
    assert command.verdict is ValidationVerdict.BLOCK


# --- Codex CP3 review 1 ------------------------------------------------------------------------------------------------------

def test_a_lost_or_damaged_deletion_journal_publishes_nothing(tmp_path: Path, repo: Path) -> None:
    """Finding 1: the journal is the only record of a purge across a lost volume. Gone, or damaged, it cannot show the purge
    happened, so the restore fails closed."""
    import shutil

    for damage in ("removed", "corrupted"):
        root = tmp_path / damage
        root.mkdir()
        host = _Host(root, repo)
        secret = host.remember(CANARY)
        host.remember("Never push to main.")
        host.run("/memory export")
        host.run(f"/forget {secret[0]}@1 --purge")
        generation = mr.generations(mr.location(repo))[0]
        host.service._store._purge_journal.close()  # type: ignore[attr-defined]  # the host stopped; its journal stream is closed
        if damage == "removed":
            shutil.rmtree(root / "journal")
        else:
            segment = next(path for path in (root / "journal").rglob("*") if path.is_file() and path.stat().st_size > 40)
            data = bytearray(segment.read_bytes())
            data[len(data) // 2] ^= 0xFF
            segment.write_bytes(bytes(data))
        lost = _Host(root, repo, Server())
        answer = lost.run(f"/memory restore {generation.name}")
        assert "journal is damaged or shorter" in answer.text, (damage, answer.text)
        assert lost.items() == {}
        shutil.rmtree(mr.location(repo))


def test_a_change_during_an_export_keeps_the_copy_dirty_and_its_cleanup_scheduled(tmp_path: Path, repo: Path) -> None:
    """Finding 2: a withdrawal landing while an export reads is not in that generation, so the copy stays dirty and the item's
    cleanup stays scheduled until every managed copy is clean."""
    host = _Host(tmp_path, repo)
    item = host.remember(CANARY)
    host.run("/memory export")
    read = host.recovery._read_generation

    def racing(bind: str) -> Any:
        found = read(bind)
        _Host(tmp_path, repo, host.server).run(f"/forget {item[0]}@1")  # another host of the project, the same config
        return found

    host.recovery._read_generation = racing  # type: ignore[method-assign]
    host.recovery.export()
    state = host.recovery.state()
    assert state.dirty and item[0] in state.cleanup_pending and b"zebra-quartz" in _files(mr.location(repo))
    host.recovery._read_generation = read  # type: ignore[method-assign]
    host.recovery.export_if_dirty()
    assert b"zebra-quartz" not in _files(mr.location(repo)) and not host.recovery.state().cleanup_pending


def test_restore_writes_only_the_generation_that_was_confirmed(tmp_path: Path, repo: Path) -> None:
    """Finding 3: the confirmation binds the generation's seal. Another valid generation put in its place while the question
    was open restores nothing."""
    import shutil

    host = _Host(tmp_path, repo)
    clock = iter(range(1, 100))
    host.recovery._clock = lambda: next(clock) * 1000
    host.remember("Never push to main.")
    host.run("/memory export")
    host.remember("Use uv for every command.")
    host.run("/memory export")
    newer, older = mr.generations(mr.location(repo))
    lost = _Host(tmp_path, repo, Server())
    question = lost.commands.run(mc.MemoryCommand("restore", generation=older.name), block="command:1").confirm
    assert question is not None and question.meta["seal"] == older.seal
    destination = mr.location(repo)
    shutil.rmtree(destination / older.name)
    shutil.copytree(destination / newer.name, destination / older.name)
    entries = [json.loads(line) for line in (destination / older.name / "entries.jsonl").read_bytes().splitlines() if line.strip()]
    (destination / older.name / "MEMORY.md").write_bytes(mr.memory_md(entries, older.name))  # a substitute that reads as valid
    answer = lost.commands.confirmed(question)
    assert "not the copy you confirmed" in answer.text and lost.items() == {}


def test_a_store_emptied_after_a_healthy_answer_takes_no_write(tmp_path: Path, repo: Path) -> None:
    """Finding 4: the cached "healthy" answer never lets a write into a store emptied since; each write asks again under its
    lease, so neither an admission nor a checkpoint makes the lost store non-empty."""
    from optimus.context.memory_continuity import Continuity, Settled

    host = _Host(tmp_path, repo)
    host.remember("Never push to main.")
    assert not host.recovery.recovery_required()  # cached for 30 seconds
    fresh = purge_store(tmp_path, Server())[0]
    host.rebind(fresh)  # the store's volume is replaced under the same host
    assert "Restore it first" in host.run("/remember Use uv.").text
    continuity = Continuity(host.store, workspace=repo, worktree="worktree:a", session="s-1")
    assert not continuity.record(Settled(1, "run-1", "completed", "Port the cache layer to the new client."))
    assert host.items() == {} and host.store.checkpoints(limit=20) == []


def test_a_removed_location_moves_only_on_confirmation_and_the_old_one_is_cleaned(tmp_path: Path, repo: Path) -> None:
    import shutil

    host = _Host(tmp_path, repo)
    host.remember("Never push to main.")
    host.run("/memory export")
    old = mr.location(repo).resolve()
    shutil.rmtree(old)
    other = tmp_path / "other"
    other.mkdir()
    elsewhere = _Host(tmp_path, other, host.server)
    question = elsewhere.commands.run(mc.MemoryCommand("export"), block="command:1").confirm
    assert question is not None and question.meta["moved_from"] == str(old) and "is gone" in question.text
    elsewhere.recovery.confirm(mr.location(other), sync_consent=False)
    assert str(old) in elsewhere.recovery.state().prior  # inventoried until no copy is left in it
    (old / "gen-1-aaaaaaaaaaaa").mkdir(parents=True)  # the old location came back holding a stale copy (a sync, a restore)
    (old / "gen-1-aaaaaaaaaaaa" / "entries.jsonl").write_bytes(b"stale")
    assert "earlier locations still holding copies" in elsewhere.recovery.status_line()
    elsewhere.recovery.export()
    assert not any(old.glob("gen-*")) and elsewhere.recovery.state().prior == []
    assert len(mr.generations(mr.location(other))) == 1


def test_restore_refuses_a_copy_mapped_to_another_registration(tmp_path: Path, repo: Path) -> None:
    host = _Host(tmp_path, repo, registry=_snapshot({"git:a": "p-1"}))
    host.remember("Never push to main.")
    host.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    lost = _Host(tmp_path, repo, Server(), registry=_snapshot({"git:b": "p-1"}))
    assert "another workspace's registration" in lost.run(f"/memory restore {generation.name}").text and lost.items() == {}


def test_a_lost_registry_is_repaired_only_from_an_authenticated_copy_for_this_workspace(tmp_path: Path, repo: Path) -> None:
    from optimus.acp.trusted_paths import resolve_workspace_identity
    from optimus.context.project_registry import ProjectRegistry, ProjectRegistryError, project_key

    registry = ProjectRegistry(tmp_path / "config")
    identity = resolve_workspace_identity(repo)
    project = registry.resolve(identity, create=True).project_id
    host = _Host(tmp_path, repo, project=project, registry=registry.snapshot)
    host.remember("Never push to main.")
    host.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    registry.path.unlink()  # the registry is lost; its marker says projects were registered
    with pytest.raises(ProjectRegistryError):
        registry.resolve(identity, create=True)
    fresh = purge_store(tmp_path, Server())[0]

    def store_for(name: str) -> GatewayMemoryStore:
        return GatewayMemoryStore(object(), project=name, owner="host-2",  # type: ignore[arg-type]
                                  post=lambda *_a, **_k: (lambda body: fresh.handle(body, deadline=_deadline())))

    def repair(key: str) -> mc.MemoryCommands:
        return mc.MemoryCommands(None, trusted=True, sanitize=lambda v: v, registry_recovery=mr.RegistryRecovery(
            repo, key=key, restore_registry=registry.restore, open_store=store_for,
            state_for=lambda name: mr.StateFile(tmp_path / "config", name)))

    assert "Recovery required" in repair(project_key(identity)).run(mc.MemoryCommand("list"), block="command:1").text
    wrong = repair("git:elsewhere")
    question = wrong.run(mc.MemoryCommand("restore", generation=generation.name), block="command:1").confirm
    assert question is not None and "another workspace" in wrong.confirmed(question).text and not registry.path.exists()
    manifest_path = mr.location(repo) / generation.name / "manifest.json"
    original = manifest_path.read_bytes()
    forged = json.loads(original)
    forged["bind_mac"] = "0" * 64
    manifest_path.write_text(json.dumps(forged), encoding="utf-8")
    commands = repair(project_key(identity))
    question = commands.run(mc.MemoryCommand("restore", generation=generation.name), block="command:1").confirm
    assert question is not None and "did not write" in commands.confirmed(question).text and not registry.path.exists()
    manifest_path.write_bytes(original)
    question = commands.run(mc.MemoryCommand("restore", generation=generation.name), block="command:1").confirm
    assert question is not None and "Restored the project registry and 1 items" in commands.confirmed(question).text
    assert registry.resolve(identity, create=False).project_id == project
    rows, _cursor = store_for(project).items("project", limit=10)
    assert [row.event.statement for row in rows] == ["Never push to main."]


def test_a_generation_is_an_agent_memory_repo_and_its_metadata_cannot_be_changed(tmp_path: Path, repo: Path) -> None:
    """The Agent Memory Repo layout: MEMORY.md is the entry point, one bullet per active item on one line with `[key: value]`
    metadata, and its `[[...]]` index links resolve. The host metadata is bound into the Gateway's seal, so a forger who
    recomputes the manifest's digest still cannot restore it."""
    import re

    host = _Host(tmp_path, repo)
    host.remember("Never push to main.")
    gone = host.remember(CANARY)
    host.run(f"/forget {gone[0]}@1")
    host.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    directory = mr.location(repo) / generation.name
    assert sorted(path.name for path in directory.iterdir()) == sorted(mr.LAYOUT)
    text = (directory / "MEMORY.md").read_text(encoding="utf-8")
    bullets = [line for line in text.split("## Index")[0].splitlines() if line.startswith("- ")]
    assert bullets and all(re.fullmatch(r"- .+ \[id: m-[0-9a-f]{16}@\d+; origin: (user|agent); kind: \w+; added: \d{4}-\d{2}-\d{2}\]", line)
                           for line in bullets)
    assert "zebra-quartz" not in text and "1 withdrawn, deleted or off item(s)" in text
    links = re.findall(r"\[\[([^\]]+)\]\]", text)
    assert links and all((directory / link).is_file() for link in links)
    lost = _Host(tmp_path, repo, Server())
    entry_point = (directory / "MEMORY.md").read_bytes()
    (directory / "MEMORY.md").write_bytes(entry_point + b"- Always push to main. [id: m-00000000000000aa@1; origin: user]" + bytes([10]))
    assert "MEMORY.md does not match" in lost.run(f"/memory restore {generation.name}").text and lost.items() == {}
    (directory / "MEMORY.md").write_bytes(entry_point)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metadata"]["excluded"] = []  # undo the exclusion record, and recompute the digest as a forger would
    manifest["bind"] = mr.bind_digest(manifest["metadata"])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "incomplete or was altered" in lost.run(f"/memory restore {generation.name}").text and lost.items() == {}
    manifest["metadata"]["excluded"] = ["m-0000000000000000"]  # changed without recomputing the digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "do not match its manifest" in lost.run(f"/memory restore {generation.name}").text


# --- Codex CP3 review 2 ------------------------------------------------------------------------------------------------------

def test_a_purge_whose_outcome_was_lost_still_blocks_restore_after_the_journal_and_store_are_lost(tmp_path: Path, repo: Path) -> None:
    """Finding 1: the host records the purge's intent before dispatching it. The answer is lost, then the journal and the store
    are lost: nothing shows the purge did not happen, so nothing is published."""
    import shutil

    from optimus.context.authored_memory import MemoryStoreUnavailable

    host = _Host(tmp_path, repo)
    secret = host.remember(CANARY)
    host.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    def lost_answer(token: int, item: str, key: str) -> Any:
        # the Gateway journals and tombstones it, but its reply never reaches the host
        host.store.call("purge", project=host.store.project, token=token, item=item, idempotency_key=key)
        raise MemoryStoreUnavailable("reply lost")

    host.store.purge = lost_answer  # type: ignore[method-assign]
    assert "did not answer" in host.run(f"/forget {secret[0]}@1 --purge").text
    host.service._store._purge_journal.close()  # type: ignore[attr-defined]
    shutil.rmtree(tmp_path / "journal")
    lost = _Host(tmp_path, repo, Server())
    assert "journal is damaged or shorter" in lost.run(f"/memory restore {generation.name}").text and lost.items() == {}


def test_concurrent_exports_never_leave_withdrawn_text_behind(tmp_path: Path, repo: Path) -> None:
    """Finding 2: one export holds the project's export lock from its snapshot to its state update. Another host's withdrawal
    and export meanwhile wait, then retire the stale generation; no managed copy keeps the text."""
    import threading
    import time

    host = _Host(tmp_path, repo)
    item = host.remember(CANARY)
    host.run("/memory export")
    other = _Host(tmp_path, repo, host.server)
    read = host.recovery._read_generation
    workers: list[threading.Thread] = []

    def racing(bind: str) -> Any:
        found = read(bind)
        other.run(f"/forget {item[0]}@1")
        lock = host.recovery._state.path.with_name(host.recovery._state.path.name + ".export.lock")
        os.utime(lock, (0, 0))  # Codex CP3 review 3: an old lock whose owner is alive is still held, whatever its age
        worker = threading.Thread(target=other.recovery.export_if_dirty)
        worker.start()
        time.sleep(0.5)  # without the lock the other export would finish now, before this one publishes its stale read
        workers.append(worker)
        return found

    host.recovery._read_generation = racing  # type: ignore[method-assign]
    host.recovery.export()
    host.recovery._read_generation = read  # type: ignore[method-assign]
    workers[0].join(30)
    host.recovery.export_if_dirty()
    assert b"zebra-quartz" not in _files(mr.location(repo)) and not host.recovery.state().cleanup_pending


def test_a_repaired_registry_keeps_every_other_project_s_identity(tmp_path: Path, repo: Path) -> None:
    """Finding 3: a generation carries the whole registry snapshot, and the repair restores all of it."""
    import subprocess as sp

    from optimus.acp.trusted_paths import resolve_workspace_identity
    from optimus.context.project_registry import ProjectRegistry, project_key

    second = tmp_path / "second"
    second.mkdir()
    sp.run(["git", "init", "-q"], cwd=second, check=True, stdin=sp.DEVNULL, capture_output=True)
    registry = ProjectRegistry(tmp_path / "config")
    identity = resolve_workspace_identity(repo)
    project = registry.resolve(identity, create=True).project_id
    other_project = registry.resolve(resolve_workspace_identity(second), create=True).project_id
    host = _Host(tmp_path, repo, project=project, registry=registry.snapshot)
    host.remember("Never push to main.")
    host.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    registry.path.unlink()
    fresh = purge_store(tmp_path, Server())[0]
    repair = mc.MemoryCommands(None, trusted=True, sanitize=lambda v: v, registry_recovery=mr.RegistryRecovery(
        repo, key=project_key(identity), restore_registry=registry.restore,
        open_store=lambda name: GatewayMemoryStore(object(), project=name, owner="host-2",  # type: ignore[arg-type]
                                                   post=lambda *_a, **_k: (lambda body: fresh.handle(body, deadline=_deadline()))),
        state_for=lambda name: mr.StateFile(tmp_path / "config", name)))
    question = repair.run(mc.MemoryCommand("restore", generation=generation.name), block="command:1").confirm
    assert question is not None and "Restored the project registry" in repair.confirmed(question).text
    assert registry.resolve(resolve_workspace_identity(second), create=True).project_id == other_project


def test_the_notice_backlog_keeps_every_undelivered_notice(tmp_path: Path) -> None:
    """Finding 4: nothing is dropped for room; every undelivered notice survives a restart until it is acknowledged."""
    records = [{"event_id": f"e-{n}", "item": f"m-{n:016x}", "version": 1, "action": "admit", "durable_state": "confirmed",
                "projection_state": "current"} for n in range(257)]
    mr.NoticeBacklog(tmp_path, "p-1").add(records)
    assert mr.NoticeBacklog(tmp_path, "p-1").pending() == records  # a new instance: only the file carries over


def test_a_held_lock_is_never_taken_over_by_its_age(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex CP3 review 3: the lock is the OS's, held until its owner releases it or dies. An old lock whose owner is alive is
    neither deleted nor entered, on any OS (Windows would refuse the deletion; POSIX would allow it, letting a second export
    publish stale plaintext)."""
    lock = tmp_path / "state.json.export.lock"
    attempts: list[Any] = []
    real_unlink = Path.unlink

    def watched(self: Path, *args: Any, **kwargs: Any) -> None:
        attempts.append(self)
        real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", watched)
    monkeypatch.setattr(os, "unlink", lambda path, *a, **k: attempts.append(path))
    import threading

    outcome: list[str] = []

    def contender() -> None:
        try:
            with mr._file_lock(lock, wait=0.3):
                outcome.append("entered")
        except mr.RecoveryError:
            outcome.append("busy")

    with mr._file_lock(lock):
        os.utime(lock, (0, 0))  # as old as can be; its owner is this live block
        thread = threading.Thread(target=contender, daemon=True)  # bounded: a lock that spins never hangs the test
        thread.start()
        thread.join(5)
    assert outcome == ["busy"] and attempts == []
    with mr._file_lock(lock, wait=0.3):  # released by its owner: free again at once
        pass


# --- a mapped restore: an earlier registration's copy into this project (Plan 12.11 Task 5, M21) ---------------------------

def _earlier(tmp_path: Path, repo: Path, project: str, key: str = "git:x") -> _Host:
    return _Host(tmp_path, repo, project=project, registry=_snapshot({key: project}))


def test_an_earlier_registration_s_copy_is_mapped_into_this_project_only_on_confirmation(tmp_path: Path, repo: Path) -> None:
    (repo / ".editorconfig").write_text("indent_style = tab\n", encoding="utf-8")
    old = _earlier(tmp_path, repo, "u-alpha-old")
    indent = old.remember("Use tabs for indentation, as .editorconfig says.")
    gone = old.remember(CANARY)
    old.run(f"/forget {gone[0]}@1 --purge")  # the copy's own deletion journal names it purged
    old.run("/memory export")
    before = old.items()
    (generation,) = mr.generations(mr.location(repo))
    new = _Host(tmp_path, repo, Server(), project="proj-alpha", registry=_snapshot({"git:x": "proj-alpha"}))
    listing = new.run("/memory restore").text
    assert generation.name in listing and "written for project `u-alpha-old`" in listing
    plain = new.run(f"/memory restore {generation.name}").text
    assert "--map" in plain and new.items() == {}  # never restored into another project without the mapping
    question = new.commands.run(mc.parse_command(f"/memory restore {generation.name} --map", attachments=False), block="b")
    assert question.confirm is not None and "Map project `u-alpha-old` to this project (`proj-alpha`)" in question.confirm.text
    assert new.items() == {}  # nothing before the confirmation
    answer = new.commands.confirmed(question.confirm)
    assert "into this project" in answer.text and "is mapped to this one" in answer.text, answer.text
    assert new.items() == before and new.items()[gone[0]][2:] == ("purged", "")
    assert [item.item for item in new.commands.served().items] == [indent[0]]  # its pinned file holds here: served
    assert new.recovery.state().mapped_from == "u-alpha-old"
    text = answer.text  # in the order the restore did them: mapping, pins, deletions
    assert text.index("is mapped to this one") < text.index(f"Pinned files hold for `{indent[0]}@1`") < text.index("stay deleted")


@pytest.mark.parametrize("change", ["edited", "ignored"])
def test_a_restore_validates_each_pin_before_it_writes_and_reports_what_no_longer_holds(
        tmp_path: Path, repo: Path, change: str, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / ".editorconfig").write_text("indent_style = tab\n", encoding="utf-8")
    old = _earlier(tmp_path, repo, "u-alpha-old")
    indent = old.remember("Use tabs for indentation, as .editorconfig says.")
    old.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    if change == "edited":
        (repo / ".editorconfig").write_text("indent_style = space\n", encoding="utf-8")
    else:  # unchanged bytes, but no longer a file an anchor may read
        (repo / ".gitignore").write_text(".editorconfig\n", encoding="utf-8")
    new = _Host(tmp_path, repo, Server(), project="proj-alpha", registry=_snapshot({"git:x": "proj-alpha"}))
    order: list[str] = []
    check, call = mr.check_anchors, new.store.call
    monkeypatch.setattr(mr, "check_anchors", lambda *a, **k: order.append("anchors") or check(*a, **k))
    monkeypatch.setattr(new.store, "call", lambda op, **body: order.append(op) or call(op, **body))
    question = new.commands.run(mc.parse_command(f"/memory restore {generation.name} --map", attachments=False), block="b")
    answer = new.commands.confirmed(question.confirm)
    assert f"`{indent[0]}@1` needs re-verification: `.editorconfig` changed" in answer.text, answer.text
    assert "Pinned files hold" not in answer.text
    assert order.index("anchors") < order.index("restore")  # validated before anything is written
    assert new.items()[indent[0]][2] == "active"  # still restored: nothing the user saved is dropped
    served = new.commands.served()
    assert served.items == () and served.reverify == ((indent[0], 1, ".editorconfig"),)


@pytest.mark.parametrize("later", ["withdraw", "purge"])
def test_deletions_in_the_mapped_project_after_the_copy_still_apply(tmp_path: Path, repo: Path, later: str) -> None:
    old = _earlier(tmp_path, repo, "u-alpha-old")
    indent = old.remember("Use tabs for indentation.")
    old.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    new = _Host(tmp_path, repo, Server(), project="proj-alpha", registry=_snapshot({"git:x": "proj-alpha"}))
    new.run(f"/memory restore {generation.name} --map")
    new.run(f"/forget {indent[0]}@1" + (" --purge" if later == "purge" else ""))
    again = _Host(tmp_path, repo, Server(), project="proj-alpha", registry=_snapshot({"git:x": "proj-alpha"}))  # lost again
    answer = again.run(f"/memory restore {generation.name} --map")
    assert "Restored" in answer.text, answer.text
    status = "purged" if later == "purge" else "withdrawn"
    assert again.items()[indent[0]][2:] == (status, "") and again.commands.served().items == ()  # the freshest deletion wins


def test_a_mapping_is_one_to_one_and_only_from_this_workspace_s_registration(tmp_path: Path, repo: Path) -> None:
    for project in ("u-alpha-old", "u-beta-old"):
        earlier = _earlier(tmp_path, repo, project)
        earlier.remember("Use tabs for indentation.")
        earlier.run("/memory export")
    alpha = next(g for g in mr.generations(mr.location(repo)) if g.project == "u-alpha-old")
    new = _Host(tmp_path, repo, Server(), project="proj-alpha", registry=_snapshot({"git:x": "proj-alpha"}))
    refused = new.run(f"/memory restore {alpha.name} --map").text
    assert "more than one earlier project claims this one" in refused and new.items() == {}
    elsewhere = _Host(tmp_path, repo, Server(), project="proj-gamma", registry=_snapshot({"git:other": "proj-gamma"}))
    assert "another workspace's registration" in elsewhere.run(f"/memory restore {alpha.name} --map").text
    assert elsewhere.items() == {}


def test_a_mapped_restore_authenticates_the_copy_as_its_source_project_s(tmp_path: Path, repo: Path) -> None:
    """The host refuses a copy whose metadata names another project than the confirmed source, and the Gateway refuses entries
    that were not written for the source it is told, so neither can restore another project's copy under a false mapping."""
    old = _earlier(tmp_path, repo, "u-alpha-old")
    old.remember("Use tabs for indentation.")
    old.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    directory = mr.location(repo) / generation.name
    new = _Host(tmp_path, repo, Server(), project="proj-alpha", registry=_snapshot({"git:x": "proj-alpha"}))
    new.recovery.mapping_source = lambda _name, _place: "u-forged"  # type: ignore[method-assign]  # a host naming the wrong source
    with pytest.raises(mr.RecoveryError) as foreign:
        new.recovery.restore(generation.name, seal=generation.seal, source="u-forged", directory=directory)
    assert foreign.value.code == "RECOVERY_GENERATION_FOREIGN" and new.items() == {}
    manifest, entries = mr.read_generation(directory, "u-alpha-old")
    with new.store.lease(guarded=False) as token, pytest.raises(MemoryStoreRefused) as refused:
        new.store.call("restore", project="proj-alpha", token=token, generation=manifest["seal"], batch=0, final=False,
                       entries=entries, source="u-forged")
    assert refused.value.code == "RESTORE_ENTRY_INVALID" and new.items() == {}


def test_a_mapping_is_checked_again_when_it_is_confirmed(tmp_path: Path, repo: Path) -> None:
    old = _earlier(tmp_path, repo, "u-alpha-old")
    old.remember("Use tabs for indentation.")
    old.run("/memory export")
    (generation,) = mr.generations(mr.location(repo))
    new = _Host(tmp_path, repo, Server(), project="proj-alpha", registry=_snapshot({"git:x": "proj-alpha"}))
    question = new.commands.run(mc.parse_command(f"/memory restore {generation.name} --map", attachments=False), block="b")
    assert question.confirm is not None
    other = _earlier(tmp_path, repo, "u-beta-old")  # a second earlier project appears before the user confirms
    other.remember("Use spaces for indentation.")
    other.run("/memory export")
    assert "more than one earlier project claims this one" in new.commands.confirmed(question.confirm).text
    assert new.items() == {}


class _WritesBetweenPages:
    """Another host of the project writes after every export page the store answers (a sustained import or extraction)."""

    def __init__(self, host: _Host, other: _Host, *, forget: str | None = None) -> None:
        self.host, self.other, self.forget, self.pages = host, other, forget, 0
        self._call = host.store.call

    def __call__(self, op: str, **fields: Any) -> dict[str, Any]:
        reply = self._call(op, **fields)
        if op == "export":
            self.pages += 1
            if self.forget is not None and self.pages == 1:
                self.other.run(f"/forget {self.forget}@1")  # a deletion lands while the copy is read
            else:
                self.other.remember(f"Written while the copy was read, number {self.pages}.")
        return reply


def test_an_export_stays_one_generation_while_writes_land_between_its_pages(tmp_path: Path, repo: Path) -> None:
    """Plan 12.12 CP3 (Codex CP2 review 5): the Gateway fixes the generation at its first page's head, so writes between pages
    never break it; the copy is that head's, sealed, and restores."""
    host = _Host(tmp_path, repo)
    for n in range(mr.PAGE + 30):
        host.remember(f"Rule number {n} for this project.")
    host.run("/memory export")  # the location, confirmed, and a first copy
    other = _Host(tmp_path, repo, host.server)
    writes = _WritesBetweenPages(host, other)
    host.store.call = writes  # type: ignore[method-assign]
    generation = host.recovery.export()
    assert writes.pages >= 2 and generation.count == mr.PAGE + 30  # the first page's head: none of the later writes
    manifest, entries = mr.read_generation(mr.location(repo) / generation.name, host.store.project)
    assert manifest["head"] == generation.head and len(entries) == mr.PAGE + 30
    assert not any("Written while the copy was read" in json.dumps(entry) for entry in entries)


def test_a_deletion_landing_while_an_export_is_read_is_never_completed_into_a_copy(tmp_path: Path, repo: Path) -> None:
    """A withdrawal between pages makes the Gateway refuse the last page (`RECOVERY_DELETION_RACED`); the host reads again, and
    the copy it completes holds no text of the withdrawn item."""
    host = _Host(tmp_path, repo)
    canary = host.remember(CANARY)
    for n in range(mr.PAGE + 10):
        host.remember(f"Rule number {n} for this project.")
    host.run("/memory export")
    other = _Host(tmp_path, repo, host.server)
    writes = _WritesBetweenPages(host, other, forget=canary[0])
    host.store.call = writes  # type: ignore[method-assign]
    generation = host.recovery.export()
    body = (mr.location(repo) / generation.name / "entries.jsonl").read_bytes()
    assert b"zebra-quartz" not in body and canary[0].encode() in body  # its payload-free lifecycle only


def test_the_gateway_refuses_a_pinned_head_it_no_longer_holds(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A read naming a head the Gateway neither holds nor is at is refused, never answered from a newer head."""
    from optimus_gateway import memory_store

    host = _Host(tmp_path, repo)
    host.remember("Never push to main.")
    host.run("/memory export")
    head = host.recovery.state().exported["head"]
    host.remember("Tests run with pytest -q.")
    monkeypatch.setattr(memory_store, "_PINNED_SECONDS", -1.0)  # every kept generation has lapsed
    bind = json.loads((mr.location(repo) / host.recovery.state().exported["name"] / "manifest.json").read_text(encoding="utf-8"))["bind"]
    with pytest.raises(mr.RecoveryError) as moved:
        host.recovery._read_generation(bind, pin=head)
    assert moved.value.code == "RECOVERY_SOURCE_MOVED"


# --- a lock the OS refuses for a reason other than another holder (#529 review 2) ---------------------------------------------

LOCK_FAULTS = [errno.ENOLCK] + ([] if sys.platform == "win32" else [errno.EACCES])  # EACCES is a holder only on Windows


def fault_platform_lock(monkeypatch: pytest.MonkeyPatch, number: int) -> None:
    """Make the platform's own lock call fail with `number`, as the OS would, below every lock helper."""
    def refuse(*_args: Any) -> None:
        raise OSError(number, os.strerror(number))

    if sys.platform == "win32":
        import msvcrt

        monkeypatch.setattr(msvcrt, "locking", refuse)
    else:
        import fcntl

        monkeypatch.setattr(fcntl, "flock", refuse)


@pytest.mark.parametrize("number", LOCK_FAULTS)
def test_a_lock_fault_is_its_own_refusal_at_once_never_a_busy_wait(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, number: int) -> None:
    import time

    fault_platform_lock(monkeypatch, number)
    started = time.monotonic()
    with pytest.raises(mr.RecoveryError) as refused, mr._file_lock(tmp_path / "x.lock", wait=30.0, fault_code="SOME_LOCK_FAILED"):
        pytest.fail("the lock was not taken")
    assert refused.value.code == "SOME_LOCK_FAILED" and f"errno {number}" in refused.value.message
    assert time.monotonic() - started < 5.0  # a retried fault would have waited out the 30 s


@pytest.mark.parametrize("number", LOCK_FAULTS)
def test_a_lock_fault_stops_an_export_with_its_errno(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path, number: int) -> None:
    host = _Host(tmp_path, repo)
    host.remember(CANARY)
    destination = mr.location(repo)
    host.recovery.confirm(destination, sync_consent=False)
    fault_platform_lock(monkeypatch, number)
    with pytest.raises(mr.RecoveryError) as refused:
        host.recovery.export()
    assert refused.value.code == "RECOVERY_LOCK_FAILED" and f"errno {number}" in refused.value.message
    assert not mr.generations(destination)


def test_a_state_lock_fault_after_publication_claims_nothing_about_what_was_written(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                                                     repo: Path) -> None:
    """#529 review 3: an export takes the state lock only after it has published, so a fault there must not say nothing changed."""
    host = _Host(tmp_path, repo)
    host.remember(CANARY)
    destination = mr.location(repo)
    host.recovery.confirm(destination, sync_consent=False)
    state_lock, real_lock = host.recovery._state.path.name + ".lock", optimus_file_lock._lock

    def refuse_the_state_lock(handle: Any) -> None:  # the one OS lock call, since #532 in optimus_file_lock
        if Path(handle.name).name == state_lock:
            raise OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))
        real_lock(handle)

    monkeypatch.setattr(optimus_file_lock, "_lock", refuse_the_state_lock)
    with pytest.raises(mr.RecoveryError) as refused:
        host.recovery.export()
    assert refused.value.code == "RECOVERY_LOCK_FAILED" and f"errno {errno.ENOLCK}" in refused.value.message
    assert "nothing" not in refused.value.message.lower()
    assert mr.generations(destination)  # published before the state lock was refused


def test_a_lock_file_that_cannot_be_opened_stays_the_callers_own_filesystem_error(tmp_path: Path) -> None:
    """#532: opening the lock's file is the caller's filesystem step, so it is the OSError it always was, never a lock
    fault code: a backup keeps reading a vanished or unwritable target from its errno."""
    import optimus_file_lock

    (tmp_path / "x.lock").mkdir()
    with pytest.raises(OSError) as failed, mr._file_lock(tmp_path / "x.lock", wait=30.0, fault_code="SOME_LOCK_FAILED"):
        pytest.fail("the lock was not taken")
    assert not isinstance(failed.value, (mr.RecoveryError, optimus_file_lock.LockFault)) and failed.value.errno is not None
