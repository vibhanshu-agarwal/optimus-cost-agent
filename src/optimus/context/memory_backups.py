"""Configured memory backups (Plan 12.12 Task 1, D2): copies of the recovery copy's signed generations on another drive or a
consented sync folder, off by default.

**What a backup is.** The exact bytes of a generation the recovery copy (`memory_recovery`) published for this project:
`MEMORY.md`, `entries.jsonl` and `manifest.json`, sealed by the Gateway. Every copied file is compared byte for byte with its
source, and the published copy is then authenticated against the Gateway: the same generation read again from the store (same
host metadata, same head) must give the same entries and the same seal, or the backup is not counted and nothing is retired. A
backup never re-serializes memory and never copies a live Redis directory, so restoring one goes through the same
authenticated, empty-store, deletion-reconciled restore as the recovery copy, including a confirmed mapping from an earlier
registration of the same workspace. Backups are plaintext: encryption is unavailable until the recovery-secret channel and key
rotation are qualified (#491).

**Where.** One target per project, recorded privately in the host's config (`<config>/memory-backups/<project>.json`), never in
the workspace. A target is refused when it lies inside a Git work tree (or under any folder holding a `.git` entry, so a Git
error never reads as "no repository"), overlaps the workspace, the host's config, the recovery copy or the memory store's data,
reaches its folder through a link or reparse point (cloud placeholders excepted), or has no stable folder identity. The user
confirms a folder bound to the identity it had when it was assessed. These checks, the target's identity and its sync status
are checked again before every write and every removal, and identity once more under the folder's writer lock: a target that
changed is never written or pruned through. Several projects may share one folder: each only lists, prunes or cleans its own
generations, and only its own staging folders (`.staging-<project tag>-...`) are ever removed.

**Failure domain.** The physical disks behind the target are compared, at every backup, with those behind the memory store's data
and the recovery copy. The store's data counts only where Docker records it (Docker Desktop's settings or its default WSL disk
image; Docker's configured data root on Linux); anything else is unknown. Only disjoint, known, physical disks count as a
separate drive; virtual, file-backed or pooled disks stay unknown; a shared disk gets the same-drive warning.

**Sync folders.** A target in a known sync root (including a sync root itself), or one the user declares synced, needs consent
bound to it; relocating it, or a sync root appearing later, voids the consent. Each write to such a target, and each cleanup in
an earlier synced target, is the user's own `/memory backup now`: scheduled work stays held, with the reason.

**When.** While a session of the project runs, the host checks every minute and takes one snapshot once 24 hours have passed
since the last success (one catch-up after downtime, never a backlog); scheduling pauses while no session is open. One
publisher per project. A failure keeps the last good backup and its time. A transient failure is tried at most three times,
and the next scheduled attempt waits a day; a permanent failure is not retried until the user runs `/memory backup now` or
configures the folder again.

**Retention and deletion.** Generations older than 30 days are removed only after a newer one is authenticated; folders that are
not this project's readable generations, and the newest usable generation, are never removed. After a withdrawal or purge, a
generation is published that provably holds no text for the withdrawn items, and only then is every older managed generation
removed, here and in earlier targets (each checked against the identity and placement it had). Items withdrawn during the
backup stay pending for the next one. A target that cannot be reached, verified or released, or an unreadable folder that may
hold the text, keeps cleanup pending and says so. Synced history, recycle bins and copies made elsewhere are outside what
Optimus can erase.
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import secrets
import shutil
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from optimus.context import memory_recovery as mr
from optimus.context.memory_workspace import _git

_LOG = logging.getLogger(__name__)
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
_VIRTUAL_BUSES: Final = frozenset({0x0E, 0x0F, 0x10})  # STORAGE_BUS_TYPE Virtual, FileBackedVirtual, Spaces
_DOMAINS: Final = frozenset({"separate", "same", "unknown"})


class BackupError(Exception):
    """A stable `code`, a sentence for the user and whether trying again may help. Nothing is published when one is raised."""

    def __init__(self, code: str, message: str, *, transient: bool = False) -> None:
        super().__init__(code)
        self.code, self.message, self.transient = code, message, transient


def _corrupt() -> BackupError:
    return BackupError("BACKUP_STATE_CORRUPT", "The backup settings cannot be read; nothing was changed.")


def _optional(value: Any, kind: type | tuple[type, ...]) -> bool:
    return value is None or isinstance(value, kind)


@dataclass
class BackupState:
    project: str
    target: str | None = None  # the configured target's canonical path
    enabled: bool = False
    identity: dict[str, Any] | None = None  # the target's volume and folder id when it was configured
    domain: str = "unknown"  # "separate" | "same" | "unknown", refreshed at every backup
    domain_reason: str = ""
    synced: str | None = None  # the sync service the target lies in, or "declared"
    consent: str | None = None  # the canonical target the user consented to although it is synced
    last_success: dict[str, Any] | None = None  # name, head, count, at_ms
    last_attempt_ms: int | None = None
    failure: dict[str, Any] | None = None  # code, message, at_ms, attempts, transient
    held: str | None = None  # why a due snapshot was not written
    cleanup_pending: list[str] = field(default_factory=list)  # withdrawn items older generations at the target may still hold
    unreadable: list[str] = field(default_factory=list)  # folders at the target that may hold withdrawn text but cannot be read
    prior: list[dict[str, Any]] = field(default_factory=list)  # earlier targets: path, identity, synced, owes_cleanup, unreachable
    deletion_revision: int = 0  # moves with every withdrawal: a cleanup that started before one never clears its obligation

    def to_json(self) -> dict[str, Any]:
        return {"version": 3, **self.__dict__}

    @classmethod
    def from_json(cls, data: Any, project: str) -> BackupState:
        """The persisted state, every field checked: anything malformed is `BACKUP_STATE_CORRUPT`, never a later TypeError."""
        if not isinstance(data, dict) or data.get("project") != project:
            raise _corrupt()
        names = set(cls.__dataclass_fields__)
        try:
            state = cls(**{name: value for name, value in data.items() if name in names})
        except TypeError:
            raise _corrupt() from None
        if not _valid(state):
            raise _corrupt()
        return state


def _manifest_and_entries(captured: dict[str, bytes], name: str, project: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """`memory_recovery.read_generation`'s host checks on bytes already in memory."""
    damaged = BackupError("RECOVERY_GENERATION_DAMAGED", "That generation's files do not match its manifest; it is not used.")
    try:
        manifest = json.loads(captured["manifest.json"].decode("ascii"))
        entries = [json.loads(line) for line in captured["entries.jsonl"].splitlines() if line.strip()]
    except (UnicodeDecodeError, ValueError):
        raise damaged from None
    metadata = manifest.get("metadata") if isinstance(manifest, dict) else None
    if (not isinstance(metadata, dict) or manifest.get("format") != mr.FORMAT or metadata.get("format") != mr.FORMAT
            or metadata.get("project") != project or tuple(metadata.get("layout", ())) != mr.LAYOUT):
        raise BackupError("RECOVERY_GENERATION_FOREIGN", "That generation is not this project's, or not a format this host reads.")
    if (hashlib.sha256(captured["entries.jsonl"]).hexdigest() != manifest.get("entries_sha256")
            or mr.bind_digest(metadata) != manifest.get("bind") or captured["MEMORY.md"] not in mr.entry_points(entries, name)):
        raise damaged
    return manifest, entries


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _fields(record: Any, required: Mapping[str, Callable[[Any], bool]]) -> bool:
    return isinstance(record, dict) and all(name in record and check(record[name]) for name, check in required.items())


