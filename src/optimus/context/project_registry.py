"""Registered project identity (Plan 12.6 Task 2, ADR-031): one local UUID per trusted canonical Git common directory,
so linked worktrees share it while clones and forks do not; a folder outside Git is registered by its canonical path.

The registry is versioned JSON under the per-user config root, outside every workspace. A cross-process lock, an
fsynced temporary file and an atomic replacement protect allocation against concurrent writers and an interrupted
process on every platform; power-loss durability of the replacement is POSIX-only (the directory is fsynced there, and
a Windows rename is not written through). A marker written before the first registration tells first use apart from
a lost registry: a corrupt or missing registry with prior state is reported, never silently reallocated, and only an
explicit restore() writes it back. A relocated project gets no automatic link: linking is a future authenticated host
action. The project ID is grouping only; it never changes a workspace's trust identity, approvals or file permissions.
"""

from __future__ import annotations

import errno
import json
import os
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from optimus.acp.trusted_paths import GitContextDisposition, WorkspaceIdentity

REGISTRY_VERSION = 1
REGISTRY_FILE_NAME = "project-registry.json"
MARKER_FILE_NAME = "project-registry.initialized"
_LOCK_FILE_NAME = "project-registry.lock"
_LOCK_WAIT_SECONDS = 5.0
_LOCK_POLL_SECONDS = 0.05
_CONTENTION_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK})


