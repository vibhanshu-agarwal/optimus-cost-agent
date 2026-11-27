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
the next opportunity in any session, so a restart loses no notice that was written and a resend repeats no change. A write the disk refuses
is held in the process and retried by later backlog calls (#643); what is still held when the host exits is lost with it (a
card, never the change: see `NoticeBacklog`).
"""

from __future__ import annotations

import contextlib
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
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from optimus.context.memory_workspace import _git
from optimus_file_lock import FileLock, LockBusy, LockFault

_LOG = logging.getLogger(__name__)

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


def os_reason(failure: OSError, path: Path) -> str:
    """The OS's reason, plus the likely cause when Windows refuses a long path: the path that failed (else `path`) reaches the
    248 characters a folder may have without long-path support."""
    reason = failure.strerror or str(failure)
    if sys.platform == "win32" and len(failure.filename if isinstance(failure.filename, str) else str(path)) >= 248:
        reason += "; the path is longer than Windows allows unless long paths are enabled"
    return reason


class RecoveryError(Exception):
    """A stable `code` and a sentence for the user. Nothing was written when one is raised before publication."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


@contextlib.contextmanager
def _file_lock(path: Path, *, wait: float = STATE_LOCK_SECONDS, code: str = "RECOVERY_STATE_BUSY",
               message: str = "The recovery state is held by another process; try again shortly.",
               fault_code: str = "RECOVERY_LOCK_FAILED") -> Iterator[None]:
    """An OS-held lock on a file shared by every process on this machine (Codex CP3 review 1, finding 2), through
    optimus_file_lock (#532): it ends only when its owner releases it, closes the file or dies, never by age, and the file
    is left in place. Another holder past `wait` is `code`; a lock call the OS refuses for any other reason is `fault_code`
    with its errno, at once (#529 review 2). Its message claims nothing about earlier work: a caller can hold this lock after
    writing, so only the caller can say what was left. Creating the lock's folder or opening its file is the caller's own
    filesystem step, so that failure stays the OSError it always was: a backup still reads a vanished or unwritable target
    from its errno, retrying the transient ones (#532 review)."""
    lock = FileLock(path)
    try:
        lock.acquire(wait=wait)
    except LockBusy:
        raise RecoveryError(code, message) from None
    except LockFault as fault:
        if fault.stage == "open" and isinstance(fault.__cause__, OSError):
            raise fault.__cause__ from None
        raise RecoveryError(fault_code, f"The lock file {path.name} could not be taken (errno {fault.errno}).") from None
    try:
        yield
    finally:
        lock.release()


@contextlib.contextmanager
def _opened_lock(path: Path, unopened: Callable[[OSError], Exception], **kwargs: Any) -> Iterator[None]:
    """`_file_lock`, for a lock file in Optimus's own config folder: when that file cannot be created or opened (a read-only or
    full disk), `unopened(failure)` is raised instead of the raw OSError (Codex CP3 review 2, finding 1). Errors raised inside
    the locked block pass through untouched, and contention and lock faults keep their own codes."""
    held = _file_lock(path, **kwargs)
    try:
        held.__enter__()
    except OSError as failure:
        raise unopened(failure) from None
    try:
        yield
    except BaseException:
        if not held.__exit__(*sys.exc_info()):
            raise
    else:
        held.__exit__(None, None, None)


def _state_unopened(path: Path) -> Callable[[OSError], Exception]:
    return lambda failure: RecoveryError("RECOVERY_STATE_UNWRITABLE", f"The recovery state's lock file could not be opened "
                                         f"({os_reason(failure, path)}); the earlier state is kept.")