_STR = lambda value: isinstance(value, str)  # noqa: E731
_BOOL = lambda value: isinstance(value, bool)  # noqa: E731
_SUCCESS: Final = {"name": _STR, "head": _STR, "count": _int, "at_ms": _int}
_FAILURE: Final = {"code": _STR, "message": _STR, "at_ms": _int, "attempts": _int, "transient": _BOOL}
_IDENTITY: Final = {"path": _STR, "volume": _int, "folder": _int}
_PRIOR: Final = {"path": _STR, "owes_cleanup": _BOOL, "unreachable": _BOOL}


def _valid(state: BackupState) -> bool:
    """Every persisted field's type, outer types before anything nested is read (each check short-circuits)."""
    return bool(
        _optional(state.target, str) and isinstance(state.enabled, bool)
        and (state.identity is None or _fields(state.identity, _IDENTITY))
        and isinstance(state.domain, str) and state.domain in _DOMAINS and isinstance(state.domain_reason, str)
        and _optional(state.synced, str) and _optional(state.consent, str)
        and (state.last_success is None or _fields(state.last_success, _SUCCESS))
        and (state.last_attempt_ms is None or _int(state.last_attempt_ms))
        and (state.failure is None or _fields(state.failure, _FAILURE)) and _optional(state.held, str)
        and isinstance(state.cleanup_pending, list) and all(isinstance(item, str) for item in state.cleanup_pending)
        and isinstance(state.unreadable, list) and all(isinstance(name, str) for name in state.unreadable)
        and _int(state.deletion_revision)
        and isinstance(state.prior, list) and all(
            _fields(entry, _PRIOR) and (entry.get("identity") is None or _fields(entry["identity"], _IDENTITY))
            and _optional(entry.get("synced"), str) and isinstance(entry.get("held", False), bool) for entry in state.prior))


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
        self.project = project
        self._lock = threading.Lock()

    def load(self) -> BackupState:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return BackupState(self.project)
        except (OSError, ValueError):
            raise _corrupt() from None
        return BackupState.from_json(data, self.project)

    def update(self, change: Callable[[BackupState], None]) -> BackupState:
        try:
            with self._lock, mr._file_lock(self.path.with_name(self.path.name + ".lock"), fault_code="BACKUP_LOCK_FAILED"):
                state = self.load()
                change(state)
                mr._durable_json(self.path, state.to_json())
                return state
        except mr.RecoveryError as refused:  # a fault keeps its own code: only another holder is busy (#529 review 2)
            code = refused.code if refused.code == "BACKUP_LOCK_FAILED" else "BACKUP_BUSY"
            raise BackupError(code, refused.message, transient=True) from None


# --- the target's identity and disks ------------------------------------------------------------------------------------


def _cloud_placeholder(info: os.stat_result) -> bool:
    """A sync service's cloud-file reparse tag (IO_REPARSE_TAG_CLOUD*): a placeholder, not a redirection."""
    tag = getattr(info, "st_reparse_tag", 0)
    return bool(tag) and (tag & 0xFFFF0FFF) == 0x9000001A