class ProjectRegistryError(Exception):
    """``code``: CORRUPT, RECOVERY_REQUIRED, UNAVAILABLE, LOCK_CONTENTION, LOCK_FAILED, WRITE_FAILED, WRITE_UNCERTAIN,
    NOT_REGISTERED or RESTORE_REFUSED; it never carries registry content."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ProjectRegistration:
    project_id: str
    registry_version: int
    key: str  # "git:<canonical common dir>" or "path:<canonical folder>"
    worktree: str  # the canonical workspace this resolution is for, recorded separately from the grouping key
    created: bool


class ProjectRegistry:
    def __init__(self, config_root: Path, *, lock_wait_seconds: float = _LOCK_WAIT_SECONDS) -> None:
        self._root = config_root
        self._path = config_root / REGISTRY_FILE_NAME
        self._marker = config_root / MARKER_FILE_NAME
        self._lock_wait_seconds = lock_wait_seconds

    @property
    def path(self) -> Path:
        return self._path

    def resolve(self, identity: WorkspaceIdentity, *, create: bool) -> ProjectRegistration:
        key, worktree = project_key(identity), _normalized(identity.canonical_path)  # refuse before locking
        with self._lock():
            data = self._load()
            entry = data["projects"].get(key)
            if entry is not None:
                if worktree not in entry["worktrees"]:
                    entry["worktrees"] = sorted({*entry["worktrees"], worktree})
                    self._store(data)
                return ProjectRegistration(entry["project_id"], REGISTRY_VERSION, key, worktree, created=False)
            if not create:
                raise ProjectRegistryError("NOT_REGISTERED", "this project has no registration")
            project_id = uuid.uuid4().hex
            data["projects"][key] = {"project_id": project_id, "worktrees": [worktree]}
            self._store(data)
            return ProjectRegistration(project_id, REGISTRY_VERSION, key, worktree, created=True)

    def snapshot(self) -> dict[str, Any]:
        """An exportable copy of the whole registry, for recovery (M3)."""
        with self._lock():
            return self._load()

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Write back an exported snapshot after the registry was lost; an existing registry is never overwritten."""
        if not _well_formed(snapshot):
            raise ProjectRegistryError("RESTORE_REFUSED", "the snapshot does not match the registry schema")
        with self._lock():
            if self._path.exists():
                raise ProjectRegistryError("RESTORE_REFUSED", "a registry already exists; it is never overwritten")
            self._store(snapshot)

    def _load(self) -> dict[str, Any]:
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            if self._marker.exists():
                raise ProjectRegistryError(
                    "RECOVERY_REQUIRED", "the registry is missing although projects were registered; restore it"
                ) from None
            return {"registry_version": REGISTRY_VERSION, "projects": {}}
        except OSError as exc:
            raise ProjectRegistryError("CORRUPT", f"the registry cannot be read (errno {exc.errno})") from None
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProjectRegistryError("CORRUPT", "the registry is not valid JSON; recover it before use") from None
        if not _well_formed(data):
            raise ProjectRegistryError("CORRUPT", "the registry does not match its schema; recover it before use")
        return data

    def _store(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, sort_keys=True, indent=2).encode("utf-8")
        temporary = self._path.with_name(f"{self._path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            if not self._marker.exists():  # before any registration exists, so its loss is always detectable
                _write_durably(self._marker, json.dumps({"registry_version": REGISTRY_VERSION}).encode("utf-8"))
                _fsync_directory(self._root)
            _write_durably(temporary, payload)
            os.replace(temporary, self._path)
        except OSError as exc:
            raise ProjectRegistryError("WRITE_FAILED", f"the registry was not changed (errno {exc.errno})") from None
        finally:
            temporary.unlink(missing_ok=True)
        try:
            _fsync_directory(self._root)
        except OSError as exc:
            raise ProjectRegistryError(
                "WRITE_UNCERTAIN", f"the registry was replaced but may not be durable (errno {exc.errno}); reopen it"
            ) from None

    @contextmanager
    def _lock(self) -> Iterator[None]:
        try:
            lock_dir = self._root / "locks"
            lock_dir.mkdir(parents=True, exist_ok=True)
            handle = open(lock_dir / _LOCK_FILE_NAME, "w")  # noqa: SIM115
        except OSError as exc:
            raise ProjectRegistryError("LOCK_FAILED", f"cannot open the registry lock file (errno {exc.errno})") from None
        try:
            deadline = time.monotonic() + self._lock_wait_seconds
            while True:
                try:
                    if sys.platform == "win32":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in _CONTENTION_ERRNOS:
                        raise ProjectRegistryError("LOCK_FAILED", f"cannot lock the registry (errno {exc.errno})") from None
                    if time.monotonic() >= deadline:
                        raise ProjectRegistryError("LOCK_CONTENTION", "another process holds the registry") from None
                    time.sleep(_LOCK_POLL_SECONDS)
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            handle.close()


def project_key(identity: WorkspaceIdentity) -> str:
    """The grouping key: the canonical Git common directory shared by linked worktrees, else the canonical folder.
    Unavailable Git evidence is refused: a repository must never be registered by its folder by mistake."""
    disposition = identity.git_context.disposition
    if disposition is GitContextDisposition.PRESENT and identity.git_common_dir:
        return "git:" + _normalized(identity.git_common_dir)
    if disposition is GitContextDisposition.ABSENT:
        return "path:" + _normalized(identity.canonical_path)
    raise ProjectRegistryError("UNAVAILABLE", "the workspace's Git context could not be established")


def _normalized(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))  # NTFS compares names case-insensitively


def _well_formed(data: object) -> bool:
    if not isinstance(data, dict) or data.get("registry_version") != REGISTRY_VERSION:
        return False
    projects = data.get("projects")
    if not isinstance(projects, dict):
        return False
    seen: set[str] = set()
    for key, entry in projects.items():
        if not (isinstance(key, str) and key.startswith(("git:", "path:")) and isinstance(entry, dict)):
            return False
        project_id, worktrees = entry.get("project_id"), entry.get("worktrees")
        if not (isinstance(project_id, str) and len(project_id) == 32 and project_id not in seen):
            return False
        if not (isinstance(worktrees, list) and all(isinstance(item, str) for item in worktrees)):
            return False
        seen.add(project_id)
    return True


def _write_durably(path: Path, payload: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(directory: Path) -> None:
    if sys.platform == "win32":
        return  # a directory cannot be opened for fsync on Windows; see the module docstring's durability limit
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
