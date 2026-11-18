"""The plaintext recovery copy (Plan 12.11 Task 4, D5 and D8; ADR-042): one confirmed location per project, generations written
there atomically, and restore into an empty store.

**Where.** One location per project, `.optimus/memory-recovery/` in the trusted worktree the user confirmed, recorded privately
in the host's config (`<config>/memory-recovery/<project>.json`); linked worktrees share it and its writer lock. A missing
location is unavailable, never silently replaced. `.optimus/` is the reserved runtime tree: the model never reads, writes or
receives it as context (`optimus.guardrails.runtime_tree`). That is not an execution sandbox: an authorized TEST or shell
command can still read it, which `/memory` says.

**What.** A generation holds every item's latest event as the Gateway signed it: active items whole, every other item only its
payload-free lifecycle (no text or title for off, withdrawn, purged or superseded items), with the generation's head, deletion
frontier and seal, a registry snapshot for this project and the items withdrawn since. Same-drive plaintext is not a backup.

**Before any payload is written.** In a Git work tree the location gets its own `.gitignore` holding `*` if it has none (a user's
file is never overwritten), and Git must show it ignored and nothing in it tracked; otherwise nothing is written and the reason
is shown. A location under a known sync root needs the user's consent first, bound to that location.

**Withdrawal.** A withdrawal or purge marks every older generation for retirement: the next generation is written without the
item and the older ones are then removed. Until that succeeds `/memory` says cleanup is pending.

**Restore** sends a generation's entries to the Gateway, which verifies every entry and the seal, refuses a project holding
anything, applies the deletion journal and this host's later withdrawals, and publishes in one fenced transaction.

**Recovery required (Q3).** The state records that the project held memory. An emptied store for such a project is reported as
recovery-required: nothing is served, nothing is written (a write would make the store non-empty and refuse the restore), and
no export replaces the copy with an empty one.
"""

from __future__ import annotations

import contextlib
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

from optimus.context.memory_workspace import _git

FORMAT: Final = "optimus-agent-memory-repo/1"
LOCATION: Final = (".optimus", "memory-recovery")
EXPORT_SECONDS: Final = 15 * 60  # dirty projects are exported every 15 minutes while the host runs
CATCH_UP_SECONDS: Final = 60  # the first scheduled export after launch
KEEP_GENERATIONS: Final = 3
PAGE: Final = 100
BATCH: Final = 10
LOCK_STALE_SECONDS: Final = 600
EXPORT_TRIES: Final = 3
_SYNC_MARKERS: Final = ("onedrive", "dropbox", "google drive", "googledrive", "my drive", "icloud drive", "iclouddrive", "box sync",
                        "pcloud", "nextcloud", "owncloud", "sync.com", "mega")


