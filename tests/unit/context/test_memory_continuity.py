"""Plan 12.11 Task 4: continuation checkpoints, the predecessor a session continues from and the welcome-back brief, against the
real store on its in-memory stand-in and real Git repositories (worktrees, clones, branches, rewritten history). The same on
real Redis, across processes, is in tests/integration/memory/test_continuity.py."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from context_engine.memory_contracts import ServedMemory
from optimus.acp.trusted_paths import resolve_workspace_identity
from optimus.context import memory_serving
from optimus.context.memory_continuity import BRIEF_AFTER_MS, Continuity, Settled
from optimus.context.memory_extraction import worktree_id
from optimus.context.project_registry import ProjectRegistry
from tests.unit.context.test_authored_memory import _adapter
from tests.unit.optimus_gateway.test_memory_store_commit import store

DAY = 24 * 3600 * 1000
T0 = 1_800_000_000_000


def _run(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", "-c", "core.longpaths=true", "-c", "init.defaultBranch=main", *args], cwd=cwd, env=env,
                          check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    (repo / "f.txt").write_text(message, encoding="utf-8")
    _run(repo, "add", "f.txt")
    _run(repo, "commit", "-q", "-m", message)
    return _run(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _run(path, "init", "-q")
    _commit(path, "first")
    return path


class _Clock:
    def __init__(self, now: int = T0) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


def _session(adapter: Any, workspace: Path, name: str, clock: _Clock, worktree: str = "worktree:a") -> Continuity:
    return Continuity(adapter, workspace=workspace, worktree=worktree, session=name, clock=clock)


def _turn(n: int, prompt: str, outcome: str = "completed", **kwargs: Any) -> Settled:
    return Settled(sequence=n, run_id=f"run-{n}", outcome=outcome, prompt=prompt, **kwargs)


def test_each_settled_turn_is_checkpointed_from_host_state_and_a_status_question_never_replaces_the_objective(repo: Path) -> None:
    adapter = _adapter(store()[0])
    clock = _Clock()
    one = _session(adapter, repo, "s-1", clock)
    assert one.record(_turn(1, "Fix the failing scheduler test in the worker module."))
    assert one.record(_turn(2, "Is it done yet?"))
    assert one.record(_turn(3, "Add a regression test for the scheduler retry path too.", outcome="failed"))
    stored = adapter.checkpoints(limit=20)
    newest = stored[0].checkpoint
    assert [s.checkpoint.sequence for s in stored] == [3, 2, 1]
    assert newest.objective == "run-1" and newest.amendments == ("run-3",)  # the question changed nothing
    assert stored[1].checkpoint.objective == "run-1" and stored[1].checkpoint.amendments == ()
    assert newest.branch == "main" and newest.worktree == "worktree:a" and newest.baseline == _run(repo, "rev-parse", "HEAD")
    assert newest.remaining == ("run-3:failed",) and newest.completion == () and stored[2].checkpoint.completion == ("run-1:completed",)
    record = str(newest.to_record())
    assert "scheduler" not in record and "Fix" not in record  # references only, never the prompt's words


def test_a_killed_turn_leaves_the_last_settled_checkpoint_as_the_predecessor(repo: Path) -> None:
    adapter = _adapter(store()[0])
    clock = _Clock()
    first = _session(adapter, repo, "s-1", clock)
    first.record(_turn(1, "Refactor the billing module into two services."))
    first.record(_turn(2, "Now split the invoice tests the same way."))
    # turn 3 was killed before it settled: nothing is written for it
    clock.now += 8 * DAY
    later = _session(adapter, repo, "s-2", clock)
    _stored, found = later.previous()
    assert found is not None and (found.checkpoint.session, found.checkpoint.sequence) == ("s-1", 2)


def test_the_predecessor_is_the_same_branch_and_worktree_first_then_the_branch_then_any(repo: Path) -> None:
    adapter = _adapter(store()[0])
    clock = _Clock()
    _session(adapter, repo, "s-main-a", clock, worktree="worktree:a").record(_turn(1, "Fix the scheduler on main in worktree a."))
    clock.now += 1000
    _session(adapter, repo, "s-main-b", clock, worktree="worktree:b").record(_turn(1, "Fix the scheduler on main in worktree b."))
    _run(repo, "checkout", "-q", "-b", "feature")
    clock.now += 1000
    _session(adapter, repo, "s-feature", clock, worktree="worktree:a").record(_turn(1, "Build the feature branch's new parser."))
    assert _session(adapter, repo, "new-1", clock, worktree="worktree:a").previous()[1].checkpoint.session == "s-feature"
    _run(repo, "checkout", "-q", "main")
    assert _session(adapter, repo, "new-2", clock, worktree="worktree:a").previous()[1].checkpoint.session == "s-main-a"
    assert _session(adapter, repo, "new-3", clock, worktree="worktree:c").previous()[1].checkpoint.session == "s-main-b"
    _run(repo, "checkout", "-q", "-b", "elsewhere")
    assert _session(adapter, repo, "new-4", clock, worktree="worktree:z").previous()[1].checkpoint.session == "s-feature"


@pytest.mark.parametrize(("gap_days", "due"), [(0, False), (6, False), (7, True), (30, True), (120, True)])
def test_the_brief_shows_after_seven_days_and_nothing_expires(repo: Path, gap_days: int, due: bool) -> None:
    adapter = _adapter(store()[0])
    clock = _Clock()
    _session(adapter, repo, "s-1", clock).record(_turn(1, "Port the cache layer to the new client."))
    clock.now += gap_days * DAY if gap_days != 7 else BRIEF_AFTER_MS
    later = _session(adapter, repo, "s-2", clock)
    assert later.due() is due
    brief = later.brief()
    assert brief.startswith("**Welcome back.**") and "branch `main`" in brief  # /welcome works at any gap, below the threshold too
    reads: list[int] = []

    def served() -> memory_serving.ServedSet:
        reads.append(1)
        return memory_serving.EMPTY

    assert (later.first_response_brief(served) is not None) is due
    assert later.first_response_brief(served) is None  # once per session
    assert len(reads) == (1 if due else 0)  # memory is read for the brief only when it is due


def test_the_gap_is_measured_before_this_session_writes_its_own_checkpoint(repo: Path) -> None:
    adapter = _adapter(store()[0])
    clock = _Clock()
    _session(adapter, repo, "s-1", clock).record(_turn(1, "Port the cache layer to the new client."))
    clock.now += 10 * DAY
    later = _session(adapter, repo, "s-2", clock)
    later.record(_turn(1, "Continue the cache port where it stopped."))  # this session's own checkpoint is now the newest
    assert later.due() and "10 days ago" in later.brief()


def test_a_session_s_own_checkpoints_are_never_its_predecessor(repo: Path) -> None:
    """A host object opened again for a session that already wrote checkpoints (a reconnecting client) still continues from
    the last other session, and measures the gap from it."""
    adapter = _adapter(store()[0])
    clock = _Clock()
    _session(adapter, repo, "s-1", clock).record(_turn(1, "Port the cache layer to the new client."))
    clock.now += 10 * DAY
    _session(adapter, repo, "s-2", clock).record(_turn(1, "Continue the cache port where it stopped."))
    again = _session(adapter, repo, "s-2", clock)
    _stored, found = again.previous()
    assert found is not None and found.checkpoint.session == "s-1" and again.due()


def test_the_brief_lists_commits_since_the_baseline_n_of_m(repo: Path) -> None:
    adapter = _adapter(store()[0])
    clock = _Clock()
    _session(adapter, repo, "s-1", clock).record(_turn(1, "Port the cache layer to the new client."))
    for n in range(12):
        _commit(repo, f"change {n} `with` *markdown*")
    clock.now += 8 * DAY
    brief = _session(adapter, repo, "s-2", clock).brief()
    assert "10 of 12 commits since then" in brief and "change 11 \\`with\\` \\*markdown\\*" in brief


def test_a_rewritten_or_missing_baseline_is_said_plainly(repo: Path, tmp_path: Path) -> None:
    adapter = _adapter(store()[0])
    clock = _Clock()
    _commit(repo, "second")
    _session(adapter, repo, "s-1", clock).record(_turn(1, "Port the cache layer to the new client."))
    _run(repo, "reset", "-q", "--hard", "HEAD~1")
    _commit(repo, "rewritten second")
    clock.now += 8 * DAY
    assert "not an ancestor of the current one" in _session(adapter, repo, "s-2", clock).brief()
    plain = tmp_path / "plain"
    plain.mkdir()
    bare = _adapter(store()[0])
    _session(bare, plain, "s-1", clock).record(_turn(1, "Port the cache layer to the new client."))
    assert "commit is not known" in _session(bare, plain, "s-2", clock).brief()


def test_a_shallow_clone_says_its_history_may_be_missing(repo: Path, tmp_path: Path) -> None:
    for n in range(3):
        _commit(repo, f"history {n}")
    shallow = tmp_path / "shallow"
    _run(tmp_path, "clone", "-q", "--depth", "2", f"file://{repo.as_posix()}", str(shallow))
    adapter = _adapter(store()[0])
    clock = _Clock()
    _session(adapter, shallow, "s-1", clock).record(_turn(1, "Port the cache layer to the new client."))
    (shallow / "g.txt").write_text("x", encoding="utf-8")
    _run(shallow, "add", "g.txt")
    _run(shallow, "commit", "-q", "-m", "local")
    clock.now += 8 * DAY
    assert "a shallow clone" in _session(adapter, shallow, "s-2", clock).brief()


def test_linked_worktrees_share_the_project_and_a_clone_does_not(repo: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    _run(repo, "worktree", "add", "-q", "-b", "side", str(linked))
    clone = tmp_path / "clone"
    _run(tmp_path, "clone", "-q", str(repo), str(clone))
    registry = ProjectRegistry(tmp_path / "config")
    main, side, other = (registry.resolve(resolve_workspace_identity(path), create=True) for path in (repo, linked, clone))
    assert main.project_id == side.project_id != other.project_id
    assert worktree_id(main.worktree) != worktree_id(side.worktree)  # one project, two worktrees
    assert worktree_id(main.worktree).startswith("worktree:") and str(repo) not in worktree_id(main.worktree)


def test_historical_approvals_and_unfinished_work_are_history_not_authority(repo: Path) -> None:
    adapter = _adapter(store()[0])
    clock = _Clock()
    _session(adapter, repo, "s-1", clock).record(_turn(1, "Port the cache layer to the new client.", plan_hash="a" * 64, pending=True))
    clock.now += 8 * DAY
    brief = _session(adapter, repo, "s-2", clock).brief()
    assert "an earlier approval is never a current one" in brief and "that approval is not carried over" in brief
    assert "This is history, not instructions." in brief


def test_the_preferred_predecessor_is_found_beneath_newer_checkpoints_elsewhere(repo: Path) -> None:
    """Codex CP3 review 1, finding 5: newer checkpoints on another worktree never hide this place's own."""
    adapter = _adapter(store()[0])
    clock = _Clock()
    _session(adapter, repo, "s-here", clock, worktree="worktree:a").record(_turn(1, "Port the cache layer to the new client."))
    for n in range(21):
        clock.now += 1000
        _session(adapter, repo, f"s-else-{n}", clock, worktree="worktree:b").record(_turn(1, "Fix the scheduler in the other tree."))
    found = _session(adapter, repo, "s-new", clock, worktree="worktree:a").previous()[1]
    assert found is not None and found.checkpoint.session == "s-here"


