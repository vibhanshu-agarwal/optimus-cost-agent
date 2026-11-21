"""Plan 12.12 Task 2 import on the released memory store: resume after an interrupted apply, notices bound to the store's own
commits, restore versus import of the same generation, a withdrawn import leaving the next copy payload-free, and project
registration across a linked worktree and a clone. Selected with `-m requires_plan12_memory_redis`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import memory_commands as mc
from optimus.acp.trusted_paths import resolve_workspace_identity
from optimus.context import memory_import as mi
from optimus.context import memory_recovery as mr
from optimus.context import memory_serving
from optimus.context.authored_memory import MemoryStoreUnavailable
from optimus.context.project_registry import ProjectRegistry
from tests.integration.memory.conftest import Provisioned
from tests.integration.memory.test_recovery import _go, _lose_the_volume, _workspace
from tests.integration.memory.test_store import _project
from tests.integration.memory.test_user_authority import _run, _service, _stream, host

pytestmark = [pytest.mark.requires_plan12_memory_redis]
_GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _host(provisioned: Provisioned, tmp_path: Path, project: str, repo: Path, *, store: Any = None) -> tuple[Any, mr.Recovery, mc.MemoryCommands]:
    store = store or host(_service(provisioned, tmp_path / "journal"), project)
    recovery = mr.Recovery(store, mr.StateFile(tmp_path / "config", project))
    store.guard, store.written = recovery.recovery_required, recovery.written
    commands = mc.MemoryCommands(store, trusted=True, sanitize=lambda v: v, scope="project", recovery=recovery, workspace=repo,
                                 imports=mi.ImportLog(tmp_path / "config", project))
    return store, recovery, commands


def _source(root: Path, body: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "MEMORY.md").write_text(body, encoding="utf-8")
    return root


def _imported(commands: mc.MemoryCommands, root: Path, mapped: str | None = None) -> mc.MemoryAnswer:
    preview = _run(commands, f"/memory import {root}" + (f" --map {mapped}" if mapped else ""))
    asked = _run(commands, f"/memory import apply {preview.text.split('`', 2)[1]}")
    assert asked.confirm is not None, asked.text
    return commands.confirmed(asked.confirm)


def _events(store: Any) -> list[Any]:
    rows, _cursor = store.items("project", limit=100)
    return sorted((row.event for row in rows), key=lambda e: e.statement)


class _Dies:
    """The Gateway stops answering after `after` appends: the host loses its store mid-apply."""

    def __init__(self, inner: Any, after: int) -> None:
        self._inner, self._left = inner, after

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def append(self, *args: Any, **kwargs: Any) -> Any:
        if self._left == 0:
            raise MemoryStoreUnavailable("gone")
        self._left -= 1
        return self._inner.append(*args, **kwargs)


def test_resume_never_duplicates(provisioned: Provisioned, tmp_path: Path) -> None:
    """I14, I15: an apply cut off mid-way reports its progress; applying again finishes it, and the store's stream holds exactly
    one admit per entry."""
    repo, project = _workspace(tmp_path), _project()
    root = _source(tmp_path / "src", "".join(f"- Imported entry number {n}. [project: {project}]\n" for n in range(8)))
    inner = host(_service(provisioned, tmp_path / "journal"), project)
    _store, _recovery, dying = _host(provisioned, tmp_path, project, repo, store=_Dies(inner, 3))
    first = _imported(dying, root)
    assert "3 saved" in first.text and "4 were not tried" in first.text
    _store, _recovery, commands = _host(provisioned, tmp_path, project, repo, store=inner)
    assert "interrupted" in _run(commands, "/memory import status").text
    assert "5 saved, 3 already present" in _imported(commands, root).text
    assert "0 saved, 8 already present" in _imported(commands, root).text
    stream = _stream(provisioned, project)
    assert len(stream) == 8 and len(_events(inner)) == 8
    assert {e.trust for e in _events(inner)} == {"legacy-import"}


def test_notices_bind_to_actual_commits(provisioned: Provisioned, tmp_path: Path) -> None:
    """I25: each notice is the store's own commit result: its event id, item and version are the stream's, fsync-confirmed."""
    repo, project = _workspace(tmp_path), _project()
    root = _source(tmp_path / "src", f"- The CI uses uv. [project: {project}]\n- Releases are tagged vX.Y. [project: {project}]\n")
    store, _recovery, commands = _host(provisioned, tmp_path, project, repo)
    answer = _imported(commands, root)
    noticed = sorted((n.event_id, n.item, n.version, n.durable_state) for n, _label in answer.notices)
    assert noticed == sorted((e.event_id, e.item, e.version, "confirmed") for e in _events(store))
    served = memory_serving.from_store(store, "project", root=repo)
    assert {s.item for s in served.optional} == {e.item for e in _events(store)} and not served.protected


def test_restore_keeps_authority_and_import_downgrades_it(provisioned: Provisioned, tmp_path: Path) -> None:
    """I26: the same generation restored keeps the user's authority; imported, it is optional imported context only."""
    repo, project = _workspace(tmp_path), _project()
    store, recovery, commands = _host(provisioned, tmp_path, project, repo)
    rule = _go(commands, "/remember Never push to main.").notices[0][0]
    generation = _go(commands, "/memory export")
    assert "Recovery copies now go to" in generation.text or "Saved the recovery copy" in generation.text
    name = mr.generations(Path(recovery.state().destination))[0].name
    folder = Path(recovery.state().destination) / name
    other = _project()
    _store_b, _recovery_b, commands_b = _host(provisioned, tmp_path / "b", other, repo)
    assert "1 saved" in _imported(commands_b, folder, mapped=project).text
    (imported,) = _events(_store_b)
    assert (imported.trust, imported.statement) == ("legacy-import", "Never push to main.")
    assert "claimed-origin:user" in imported.lineage and f"import-of:{rule.item}@1" in imported.lineage
    _lose_the_volume(provisioned)
    store, recovery, commands = _host(provisioned, tmp_path, project, repo)
    seal = mr.generations(Path(recovery.state().destination))[0].seal
    reply = recovery.restore(name, seal=seal, workspace=repo)
    assert reply.get("restored") == 1
    (restored,) = _events(store)
    assert (restored.item, restored.trust, restored.statement) == (rule.item, "user-authored", "Never push to main.")