def _durable_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        with open(temporary, "wb") as handle:
            handle.write(json.dumps(value, sort_keys=True, ensure_ascii=True).encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            temporary.unlink()  # a write the disk refused leaves no partial file behind
        raise


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
    mapped_from: str | None = None  # the earlier project id a confirmed mapping restored this project from (M21)
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
        lock = self.path.with_name(self.path.name + ".lock")
        with self._lock, _opened_lock(lock, _state_unopened(lock)):
            state = self.load()
            change(state)
            try:
                _durable_json(self.path, state.to_json())
            except OSError as failure:  # a full or read-only disk: an answer, never a raw error (Codex CP3 review 1, finding 2)
                raise RecoveryError("RECOVERY_STATE_UNWRITABLE", f"The recovery state could not be saved "
                                    f"({os_reason(failure, self.path)}); the earlier state is kept.") from None
            return state


class NoticeBacklog:
    """Memory notices a person has not been shown yet, for one project, durable across restarts (Codex CP3 review 1, finding 6).
    A notice is added before it is sent and removed once its send is confirmed; any session of the project delivers what is left,
    under the same event id, so a resend never repeats a change.

    #643: an add or remove the disk refuses is held in this process (records, and removals as tombstones) and written by a later
    non-empty add or remove, each turn's `pending`, or `flush`, one attempt per call, so every session of the project in this
    process still sees it; `pending` returns no tombstoned id. Held state is capped (`HELD_LIMIT` each, oldest dropped and
    counted). Known limits: what is still held when the process ends is lost with it (a card not shown, or a delivered card shown
    again by the next process); a tombstone dropped at the cap can likewise show a delivered card again after a restart. The
    change itself stays in the store and `/memory` lists it."""

    HELD_LIMIT: Final = 256

    def __init__(self, config_root: Path, project: str) -> None:
        self.path = config_root / "memory-notices" / f"{hashlib.sha256(project.encode()).hexdigest()[:32]}.json"
        self._lock = threading.Lock()  # guards the file and every held field below
        self._held: dict[str, dict[str, Any]] = {}  # event id -> record not yet written, oldest first
        self._gone: dict[str, None] = {}  # event ids delivered whose removal is not yet written, oldest first
        self._acked: dict[str, None] = {}  # event ids this process delivered, newest last, capped (#643 review 2, finding 2)
        self._dropped = 0  # held records or tombstones dropped at the cap while failing
        self._failing = False

    @classmethod
    def shared(cls, config_root: Path, project: str) -> NoticeBacklog:
        candidate = cls(config_root, project)
        with _SHARED_LOCK:
            found: NoticeBacklog = _SHARED.setdefault(candidate.path, candidate)
            return found

    def _load(self, *, writing: bool = False) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except OSError:
            if writing:
                raise  # a file that cannot be read now is never overwritten with only what this process holds (#643)
            return []
        except ValueError:
            return []
        return [record for record in data if isinstance(record, dict)] if isinstance(data, list) else []

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._held or self._gone:
                with contextlib.suppress(Exception):  # `_apply` logged the cause; what is held stays held
                    self._apply()
            current = [record for record in self._load() if _event_key(record) not in self._gone]
            known = {_event_key(record) for record in current}
            return current + [record for event_id, record in self._held.items() if event_id not in known]

    def add(self, records: list[dict[str, Any]]) -> None:
        """Raises what the write raised, with the records already held for the next call (an import stops on it)."""
        if not records:
            return
        with self._lock:
            for record in records:
                if record["event_id"] not in self._gone:  # a delivered notice added again (an import's resume) stays delivered
                    self._hold(self._held, record["event_id"], record)
            self._apply()

    def remove(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self._lock:
            for event_id in event_ids:
                self._held.pop(event_id, None)  # a delivered record is never written or shown again
                self._hold(self._gone, event_id, None)
                self._hold(self._acked, event_id, None)
                if len(self._acked) > self.HELD_LIMIT:
                    del self._acked[next(iter(self._acked))]
            self._apply()

    def acknowledged(self, event_ids: list[str]) -> set[str]:
        """Which of `event_ids` a session of this project in this process has delivered: the evidence a session's own queue
        needs before dropping its copy, since an unreadable file or a held record dropped at the cap is no evidence."""
        with self._lock:
            return {event_id for event_id in event_ids if event_id in self._acked}

    def flush(self) -> None:
        """One attempt to write what is held (a session's close); never raises."""
        with self._lock:
            if self._held or self._gone:
                with contextlib.suppress(Exception):
                    self._apply()

    @staticmethod
    def _hold(held: dict[str, Any], key: str, value: Any) -> None:
        held.pop(key, None)
        held[key] = value  # newest last

    def _apply(self) -> None:
        """Under `self._lock`: one attempt to apply the held records and tombstones to the file. Held state is cleared as soon as
        the file holds it, so an error releasing the lock afterwards never re-applies it. The first failure and the first write
        after it are each logged once, with the error's class and counts, no values."""
        try:
            with _file_lock(self.path.with_name(self.path.name + ".lock")):
                current = self._load(writing=True)
                known = {_event_key(record) for record in current}  # a malformed record never blocks the rest
                for event_id in [event_id for event_id in self._gone if event_id not in known]:
                    del self._gone[event_id]  # nothing on disk to remove: it never takes a real tombstone's place at the cap
                target = [record for record in current if _event_key(record) not in self._gone]
                target += [record for event_id, record in self._held.items() if event_id not in known and event_id not in self._gone]
                if target != current:
                    _durable_json(self.path, target)  # kept until acknowledged, however many (Codex CP3 review 2, finding 4)
                    if self._failing:  # only a real write shows the disk takes writes again; logged before the lock is released
                        _LOG.warning("Memory notice backlog written again; %d held notice(s) or removal(s) were dropped at the "
                                     "cap meanwhile", self._dropped)
                    self._failing, self._dropped = False, 0
                self._held.clear()
                self._gone.clear()
        except Exception as failure:
            for held in (self._held, self._gone):  # only what stays unwritten is capped; a write takes any number
                while len(held) > self.HELD_LIMIT:
                    del held[next(iter(held))]
                    self._dropped += 1
            if (self._held or self._gone) and not self._failing:
                self._failing = True
                _LOG.warning("Memory notice backlog write failed (%s); holding %d notice(s) and %d removal(s) in this process",
                             _failure_class(failure), len(self._held), len(self._gone))
            raise


def _event_key(record: dict[str, Any]) -> str | None:
    """A record's event id, or None for a malformed one, which is kept but never matched (#643 review 1, finding 6)."""
    event_id = record.get("event_id")
    return event_id if isinstance(event_id, str) else None


def _failure_class(failure: BaseException) -> str:
    """A value-free name for a failure: an OSError's errno name, a RecoveryError's code, else the exception's class."""
    if isinstance(failure, OSError) and failure.errno is not None:
        return errno.errorcode.get(failure.errno, f"errno {failure.errno}")
    if isinstance(failure, RecoveryError):
        return failure.code
    return type(failure).__name__


def location(worktree: Path) -> Path:
    return worktree.joinpath(*LOCATION)


def sync_root(path: Path) -> str | None:
    """The known sync service a location lies in, from the environment's sync folders and well-known folder names."""
    resolved = os.path.normcase(str(path.resolve()))
    for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        root = os.environ.get(name)
        if not root:
            continue
        base = os.path.normcase(str(Path(root).resolve()))
        if resolved == base or resolved.startswith(base + os.sep):  # the sync root itself, or anything in it
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


def memory_md(entries: list[dict[str, Any]], name: str, *, imported: str = "imported") -> bytes:
    """The generation's Agent Memory Repo entry point, derived only from its signed entries: one bullet per active item, on one
    line, with `[key: value; ...]` metadata (`added` is the store's transaction date), and an index of the generation's files.
    Withdrawn, deleted and off items appear only as counts. An imported item's origin is `imported`; format 2 before Plan 12.12
    wrote `agent` for it (`imported="agent"`), which `entry_points` still accepts."""
    active = [shaped["entry"] for shaped in entries if shaped["entry"]["status"] == "active" and shaped["entry"]["trust"] != "off"]
    other = len(entries) - len(active)
    lines = ["# Project memory", "", f"Optimus recovery copy `{name}`: this project's active memory items. Same-drive plaintext, not "
             "a backup. Restore it into an empty store with `/memory restore " + name + "`.", ""]
    for entry in sorted(active, key=lambda e: e["item"]):
        added = time.strftime("%Y-%m-%d", time.gmtime(int(entry["stream_id"].split("-")[0]) / 1000))
        origin = {"user-authored": "user", "legacy-import": imported}.get(entry["trust"], "agent")
        statement = " ".join(entry["statement"].split())
        lines.append(f"- {statement} [id: {entry['item']}@{entry['version']}; origin: {origin}; kind: {entry['kind']}; added: {added}]")
    if not active:
        lines.append("- (no active items)")
    lines += ["", "## Index", "", "- [[manifest.json]]: the generation, its seal and deletion frontier",
              f"- [[entries.jsonl]]: every item's latest event as the store signed it; {other} withdrawn, deleted or off item(s) "
              "carry no text"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def entry_points(entries: list[dict[str, Any]], name: str) -> tuple[bytes, bytes]:
    """The entry points a format-2 generation of these entries may hold: the current one, and the one format 2 wrote before
    Plan 12.12 named imported items (`origin: agent`). Existing signed copies are verified as written, never rewritten (Codex
    CP2 review 1, finding 9)."""
    return memory_md(entries, name), memory_md(entries, name, imported="agent")


def checked_generation(manifest_bytes: bytes, body: bytes, entry_point: bytes, name: str,
                       project: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A generation's manifest and entries from its three files' bytes, checked by the host: its format and layout, its project
    (when given), its entries' digest and metadata binding, and an entry point that is exactly one its entries give. The seal
    over the entries and the metadata is the Gateway's check."""
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        entries = [json.loads(line) for line in body.splitlines() if line.strip()]
    except (UnicodeDecodeError, ValueError):
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation's files cannot be read; it is not used.") from None
    metadata = manifest.get("metadata") if isinstance(manifest, dict) else None
    if (not isinstance(manifest, dict) or manifest.get("format") != FORMAT or not isinstance(metadata, dict)
            or metadata.get("format") != FORMAT or (project is not None and metadata.get("project") != project)
            or not isinstance(metadata.get("layout"), list) or tuple(metadata["layout"]) != LAYOUT):  # shapes checked first
        raise RecoveryError("RECOVERY_GENERATION_FOREIGN", "That generation is not this project's, or not a format this host reads.")
    try:
        bound = bind_digest(metadata)
    except (TypeError, ValueError):
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation's manifest is not in the copy's form; it is not used.") from None
    if hashlib.sha256(body).hexdigest() != manifest.get("entries_sha256") or bound != manifest.get("bind"):
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation's files do not match its manifest; it is not used.")
    if not all(isinstance(shaped, dict) and isinstance(shaped.get("entry"), dict) for shaped in entries):
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation's entries are not in the copy's form; it is not used.")
    try:
        points = entry_points(entries, name)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation's entries are not in the copy's form; it is not used.") from None
    if entry_point not in points:
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation's MEMORY.md does not match its entries; it is not used.")
    return manifest, entries


@dataclass(frozen=True)
class Generation:
    name: str
    head: str
    count: int
    deletions: int
    created_ms: int
    seal: str
    project: str = ""  # the project the generation was written for
    registry_key: str = ""  # that project's registry key when it was written: an earlier registration of this workspace shares it


def generations(destination: Path) -> list[Generation]:
    """The published generations at a location, newest first, each as its manifest says. An unreadable one is skipped."""
    found = []
    for directory in destination.glob("gen-*"):
        try:
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("format") != FORMAT:
                continue
            project = manifest["metadata"]["project"]
            entry = registry_entry(manifest["metadata"].get("registry"), project) or {}
            found.append(Generation(directory.name, manifest["head"], manifest["count"], manifest["frontier"]["deletions"],
                                    manifest["metadata"]["created_ms"], manifest["seal"], project, str(entry.get("key", ""))))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(found, key=lambda g: (g.created_ms, g.name), reverse=True)


def _read_or_none(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def read_generation(directory: Path, project: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A generation's manifest and entries, checked by the host: its format and layout, its project, its entries' digest, and an
    entry point that is exactly the one its entries give. The seal over the entries and the metadata is the Gateway's check."""
    try:
        manifest_bytes = (directory / "manifest.json").read_bytes()
        body = (directory / "entries.jsonl").read_bytes()
        entry_point = (directory / "MEMORY.md").read_bytes()
    except OSError:
        raise RecoveryError("RECOVERY_GENERATION_DAMAGED", "That generation is missing a file or cannot be read; it is not used.") from None
    return checked_generation(manifest_bytes, body, entry_point, directory.name, project)


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
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as failure:
            raise RecoveryError("RECOVERY_LOCATION_UNWRITABLE", f"{destination} could not be created ({os_reason(failure, destination)})."
                                " Nothing was changed.") from None
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
        with self._lock, _opened_lock(export_lock, _state_unopened(export_lock), wait=EXPORT_LOCK_SECONDS):  # Codex CP3 review 2, finding 2
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
                raise self._recorded(failure) from None
            except OSError as failure:  # not recorded as exported; one renamed into place first is retired like any older copy
                raise self._recorded(RecoveryError("RECOVERY_WRITE_FAILED", f"The recovery copy could not be written to {destination} "
                                                   f"({os_reason(failure, destination)}). The last copy is kept.")) from None
            self._clean_prior()
            return generation

    def _recorded(self, failure: RecoveryError) -> RecoveryError:
        """`failure`, recorded as the last export's. When even that record cannot be saved (often the same full disk), the
        answer is still this failure's, and says the record is missing too."""
        if failure.code == "RECOVERY_STATE_UNWRITABLE":
            return failure  # the state file itself is what the disk refused: recording it there would only fail again
        try:
            self._state.update(lambda s: setattr(s, "failure", failure.code))
        except RecoveryError as unsaved:
            return RecoveryError(failure.code, f"{failure.message} It could not be recorded either: {unsaved.message}")
        return failure

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
            manifest_bytes = json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=True).encode("ascii")
            entry_point = memory_md(entries, name)
            published = destination / name
            if published.is_dir():  # the same name: an export repeated in the same millisecond, or a rename whose record was lost
                held = [_read_or_none(published / file) for file in ("entries.jsonl", "MEMORY.md", "manifest.json")]
                if held != [body, entry_point, manifest_bytes]:  # every file, not the manifest alone (Codex CP3 review 1, finding 1)
                    raise RecoveryError("RECOVERY_GENERATION_DAMAGED", f"A recovery copy named {name} is already in {destination} "
                                        "but differs from what was read; it was not replaced or counted, and no older copy was "
                                        "removed.")
            else:
                staging = destination / f".staging-{secrets.token_hex(8)}"
                staging.mkdir()
                try:
                    _write(staging / "entries.jsonl", body)
                    _write(staging / "MEMORY.md", entry_point)
                    _write(staging / "manifest.json", manifest_bytes)
                    _fsync_dir(staging)
                    os.replace(staging, published)  # one atomic rename on the same volume publishes the whole generation
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

    def _read_generation(self, bind: str, *, pin: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Every page of one generation at one head: the Gateway fixes it at the first page's head (or at `pin`, a copy's own
        head when a backup authenticates it) and serves every later page from it, so writes landing meanwhile never break it
        (Plan 12.12 CP3). A deletion landing meanwhile makes the Gateway refuse the last page: the read starts again (bounded).
        With `pin`, a head the Gateway no longer holds is `RECOVERY_SOURCE_MOVED`."""
        from optimus.context.authored_memory import MemoryStoreRefused

        for _attempt in range(EXPORT_TRIES):
            entries: list[dict[str, Any]] = []
            heads: set[str] = set()
            cursor: str | None = None
            at = pin
            try:
                while True:
                    reply = self._store.call("export", project=self._store.project, limit=PAGE, bind=bind,
                                             **({"pin": at} if at else {}), **({"cursor": cursor} if cursor else {}))
                    entries += reply["entries"]
                    heads.add(reply["head"])
                    at = reply["head"]
                    cursor = reply["cursor"]
                    if cursor is None:
                        break
            except MemoryStoreRefused as refused:
                if refused.code == "RECOVERY_EXPORT_MOVED" and pin is not None:
                    raise RecoveryError("RECOVERY_SOURCE_MOVED", "Memory moved on from that copy; it will be read again.") from None
                if refused.code in ("RECOVERY_EXPORT_MOVED", "RECOVERY_DELETION_RACED"):
                    continue  # a deletion landed, or the pinned generation lapsed: read it again
                raise
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

    def read_generation(self, name: str, *, source: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        state = self._state.load()
        if state.destination is None:
            raise RecoveryError("RECOVERY_NOT_SET_UP", "No recovery location is set up for this project.")
        directory = Path(state.destination) / name
        if not name.startswith("gen-") or directory.parent != Path(state.destination) or not directory.is_dir():
            raise RecoveryError("RECOVERY_GENERATION_UNKNOWN", f"There is no recovery generation `{name}` here.")
        return read_generation(directory, source or self._store.project)

    def mapping_source(self, name: str, place: Path) -> str:
        """The earlier project a generation may be mapped from into this one (Plan 12.11 Task 5, M21), or a refusal. One to one:
        it must be an earlier registration of this same workspace (its registry key is this project's current key), the only
        earlier project id this location holds for that key, and not another than one this project was already mapped from.
        `place` is where the copies are: this project's location, or, before it has one, its worktree's default location."""
        state = self._state.load()
        found = generations(place)
        chosen = next((g for g in found if g.name == name), None)
        if chosen is None:
            raise RecoveryError("RECOVERY_GENERATION_UNKNOWN", f"There is no recovery generation `{name}` here.")
        project = self._store.project
        if chosen.project == project:
            raise RecoveryError("RECOVERY_MAPPING_NOT_NEEDED", f"`{name}` is this project's own copy: `/memory restore {name}` restores it.")
        current = registry_entry(self._registry(), project) if self._registry is not None else None
        if not current or not chosen.registry_key or chosen.registry_key != current.get("key"):
            raise RecoveryError("RECOVERY_MAPPING_MISMATCH", "That copy was written for another workspace's registration; nothing was "
                                "restored.")
        claims = {g.project for g in found if g.registry_key == chosen.registry_key and g.project != project}
        if len(claims) > 1 or (state.mapped_from is not None and state.mapped_from != chosen.project):
            raise RecoveryError("RECOVERY_MAPPING_REJECTED", "Not restored: more than one earlier project claims this one ("
                                + ", ".join(sorted(claims | ({state.mapped_from} if state.mapped_from else set()))) + "), so no "
                                "mapping is chosen for you. Nothing was changed.")
        return chosen.project

    def restore(self, name: str, *, seal: str, directory: Path | None = None, source: str | None = None,
                workspace: Path | None = None) -> dict[str, Any]:
        """Restore exactly the generation the user confirmed (its seal must match: Codex CP3 review 1, finding 3) into the empty
        store, after checking its registry mapping is this project's current one. Then, before anything is written, each restored
        live item's pinned files are validated in `workspace` (plan v5 Recovery: "validate anchors"; Codex CP4 review 2, F8);
        the reply's `anchors` says which hold and which need re-verification. An item whose pin no longer holds is still restored:
        serving keeps it out until the user edits it. The Gateway verifies every entry, the seal over the entries and the
        metadata, refuses a project holding anything, applies the deletion journal and this host's later deletions, and publishes
        only on the last batch."""
        if source is not None and (directory is None or self.mapping_source(name, directory.parent) != source):  # rechecked now
            raise RecoveryError("RECOVERY_MAPPING_REJECTED", "Not restored: the mapping you confirmed no longer holds. Nothing was changed.")
        manifest, entries = (read_generation(directory, source or self._store.project) if directory is not None
                             else self.read_generation(name, source=source))
        if manifest["seal"] != seal:
            raise RecoveryError("RECOVERY_GENERATION_CHANGED", f"`{name}` is not the copy you confirmed (it changed meanwhile). "
                                "Nothing was restored.")
        project = self._store.project
        snapshot = manifest["metadata"].get("registry")
        mapped = registry_entry(snapshot, source or project) if isinstance(snapshot, dict) else None
        current = registry_entry(self._registry(), project) if self._registry is not None else None
        if current and mapped and mapped.get("key") != current.get("key"):
            raise RecoveryError("RECOVERY_MAPPING_MISMATCH", "That copy was written for another workspace's registration; nothing was restored.")
        known = self._state.load()
        withdrawn, purged = sorted(set(known.withdrawn)), sorted(set(known.purged))
        held, changed = check_anchors(entries, workspace, excluded=set(withdrawn) | set(purged))
        batches = [entries[n:n + BATCH] for n in range(0, len(entries), BATCH)] or [[]]
        if len(batches[-1]) == BATCH:
            batches.append([])
        mapping = {"source": source} if source is not None else {}
        with self._store.lease(guarded=False) as token:
            for number, batch in enumerate(batches[:-1]):
                self._store.call("restore", project=self._store.project, token=token, generation=seal, batch=number, final=False,
                                 entries=batch, **mapping)
            reply: dict[str, Any] = self._store.call(
                "restore", project=self._store.project, token=token, generation=seal, batch=len(batches) - 1, final=True,
                entries=batches[-1], head=manifest["head"], frontier=manifest["frontier"], withdrawn=withdrawn, bind=manifest["bind"],
                journal=manifest["journal"], purged=purged, **mapping)
        self._required = None

        def change(state: RecoveryState) -> None:
            state.held_memory = True
            state.dirty = True
            if source is not None:
                state.mapped_from = source
        self._state.update(change)
        return {**reply, "anchors": {"held": held, "changed": changed}}

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
        reply = recovery.restore(name, seal=seal, directory=location(self.workspace) / name, workspace=self.workspace)
        return f"Restored the project registry and {reply.get('restored', 0)} items from `{name}`."


def check_anchors(entries: list[dict[str, Any]], workspace: Path | None, *,
                  excluded: set[str]) -> tuple[list[list[Any]], list[list[Any]]]:
    """Each live item's newest restored version that rests on workspace files (`file:` lineage), checked now in `workspace`
    through the anchor file policy: ([item, version] whose files hold, [item, version, path] whose file changed, is gone or is no
    longer readable as an anchor). Items this host already withdrew or purged are not checked: they will not be served."""
    from optimus.context import memory_serving
    from optimus.guardrails.file_policy import FilePolicy

    newest: dict[str, dict[str, Any]] = {}
    for entry in (shaped["entry"] for shaped in entries):
        if entry["item"] not in newest or entry["version"] > newest[entry["item"]]["version"]:
            newest[entry["item"]] = entry
    policy = FilePolicy(workspace) if workspace is not None else None
    held: list[list[Any]] = []
    changed: list[list[Any]] = []
    for item, entry in sorted(newest.items()):
        lineage = entry.get("lineage") or ()
        if item in excluded or entry.get("status") not in ("active", "reverify") or not any(
                ref.startswith(memory_serving.FILE_PREFIX) for ref in lineage):
            continue
        path = memory_serving.changed_file(lineage, workspace, policy)
        if path is None:
            held.append([item, entry["version"]])
        else:
            changed.append([item, entry["version"], path])
    return held, changed


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
