"""Configured memory backups (Plan 12.12 Task 1, D2): copies of the recovery copy's signed generations on another drive or a
consented sync folder, off by default.

**What a backup is.** The exact bytes of a generation the recovery copy (`memory_recovery`) published: `MEMORY.md`,
`entries.jsonl` and `manifest.json`, sealed by the Gateway. A backup never re-serializes memory and never copies a live Redis
directory, so restoring one goes through the same authenticated, empty-store, deletion-reconciled restore as the recovery copy.
Backups are plaintext: encryption is unavailable until the recovery-secret channel and key rotation are qualified (#491).

**Where.** One target per project, recorded privately in the host's config (`<config>/memory-backups/<project>.json`), never in
the workspace. A target is refused when it lies inside a Git work tree, overlaps the workspace, the host's config or the recovery
copy, or reaches its folder through a link or reparse point. Its identity (volume and folder id) is recorded at configuration and
checked again before every write and every removal: a target that changed is never written or pruned through.

**Failure domain.** The physical disks behind the target are compared with those behind the memory store's data and the recovery
copy. Only disjoint, known disks count as a separate drive; a shared disk gets the same-drive warning and no drive-loss credit;
anything not established stays unknown. Drive letters or mount points alone prove nothing.

**Sync folders.** A target in a known sync root, or one the user declares synced, needs consent bound to it; relocating it voids
the consent. Each write to such a target is the user's own `/memory backup now`: scheduled snapshots stay due, with the reason.

**When.** While a session of the project runs, the host checks every minute and takes one snapshot once 24 hours have passed
since the last success (one catch-up after downtime, never a backlog). One publisher per project: a busy lock means another host
is doing it. A failure keeps the last good backup and its time; a transient failure is tried at most three times.

**Retention and deletion.** Generations older than 30 days are removed only after a newer one is verified; unknown folders and the
newest usable generation are never removed. After a withdrawal or purge, a clean generation is published first and every older
managed generation, here and in earlier targets, is then removed; a target that cannot be reached keeps cleanup pending and
says so. Synced history, recycle bins and copies made elsewhere are outside what Optimus can erase.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import secrets
import shutil
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from optimus.context import memory_recovery as mr
from optimus.context.memory_workspace import _git

CHECK_SECONDS: Final = 60
DUE_AFTER_MS: Final = 24 * 3600 * 1000
RETENTION_MS: Final = 30 * 24 * 3600 * 1000
TRANSIENT_TRIES: Final = 3
LOCK_SECONDS: Final = 2.0
ENCRYPTION_UNAVAILABLE: Final = ("Encryption unavailable: the recovery-secret channel and key rotation are not qualified. "
                                 "These copies are plaintext.")
_TRANSIENT_ERRNOS: Final = frozenset({errno.EAGAIN, errno.EBUSY, errno.EINTR, errno.ETIMEDOUT})
_SHARING_VIOLATION: Final = 32  # Windows ERROR_SHARING_VIOLATION
_REPARSE_POINT: Final = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT


class BackupError(Exception):
    """A stable `code`, a sentence for the user and whether trying again may help. Nothing is published when one is raised."""

    def __init__(self, code: str, message: str, *, transient: bool = False) -> None:
        super().__init__(code)
        self.code, self.message, self.transient = code, message, transient


@dataclass
class BackupState:
    project: str
    target: str | None = None  # the configured target's canonical path
    enabled: bool = False
    identity: dict[str, Any] | None = None  # the target's volume and folder id when it was configured
    domain: str = "unknown"  # "separate" | "same" | "unknown"
    domain_reason: str = ""
    synced: str | None = None  # the sync service the target lies in, or "declared"
    consent: str | None = None  # the canonical target the user consented to although it is synced
    last_success: dict[str, Any] | None = None  # name, head, count, at_ms
    last_attempt_ms: int | None = None
    failure: dict[str, Any] | None = None  # code, message, at_ms, attempts
    held: str | None = None  # why a due snapshot was not written
    cleanup_pending: list[str] = field(default_factory=list)  # withdrawn items older generations may still hold
    prior: list[str] = field(default_factory=list)  # earlier targets that may still hold managed generations

    def to_json(self) -> dict[str, Any]:
        return {"version": 1, **self.__dict__}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> BackupState:
        names = set(cls.__dataclass_fields__)
        return cls(**{name: value for name, value in data.items() if name in names})


class BackupStateFile:
    """The host's private backup state for one project, durable (fsync then atomic replace) under a lock every process shares."""

    _shared: dict[Path, BackupStateFile] = {}
    _shared_lock = threading.Lock()

    @classmethod
    def shared(cls, config_root: Path, project: str) -> BackupStateFile:
        candidate = cls(config_root, project)
        with cls._shared_lock:
            return cls._shared.setdefault(candidate.path, candidate)

    def __init__(self, config_root: Path, project: str) -> None:
        self.path = config_root / "memory-backups" / f"{hashlib.sha256(project.encode()).hexdigest()[:32]}.json"
        self._project = project
        self._lock = threading.Lock()

    def load(self) -> BackupState:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return BackupState(self._project)
        except (OSError, ValueError):
            raise BackupError("BACKUP_STATE_CORRUPT", "The backup settings cannot be read; nothing was changed.") from None
        state = BackupState.from_json(data)
        if state.project != self._project:
            raise BackupError("BACKUP_STATE_CORRUPT", "The backup settings name another project; nothing was changed.")
        return state

    def update(self, change: Callable[[BackupState], None]) -> BackupState:
        with self._lock, mr._file_lock(self.path.with_name(self.path.name + ".lock")):
            state = self.load()
            change(state)
            mr._durable_json(self.path, state.to_json())
            return state


