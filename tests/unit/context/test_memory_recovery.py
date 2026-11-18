"""Plan 12.11 Task 4 (D5, D8): the plaintext recovery copy and restore, against the real store on its in-memory stand-in, real Git
repositories and the real file guards. The same on real Redis, with a killed store and a lost volume, is in
tests/integration/memory/test_recovery.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from optimus.acp import memory_commands as mc
from optimus.context import memory_recovery as mr
from optimus.context.authored_memory import GatewayMemoryStore, MemoryStoreRefused
from optimus.guardrails.path_safety import PathSafetyValidator, ValidationVerdict
from tests.unit.context.test_authored_memory import _adapter
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

    def __init__(self, tmp_path: Path, workspace: Path, server: Server | None = None, *, config: str = "config") -> None:
        self.service, self.server, _journal = purge_store(tmp_path, server)
        self.store: GatewayMemoryStore = _adapter(self.service)
        self.recovery = mr.Recovery(self.store, mr.StateFile(tmp_path / config, "p-1"), registry=lambda: {"key": "git:x"})
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

    def items(self) -> dict[str, tuple[int, str, str, str]]:
        rows, _cursor = self.store.items("project", limit=100)
        return {r.event.item: (r.event.version, r.event.trust, r.event.status, r.event.statement) for r in rows}


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
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries_sha256"] = hashlib.sha256(body).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    entries.write_bytes(lines[0])
    lost = _Host(tmp_path, repo, Server())
    assert "do not match its manifest" in lost.run(f"/memory restore {generation.name}").text  # the file alone was cut
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
                        head=manifest["head"], frontier=manifest["frontier"], withdrawn=[])
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
