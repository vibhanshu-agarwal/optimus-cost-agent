"""Plan 12.6 Task 2: registered project identity, on real temporary Git repositories, real subprocesses and the real
filesystem. Every registry lives under a temporary config root; no real user registry or keyring is touched."""

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from optimus.acp.trusted_paths import GitContextDisposition, resolve_workspace_identity
from optimus.context import project_registry
from optimus.context.project_registry import ProjectRegistry, ProjectRegistryError

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs a real Git for worktrees and clones")

_GIT = ("git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "init.defaultBranch=main")


def _git(*args: str) -> None:
    subprocess.run([*_GIT, *args], check=True, capture_output=True)


@pytest.fixture
def repos(tmp_path):
    """A repository, its linked worktree, a clone of it, a second clone, and a folder outside Git."""
    origin, worktree, clone, fork = (tmp_path / name for name in ("origin", "worktree", "clone", "fork"))
    _git("init", "-q", str(origin))
    _git("-C", str(origin), "commit", "-q", "--allow-empty", "-m", "root")
    _git("-C", str(origin), "worktree", "add", "-q", str(worktree), "-b", "side")
    _git("clone", "-q", str(origin), str(clone))
    _git("clone", "-q", str(origin), str(fork))
    plain = tmp_path / "plain"
    plain.mkdir()
    return {"origin": origin, "worktree": worktree, "clone": clone, "fork": fork, "plain": plain}


def _registry(tmp_path: Path) -> ProjectRegistry:
    return ProjectRegistry(tmp_path / "config")


def test_linked_worktrees_share_one_id_and_clones_and_forks_do_not(tmp_path, repos):
    registry = _registry(tmp_path)
    ids = {name: registry.resolve(resolve_workspace_identity(path), create=True).project_id for name, path in repos.items()}

    assert ids["origin"] == ids["worktree"]
    assert len({ids["origin"], ids["clone"], ids["fork"], ids["plain"]}) == 4, "same root commit, distinct projects"
    entry = registry.snapshot()["projects"][project_registry.project_key(resolve_workspace_identity(repos["origin"]))]
    assert len(entry["worktrees"]) == 2, "worktree applicability is recorded beside the shared id"


def test_resolution_is_stable_and_lookup_never_allocates(tmp_path, repos):
    registry = _registry(tmp_path)
    identity = resolve_workspace_identity(repos["plain"])

    with pytest.raises(ProjectRegistryError) as missing:
        registry.resolve(identity, create=False)
    assert missing.value.code == "NOT_REGISTERED" and not registry.path.exists(), "a lookup writes nothing"
    first = registry.resolve(identity, create=True)
    again = ProjectRegistry(tmp_path / "config").resolve(identity, create=False)

    assert first.created and not again.created and again.project_id == first.project_id
    assert first.key.startswith("path:") and first.registry_version == project_registry.REGISTRY_VERSION


def test_a_shared_project_id_leaves_workspace_security_identity_unchanged(tmp_path, repos):
    before = {name: resolve_workspace_identity(repos[name]) for name in ("origin", "worktree")}
    registry = _registry(tmp_path)
    for identity in before.values():
        registry.resolve(identity, create=True)
    after = {name: resolve_workspace_identity(repos[name]) for name in ("origin", "worktree")}

    def security(identity):  # probe diagnostics carry timings, so compare what approvals bind
        return identity.digest, identity.canonical_path, identity.git_common_dir, identity.repository_root

    assert {name: security(item) for name, item in after.items()} == {name: security(item) for name, item in before.items()}
    assert before["origin"].digest != before["worktree"].digest, "worktrees keep distinct workspace identities"


def test_concurrent_processes_allocate_exactly_one_id(tmp_path, repos):
    config = tmp_path / "config"
    script = (
        "import sys; from pathlib import Path\n"
        "from optimus.acp.trusted_paths import resolve_workspace_identity\n"
        "from optimus.context.project_registry import ProjectRegistry\n"
        "r = ProjectRegistry(Path(sys.argv[1]), lock_wait_seconds=30)\n"
        "print(r.resolve(resolve_workspace_identity(Path(sys.argv[2])), create=True).project_id)\n"
    )
    targets = [repos["origin"], repos["worktree"]] * 3
    workers = [
        subprocess.Popen([sys.executable, "-c", script, str(config), str(target)], stdout=subprocess.PIPE, text=True)
        for target in targets
    ]
    outputs = [worker.communicate(timeout=120)[0].strip() for worker in workers]

    assert all(worker.returncode == 0 for worker in workers)
    assert len(set(outputs)) == 1 and len(outputs[0]) == 32
    assert len(ProjectRegistry(config).snapshot()["projects"]) == 1


def test_an_interrupted_replacement_keeps_the_previous_registry(tmp_path, repos, monkeypatch):
    registry = _registry(tmp_path)
    kept = registry.resolve(resolve_workspace_identity(repos["origin"]), create=True)
    before = registry.path.read_bytes()

    def crash(source, destination):
        raise OSError(5, "simulated crash before the atomic replacement")

    monkeypatch.setattr(project_registry.os, "replace", crash)
    with pytest.raises(ProjectRegistryError) as failed:
        registry.resolve(resolve_workspace_identity(repos["clone"]), create=True)
    monkeypatch.undo()

    assert failed.value.code == "WRITE_FAILED"
    assert registry.path.read_bytes() == before
    assert not [path for path in registry.path.parent.iterdir() if path.suffix == ".tmp"], "no temporary file is left"
    assert registry.resolve(resolve_workspace_identity(repos["origin"]), create=False).project_id == kept.project_id


@pytest.mark.parametrize(
    "content",
    [b"{not json", b'{"registry_version": 99, "projects": {}}', b'{"registry_version": 1, "projects": []}',
     b'{"registry_version": 1, "projects": {"git:x": {"project_id": "short", "worktrees": []}}}', b"\xff\xfe"],
)
def test_a_corrupt_registry_is_reported_and_never_replaced(tmp_path, repos, content):
    registry = _registry(tmp_path)
    registry.path.parent.mkdir(parents=True)
    registry.path.write_bytes(content)

    with pytest.raises(ProjectRegistryError) as corrupt:
        registry.resolve(resolve_workspace_identity(repos["plain"]), create=True)

    assert corrupt.value.code == "CORRUPT" and registry.path.read_bytes() == content
    assert "not json" not in str(corrupt.value), "the error carries no registry content"


def test_duplicate_ids_across_projects_are_corrupt(tmp_path, repos):
    registry = _registry(tmp_path)
    registry.resolve(resolve_workspace_identity(repos["origin"]), create=True)
    registry.resolve(resolve_workspace_identity(repos["clone"]), create=True)
    data = json.loads(registry.path.read_text(encoding="utf-8"))
    ids = [entry["project_id"] for entry in data["projects"].values()]
    for entry in data["projects"].values():
        entry["project_id"] = ids[0]
    registry.path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ProjectRegistryError, match="CORRUPT"):
        registry.snapshot()


