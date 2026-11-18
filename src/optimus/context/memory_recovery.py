"""The plaintext recovery copy (Plan 12.11 Task 4, D5 and D8; ADR-042): one confirmed location per project, generations written
there atomically in the Agent Memory Repo layout, and restore into an empty store.

**Where.** One location per project, `.optimus/memory-recovery/` in the trusted worktree the user confirmed, recorded privately
in the host's config (`<config>/memory-recovery/<project>.json`); linked worktrees share it and its writer lock. A missing
location is unavailable, never silently replaced: the user confirms a move, and every prior location is listed until no
managed copy is left in it. `.optimus/` is the reserved runtime tree: the model never reads, writes or receives it as context
(`optimus.guardrails.runtime_tree`). That is not an execution sandbox: an authorized TEST or shell command can still read it.

**What.** A generation is an Agent Memory Repo (https://cognition.com/agent-memory-repo): `MEMORY.md`, the entry point, one bullet
per active item with `[key: value]` metadata and an index of `[[...]]` links; `entries.jsonl`, every item's latest event as the
Gateway signed it (active items whole, every other item only its payload-free lifecycle); and `manifest.json`. The host's
metadata (format, project, registry mapping, layout, exclusions) is bound into the Gateway's seal, so changing any of it, or
the entries, makes the generation unusable. Same-drive plaintext is not a backup.

**Before any payload is written.** In a Git work tree the location gets its own `.gitignore` holding `*` if it has none (a user's
file is never overwritten), and Git must show it ignored and nothing in it tracked; otherwise nothing is written and the reason
is shown. A location under a known sync root needs the user's consent first, bound to that location.

**Withdrawal.** A withdrawal or purge marks every older generation for retirement: the next generation is written without the
item and the older ones are then removed. A change during an export leaves the copy dirty, so it is written again. Until cleanup
succeeds `/memory` says it is pending.

**Restore** sends one confirmed generation, whose seal must be the one the user was shown, to the Gateway, which verifies every
entry and the seal, refuses a project holding anything, applies the deletion journal (failing closed when it is damaged or
shorter than when the copy was written) and this host's later deletions, and publishes in one fenced transaction.

**Recovery required (Q3).** The state records that the project held memory. An emptied store for such a project is reported as
recovery-required: nothing is served, nothing is written (checked again under each write's lease), and no export replaces the
copy with an empty one. A lost project registry is repaired only from a generation the Gateway authenticates, for this
workspace's own registry key.

**Notices.** Memory notices not yet shown are kept in a durable backlog per project (`NoticeBacklog`), delivered by event id at
the next opportunity in any session, so a restart loses no notice and a resend repeats no change.
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
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from optimus.context.memory_workspace import _git

FORMAT: Final = "optimus-agent-memory-repo/2"
LAYOUT: Final = ("MEMORY.md", "entries.jsonl", "manifest.json")
LOCATION: Final = (".optimus", "memory-recovery")
EXPORT_SECONDS: Final = 15 * 60  # dirty projects are exported every 15 minutes while the host runs
CATCH_UP_SECONDS: Final = 60  # the first scheduled export after launch
KEEP_GENERATIONS: Final = 3
PAGE: Final = 100
BATCH: Final = 10
STATE_LOCK_SECONDS: Final = 10.0
EXPORT_LOCK_SECONDS: Final = 120.0  # another host's export of the same project finishes first
EXPORT_TRIES: Final = 3
_SYNC_MARKERS: Final = ("onedrive", "dropbox", "google drive", "googledrive", "my drive", "icloud drive", "iclouddrive", "box sync",
                        "pcloud", "nextcloud", "owncloud", "sync.com", "mega")


class RecoveryError(Exception):
    """A stable `code` and a sentence for the user. Nothing was written when one is raised before publication."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