# --- the target's identity and disks ------------------------------------------------------------------------------------


def _reparse_in_chain(path: Path) -> Path | None:
    """The first existing component of `path` (itself or an ancestor) that is a link or reparse point, if any."""
    for candidate in [path, *path.parents]:
        try:
            info = os.lstat(candidate)
        except FileNotFoundError:
            continue
        except OSError:
            return candidate
        if os.path.islink(candidate) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            return candidate
    return None


def _disks_windows(path: Path) -> frozenset[str] | None:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    mount = ctypes.create_unicode_buffer(1024)
    volume = ctypes.create_unicode_buffer(1024)
    if not kernel.GetVolumePathNameW(str(path), mount, 1024) or not kernel.GetVolumeNameForVolumeMountPointW(mount.value, volume, 1024):
        return None
    create = kernel.CreateFileW
    create.restype = wintypes.HANDLE
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    handle = create(volume.value.rstrip("\\"), 0, 3, None, 3, 0, None)  # no access rights needed for the extents query
    if handle in (None, wintypes.HANDLE(-1).value):
        return None
    try:
        control = kernel.DeviceIoControl
        control.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                            ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        out = ctypes.create_string_buffer(8 + 24 * 32)
        returned = wintypes.DWORD()
        if not control(handle, 0x00560000, None, 0, out, len(out), ctypes.byref(returned), None):  # VOLUME_GET_VOLUME_DISK_EXTENTS
            return None
        raw = out.raw
        count = int.from_bytes(raw[0:4], "little")  # VOLUME_DISK_EXTENTS: count, then 24-byte DISK_EXTENTs from offset 8
        return frozenset(f"disk{int.from_bytes(raw[8 + 24 * n:12 + 24 * n], 'little')}" for n in range(min(count, 32))) or None
    finally:
        kernel.CloseHandle(handle)


def _disks_linux(path: Path) -> frozenset[str] | None:
    if sys.platform == "win32":
        return None
    device = os.stat(path).st_dev
    link = Path(f"/sys/dev/block/{os.major(device)}:{os.minor(device)}")
    if not link.exists():
        return None  # not a block device (network, 9p, overlay): unknown
    node = link.resolve()
    if (node / "partition").exists():
        node = node.parent
    slaves = node / "slaves"
    if slaves.is_dir() and any(slaves.iterdir()):
        return None  # device mapper, RAID or LVM: not established here
    return frozenset({node.name})


