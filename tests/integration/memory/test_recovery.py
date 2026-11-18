"""Plan 12.11 Task 4 recovery on the released memory store: a real lost volume (the container and its volume removed and recreated
from the same configuration and credential), restore, the deletion journal across it, an unfinished purge that blocks
publication, and refusal of a store holding anything. Selected with `-m requires_plan12_memory_redis`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import local_infra
from optimus.acp import memory_commands as mc
from optimus.context import memory_recovery as mr
from optimus_gateway import memory_store
from tests.integration.memory.conftest import CONTAINER, VOLUME, Provisioned, docker, wait_for_auth
from tests.integration.memory.test_store import _project
from tests.integration.memory.test_user_authority import _run, _service, _stream, host

pytestmark = [pytest.mark.requires_plan12_memory_redis]
CANARY = "Remember the canary phrase zebra-quartz-7731."


def _lose_the_volume(provisioned: Provisioned) -> None:
    """The store's container and its volume are gone; the launch recreates both, empty, from the same config and credential."""
    docker("rm", "-f", CONTAINER, check=True)
    docker("volume", "rm", "-f", VOLUME, check=True)
    status = local_infra.ensure_memory_store_redis(provisioned.root)
    assert status.state == "ready", status
    memory_store.verify_resource(wait_for_auth(provisioned), provisioned.config.resource)


def _workspace(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q"], cwd=repo, env=env, check=True, stdin=subprocess.DEVNULL)
    return repo


def _host(provisioned: Provisioned, tmp_path: Path, project: str, repo: Path) -> tuple[Any, mr.Recovery, mc.MemoryCommands]:
    store = host(_service(provisioned, tmp_path / "journal"), project)
    recovery = mr.Recovery(store, mr.StateFile(tmp_path / "config", project))
    store.guard, store.written = recovery.recovery_required, recovery.written
    return store, recovery, mc.MemoryCommands(store, trusted=True, sanitize=lambda v: v, recovery=recovery, workspace=repo)


def _go(commands: mc.MemoryCommands, text: str) -> mc.MemoryAnswer:
    answer = _run(commands, text)
    if answer.confirm is not None:
        answer = commands.confirmed(answer.confirm)
    if answer.purge is not None:
        answer = commands.purge(answer.purge)
    return answer


def test_a_lost_volume_is_restored_from_the_copy_with_later_deletions_kept(provisioned: Provisioned, tmp_path: Path) -> None:
    repo, project = _workspace(tmp_path), _project()
    store, recovery, commands = _host(provisioned, tmp_path, project, repo)
    rule = _go(commands, "/remember Never push to main.").notices[0][0]
    secret = _go(commands, f"/remember {CANARY}").notices[0][0]
    other = _go(commands, "/remember Use uv for every command.").notices[0][0]
    _go(commands, "/memory export")
    _go(commands, f"/forget {secret.item}@1 --purge")  # purged after the copy: the journal outlives the volume
    _go(commands, f"/forget {other.item}@1")  # withdrawn after the copy: the host's state outlives it
    (generation,) = mr.generations(mr.location(repo))
    _lose_the_volume(provisioned)
    store, recovery, commands = _host(provisioned, tmp_path, project, repo)
    assert recovery.recovery_required() and "Restore it first" in _go(commands, "/remember Use ruff.").text
    assert _stream(provisioned, project) == []
    answer = _go(commands, f"/memory restore {generation.name}")
    assert "Restored" in answer.text, answer.text
    assert (store.read(rule.item).event.version, store.read(rule.item).event.statement) == (1, "Never push to main.")
    assert store.read(secret.item).event.status == "purged" and store.read(secret.item).event.statement == ""
    assert store.read(other.item).event.status == "withdrawn"
    raw = b"".join(provisioned.connect().hgetall(memory_store.MemoryStore._key(project, "payloads")).values())
    assert b"zebra-quartz" not in raw  # the purged text was not brought back into Redis
    assert _go(commands, "/remember Use ruff.").notices[0][0].saved


def test_a_purge_interrupted_before_its_tombstone_blocks_restore_after_the_volume_is_lost(provisioned: Provisioned, tmp_path: Path) -> None:
    """The deletion intent is journalled before the tombstone is sent; the volume is then lost. An old copy alone cannot show
    the purge did not happen, so restore publishes nothing."""
    repo, project = _workspace(tmp_path), _project()
    store, recovery, commands = _host(provisioned, tmp_path, project, repo)
    secret = _go(commands, f"/remember {CANARY}").notices[0][0]
    _go(commands, "/memory export")
    (generation,) = mr.generations(mr.location(repo))
    service = _service(provisioned, tmp_path / "journal")
    inner = service._store  # type: ignore[attr-defined]
    inner._need_journal().record(inner._project_hash(project), secret.item, "intent", version=2, key="k" * 64)
    _lose_the_volume(provisioned)
    _store, _recovery, commands = _host(provisioned, tmp_path, project, repo)
    assert "a deletion is unfinished" in _go(commands, f"/memory restore {generation.name}").text
    assert _stream(provisioned, project) == []


def test_restore_refuses_a_store_holding_anything_and_leaves_it_unchanged(provisioned: Provisioned, tmp_path: Path) -> None:
    repo, project = _workspace(tmp_path), _project()
    _store, _recovery, commands = _host(provisioned, tmp_path, project, repo)
    _go(commands, "/remember Never push to main.")
    _go(commands, "/memory export")
    (generation,) = mr.generations(mr.location(repo))
    before = _stream(provisioned, project)
    assert "already holds" in _go(commands, f"/memory restore {generation.name}").text
    assert _stream(provisioned, project) == before
    assert _go(commands, "/remember Never push to main.").notices[0][0].saved and _stream(provisioned, project) == before  # replayed


def test_an_admission_landing_during_staging_aborts_publication(provisioned: Provisioned, tmp_path: Path) -> None:
    repo, project = _workspace(tmp_path), _project()
    _store, recovery, commands = _host(provisioned, tmp_path, project, repo)
    for n in range(11):
        _go(commands, f"/remember Rule number {n} holds.")
    _go(commands, "/memory export")
    (generation,) = mr.generations(mr.location(repo))
    manifest, entries = recovery.read_generation(generation.name)
    _lose_the_volume(provisioned)
    store, _recovery, _commands = _host(provisioned, tmp_path, project, repo)
    with store.lease(guarded=False) as token:
        store.call("restore", project=project, token=token, generation=manifest["seal"], batch=0, final=False, entries=entries[:10])
    newcomer = host(_service(provisioned, tmp_path / "journal"), project, owner="host-2")  # a host that never knew the project
    _run(mc.MemoryCommands(newcomer, trusted=True, sanitize=lambda v: v), "/remember A concurrent rule.")
    from optimus.context.authored_memory import MemoryStoreRefused

    with store.lease(guarded=False) as token, pytest.raises(MemoryStoreRefused) as refused:
        store.call("restore", project=project, token=token, generation=manifest["seal"], batch=1, final=True, entries=entries[10:],
                   head=manifest["head"], frontier=manifest["frontier"], withdrawn=[], bind=manifest["bind"], journal=manifest["journal"],
                   purged=[])
    assert refused.value.code == "RESTORE_TARGET_NOT_EMPTY" and len(_stream(provisioned, project)) == 1