def _reparse_in_chain(path: Path) -> Path | None:
    """The first existing component of `path` (itself or an ancestor) that is a link or reparse point, if any."""
    for candidate in [path, *path.parents]:
        try:
            info = os.lstat(candidate)
        except FileNotFoundError:
            continue
        except OSError:
            return candidate
        if os.path.islink(candidate) or (getattr(info, "st_file_attributes", 0) & _REPARSE_POINT and not _cloud_placeholder(info)):
            return candidate
    return None


def _in_repository(path: Path, git: Callable[..., str | None]) -> bool:
    """Inside a Git work tree, by Git or by a `.git` entry in any existing ancestor (a Git failure never means "not one")."""
    existing = _existing(path)
    if existing is None:
        return False
    if any((ancestor / ".git").exists() for ancestor in [existing, *existing.parents]):
        return True
    return git(existing if existing.is_dir() else existing.parent, "rev-parse", "--is-inside-work-tree") is not None


def _existing(path: Path) -> Path | None:
    return next((p for p in [path, *path.parents] if p.exists()), None)


def _windows_physical(disk: int) -> bool:
    """Whether disk number `disk` is a physical disk: not a virtual, file-backed virtual or Storage Spaces disk."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.restype = wintypes.HANDLE
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = create(f"\\\\.\\PhysicalDrive{disk}", 0, 3, None, 3, 0, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        return False
    try:
        control = kernel.DeviceIoControl
        control.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                            ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        query = ctypes.create_string_buffer(12)  # STORAGE_PROPERTY_QUERY: StorageDeviceProperty, PropertyStandardQuery
        out = ctypes.create_string_buffer(1024)
        returned = wintypes.DWORD()
        if not control(handle, 0x002D1400, query, len(query), out, len(out), ctypes.byref(returned), None):  # STORAGE_QUERY_PROPERTY
            return False
        if returned.value < 32:
            return False
        bus = int.from_bytes(out.raw[28:32], "little")  # STORAGE_DEVICE_DESCRIPTOR.BusType
        return bus not in _VIRTUAL_BUSES
    finally:
        kernel.CloseHandle(handle)


def _disks_windows(path: Path) -> frozenset[str] | None:
    if sys.platform != "win32":
        return None
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
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
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
        numbers = {int.from_bytes(raw[8 + 24 * n:12 + 24 * n], "little") for n in range(min(count, 32))}
    finally:
        kernel.CloseHandle(handle)
    if not numbers or not all(_windows_physical(number) for number in numbers):
        return None  # a virtual, file-backed or pooled disk stands on disks this cannot name
    return frozenset(f"disk{number}" for number in numbers)


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
    if (slaves.is_dir() and any(slaves.iterdir())) or not (node / "device").exists():
        return None  # device mapper, RAID, LVM, loop or other virtual devices: not established here
    return frozenset({node.name})


def disks(path: Path) -> frozenset[str] | None:
    """The physical disks behind `path`'s volume, or None when that cannot be established."""
    existing = _existing(path)
    if existing is None:
        return None
    try:
        return _disks_windows(existing) if sys.platform == "win32" else _disks_linux(existing)
    except (OSError, AttributeError, ValueError):
        return None


def unbound_store_disk() -> Path | None:
    """The memory store's storage as a failure-domain reference: not bound to the active engine and resource yet, so None,
    and every target's drive independence is reported unknown (Codex CP1 review 3 ruling)."""
    return None