class RecoveryError(Exception):
    """A stable `code` and a sentence for the user. Nothing was written when one is raised before publication."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


@dataclass
class RecoveryState:
    project: str
    destination: str | None = None  # the confirmed location's canonical path
    sync_consent: str | None = None  # the location consented to although it is in a sync root
    held_memory: bool = False  # the project once held memory (Q3)
    exported: dict[str, Any] | None = None  # the newest published generation: name, head, count, at_ms
    withdrawn: list[str] = field(default_factory=list)  # items withdrawn or purged through this host, newest last
    cleanup_pending: list[str] = field(default_factory=list)  # withdrawn items older generations may still hold
    dirty: bool = True
    failure: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"version": 1, **self.__dict__}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RecoveryState:
        fields = set(cls.__dataclass_fields__)
        return cls(**{name: value for name, value in data.items() if name in fields})


_SHARED: dict[Path, StateFile] = {}
_SHARED_LOCK = threading.Lock()


class StateFile:
    """The host's private recovery state for one project, written durably (fsync, then an atomic replace). `shared` gives every
    session of one project in this process the same instance, so their updates never overwrite each other."""

    @classmethod
    def shared(cls, config_root: Path, project: str) -> StateFile:
        candidate = cls(config_root, project)
        with _SHARED_LOCK:
            return _SHARED.setdefault(candidate.path, candidate)

    def __init__(self, config_root: Path, project: str) -> None:
        self.path = config_root / "memory-recovery" / f"{hashlib.sha256(project.encode()).hexdigest()[:32]}.json"
        self._project = project
        self._lock = threading.Lock()

    def load(self) -> RecoveryState:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return RecoveryState(self._project)
        except (OSError, ValueError):
            raise RecoveryError("RECOVERY_STATE_CORRUPT", "The recovery state cannot be read; nothing was changed.") from None
        state = RecoveryState.from_json(data)
        if state.project != self._project:
            raise RecoveryError("RECOVERY_STATE_CORRUPT", "The recovery state names another project; nothing was changed.")
        return state

    def update(self, change: Callable[[RecoveryState], None]) -> RecoveryState:
        with self._lock:
            state = self.load()
            change(state)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f"{self.path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
            with open(temporary, "wb") as handle:
                handle.write(json.dumps(state.to_json(), sort_keys=True, ensure_ascii=True).encode("ascii"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            return state


def location(worktree: Path) -> Path:
    return worktree.joinpath(*LOCATION)


def sync_root(path: Path) -> str | None:
    """The known sync service a location lies in, from the environment's sync folders and well-known folder names."""
    resolved = os.path.normcase(str(path.resolve()))
    for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        root = os.environ.get(name)
        if root and resolved.startswith(os.path.normcase(str(Path(root).resolve())) + os.sep):
            return name
    parts = [part.casefold() for part in Path(resolved).parts]
    return next((marker for marker in _SYNC_MARKERS for part in parts if part == marker or part.startswith(marker + " -")), None)


def check_git_exclusion(destination: Path, git: Callable[..., str | None] = _git) -> None:
    """Before any payload: the location's own `.gitignore` (created holding `*` if absent, never overwritten), then Git must say
    the location is ignored and holds nothing tracked. Outside Git nothing is needed. Raises with the remedy otherwise."""
    if git(destination.parent, "rev-parse", "--is-inside-work-tree") is None:
        return
    ignore = destination / ".gitignore"
    if not ignore.exists():
        destination.mkdir(parents=True, exist_ok=True)
        with open(ignore, "xb") as handle:  # exclusive: a file that appeared meanwhile is the user's and is kept
            handle.write(b"*\n")
    probe = destination / "gen-probe" / "entries.jsonl"
    if git(destination, "check-ignore", "-q", "--", str(probe)) is None:
        raise RecoveryError("RECOVERY_NOT_IGNORED", f"Git does not ignore {destination}, so recovery copies could be committed. "
                            "Make sure no ignore rule re-includes it (a `!` pattern) and keep its `.gitignore` holding `*`. "
                            "Nothing was written.")
    tracked = git(destination, "ls-files", "--", ".")
    if tracked is None or tracked.strip():
        raise RecoveryError("RECOVERY_TRACKED", f"Git tracks files under {destination} (for example a forced add). Remove them from "
                            "the index (`git rm --cached`) before recovery copies are written there. Nothing was written.")


@contextlib.contextmanager
def writer_lock(destination: Path) -> Any:
    """One writer per location, across every host sharing it. A lock older than `LOCK_STALE_SECONDS` was left by a dead host."""
    lock = destination / ".lock"
    with contextlib.suppress(OSError):
        if time.time() - lock.stat().st_mtime > LOCK_STALE_SECONDS:
            lock.unlink()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RecoveryError("RECOVERY_BUSY", "Another session is writing the recovery copy; try again shortly.") from None
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        with contextlib.suppress(OSError):
            lock.unlink()