def _try_lock(handle: Any) -> bool:
    """Take the OS lock on the file's first byte without waiting. The OS releases it when its owner's handle closes or the
    owner dies, so a live owner is never taken over, however long it holds it (Codex CP3 review 3)."""
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: Any) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _file_lock(path: Path, *, wait: float = STATE_LOCK_SECONDS, code: str = "RECOVERY_STATE_BUSY",
               message: str = "The recovery state is held by another process; try again shortly.") -> Iterator[None]:
    """An OS-held lock on a file shared by every process on this machine (Codex CP3 review 1, finding 2): it ends only when its
    owner releases it, closes the file or dies, never by age. The file itself is left in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as handle:
        deadline = time.monotonic() + wait
        while not _try_lock(handle):
            if time.monotonic() > deadline:
                raise RecoveryError(code, message)
            time.sleep(0.02)
        try:
            yield
        finally:
            _unlock(handle)


def _durable_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    with open(temporary, "wb") as handle:
        handle.write(json.dumps(value, sort_keys=True, ensure_ascii=True).encode("ascii"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


@dataclass
class RecoveryState:
    project: str
    destination: str | None = None  # the confirmed location's canonical path
    sync_consent: str | None = None  # the location consented to although it is in a sync root
    held_memory: bool = False  # the project once held memory (Q3)
    exported: dict[str, Any] | None = None  # the newest published generation: name, head, count, at_ms
    withdrawn: list[str] = field(default_factory=list)  # items withdrawn or purged through this host, newest last
    purged: list[str] = field(default_factory=list)  # items purged through this host: the journal must still show each one
    cleanup_pending: list[str] = field(default_factory=list)  # withdrawn items older generations may still hold
    prior: list[str] = field(default_factory=list)  # earlier locations that may still hold managed copies
    revision: int = 0  # moves with every confirmed change, so an export knows whether it saw the latest
    dirty: bool = True
    failure: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"version": 2, **self.__dict__}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RecoveryState:
        fields = set(cls.__dataclass_fields__)
        return cls(**{name: value for name, value in data.items() if name in fields})


_SHARED: dict[Path, Any] = {}
_SHARED_LOCK = threading.Lock()


class StateFile:
    """The host's private recovery state for one project, written durably (fsync, then an atomic replace) under a lock every
    process shares. `shared` gives every session of one project in this process the same instance."""

    @classmethod
    def shared(cls, config_root: Path, project: str) -> StateFile:
        candidate = cls(config_root, project)
        with _SHARED_LOCK:
            found: StateFile = _SHARED.setdefault(candidate.path, candidate)
            return found

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
        with self._lock, _file_lock(self.path.with_name(self.path.name + ".lock")):
            state = self.load()
            change(state)
            _durable_json(self.path, state.to_json())
            return state


class NoticeBacklog:
    """Memory notices a person has not been shown yet, for one project, durable across restarts (Codex CP3 review 1, finding 6).
    A notice is added before it is sent and removed once its send is confirmed; any session of the project delivers what is left,
    under the same event id, so a resend replaces a card and never repeats a change."""

    def __init__(self, config_root: Path, project: str) -> None:
        self.path = config_root / "memory-notices" / f"{hashlib.sha256(project.encode()).hexdigest()[:32]}.json"
        self._lock = threading.Lock()

    @classmethod
    def shared(cls, config_root: Path, project: str) -> NoticeBacklog:
        candidate = cls(config_root, project)
        with _SHARED_LOCK:
            found: NoticeBacklog = _SHARED.setdefault(candidate.path, candidate)
            return found

    def _load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [record for record in data if isinstance(record, dict)] if isinstance(data, list) else []

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._load()

    def add(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        with self._lock, _file_lock(self.path.with_name(self.path.name + ".lock")):
            current = self._load()
            known = {record["event_id"] for record in current}
            current += [record for record in records if record["event_id"] not in known]
            _durable_json(self.path, current)  # kept until acknowledged, however many (Codex CP3 review 2, finding 4)

    def remove(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self._lock, _file_lock(self.path.with_name(self.path.name + ".lock")):
            current = self._load()
            kept = [record for record in current if record["event_id"] not in set(event_ids)]
            if kept != current:
                _durable_json(self.path, kept)


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


def writer_lock(destination: Path) -> Any:
    """One writer per location, across every host sharing it: the same OS-held lock, never taken over by age."""
    return _file_lock(destination / ".lock", wait=2.0, code="RECOVERY_BUSY",
                      message="Another session is writing the recovery copy; try again shortly.")


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


def bind_digest(metadata: dict[str, Any]) -> str:
    """The digest of a generation's host metadata, which the Gateway's seal binds."""
    return hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def memory_md(entries: list[dict[str, Any]], name: str) -> bytes:
    """The generation's Agent Memory Repo entry point, derived only from its signed entries: one bullet per active item, on one
    line, with `[key: value; ...]` metadata (`added` is the store's transaction date), and an index of the generation's files.
    Withdrawn, deleted and off items appear only as counts."""
    active = [shaped["entry"] for shaped in entries if shaped["entry"]["status"] == "active" and shaped["entry"]["trust"] != "off"]
    other = len(entries) - len(active)
    lines = ["# Project memory", "", f"Optimus recovery copy `{name}`: this project's active memory items. Same-drive plaintext, not "
             "a backup. Restore it into an empty store with `/memory restore " + name + "`.", ""]
    for entry in sorted(active, key=lambda e: e["item"]):
        added = time.strftime("%Y-%m-%d", time.gmtime(int(entry["stream_id"].split("-")[0]) / 1000))
        origin = "user" if entry["trust"] == "user-authored" else "agent"
        statement = " ".join(entry["statement"].split())
        lines.append(f"- {statement} [id: {entry['item']}@{entry['version']}; origin: {origin}; kind: {entry['kind']}; added: {added}]")
    if not active:
        lines.append("- (no active items)")
    lines += ["", "## Index", "", "- [[manifest.json]]: the generation, its seal and deletion frontier",
              f"- [[entries.jsonl]]: every item's latest event as the store signed it; {other} withdrawn, deleted or off item(s) "
              "carry no text"]
    return ("\n".join(lines) + "\n").encode("utf-8")


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
            if manifest.get("format") != FORMAT:
                continue
            found.append(Generation(directory.name, manifest["head"], manifest["count"], manifest["frontier"]["deletions"],
                                    manifest["metadata"]["created_ms"], manifest["seal"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(found, key=lambda g: (g.created_ms, g.name), reverse=True)


def read_generation(directory: Path, project: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A generation's manifest and entries, checked by the host: its format and layout, its project, its entries' digest, and an
    entry point that is exactly the one its entries give. The seal over the entries and the metadata is the Gateway's check."""
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        body = (directory / "entries.jsonl").read_bytes()
        entry_point = (directory / "MEMORY.md").read_bytes()
    except (OSError, ValueError):
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation is missing a file or cannot be read; it is not used.") from None
    metadata = manifest.get("metadata") if isinstance(manifest, dict) else None
    if (manifest.get("format") != FORMAT or not isinstance(metadata, dict) or metadata.get("format") != FORMAT
            or (project is not None and metadata.get("project") != project) or tuple(metadata.get("layout", ())) != LAYOUT):
        raise RecoveryError("RECOVERY_GENERATION_FOREIGN", "That generation is not this project's, or not a format this host reads.")
    if hashlib.sha256(body).hexdigest() != manifest.get("entries_sha256") or bind_digest(metadata) != manifest.get("bind"):
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation's files do not match its manifest; it is not used.")
    entries = [json.loads(line) for line in body.splitlines() if line.strip()]
    if entry_point != memory_md(entries, directory.name):
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation's MEMORY.md does not match its entries; it is not used.")
    return manifest, entries


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
        """A confirmed change: the project holds memory, the copy is dirty and its revision moves; a withdrawal or purge also
        marks every older generation for cleanup."""
        def change(state: RecoveryState) -> None:
            state.held_memory = True
            state.dirty = True
            state.revision += 1
            if action in ("withdraw", "tombstone"):
                for target in (state.withdrawn, state.cleanup_pending, *((state.purged,) if action == "tombstone" else ())):
                    if item not in target:
                        target.append(item)
                del state.withdrawn[:-10_000]
                del state.purged[:-10_000]
        self._state.update(change)

    def purging(self, item: str) -> None:
        """Before a purge is dispatched (Codex CP3 review 2, finding 1): the host durably records that it may happen, so a journal
        lost after the Gateway's intent record still cannot let a restore bring the item's text back."""
        def change(state: RecoveryState) -> None:
            if item not in state.purged:
                state.purged.append(item)
            state.dirty = True
            state.revision += 1
        self._state.update(change)

    def purge_refused(self, item: str) -> None:
        """The store answered that this purge was not done (no such item, or it refused); its intent no longer stands. A purge
        whose outcome is unknown keeps it, so the restore waits for the purge to be finished."""
        self._state.update(lambda state: setattr(state, "purged", [entry for entry in state.purged if entry != item]))

    def recovery_required(self, *, fresh: bool = False) -> bool:
        """Q3: the project held memory and its store is now empty (lost volume or a fresh store). Cached for 30 seconds for
        reads; `fresh` asks the store now, as every write does under its lease (Codex CP3 review 1, finding 4)."""
        now = time.monotonic()
        if not fresh and self._required is not None and now - self._required[0] < 30:
            return self._required[1]
        required = False
        if self._state.load().held_memory:
            rows, _cursor = self._store.items("project", limit=1)
            required = not rows and not self._store.checkpoints(limit=1)
        self._required = (now, required)
        return required

    def confirm(self, destination: Path, *, sync_consent: bool) -> None:
        """Record the location the user confirmed (and their sync consent for it), creating it now: from then on a missing
        location means it was removed, and it is never silently made again. A different earlier location is kept in the
        inventory until no managed copy is left in it."""
        destination.mkdir(parents=True, exist_ok=True)
        canonical = str(destination.resolve())

        def change(state: RecoveryState) -> None:
            if state.destination is not None and state.destination != canonical and state.destination not in state.prior:
                state.prior.append(state.destination)
            state.destination = canonical
            state.sync_consent = canonical if sync_consent else None
            state.dirty = True
        self._state.update(change)

    # --- export --------------------------------------------------------------------------------------------------------

    def export(self) -> Generation:
        """Write one generation now, or raise why not; nothing is published when anything fails."""
        export_lock = self._state.path.with_name(self._state.path.name + ".export.lock")
        with self._lock, _file_lock(export_lock, wait=EXPORT_LOCK_SECONDS):  # Codex CP3 review 2, finding 2
            state = self._state.load()
            if state.destination is None:
                raise RecoveryError("RECOVERY_NOT_SET_UP", "No recovery location is set up for this project: `/memory export` sets one up.")
            destination = Path(state.destination)
            if not destination.is_dir():
                raise RecoveryError("RECOVERY_LOCATION_MISSING", f"The recovery location {destination} is gone; it is not replaced "
                                    "automatically. `/memory export` from a trusted worktree offers to move it there.")
            if sync_root(destination) and state.sync_consent != state.destination:
                raise RecoveryError("RECOVERY_SYNC_CONSENT", f"{destination} is in a synced folder; its copies may be kept by the sync "
                                    "service. Confirm with `/memory export` first. Nothing was written.")
            try:
                generation = self._export(state, destination)
            except RecoveryError as failure:
                code = failure.code
                self._state.update(lambda s: setattr(s, "failure", code))
                raise
            self._clean_prior()
            return generation

    def _export(self, state: RecoveryState, destination: Path) -> Generation:
        check_git_exclusion(destination, self._git)
        destination.mkdir(parents=True, exist_ok=True)
        created = self._clock()
        metadata = {"format": FORMAT, "project": self._store.project, "created_ms": created, "layout": list(LAYOUT),
                    "excluded": sorted(set(state.withdrawn)), "registry": self._registry() if self._registry is not None else None}
        # `registry` is the whole registry snapshot: a lost registry is repaired from it, every project's mapping intact
        bind = bind_digest(metadata)
        entries, final = self._read_generation(bind)
        if not entries and state.held_memory:
            raise RecoveryError("RECOVERY_REQUIRED", "The memory store holds nothing for this project although it held memory before. "
                                "The recovery copy is kept; restore it with `/memory restore`.")
        name = f"gen-{created}-{final['seal'][:12]}"
        with writer_lock(destination):
            body = b"".join(json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"
                            for entry in entries)
            manifest = {"format": FORMAT, "metadata": metadata, "bind": bind, "bind_mac": final["bind_mac"], "head": final["head"],
                        "frontier": final["frontier"], "journal": final["journal"], "seal": final["seal"], "count": len(entries),
                        "entries_sha256": hashlib.sha256(body).hexdigest()}
            staging = destination / f".staging-{secrets.token_hex(8)}"
            staging.mkdir()
            try:
                _write(staging / "entries.jsonl", body)
                _write(staging / "MEMORY.md", memory_md(entries, name))
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
            current.dirty = current.revision != state.revision  # a change during the export is not in this generation
            current.failure = None
            current.cleanup_pending = [item for item in current.cleanup_pending if item not in pending]
        self._state.update(change)
        return Generation(name, final["head"], len(entries), final["frontier"]["deletions"], created, final["seal"])

    def _read_generation(self, bind: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Every page at one head. Pages read across a write do not seal together, so the read starts again (bounded)."""
        for _attempt in range(EXPORT_TRIES):
            entries: list[dict[str, Any]] = []
            heads: set[str] = set()
            cursor: str | None = None
            while True:
                reply = self._store.call("export", project=self._store.project, limit=PAGE, bind=bind,
                                         **({"cursor": cursor} if cursor else {}))
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
        published = [path.name for path in destination.glob("gen-*") if path.is_dir()]
        ordered = sorted((g.name for g in generations(destination) if g.name != keep), reverse=True)
        unreadable = [name for name in published if name not in ordered and name != keep]
        doomed = ordered + unreadable if all_older else ordered[KEEP_GENERATIONS - 1:] + unreadable
        for name in doomed:
            shutil.rmtree(destination / name, ignore_errors=True)
            if (destination / name).exists():
                raise RecoveryError("RECOVERY_CLEANUP_FAILED", f"An older recovery copy ({name}) could not be removed; "
                                    "withdrawn text may remain in it. Cleanup stays pending.")

    def _clean_prior(self) -> None:
        """Remove the managed copies left in earlier locations; a location leaves the inventory once none is left in it."""
        state = self._state.load()
        cleaned = []
        for path in state.prior:
            folder = Path(path)
            for managed in [*folder.glob("gen-*"), *folder.glob(".staging-*")] if folder.is_dir() else []:
                shutil.rmtree(managed, ignore_errors=True)
            if not folder.is_dir() or not any(folder.glob("gen-*")) and not any(folder.glob(".staging-*")):
                cleaned.append(path)
        if cleaned:
            self._state.update(lambda s: setattr(s, "prior", [p for p in s.prior if p not in cleaned]))

    def export_if_dirty(self) -> Generation | None:
        """A scheduled export. When a change landed during it and older copies still need cleaning, it runs once more."""
        last = None
        for _ in range(2):
            state = self._state.load()
            if state.destination is None or not state.dirty or self.recovery_required():
                return last
            try:
                last = self.export()
            except RecoveryError:
                return last
            if not self._state.load().cleanup_pending:
                return last
        return last

    # --- restore -------------------------------------------------------------------------------------------------------

    def read_generation(self, name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        state = self._state.load()
        if state.destination is None:
            raise RecoveryError("RECOVERY_NOT_SET_UP", "No recovery location is set up for this project.")
        directory = Path(state.destination) / name
        if not name.startswith("gen-") or directory.parent != Path(state.destination) or not directory.is_dir():
            raise RecoveryError("RECOVERY_GENERATION_UNKNOWN", f"There is no recovery generation `{name}` here.")
        return read_generation(directory, self._store.project)

    def restore(self, name: str, *, seal: str, directory: Path | None = None) -> dict[str, Any]:
        """Restore exactly the generation the user confirmed (its seal must match: Codex CP3 review 1, finding 3) into the empty
        store, after checking its registry mapping is this project's current one. The Gateway verifies every entry, the seal
        over the entries and the metadata, refuses a project holding anything, applies the deletion journal and this host's
        later deletions, and publishes only on the last batch."""
        manifest, entries = read_generation(directory, self._store.project) if directory is not None else self.read_generation(name)
        if manifest["seal"] != seal:
            raise RecoveryError("RECOVERY_GENERATION_CHANGED", f"`{name}` is not the copy you confirmed (it changed meanwhile). "
                                "Nothing was restored.")
        project = self._store.project
        snapshot = manifest["metadata"].get("registry")
        mapped = registry_entry(snapshot, project) if isinstance(snapshot, dict) else None
        current = registry_entry(self._registry(), project) if self._registry is not None else None
        if current and mapped and mapped.get("key") != current.get("key"):
            raise RecoveryError("RECOVERY_MAPPING_MISMATCH", "That copy was written for another workspace's registration; nothing was restored.")
        known = self._state.load()
        withdrawn, purged = sorted(set(known.withdrawn)), sorted(set(known.purged))
        batches = [entries[n:n + BATCH] for n in range(0, len(entries), BATCH)] or [[]]
        if len(batches[-1]) == BATCH:
            batches.append([])
        with self._store.lease(guarded=False) as token:
            for number, batch in enumerate(batches[:-1]):
                self._store.call("restore", project=self._store.project, token=token, generation=seal, batch=number, final=False,
                                 entries=batch)
            reply: dict[str, Any] = self._store.call(
                "restore", project=self._store.project, token=token, generation=seal, batch=len(batches) - 1, final=True,
                entries=batches[-1], head=manifest["head"], frontier=manifest["frontier"], withdrawn=withdrawn, bind=manifest["bind"],
                journal=manifest["journal"], purged=purged)
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
        if not Path(state.destination).is_dir():
            lines.append("the location is gone; `/memory export` offers to move it")
        if state.exported:
            when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(state.exported["at_ms"] / 1000))
            lines.append(f"last saved {when}, {state.exported['count']} items ({state.exported['name']})")
        else:
            lines.append("never saved yet")
        if state.dirty:
            lines.append("changes since are not in it yet (saved every 15 minutes while Optimus runs)")
        if state.cleanup_pending:
            lines.append(f"withdrawn; plaintext recovery cleanup pending for {len(state.cleanup_pending)} item(s)")
        if state.prior:
            lines.append("earlier locations still holding copies: " + ", ".join(state.prior))
        if state.failure:
            lines.append(f"last attempt failed: {state.failure}")
        lines.append("same-drive plaintext, not a backup; authorized TEST or shell commands can read it; synced or copied files "
                     "cannot be erased by Optimus")
        return "; ".join(lines) + "."


class RegistryRecovery:
    """A workspace whose project registry is lost (Codex CP3 review 1, registry ruling). The registry is repaired only from a
    generation in this workspace's recovery location whose metadata the Gateway authenticates (`verify_bind`), and only for this
    workspace's own registry key; then the store is restored from it if it is empty. Nothing else is available meanwhile."""

    def __init__(self, workspace: Path, *, key: str, restore_registry: Callable[[dict[str, Any]], None],
                 open_store: Callable[[str], Any], state_for: Callable[[str], StateFile]) -> None:
        self.workspace, self._key, self._restore_registry, self._open_store, self._state_for = workspace, key, restore_registry, open_store, state_for

    def generations(self) -> list[Generation]:
        return generations(location(self.workspace))

    def read(self, name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        directory = location(self.workspace) / name
        if not name.startswith("gen-") or not directory.is_dir():
            raise RecoveryError("RECOVERY_GENERATION_UNKNOWN", f"There is no recovery generation `{name}` here.")
        return read_generation(directory, None)

    def recover(self, name: str, *, seal: str) -> str:
        manifest, _entries = self.read(name)
        metadata = manifest["metadata"]
        snapshot, project = metadata.get("registry") or {}, metadata["project"]
        mapped = registry_entry(snapshot, project) or {}
        if manifest["seal"] != seal:
            raise RecoveryError("RECOVERY_GENERATION_CHANGED", f"`{name}` is not the copy you confirmed; nothing was restored.")
        if mapped.get("key") != self._key or mapped.get("project_id") != project:
            raise RecoveryError("RECOVERY_MAPPING_MISMATCH", "That copy was written for another workspace's registration; nothing was restored.")
        store = self._open_store(project)
        if not store.call("verify_bind", project=project, bind=manifest["bind"], mac=manifest["bind_mac"])["valid"]:
            raise RecoveryError("RECOVERY_GENERATION_UNAUTHENTIC", "The memory store did not write that copy's manifest; nothing was restored.")
        # the whole authenticated snapshot, so every other project keeps its identity too (Codex CP3 review 2, finding 3)
        self._restore_registry(snapshot)
        rows, _cursor = store.items("project", limit=1)
        if rows:
            return f"Restored the project registry from `{name}`; the memory store already holds this project's memory."
        state = self._state_for(project)
        state.update(lambda s: setattr(s, "held_memory", True))
        recovery = Recovery(store, state, registry=lambda: snapshot)
        reply = recovery.restore(name, seal=seal, directory=location(self.workspace) / name)
        return f"Restored the project registry and {reply.get('restored', 0)} items from `{name}`."


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


def registry_entry(snapshot: Any, project: str) -> dict[str, Any] | None:
    """One project's mapping in a registry snapshot."""
    if not isinstance(snapshot, dict):
        return None
    for key, entry in snapshot.get("projects", {}).items():
        if entry.get("project_id") == project:
            return {"key": key, **entry}
    return None
