"""Plan 12.11 Task 4 continuity on the released memory store: checkpoints survive a killed store process, a fresh host (new
Gateway service, store client and session, with no conversation RAM) finds its predecessor, linked worktrees share a project
while a clone does not, and the brief's clocks hold. Selected with `-m requires_plan12_memory_redis`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from optimus.acp.trusted_paths import resolve_workspace_identity
from optimus.context.memory_continuity import Continuity, Settled
from optimus.context.memory_extraction import worktree_id
from optimus.context.project_registry import ProjectRegistry
from tests.integration.memory.conftest import Provisioned
from tests.integration.memory.test_lifecycle import _restart
from tests.integration.memory.test_user_authority import _service, host

pytestmark = [pytest.mark.requires_plan12_memory_redis]
DAY = 24 * 3600 * 1000


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", "-c", "init.defaultBranch=main", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


def _commit(repo: Path, message: str) -> None:
    (repo / "f.txt").write_text(message, encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", message)


def test_a_fresh_host_continues_from_the_last_settled_checkpoint_after_the_store_process_is_killed(
        provisioned: Provisioned, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, "first")
    registry = ProjectRegistry(tmp_path / "config")
    registration = registry.resolve(resolve_workspace_identity(repo), create=True)
    project = registration.project_id
    now = [1_800_000_000_000]
    old = Continuity(host(_service(provisioned, tmp_path / "journal"), project), workspace=repo, worktree=worktree_id(registration.worktree),
                     session="s-old", clock=lambda: now[0])
    assert old.record(Settled(1, "run-1", "completed", "Refactor the billing module into two services."))
    assert old.record(Settled(2, "run-2", "completed", "Now split the invoice tests the same way."))
    # turn 3 is killed before it settles: no checkpoint; then the store process itself is killed
    _restart(provisioned)
    for n in range(4):
        _commit(repo, f"later {n}")
    for gap_days, due in ((6, False), (7, True), (30, True), (120, True)):
        now[0] = 1_800_000_000_000 + gap_days * DAY
        fresh = Continuity(host(_service(provisioned, tmp_path / "journal"), project), workspace=repo,
                           worktree=worktree_id(registration.worktree), session=f"s-new-{gap_days}", clock=lambda: now[0])
        _stored, found = fresh.previous()
        assert found is not None and (found.checkpoint.session, found.checkpoint.sequence) == ("s-old", 2)
        assert fresh.due() is due
        brief = fresh.brief()
        assert "4 of 4 commits since then" in brief and "branch `main`, turn 2" in brief


def test_linked_worktrees_share_continuity_and_a_clone_does_not(provisioned: Provisioned, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, "first")
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "-b", "side", str(linked))
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(repo), str(clone))
    registry = ProjectRegistry(tmp_path / "config")
    main, side, other = (registry.resolve(resolve_workspace_identity(path), create=True) for path in (repo, linked, clone))
    service = _service(provisioned, tmp_path / "journal")
    Continuity(host(service, main.project_id), workspace=repo, worktree=worktree_id(main.worktree), session="s-main").record(
        Settled(1, "run-1", "completed", "Port the cache layer to the new client."))
    from_linked = Continuity(host(service, side.project_id), workspace=linked, worktree=worktree_id(side.worktree), session="s-side")
    assert from_linked.previous()[1] is not None and from_linked.previous()[1].checkpoint.session == "s-main"
    from_clone = Continuity(host(service, other.project_id), workspace=clone, worktree=worktree_id(other.worktree), session="s-clone")
    assert from_clone.previous() == ([], None)