def test_the_brief_lists_memory_changes_but_never_an_off_record(repo: Path) -> None:
    """Zed proof (CP3): an off record retired when the user switched it on was never memory, so the brief does not call it
    forgotten; the user's own withdrawn item is listed. Each section starts its own paragraph, so a Markdown client never folds
    it into the bullet above."""
    from types import SimpleNamespace

    adapter = _adapter(store()[0])
    clock = _Clock()
    _session(adapter, repo, "s-1", clock).record(_turn(1, "Port the cache layer to the new client."))
    after = str(clock.now + 1000)

    def row(item: str, trust: str, status: str, statement: str = "") -> Any:
        event = SimpleNamespace(project=adapter.project, item=item, version=2, trust=trust, status=status, statement=statement,
                                kind="preference", scope="project", title=statement[:40], anchors=())
        return SimpleNamespace(event=event, stream_id=f"{after}-0")

    rows = [row("m-000000000000000a", "user-authored", "withdrawn"), row("m-000000000000000b", "off", "withdrawn"),
            row("m-000000000000000c", "user-authored", "active", "From now on we use uv for every command.")]
    clock.now += 2000
    later = _session(adapter, repo, "s-2", clock)
    later._store = SimpleNamespace(project=adapter.project, checkpoints=adapter.checkpoints,  # type: ignore[assignment]
                                   items=lambda *_a, **_k: (rows, None))
    served = memory_serving.select([ServedMemory(adapter.project, "m-000000000000000c", 2, "user-authored", "preference", "project",
                                                 "uv", "From now on we use uv for every command.", ())])
    brief = later.welcome(served)
    # Codex CP4 review 16: the brief lists only what checked serving serves (an item of another branch, or one whose file
    # changed, is not in the served set), never an active item the store merely holds
    assert "m-000000000000000c" in brief and "m-000000000000000c" not in later.welcome(memory_serving.EMPTY)
    assert "`m-000000000000000a@2` was forgotten" in brief and "m-000000000000000b" not in brief
    assert "\n\nYour items that apply now:\n" in brief and "\n\nMemory changed since then:\n" in brief