def _fsync_dir(directory: Path) -> None:
    if sys.platform == "win32":
        return  # Windows cannot open a directory to fsync it; the files themselves are fsynced
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, data: bytes) -> None:
    with open(path, "xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


@dataclass(frozen=True)
class Generation:
    name: str
    head: str
    count: int
    deletions: int
    created_ms: int
    seal: str


def generations(destination: Path) -> list[Generation]:
    """The published generations at a location, newest first, each as its manifest says. An unreadable one is skipped."""
    found = []
    for directory in destination.glob("gen-*"):
        try:
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("format") != FORMAT:
            continue
        found.append(Generation(directory.name, manifest["head"], manifest["count"], manifest["frontier"]["deletions"],
                                manifest["created_ms"], manifest["seal"]))
    return sorted(found, key=lambda g: (g.created_ms, g.name), reverse=True)


class Recovery:
    """One project's recovery copy, shared by every session of that project in this host."""

    def __init__(self, store: Any, state: StateFile, *, registry: Callable[[], dict[str, Any]] | None = None,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000), git: Callable[..., str | None] = _git) -> None:
        self._store, self._state, self._registry, self._clock, self._git = store, state, registry, clock, git
        self._lock = threading.Lock()
        self._required: tuple[float, bool] | None = None

    # --- what the host knows -------------------------------------------------------------------------------------------

    def state(self) -> RecoveryState:
        return self._state.load()

    def written(self, action: str, item: str) -> None:
        """A confirmed change: the project holds memory and the copy is dirty; a withdrawal or purge also marks every older
        generation for cleanup."""
        def change(state: RecoveryState) -> None:
            state.held_memory = True
            state.dirty = True
            if action in ("withdraw", "tombstone"):
                for target in (state.withdrawn, state.cleanup_pending):
                    if item not in target:
                        target.append(item)
                del state.withdrawn[:-10_000]
        self._state.update(change)

    def recovery_required(self) -> bool:
        """Q3: the project held memory and its store is now empty (lost volume or a fresh store). Cached for 30 seconds."""
        now = time.monotonic()
        if self._required is not None and now - self._required[0] < 30:
            return self._required[1]
        required = False
        if self._state.load().held_memory:
            rows, _cursor = self._store.items("project", limit=1)
            required = not rows and not self._store.checkpoints(limit=1)
        self._required = (now, required)
        return required

    def confirm(self, destination: Path, *, sync_consent: bool) -> None:
        """Record the location the user confirmed (and their sync consent for it), creating it now: from then on a missing
        location means it was removed, and it is never silently made again."""
        destination.mkdir(parents=True, exist_ok=True)
        canonical = str(destination.resolve())

        def change(state: RecoveryState) -> None:
            state.destination = canonical
            state.sync_consent = canonical if sync_consent else None
            state.dirty = True
        self._state.update(change)

    # --- export --------------------------------------------------------------------------------------------------------

    def export(self) -> Generation:
        """Write one generation now, or raise why not; nothing is published when anything fails."""
        with self._lock:
            state = self._state.load()
            if state.destination is None:
                raise RecoveryError("RECOVERY_NOT_SET_UP", "No recovery location is set up for this project: `/memory export` sets one up.")
            destination = Path(state.destination)
            if not destination.is_dir():
                raise RecoveryError("RECOVERY_LOCATION_MISSING", f"The recovery location {destination} is gone; it is not replaced "
                                    "automatically. Nothing was written.")
            if sync_root(destination) and state.sync_consent != state.destination:
                raise RecoveryError("RECOVERY_SYNC_CONSENT", f"{destination} is in a synced folder; its copies may be kept by the sync "
                                    "service. Confirm with `/memory export` first. Nothing was written.")
            try:
                generation = self._export(state, destination)
            except RecoveryError as failure:
                code = failure.code
                self._state.update(lambda s: setattr(s, "failure", code))
                raise
            return generation

    def _export(self, state: RecoveryState, destination: Path) -> Generation:
        check_git_exclusion(destination, self._git)
        destination.mkdir(parents=True, exist_ok=True)
        entries, final = self._read_generation()
        if not entries and state.held_memory:
            raise RecoveryError("RECOVERY_REQUIRED", "The memory store holds nothing for this project although it held memory before. "
                                "The recovery copy is kept; restore it with `/memory restore`.")
        with writer_lock(destination):
            body = b"".join(json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"
                            for entry in entries)
            created = self._clock()
            manifest = {"format": FORMAT, "project": self._store.project, "head": final["head"], "frontier": final["frontier"],
                        "seal": final["seal"], "count": len(entries), "created_ms": created,
                        "entries_sha256": hashlib.sha256(body).hexdigest(), "excluded": list(state.withdrawn),
                        "registry": self._registry() if self._registry is not None else None}
            name = f"gen-{created}-{final['seal'][:12]}"
            staging = destination / f".staging-{secrets.token_hex(8)}"
            staging.mkdir()
            try:
                _write(staging / "entries.jsonl", body)
                _write(staging / "manifest.json", json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=True).encode("ascii"))
                _fsync_dir(staging)
                os.replace(staging, destination / name)  # one atomic rename on the same volume publishes the whole generation
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
            _fsync_dir(destination)
            pending = list(state.cleanup_pending)
            self._retire(destination, keep=name, all_older=bool(pending))
            for stale in destination.glob(".staging-*"):
                shutil.rmtree(stale, ignore_errors=True)  # an interrupted earlier attempt: never published, never served

        def change(current: RecoveryState) -> None:
            current.exported = {"name": name, "head": final["head"], "count": len(entries), "at_ms": created}
            current.held_memory = current.held_memory or bool(entries)
            current.dirty = False
            current.failure = None
            current.cleanup_pending = [item for item in current.cleanup_pending if item not in pending]
        self._state.update(change)
        return Generation(name, final["head"], len(entries), final["frontier"]["deletions"], created, final["seal"])

    def _read_generation(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Every page at one head. Pages read across a write do not seal together, so the read starts again (bounded)."""
        for _attempt in range(EXPORT_TRIES):
            entries: list[dict[str, Any]] = []
            heads: set[str] = set()
            cursor: str | None = None
            while True:
                reply = self._store.call("export", project=self._store.project, limit=PAGE, **({"cursor": cursor} if cursor else {}))
                entries += reply["entries"]
                heads.add(reply["head"])
                cursor = reply["cursor"]
                if cursor is None:
                    break
            if len(heads) == 1:
                return entries, reply
        raise RecoveryError("RECOVERY_BUSY", "Memory kept changing while the copy was read; it will be tried again.")

    def _retire(self, destination: Path, *, keep: str, all_older: bool) -> None:
        """Remove older generations: every one when a withdrawal happened since (they may hold its text), else beyond the newest
        `KEEP_GENERATIONS`. A generation that cannot be removed keeps cleanup pending."""
        published = generations(destination)
        older = [g for g in published if g.name != keep]
        doomed = older if all_older else older[KEEP_GENERATIONS - 1:]
        for generation in doomed:
            shutil.rmtree(destination / generation.name, ignore_errors=True)
            if (destination / generation.name).exists():
                raise RecoveryError("RECOVERY_CLEANUP_FAILED", f"An older recovery copy ({generation.name}) could not be removed; "
                                    "withdrawn text may remain in it. Cleanup stays pending.")

    def export_if_dirty(self) -> Generation | None:
        state = self._state.load()
        if state.destination is None or not state.dirty or self.recovery_required():
            return None
        try:
            return self.export()
        except RecoveryError:
            return None

    # --- restore -------------------------------------------------------------------------------------------------------

    def read_generation(self, name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        state = self._state.load()
        if state.destination is None:
            raise RecoveryError("RECOVERY_NOT_SET_UP", "No recovery location is set up for this project.")
        directory = Path(state.destination) / name
        if not name.startswith("gen-") or directory.parent != Path(state.destination) or not directory.is_dir():
            raise RecoveryError("RECOVERY_GENERATION_UNKNOWN", f"There is no recovery generation `{name}` here.")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        body = (directory / "entries.jsonl").read_bytes()
        if manifest.get("format") != FORMAT or manifest.get("project") != self._store.project:
            raise RecoveryError("RECOVERY_GENERATION_FOREIGN", "That generation is not this project's, or not a format this host reads.")
        if hashlib.sha256(body).hexdigest() != manifest["entries_sha256"]:
            raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation's entries do not match its manifest; it is not used.")
        return manifest, [json.loads(line) for line in body.splitlines() if line.strip()]

    def restore(self, name: str) -> dict[str, Any]:
        """Restore one generation into the empty store. The Gateway verifies every entry and the seal, refuses a project holding
        anything, applies the deletion journal and this host's later withdrawals, and publishes only on the last batch."""
        manifest, entries = self.read_generation(name)
        withdrawn = sorted(set(self._state.load().withdrawn))
        batches = [entries[n:n + BATCH] for n in range(0, len(entries), BATCH)] or [[]]
        if len(batches[-1]) == BATCH:
            batches.append([])
        with self._store.lease(guarded=False) as token:
            for number, batch in enumerate(batches[:-1]):
                self._store.call("restore", project=self._store.project, token=token, generation=manifest["seal"], batch=number,
                                 final=False, entries=batch)
            reply = self._store.call("restore", project=self._store.project, token=token, generation=manifest["seal"],
                                     batch=len(batches) - 1, final=True, entries=batches[-1], head=manifest["head"],
                                     frontier=manifest["frontier"], withdrawn=withdrawn)
        self._required = None

        def change(state: RecoveryState) -> None:
            state.held_memory = True
            state.dirty = True
        self._state.update(change)
        return reply

    # --- what `/memory` says -------------------------------------------------------------------------------------------

    def status_line(self) -> str:
        try:
            state = self._state.load()
        except RecoveryError as failure:
            return failure.message
        if state.destination is None:
            return ("Recovery copy: not set up. `/memory export` sets up one same-drive plaintext copy in this worktree's "
                    "`.optimus/memory-recovery/` (not a backup).")
        lines = [f"Recovery copy: {state.destination}"]
        if state.exported:
            when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(state.exported["at_ms"] / 1000))
            lines.append(f"last saved {when}, {state.exported['count']} items ({state.exported['name']})")
        else:
            lines.append("never saved yet")
        if state.dirty:
            lines.append("changes since are not in it yet (saved every 15 minutes while Optimus runs)")
        if state.cleanup_pending:
            lines.append(f"withdrawn; plaintext recovery cleanup pending for {len(state.cleanup_pending)} item(s)")
        if state.failure:
            lines.append(f"last attempt failed: {state.failure}")
        lines.append("same-drive plaintext, not a backup; authorized TEST or shell commands can read it; synced or copied files "
                     "cannot be erased by Optimus")
        return "; ".join(lines) + "."


class Scheduler:
    """Exports a dirty project every `EXPORT_SECONDS` while a session of it is open, first after `CATCH_UP_SECONDS`, and once,
    best effort, when the session closes."""

    def __init__(self, recovery: Recovery, *, first: float = CATCH_UP_SECONDS, every: float = EXPORT_SECONDS) -> None:
        self._recovery, self._first, self._every = recovery, first, every
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="memory-recovery-export", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _loop(self) -> None:
        wait = self._first
        while not self._stop.wait(wait):
            with contextlib.suppress(Exception):
                self._recovery.export_if_dirty()
            wait = self._every

    def close(self) -> None:
        self._stop.set()
        with contextlib.suppress(Exception):
            self._recovery.export_if_dirty()


def registry_entry(snapshot: dict[str, Any], project: str) -> dict[str, Any] | None:
    """This project's registry mapping, for a generation's manifest."""
    for key, entry in snapshot.get("projects", {}).items():
        if entry.get("project_id") == project:
            return {"key": key, **entry}
    return None