def disks(path: Path) -> frozenset[str] | None:
    """The physical disks behind `path`'s volume, or None when that cannot be established."""
    existing = next((p for p in [path, *path.parents] if p.exists()), None)
    if existing is None:
        return None
    try:
        return _disks_windows(existing) if sys.platform == "win32" else _disks_linux(existing)
    except (OSError, AttributeError, ValueError):
        return None


def default_store_data() -> Path | None:
    """Where the memory store's container data most likely lives: Docker Desktop's WSL disk on Windows, Docker's root on Linux."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        candidate = Path(local) / "Docker" / "wsl" if local else None
    else:
        candidate = Path("/var/lib/docker")
    return candidate if candidate is not None and candidate.exists() else None


def failure_domain(target: Path, references: dict[str, Path | None],
                   disk_of: Callable[[Path], frozenset[str] | None] = disks) -> tuple[str, str]:
    """("separate" | "same" | "unknown", the evidence). Separate only when every reference's disks and the target's are known and
    disjoint; same when any known disk is shared."""
    mine = disk_of(target)
    if mine is None:
        return "unknown", "the target's physical disk could not be established"
    unknown = []
    for name, path in references.items():
        theirs = disk_of(path) if path is not None else None
        if theirs is None:
            unknown.append(name)
        elif mine & theirs:
            return "same", f"the target shares {', '.join(sorted(mine & theirs))} with the {name}"
    if unknown:
        return "unknown", f"the disk of the {', '.join(unknown)} could not be established (target on {', '.join(sorted(mine))})"
    return "separate", f"target on {', '.join(sorted(mine))}; " + "; ".join(
        f"{name} on {', '.join(sorted(disk_of(path) or ()))}" for name, path in references.items() if path is not None)


def identity(path: Path) -> dict[str, Any]:
    info = os.stat(path)
    return {"path": str(path.resolve()), "volume": info.st_dev, "folder": info.st_ino}


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


# --- the backups of one project -----------------------------------------------------------------------------------------


class Backups:
    """One project's configured backups, shared by every session of that project in this host."""

    def __init__(self, recovery: mr.Recovery, state: BackupStateFile, *, workspace: Path | None, config_root: Path,
                 store_data: Callable[[], Path | None] = default_store_data,
                 disk_of: Callable[[Path], frozenset[str] | None] = disks,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000), git: Callable[..., str | None] = _git,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._recovery, self._state, self._workspace, self._config = recovery, state, workspace, config_root
        self._store_data, self._disk_of, self._clock, self._git, self._sleep = store_data, disk_of, clock, git, sleep
        self._lock = threading.Lock()

    def state(self) -> BackupState:
        return self._state.load()

    # --- configuration -----------------------------------------------------------------------------------------------

    def assess(self, target: Path, *, declared_sync: bool = False) -> dict[str, Any]:
        """Check a proposed target before the user confirms it; raises with the reason when it cannot be used."""
        if not target.is_absolute():
            raise BackupError("BACKUP_TARGET_RELATIVE", "Give the backup folder as an absolute path. Nothing was changed.")
        linked = _reparse_in_chain(target)
        if linked is not None:
            raise BackupError("BACKUP_TARGET_LINKED", f"{linked} is a link or reparse point, so the backup folder could be redirected. "
                              "Choose a folder reached without links. Nothing was changed.")
        resolved = Path(os.path.realpath(target))
        recovery_place = self._recovery.state().destination
        for name, other in (("workspace", self._workspace), ("Optimus configuration", self._config),
                            ("recovery copy", Path(recovery_place) if recovery_place else None)):
            if other is None:
                continue
            other = Path(os.path.realpath(other))
            if _inside(resolved, other) or _inside(other, resolved):
                raise BackupError("BACKUP_TARGET_OVERLAP", f"The backup folder overlaps the {name} ({other}); choose one outside it. "
                                  "Nothing was changed.")
        existing = next((p for p in [resolved, *resolved.parents] if p.exists()), None)
        if existing is not None and self._git(existing if existing.is_dir() else existing.parent,
                                              "rev-parse", "--is-inside-work-tree") is not None:
            raise BackupError("BACKUP_TARGET_IN_GIT", f"{resolved} is inside a Git work tree, so backups could be committed. Choose a "
                              "folder outside any repository. Nothing was changed.")
        synced = mr.sync_root(resolved)
        references: dict[str, Path | None] = {"memory store's data": self._store_data()}
        if recovery_place:  # without a recovery copy there is nothing to back up yet, so it is not a reference
            references["recovery copy"] = Path(recovery_place)
        domain, reason = failure_domain(resolved if resolved.exists() else existing or resolved, references, self._disk_of)
        return {"target": str(resolved), "synced": synced or ("declared" if declared_sync else None), "domain": domain, "reason": reason}

    def configure(self, assessed: dict[str, Any], *, consent: bool) -> BackupState:
        """Record a target the user confirmed, with their consent when it is synced, and switch backups on. The previous target
        stays in the inventory until no managed generation is left in it."""
        if assessed["synced"] and not consent:
            raise BackupError("BACKUP_SYNC_CONSENT", "That folder is synced; backups there need your consent. Nothing was changed.")
        target = Path(assessed["target"])
        target.mkdir(parents=True, exist_ok=True)
        if _reparse_in_chain(target) is not None or str(target.resolve()) != assessed["target"]:
            raise BackupError("BACKUP_TARGET_CHANGED", "The backup folder changed while you confirmed it; nothing was changed.")
        found = identity(target)

        def change(state: BackupState) -> None:
            if state.target is not None and state.target != assessed["target"] and state.target not in state.prior:
                state.prior.append(state.target)
            state.target, state.identity, state.enabled = assessed["target"], found, True
            state.domain, state.domain_reason, state.synced = assessed["domain"], assessed["reason"], assessed["synced"]
            state.consent = assessed["target"] if assessed["synced"] else None
            state.failure = state.held = None
        return self._state.update(change)

    def disable(self) -> BackupState:
        """Stop taking backups. Existing generations stay listed, with any cleanup they still owe."""
        return self._state.update(lambda state: setattr(state, "enabled", False))

    def withdrawn(self, item: str) -> None:
        """A withdrawal or purge: older generations may hold the item, so they owe cleanup until a clean one is published."""
        def change(state: BackupState) -> None:
            if item not in state.cleanup_pending:
                state.cleanup_pending.append(item)
        self._state.update(change)

    # --- taking a backup ---------------------------------------------------------------------------------------------

    def due(self, state: BackupState | None = None) -> bool:
        state = state or self._state.load()
        if not state.enabled or state.target is None:
            return False
        last = (state.last_success or {}).get("at_ms")
        return last is None or self._clock() - last >= DUE_AFTER_MS or bool(state.cleanup_pending)

    def run_if_due(self) -> mr.Generation | None:
        """A scheduled check: one snapshot when due. A synced target waits for the user's own `/memory backup now`."""
        state = self._state.load()
        if not self.due(state) or self._recovery.recovery_required():
            return None
        if state.synced:
            reason = "a synced target is written only by `/memory backup now`"
            if state.held != reason:
                self._state.update(lambda s: setattr(s, "held", reason))
            return None
        try:
            return self.backup()
        except BackupError:
            return None

    def backup(self) -> mr.Generation:
        """Take one backup now, or raise why not; the last good backup and its time stay as they were on any failure."""
        lock = self._state.path.with_name(self._state.path.name + ".publish.lock")
        try:
            with self._lock, mr._file_lock(lock, wait=LOCK_SECONDS, code="BACKUP_BUSY",
                                           message="Another session is taking this project's backup; try again shortly."):
                attempts = 0
                while True:
                    attempts += 1
                    try:
                        generation = self._backup()
                    except BackupError as failure:
                        if failure.transient and attempts < TRANSIENT_TRIES:
                            self._sleep(0.5 * attempts)
                            continue
                        self._failed(failure, attempts)
                        raise
                    return generation
        except mr.RecoveryError as busy:
            raise BackupError(busy.code, busy.message, transient=True) from None

    def _failed(self, failure: BackupError, attempts: int) -> None:
        now = self._clock()
        record: dict[str, Any] = {"code": failure.code, "message": failure.message, "at_ms": now, "attempts": attempts}

        def change(state: BackupState) -> None:
            state.failure, state.last_attempt_ms = record, now
        self._state.update(change)

    def _checked_target(self, state: BackupState) -> Path:
        if not state.enabled or state.target is None or state.identity is None:
            raise BackupError("BACKUP_OFF", "Backups are off for this project: `/memory backup configure <folder>` sets them up.")
        target = Path(state.target)
        if not target.is_dir():
            raise BackupError("BACKUP_TARGET_MISSING", f"The backup folder {target} is not available (drive missing or folder removed). "
                              "The last backup is kept; nothing was written.", transient=False)
        if _reparse_in_chain(target) is not None or identity(target) != state.identity:
            raise BackupError("BACKUP_TARGET_CHANGED", f"The backup folder {target} is not the folder you configured (it was replaced, "
                              "linked or remounted). Nothing was written or removed; configure it again.")
        if state.synced and state.consent != state.target:
            raise BackupError("BACKUP_SYNC_CONSENT", f"{target} is synced and its consent no longer holds; configure it again.")
        return target

    def _source(self) -> tuple[mr.Generation, Path]:
        """The newest recovery generation, exported first when changes are not in it yet."""
        recovery_state = self._recovery.state()
        if recovery_state.destination is None:
            raise BackupError("BACKUP_NEEDS_RECOVERY_COPY", "Backups copy the recovery copy, which is not set up: `/memory export` sets "
                              "it up first.")
        try:
            if recovery_state.dirty or recovery_state.exported is None or recovery_state.cleanup_pending:
                self._recovery.export()
        except mr.RecoveryError as failure:
            raise BackupError(failure.code, failure.message, transient=failure.code == "RECOVERY_BUSY") from None
        place = Path(self._recovery.state().destination or "")
        newest = mr.generations(place)
        if not newest:
            raise BackupError("BACKUP_NO_GENERATION", "The recovery copy holds no generation to back up yet.")
        return newest[0], place / newest[0].name

    def _backup(self) -> mr.Generation:
        state = self._state.load()
        target = self._checked_target(state)
        generation, source = self._source()
        pending = list(state.cleanup_pending)
        try:
            with mr.writer_lock(target):
                if not (target / generation.name).is_dir():
                    self._publish(source, target / generation.name)
                mr.read_generation(target / generation.name, None)  # the published copy reads back as the generation it copies
                self._retire(target, keep=generation.name, all_older=bool(pending))
                for stale in target.glob(".staging-*"):
                    shutil.rmtree(stale, ignore_errors=True)  # an interrupted earlier attempt: never a generation
        except mr.RecoveryError as failure:
            raise BackupError(failure.code, failure.message, transient=failure.code in ("RECOVERY_BUSY",)) from None
        except OSError as failure:
            transient = failure.errno in _TRANSIENT_ERRNOS or getattr(failure, "winerror", None) == _SHARING_VIOLATION
            raise BackupError("BACKUP_WRITE_FAILED", f"The backup could not be written to {target} ({failure.strerror or failure}). "
                              "The last backup is kept.", transient=transient) from None
        if pending:
            self._clean_prior()

        now = self._clock()

        def change(current: BackupState) -> None:
            current.last_success = {"name": generation.name, "head": generation.head, "count": generation.count, "at_ms": now}
            current.last_attempt_ms = now
            current.failure = current.held = None
            current.cleanup_pending = [item for item in current.cleanup_pending if item not in pending]
        self._state.update(change)
        return generation

    @staticmethod
    def _publish(source: Path, final: Path) -> None:
        """Exclusive staging, every file fsynced and compared byte for byte with the generation it copies, then one atomic rename."""
        staging = final.parent / f".staging-{secrets.token_hex(8)}"
        staging.mkdir()
        try:
            for name in mr.LAYOUT:
                data = (source / name).read_bytes()
                mr._write(staging / name, data)
                if (staging / name).read_bytes() != data:
                    raise BackupError("BACKUP_VERIFY_FAILED", "The written backup does not match its generation; it was not kept.")
            mr._fsync_dir(staging)
            os.replace(staging, final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        mr._fsync_dir(final.parent)

    def _retire(self, target: Path, *, keep: str, all_older: bool) -> None:
        """Remove readable managed generations older than 30 days, or every older one after a withdrawal. Folders that are not
        readable generations are never removed."""
        cutoff = self._clock() - RETENTION_MS
        for generation in mr.generations(target):
            if generation.name == keep or not (all_older or generation.created_ms < cutoff):
                continue
            shutil.rmtree(target / generation.name, ignore_errors=True)
            if (target / generation.name).exists():
                raise BackupError("BACKUP_CLEANUP_FAILED", f"An older backup ({generation.name}) could not be removed; withdrawn text "
                                  "may remain in it. Cleanup stays pending.")

    def _clean_prior(self) -> None:
        """After a clean publication: remove managed generations from earlier targets that are still reachable."""
        state = self._state.load()
        cleaned = []
        for path in state.prior:
            folder = Path(path)
            if not folder.is_dir():
                continue  # offline or removed: cleanup stays pending for it
            for generation in mr.generations(folder):
                shutil.rmtree(folder / generation.name, ignore_errors=True)
            if not mr.generations(folder):
                cleaned.append(path)
        if cleaned:
            self._state.update(lambda s: setattr(s, "prior", [p for p in s.prior if p not in cleaned]))

    # --- restore and status ------------------------------------------------------------------------------------------

    def generations(self) -> list[mr.Generation]:
        state = self._state.load()
        if state.target is None or not Path(state.target).is_dir():
            return []
        return mr.generations(Path(state.target))

    def place(self) -> Path | None:
        state = self._state.load()
        return Path(state.target) if state.target else None

    def status_line(self) -> str:
        try:
            state = self._state.load()
        except BackupError as failure:
            return failure.message
        if state.target is None:
            return "Backups: off (not configured). `/memory backup configure <folder>` copies the recovery copy to another drive daily."
        lines = [f"Backups: {'on' if state.enabled else 'off'}, to {state.target}"]
        lines.append({"separate": "a separate physical disk", "same": "SAME physical disk as the memory store or recovery copy: no "
                      "protection against losing that drive", "unknown": "drive independence unknown"}[state.domain]
                     + (f" ({state.domain_reason})" if state.domain_reason else ""))
        if state.synced:
            lines.append(f"synced folder ({state.synced}): the sync service may keep copies Optimus cannot erase")
        if not Path(state.target).is_dir():
            lines.append("the folder is not available now")
        if state.last_success:
            when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(state.last_success["at_ms"] / 1000))
            lines.append(f"last backup {when}, {state.last_success['count']} items ({state.last_success['name']})")
        else:
            lines.append("no backup taken yet")
        if state.enabled and self.due(state):
            lines.append("a backup is due" + (f" (overdue since {time.strftime('%Y-%m-%d', time.gmtime((state.last_success['at_ms'] + DUE_AFTER_MS) / 1000))})"
                                              if state.last_success else "") + "; taken while a session of this project is open")
        if state.held:
            lines.append(f"held: {state.held}")
        if state.failure:
            lines.append(f"last attempt failed: {state.failure['message']}")
        if state.cleanup_pending:
            lines.append(f"withdrawn; backup cleanup pending for {len(state.cleanup_pending)} item(s)")
        if state.prior:
            lines.append("earlier backup folders still listed: " + ", ".join(state.prior))
        lines.append(ENCRYPTION_UNAVAILABLE)
        return "; ".join(lines)


class Scheduler:
    """Checks every `CHECK_SECONDS` while a session of the project is open and takes a backup when one is due."""

    def __init__(self, backups: Backups, *, every: float = CHECK_SECONDS) -> None:
        self._backups, self._every = backups, every
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="memory-backup", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self._every):
            with contextlib.suppress(Exception):
                self._backups.run_if_due()

    def close(self) -> None:
        self._stop.set()