def test_a_relocated_project_is_not_linked_without_consent(tmp_path, repos):
    registry = _registry(tmp_path)
    original = registry.resolve(resolve_workspace_identity(repos["plain"]), create=True)
    moved = tmp_path / "moved"
    os.rename(repos["plain"], moved)

    with pytest.raises(ProjectRegistryError, match="NOT_REGISTERED"):
        registry.resolve(resolve_workspace_identity(moved), create=False)
    relocated = registry.resolve(resolve_workspace_identity(moved), create=True)

    assert relocated.project_id != original.project_id, "a move is a new project until a host action links it"
    assert original.key in registry.snapshot()["projects"], "the old registration is kept for recovery"


def test_unavailable_git_evidence_is_refused_rather_than_registered_by_folder(tmp_path, repos):
    identity = resolve_workspace_identity(repos["origin"])
    unavailable = dataclasses.replace(
        identity,
        git_context=dataclasses.replace(identity.git_context, disposition=GitContextDisposition.UNAVAILABLE),
    )

    with pytest.raises(ProjectRegistryError, match="UNAVAILABLE"):
        _registry(tmp_path).resolve(unavailable, create=True)
    assert not (tmp_path / "config" / project_registry.REGISTRY_FILE_NAME).exists()


def test_lock_contention_is_bounded_and_reported(tmp_path, repos):
    config = tmp_path / "config"
    holder = ProjectRegistry(config)
    waiter = ProjectRegistry(config, lock_wait_seconds=0.2)

    with holder._lock(), pytest.raises(ProjectRegistryError) as contention:
        waiter.resolve(resolve_workspace_identity(repos["plain"]), create=True)

    assert contention.value.code == "LOCK_CONTENTION"


# --- Codex round 82: registry loss, restore, and the commit boundaries ---


def test_a_lost_registry_requires_recovery_and_restore_keeps_the_ids(tmp_path, repos):
    registry = _registry(tmp_path)
    identity = resolve_workspace_identity(repos["origin"])
    original = registry.resolve(identity, create=True)
    exported = registry.snapshot()
    registry.path.unlink()

    with pytest.raises(ProjectRegistryError) as lost:
        registry.resolve(identity, create=True)
    registry.restore(exported)

    assert lost.value.code == "RECOVERY_REQUIRED"
    assert registry.resolve(identity, create=False).project_id == original.project_id