def docker_data_location() -> Path | None:
    """Where Docker most likely keeps container data, for refusing backup folders that overlap it (a false refusal is safe;
    it is never used as failure-domain evidence). The store is always a local Docker container
    (`local_infra.ensure_memory_store_redis`), so its data is the engine's: on Windows, Docker Desktop's WSL disk image (its
    configured custom location, else the default one); on Linux, the configured `data-root`, else `/var/lib/docker`, but not when
    a rootless engine's root also exists. Anything not found where Docker records it gives None: unknown."""
    if not _default_engine_selected():
        return None  # another engine or context may run the store: its storage is not established
    if sys.platform == "win32":
        appdata, local = os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")
        if not appdata:
            return None
        try:
            settings = json.loads((Path(appdata) / "Docker" / "settings-store.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # unreadable settings never fall back to a possibly stale default image
        if not isinstance(settings, dict) or settings.get("WslEngineEnabled") is False:
            return None
        custom = next((settings[key] for key in ("CustomWslDistroDir", "customWslDistroDir", "DataFolder", "dataFolder")
                       if isinstance(settings.get(key), str) and settings[key]), None)
        if custom is not None:  # a moved disk image: only its own location counts, never the stale default
            return next((p for p in (Path(custom) / "disk" / "docker_data.vhdx", Path(custom) / "docker_data.vhdx") if p.is_file()), None)
        image = Path(local) / "Docker" / "wsl" / "disk" / "docker_data.vhdx" if local else None
        return image if image is not None and image.is_file() else None
    root = Path("/var/lib/docker")
    try:
        configured = json.loads(Path("/etc/docker/daemon.json").read_text(encoding="utf-8")).get("data-root")
        root = Path(configured) if isinstance(configured, str) and configured else root
    except (OSError, ValueError, AttributeError):
        pass
    if (Path.home() / ".local" / "share" / "docker").is_dir():
        return None  # a rootless engine may be the one running the store: not established
    return root if (root / "volumes").is_dir() else None


def _default_engine_selected() -> bool:
    """Whether the Docker client selects the local default engine (Docker Desktop's own on Windows, the system daemon on Linux):
    no DOCKER_HOST or DOCKER_CONTEXT override and a current context that is the default one. Anything else is not established."""
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        return False
    config = Path(os.environ.get("DOCKER_CONFIG") or Path.home() / ".docker") / "config.json"
    try:
        current = json.loads(config.read_text(encoding="utf-8")).get("currentContext")
    except FileNotFoundError:
        current = None
    except (OSError, ValueError, AttributeError):
        return False
    allowed = {None, "", "default", "desktop-linux"} if sys.platform == "win32" else {None, "", "default"}
    return current in allowed


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
                 store_data: Callable[[], Path | None] = unbound_store_disk,
                 runtime_data: Callable[[], Path | None] = docker_data_location,
                 disk_of: Callable[[Path], frozenset[str] | None] = disks,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000), git: Callable[..., str | None] = _git,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._recovery, self._state, self._workspace, self._config = recovery, state, workspace, config_root
        self._store_data, self._disk_of, self._clock, self._git, self._sleep = store_data, disk_of, clock, git, sleep
        self._runtime_data = runtime_data
        self._lock = threading.Lock()

    @property
    def project(self) -> str:
        return self._state.project

    @property
    def _staging_prefix(self) -> str:
        return f".staging-{hashlib.sha256(self.project.encode()).hexdigest()[:12]}-"

    def state(self) -> BackupState:
        return self._state.load()

    # --- checks shared by configuration and every write --------------------------------------------------------------

    def _placement(self, resolved: Path) -> None:
        """Raise when the folder overlaps the workspace, the config, the recovery copy or the store's data, or lies in a Git work
        tree."""
        recovery_place = self._recovery.state().destination
        stores = [path for path in (self._store_data(), self._runtime_data()) if path is not None]
        for name, other in (("workspace", self._workspace), ("Optimus configuration", self._config),
                            ("recovery copy", Path(recovery_place) if recovery_place else None),
                            *(("memory store's data", store.parent if store.is_file() else store) for store in stores)):
            if other is None:
                continue
            other = Path(os.path.realpath(other))
            if _inside(resolved, other) or _inside(other, resolved):
                raise BackupError("BACKUP_TARGET_OVERLAP", f"The backup folder overlaps the {name} ({other}); choose one outside it. "
                                  "Nothing was changed.")
        if _in_repository(resolved, self._git):
            raise BackupError("BACKUP_TARGET_IN_GIT", f"{resolved} is inside a Git work tree, so backups could be committed. Choose a "
                              "folder outside any repository. Nothing was changed.")

    def _domain(self, target: Path) -> tuple[str, str]:
        recovery_place = self._recovery.state().destination
        references: dict[str, Path | None] = {"memory store's data": self._store_data()}
        if recovery_place:  # without a recovery copy there is nothing to back up yet, so it is not a reference
            references["recovery copy"] = Path(recovery_place)
        return failure_domain(_existing(target) or target, references, self._disk_of)

    # --- configuration -----------------------------------------------------------------------------------------------

    def assess(self, target: Path, *, declared_sync: bool = False) -> dict[str, Any]:
        """Check a proposed target before the user confirms it; raises with the reason when it cannot be used. The result binds
        the identity of the folder (or of its nearest existing ancestor) the user is shown."""
        if not target.is_absolute():
            raise BackupError("BACKUP_TARGET_RELATIVE", "Give the backup folder as an absolute path. Nothing was changed.")
        linked = _reparse_in_chain(target)
        if linked is not None:
            raise BackupError("BACKUP_TARGET_LINKED", f"{linked} is a link or reparse point, so the backup folder could be redirected. "
                              "Choose a folder reached without links. Nothing was changed.")
        resolved = Path(os.path.realpath(target))
        self._placement(resolved)
        anchor = _existing(resolved)
        if anchor is None:
            raise BackupError("BACKUP_TARGET_MISSING", f"No part of {resolved} exists; check the drive. Nothing was changed.")
        synced = mr.sync_root(resolved)
        domain, reason = self._domain(resolved)
        return {"target": str(resolved), "synced": synced or ("declared" if declared_sync else None), "domain": domain, "reason": reason,
                "anchor": identity(anchor)}

    def configure(self, assessed: dict[str, Any], *, consent: bool) -> BackupState:
        """Record a target the user confirmed, with their consent when it is synced, and switch backups on. The folder must still
        be the one assessed (its identity, placement and sync status). The previous target stays in the inventory, with its
        identity and sync status, until no managed generation of this project is left in it."""
        if assessed["synced"] and not consent:
            raise BackupError("BACKUP_SYNC_CONSENT", "That folder is synced; backups there need your consent. Nothing was changed.")
        target = Path(assessed["target"])
        anchor = assessed.get("anchor") or {}
        changed = BackupError("BACKUP_TARGET_CHANGED", "The backup folder changed while you confirmed it; nothing was changed.")
        if _reparse_in_chain(target) is not None or not anchor.get("path") or not Path(anchor["path"]).exists() \
                or identity(Path(anchor["path"])) != anchor:
            raise changed
        self._placement(target)
        if mr.sync_root(target) and not assessed["synced"]:
            raise changed  # it became synced after the user was shown it: the disclosure no longer holds
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as failure:
            raise BackupError("BACKUP_TARGET_UNWRITABLE", f"{target} could not be created ({mr.os_reason(failure, target)}). Choose "
                              "another folder. Nothing was changed.") from None
        if _reparse_in_chain(target) is not None or str(target.resolve()) != assessed["target"]:
            raise changed
        found = identity(target)
        if not found["folder"]:
            raise BackupError("BACKUP_TARGET_NO_IDENTITY", f"{target} has no stable folder identity (some network shares), so a "
                              "replaced folder could not be told apart. Choose a local drive. Nothing was changed.")

        def change(state: BackupState) -> None:
            if state.target is not None and state.target != assessed["target"] and not any(p["path"] == state.target for p in state.prior):
                state.prior.append({"path": state.target, "identity": state.identity, "synced": state.synced,
                                    "owes_cleanup": bool(state.cleanup_pending), "unreachable": False})
            state.prior = [p for p in state.prior if p["path"] != assessed["target"]]  # the new target is never also an earlier one
            state.target, state.identity, state.enabled = assessed["target"], found, True
            state.domain, state.domain_reason, state.synced = assessed["domain"], assessed["reason"], assessed["synced"]
            state.consent = assessed["target"] if assessed["synced"] else None
            state.failure = state.held = None
        return self._state.update(change)

    def disable(self) -> BackupState:
        """Stop taking backups. Existing generations stay listed, with any cleanup they still owe."""
        return self._state.update(lambda state: setattr(state, "enabled", False))

    def withdrawn(self, item: str) -> None:
        """A withdrawal or purge: older generations may hold the item, so they owe cleanup until a generation provably without
        its text is published. Nothing is recorded for a project that never had a backup target."""
        def change(state: BackupState) -> None:
            if state.target is None and not state.prior:
                return
            if item not in state.cleanup_pending:
                state.cleanup_pending.append(item)
            del state.cleanup_pending[:-10_000]
            state.deletion_revision += 1
            for prior in state.prior:
                prior["owes_cleanup"] = True
        self._state.update(change)

    # --- taking a backup ---------------------------------------------------------------------------------------------

    def due(self, state: BackupState | None = None) -> bool:
        state = state or self._state.load()
        if not state.enabled or state.target is None:
            return False
        last = (state.last_success or {}).get("at_ms")
        return last is None or self._clock() - last >= DUE_AFTER_MS or bool(state.cleanup_pending)

    def run_if_due(self) -> mr.Generation | None:
        """A scheduled check: earlier targets that owe cleanup are retried cheaply; one snapshot is taken when due. After a
        permanent failure nothing is retried until the user acts; after a transient one the next attempt waits a day. A synced
        target waits for the user's own `/memory backup now`."""
        state = self._state.load()
        if any(prior.get("owes_cleanup") for prior in state.prior) and not state.cleanup_pending:
            self._clean_prior(explicit=False)
        if not self.due(state) or self._recovery.recovery_required():
            return None
        if state.failure is not None:
            if not state.failure.get("transient"):
                return None  # no permanent retry: held until `/memory backup now` or a new configuration
            if state.last_attempt_ms is not None and self._clock() - state.last_attempt_ms < DUE_AFTER_MS:
                return None
        if state.synced:
            reason = "a synced target is written only by `/memory backup now`"
            if state.held != reason:
                self._state.update(lambda s: setattr(s, "held", reason))
            return None
        try:
            return self.backup()
        except BackupError as failure:
            _LOG.warning("memory backup failed: %s", failure.code)
            return None

    def backup(self, *, explicit: bool = False) -> mr.Generation:
        """Take one backup now, or raise why not; the last good backup and its time stay as they were on any failure.
        `explicit` is the user's own `/memory backup now`: it also releases cleanup held in earlier synced targets."""
        lock = self._state.path.with_name(self._state.path.name + ".publish.lock")
        try:
            with self._lock, mr._file_lock(lock, wait=LOCK_SECONDS, code="BACKUP_BUSY", fault_code="BACKUP_LOCK_FAILED",
                                           message="Another session is taking this project's backup; try again shortly."):
                attempts = 0
                while True:
                    attempts += 1
                    try:
                        generation = self._backup(explicit=explicit)
                    except BackupError as failure:
                        if failure.transient and attempts < TRANSIENT_TRIES:
                            self._sleep(0.5 * attempts)
                            continue
                        if failure.code not in ("BACKUP_BUSY", "BACKUP_SOURCE_MOVED"):  # memory moving on is not a failure
                            self._failed(failure, attempts)
                        raise
                    return generation
        except mr.RecoveryError as busy:
            raise BackupError(busy.code, busy.message, transient=True) from None

    def _failed(self, failure: BackupError, attempts: int) -> None:
        now = self._clock()
        record: dict[str, Any] = {"code": failure.code, "message": failure.message, "at_ms": now, "attempts": attempts,
                                  "transient": failure.transient}

        def change(state: BackupState) -> None:
            state.failure, state.last_attempt_ms = record, now
        self._state.update(change)

    def _checked_target(self, state: BackupState) -> Path:
        """Every check configuration made, again, plus the identity recorded then; raises when any no longer holds."""
        if not state.enabled or state.target is None or state.identity is None:
            raise BackupError("BACKUP_OFF", "Backups are off for this project: `/memory backup configure <folder>` sets them up.")
        target = Path(state.target)
        if not target.is_dir():
            raise BackupError("BACKUP_TARGET_MISSING", f"The backup folder {target} is not available (drive missing or folder removed). "
                              "The last backup is kept; nothing was written.")
        if _reparse_in_chain(target) is not None or identity(target) != state.identity:
            raise BackupError("BACKUP_TARGET_CHANGED", f"The backup folder {target} is not the folder you configured (it was replaced, "
                              "linked or remounted). Nothing was written or removed; configure it again.")
        self._placement(target)
        synced = mr.sync_root(target) or (state.synced if state.synced == "declared" else None)
        if synced and state.consent != state.target:
            raise BackupError("BACKUP_SYNC_CONSENT", f"{target} is synced ({synced}) and has no consent for it; configure it again. "
                              "Nothing was written.")
        return target

    def _source(self, project: str) -> tuple[mr.Generation, Path]:
        """This project's newest recovery generation, exported first when changes are not in it yet, and checked before use."""
        recovery_state = self._recovery.state()
        if recovery_state.destination is None:
            raise BackupError("BACKUP_NEEDS_RECOVERY_COPY", "Backups copy the recovery copy, which is not set up: `/memory export` sets "
                              "it up first.")
        try:
            if recovery_state.dirty or recovery_state.exported is None or recovery_state.cleanup_pending:
                self._recovery.export()
            exported = self._recovery.state()
            if exported.exported is None or exported.destination is None:
                raise BackupError("BACKUP_NO_GENERATION", "The recovery copy holds no generation to back up yet.")
            place = Path(exported.destination)
            name = exported.exported["name"]
            mr.read_generation(place / name, project)  # the exact generation to copy, this project's, intact
        except mr.RecoveryError as failure:
            transient = failure.code in ("RECOVERY_BUSY", "RECOVERY_STATE_BUSY")  # a damaged source stays damaged: not retried
            raise BackupError(failure.code, failure.message, transient=transient) from None
        chosen = next((g for g in mr.generations(place) if g.name == name), None)
        if chosen is None:
            raise BackupError("BACKUP_NO_GENERATION", "The recovery copy's newest generation moved meanwhile; it will be tried again.",
                              transient=True)
        return chosen, place / name

    @staticmethod
    def _capture(directory: Path, project: str) -> dict[str, bytes]:
        """The generation's three files read once into memory, checked by the host as `memory_recovery.read_generation` checks
        them (format, project, layout, entries and metadata digests, an entry point derived from the entries). Everything after
        this, authentication, staging and comparison, uses these same bytes and never the files again."""
        try:
            captured = {name: (directory / name).read_bytes() for name in mr.LAYOUT}
        except OSError:
            raise BackupError("BACKUP_SOURCE_MOVED", "The recovery copy changed while it was read; it will be tried again.",
                              transient=True) from None
        _manifest_and_entries(captured, directory.name, project)
        return captured

    def _authenticate(self, captured: dict[str, bytes], name: str, project: str) -> list[dict[str, Any]]:
        """The captured generation against the Gateway, before any byte of it is staged: the same generation read again from the
        store (same host metadata) must be at the same head and deletion-journal count, and then give byte-equal entries, the
        same deletion frontier and the same seal; the manifest's count must be its entries'. Memory moving on (head or journal)
        is transient: the generation is refreshed. Returns the entries."""
        manifest, entries = _manifest_and_entries(captured, name, project)
        try:
            fresh, final = self._recovery._read_generation(manifest["bind"], pin=manifest["head"])  # at the copy's own head
        except mr.RecoveryError as failure:
            raise BackupError(failure.code, failure.message, transient=True) from None
        if final["head"] != manifest["head"] or final["journal"] != manifest["journal"]:
            raise BackupError("BACKUP_SOURCE_MOVED", "Memory changed while the backup was checked; it will be tried again.",
                              transient=True)
        if (final["seal"] != manifest["seal"] or fresh != entries or final["frontier"] != manifest["frontier"]
                or manifest["count"] != len(entries)):
            raise BackupError("BACKUP_GENERATION_UNAUTHENTIC", "The backup does not match what the memory store sealed; it was not "
                              "counted and no older backup was removed.")
        return entries

    def _backup(self, *, explicit: bool) -> mr.Generation:
        project = self.project
        pending = list(self._state.load().cleanup_pending)  # before the source: a withdrawal after this point stays pending
        generation, source = self._source(project)  # an export may wait; the target is checked after it
        captured = self._capture(source, project)  # one immutable copy of the bytes: authenticated, then staged or compared
        entries = self._authenticate(captured, generation.name, project)
        state = self._state.load()
        target = self._checked_target(state)
        published = target / generation.name
        try:
            with mr.writer_lock(target):
                if identity(target) != state.identity or _reparse_in_chain(target) is not None:
                    raise BackupError("BACKUP_TARGET_CHANGED", f"The backup folder {target} changed while the backup started; nothing "
                                      "was written or removed.")
                if published.is_dir():
                    for name in mr.LAYOUT:  # an earlier run published it: it must be byte for byte the authenticated capture
                        if (published / name).read_bytes() != captured[name]:
                            raise BackupError("BACKUP_GENERATION_UNAUTHENTIC", f"The existing backup {generation.name} differs from "
                                              "what the memory store sealed; nothing was removed.")
                else:
                    self._publish(captured, published, self._staging_prefix)  # only the authenticated captured bytes
                mr.read_generation(published, project)
                live = {shaped["entry"]["item"] for shaped in entries if shaped["entry"].get("statement")}
                proven = [item for item in pending if item not in live]  # this generation holds no text for these items
                unreadable = self._retire(target, keep=generation.name, all_older=bool(proven) and proven == pending)
                for stale in target.glob(self._staging_prefix + "*"):
                    shutil.rmtree(stale, ignore_errors=True)  # this project's interrupted earlier attempt: never a generation
        except mr.RecoveryError as failure:
            raise BackupError(failure.code, failure.message, transient=failure.code == "RECOVERY_BUSY") from None
        except FileNotFoundError:
            raise BackupError("BACKUP_SOURCE_MOVED", "The recovery copy changed while it was copied; it will be tried again.",
                              transient=True) from None
        except OSError as failure:
            transient = failure.errno in _TRANSIENT_ERRNOS or getattr(failure, "winerror", None) == _SHARING_VIOLATION
            raise BackupError("BACKUP_WRITE_FAILED", f"The backup could not be written to {target} ({failure.strerror or failure}). "
                              "The last backup is kept.", transient=transient) from None
        domain, reason = self._domain(target)
        now = self._clock()
        cleared = proven if proven == pending and not unreadable else []

        def change(current: BackupState) -> None:
            current.last_success = {"name": generation.name, "head": generation.head, "count": generation.count, "at_ms": now}
            current.last_attempt_ms = now
            current.failure = current.held = None
            current.domain, current.domain_reason = domain, reason
            current.unreadable = unreadable
            current.cleanup_pending = [item for item in current.cleanup_pending if item not in cleared]
        self._state.update(change)
        if not self._state.load().cleanup_pending:
            self._clean_prior(explicit=explicit)
        return generation

    @staticmethod
    def _publish(captured: dict[str, bytes], final: Path, prefix: str) -> None:
        """Exclusive staging named for this project, every file written from the authenticated capture, fsynced and compared byte
        for byte with it, then one atomic rename: what is published is only ever the authenticated bytes."""
        staging = final.parent / f"{prefix}{secrets.token_hex(8)}"
        staging.mkdir()
        try:
            for name in mr.LAYOUT:
                data = captured[name]
                mr._write(staging / name, data)
                if (staging / name).read_bytes() != data:
                    raise BackupError("BACKUP_VERIFY_FAILED", "The written backup does not match its generation; it was not kept.")
            mr._fsync_dir(staging)
            os.replace(staging, final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        mr._fsync_dir(final.parent)

    def _retire(self, folder: Path, *, keep: str | None, all_older: bool) -> list[str]:
        """Remove this project's readable generations older than 30 days, or every one but `keep` after a withdrawal. Another
        project's generations and other folders are never removed. Returns the `gen-*` folders that cannot be read, which may
        hold withdrawn text, when `all_older`."""
        cutoff = self._clock() - RETENTION_MS
        readable = mr.generations(folder)
        for generation in readable:
            if generation.project != self.project or generation.name == keep or not (all_older or generation.created_ms < cutoff):
                continue
            shutil.rmtree(folder / generation.name, ignore_errors=True)
            if (folder / generation.name).exists():
                raise BackupError("BACKUP_CLEANUP_FAILED", f"An older backup ({generation.name}) could not be removed; withdrawn text "
                                  "may remain in it. Cleanup stays pending.")
        if not all_older:
            return []
        known = {g.name for g in readable}
        return sorted(p.name for p in folder.glob("gen-*") if p.is_dir() and p.name not in known and p.name != keep)

    def _prior_usable(self, prior: dict[str, Any], folder: Path) -> bool:
        if not folder.is_dir() or prior.get("identity") is None or _reparse_in_chain(folder) is not None \
                or identity(folder) != prior["identity"]:
            return False
        try:
            self._placement(folder)
        except BackupError:
            return False
        return not (mr.sync_root(folder) and not prior.get("synced"))

    def _clean_prior(self, *, explicit: bool) -> None:
        """Earlier targets: remove this project's generations that owe cleanup (after a withdrawal) or are older than 30 days,
        through the identity and placement each had, rechecked under its writer lock. A synced one is cleaned only on the user's
        own `/memory backup now`. One that is missing, changed or held stays listed with its obligation; one left with none of
        this project's generations and nothing unreadable leaves the inventory."""
        state = self._state.load()
        if not state.prior:
            return
        revision = state.deletion_revision  # a withdrawal after this keeps every obligation it set
        outcome: dict[str, dict[str, bool]] = {}
        for prior in state.prior:
            folder = Path(prior["path"])
            if prior.get("synced") and not explicit:
                outcome[prior["path"]] = {"unreachable": False, "held": True, "holds": True, "owes": bool(prior.get("owes_cleanup"))}
                continue
            if not self._prior_usable(prior, folder):
                outcome[prior["path"]] = {"unreachable": True, "held": False, "holds": True, "owes": bool(prior.get("owes_cleanup"))}
                continue
            try:
                with mr.writer_lock(folder):
                    if identity(folder) != prior["identity"] or _reparse_in_chain(folder) is not None:
                        raise BackupError("BACKUP_TARGET_CHANGED", "changed under its lock")
                    unreadable = self._retire(folder, keep=None, all_older=bool(prior.get("owes_cleanup")))
            except (BackupError, mr.RecoveryError, OSError):
                outcome[prior["path"]] = {"unreachable": True, "held": False, "holds": True, "owes": bool(prior.get("owes_cleanup"))}
                continue
            left = [g for g in mr.generations(folder) if g.project == self.project]
            outcome[prior["path"]] = {"unreachable": False, "held": False, "holds": bool(left or unreadable), "owes": bool(unreadable)}

        def change(current: BackupState) -> None:
            kept = []
            for prior in current.prior:
                result = outcome.get(prior["path"])
                if result is None:
                    kept.append(prior)
                    continue
                if not result["holds"] and current.deletion_revision == revision:
                    continue
                prior["unreachable"], prior["held"] = result["unreachable"], result["held"]
                if not result["unreachable"] and not result["held"] and current.deletion_revision == revision:
                    prior["owes_cleanup"] = result["owes"]  # cleaned: it still owes only for what it could not read
                kept.append(prior)
            current.prior = kept
        self._state.update(change)

    # --- restore and status ------------------------------------------------------------------------------------------

    def generations(self, *, mapping: bool = False) -> list[mr.Generation]:
        """This project's generations at the target; with `mapping`, also earlier registrations' of this same workspace (their
        registry key is this project's current key), which restore only through a confirmed mapping. Another project's
        generations in a shared folder are never listed."""
        state = self._state.load()
        if state.target is None or not Path(state.target).is_dir():
            return []
        found = mr.generations(Path(state.target))
        key = None
        if mapping and self._recovery._registry is not None:
            key = (mr.registry_entry(self._recovery._registry(), self.project) or {}).get("key")
        return [g for g in found if g.project == self.project or (key and g.registry_key == key)]

    def place(self) -> Path | None:
        state = self._state.load()
        return Path(state.target) if state.target else None

    def status_line(self) -> str:
        try:
            state = self._state.load()
        except BackupError as failure:
            return failure.message
        if state.target is None and not state.prior:
            return "Backups: off (not configured). `/memory backup configure <folder>` copies the recovery copy to another drive daily."
        lines = [f"Backups: {'on' if state.enabled else 'off'}, to {state.target}" if state.target else "Backups: off"]
        if state.target:
            lines.append({"separate": "a separate physical disk", "same": "SAME physical disk as the memory store or recovery copy: "
                          "no protection against losing that drive", "unknown": "drive independence unknown"}[state.domain]
                         + (f" ({state.domain_reason})" if state.domain_reason else ""))
            if state.synced:
                lines.append(f"synced folder ({state.synced}): the sync service may keep copies Optimus cannot erase")
            if not Path(state.target).is_dir():
                lines.append("the folder is not available now")
        if state.last_success:
            when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(state.last_success["at_ms"] / 1000))
            lines.append(f"last backup {when}, {state.last_success['count']} items ({state.last_success['name']})")
        elif state.target:
            lines.append("no backup taken yet")
        if state.enabled and self.due(state):
            deadline = state.last_success["at_ms"] + DUE_AFTER_MS if state.last_success else None
            if deadline is not None and self._clock() >= deadline:
                why = f" (overdue since {time.strftime('%Y-%m-%d', time.gmtime(deadline / 1000))})"
            elif state.cleanup_pending:
                why = " now, to finish cleanup"  # due early: never an overdue date still in the future (real-Zed CP3 finding)
            else:
                why = ""
            lines.append(f"a backup is due{why}; backups are taken while a session of this project is open and pause while none is")
        if state.held:
            lines.append(f"held: {state.held}")
        if state.failure:
            retry = ("next scheduled attempt a day later" if state.failure.get("transient")
                     else "not retried until `/memory backup now` or a new configuration")
            lines.append(f"last attempt failed: {state.failure['message']} ({retry})")
        if state.cleanup_pending:
            lines.append(f"backup cleanup pending for {len(state.cleanup_pending)} withdrawn item(s)")
        if state.unreadable:
            lines.append("unreadable folders in the backup folder may hold withdrawn text: " + ", ".join(state.unreadable))
        for prior in state.prior:
            if prior.get("held"):
                words = "cleanup pending; synced folder, cleaned only by `/memory backup now`"
            elif prior.get("unreachable"):
                words = "cleanup pending, folder unreachable or changed"
            else:
                words = "cleanup pending" if prior.get("owes_cleanup") else "still holds backups"
            lines.append(f"earlier backup folder {prior['path']}: {words}")
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
            try:
                self._backups.run_if_due()
            except Exception as failure:  # never ends the schedule; the cause is logged by type only
                _LOG.warning("memory backup check failed: %s", type(failure).__name__)

    def close(self) -> None:
        self._stop.set()