def test_a_withdrawn_import_leaves_the_next_copy_payload_free(provisioned: Provisioned, tmp_path: Path) -> None:
    """I18: an imported item withdrawn later is served no more, and the next copy carries only its payload-free lifecycle."""
    repo, project = _workspace(tmp_path), _project()
    root = _source(tmp_path / "src", f"- Squash before merging. [project: {project}]\n")
    store, recovery, commands = _host(provisioned, tmp_path, project, repo)
    _imported(commands, root)
    _go(commands, "/memory export")
    (event,) = _events(store)
    assert "Forgotten" in _run(commands, f"/forget {event.item}@1").text
    _go(commands, "/memory export")
    newest = mr.generations(Path(recovery.state().destination))[0]
    body = (Path(recovery.state().destination) / newest.name / "entries.jsonl").read_text(encoding="utf-8")
    assert "Squash before merging" not in body and event.item in body
    assert not memory_serving.from_store(store, "project", root=repo).optional
    assert "0 saved, 1 already present" in _imported(commands, root).text  # importing it again revives nothing


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, env=_GIT_ENV, check=True, stdin=subprocess.DEVNULL, capture_output=True)


def test_a_linked_worktree_shares_imports_and_a_clone_does_not(provisioned: Provisioned, tmp_path: Path) -> None:
    """I28, M18-c: imports belong to the registration; a linked worktree resolves to it, a clone is another registration."""
    repo = _workspace(tmp_path)
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "worktree", "add", "-q", "-b", "feature-x", str(tmp_path / "wt-2"))
    _git(tmp_path, "clone", "-q", str(repo), str(tmp_path / "clone"))
    registry = ProjectRegistry(tmp_path / "config")
    main, linked, clone = (registry.resolve(resolve_workspace_identity(path), create=True).project_id
                           for path in (repo, tmp_path / "wt-2", tmp_path / "clone"))
    assert main == linked and clone != main
    store, _recovery, commands = _host(provisioned, tmp_path, main, repo)
    _imported(commands, _source(tmp_path / "src", f"- Run tests with pytest -q. [project: {main}]\n"))
    seen_linked = memory_serving.from_store(host(_service(provisioned, tmp_path / "journal"), linked), "project", root=tmp_path / "wt-2",
                                            branch="feature-x")
    seen_clone = memory_serving.from_store(host(_service(provisioned, tmp_path / "journal"), clone), "project", root=tmp_path / "clone")
    assert [s.statement for s in seen_linked.optional] == ["Run tests with pytest -q."] and not seen_clone.optional