def test_restore_never_overwrites_and_rejects_a_malformed_snapshot(tmp_path, repos):
    registry = _registry(tmp_path)
    registry.resolve(resolve_workspace_identity(repos["plain"]), create=True)
    before = registry.path.read_bytes()

    for snapshot in (registry.snapshot(), {"registry_version": 1, "projects": []}):
        with pytest.raises(ProjectRegistryError, match="RESTORE_REFUSED"):
            registry.restore(snapshot)
    assert registry.path.read_bytes() == before


def test_a_failure_after_the_replacement_is_reported_as_uncertain(tmp_path, repos, monkeypatch):
    registry = _registry(tmp_path)
    registry.resolve(resolve_workspace_identity(repos["origin"]), create=True)

    def failing(directory):
        raise OSError(5, "simulated directory fsync failure")

    monkeypatch.setattr(project_registry, "_fsync_directory", failing)
    with pytest.raises(ProjectRegistryError) as uncertain:
        registry.resolve(resolve_workspace_identity(repos["clone"]), create=True)
    monkeypatch.undo()

    assert uncertain.value.code == "WRITE_UNCERTAIN"
    assert len(registry.snapshot()["projects"]) == 2, "reopening shows the replaced registry, whole"


def test_a_process_killed_at_the_commit_boundary_leaves_the_previous_registry(tmp_path, repos):
    config = tmp_path / "config"
    registry = ProjectRegistry(config)
    kept = registry.resolve(resolve_workspace_identity(repos["origin"]), create=True)
    before = registry.path.read_bytes()
    script = (
        "import os, sys; from pathlib import Path\n"
        "from optimus.acp.trusted_paths import resolve_workspace_identity\n"
        "from optimus.context import project_registry as pr\n"
        "pr.os.replace = lambda *a: os._exit(3)  # die after the fsynced temporary file, before the replacement\n"
        "pr.ProjectRegistry(Path(sys.argv[1])).resolve(resolve_workspace_identity(Path(sys.argv[2])), create=True)\n"
    )
    killed = subprocess.run([sys.executable, "-c", script, str(config), str(repos["clone"])], timeout=120)

    assert killed.returncode == 3
    assert registry.path.read_bytes() == before
    assert registry.resolve(resolve_workspace_identity(repos["origin"]), create=False).project_id == kept.project_id
    assert registry.resolve(resolve_workspace_identity(repos["clone"]), create=True).created


def test_the_first_registration_writes_the_marker_before_the_registry(tmp_path, repos):
    registry = _registry(tmp_path)
    registry.resolve(resolve_workspace_identity(repos["plain"]), create=True)

    assert (tmp_path / "config" / project_registry.MARKER_FILE_NAME).is_file()


def test_the_marker_exists_at_the_first_registry_replacement(tmp_path, repos, monkeypatch):
    registry = _registry(tmp_path)
    marker = tmp_path / "config" / project_registry.MARKER_FILE_NAME
    seen: list[bool] = []

    def observing(source, destination):
        seen.append(marker.is_file())
        raise OSError(5, "stop at the first publication")

    monkeypatch.setattr(project_registry.os, "replace", observing)
    with pytest.raises(ProjectRegistryError, match="WRITE_FAILED"):
        registry.resolve(resolve_workspace_identity(repos["plain"]), create=True)

    assert seen == [True], "the marker is durable before the registry is first published"


def test_a_process_killed_at_first_initialization_requires_explicit_recovery(tmp_path, repos):
    config = tmp_path / "config"
    script = (
        "import os, sys; from pathlib import Path\n"
        "from optimus.acp.trusted_paths import resolve_workspace_identity\n"
        "from optimus.context import project_registry as pr\n"
        "pr.os.replace = lambda *a: os._exit(3)  # die at the first publication, after the marker\n"
        "pr.ProjectRegistry(Path(sys.argv[1])).resolve(resolve_workspace_identity(Path(sys.argv[2])), create=True)\n"
    )
    killed = subprocess.run([sys.executable, "-c", script, str(config), str(repos["plain"])], timeout=120)
    registry = ProjectRegistry(config)
    identity = resolve_workspace_identity(repos["plain"])

    assert killed.returncode == 3 and not registry.path.exists()
    with pytest.raises(ProjectRegistryError, match="RECOVERY_REQUIRED"):
        registry.resolve(identity, create=True)
    assert not registry.path.exists(), "no identity is allocated before an explicit recovery"
    registry.restore({"registry_version": project_registry.REGISTRY_VERSION, "projects": {}})
    assert registry.resolve(identity, create=True).created
