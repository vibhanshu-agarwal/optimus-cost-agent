"""Agent Memory Repo import (Plan 12.12 Task 2): `/memory import <root>`, `... apply <preview-id>` and `... status`.

**Source.** An [Agent Memory Repo](https://cognition.com/agent-memory-repo) is read as data only: `MEMORY.md` at the root, each
entry a one-line bullet with optional `[key: value; ...]` metadata, and `[[path]]` links relative to the root (`.md` omitted for
Markdown). Only Markdown reachable from `MEMORY.md` is read for entries; any other link target is a coverage gap, listed and never
followed. Nothing is executed, fetched, cloned or pushed, and nothing in the source carries authority: the model never sees it.

**Checks.** The root is absolute and reached without links; each file is a regular file inside it, spelled exactly as it resolves
(no `..`, case or short-name aliases, links or reparse points), strict UTF-8 without NUL, at most 1 MiB, 16 MiB in all; a file
is read once by its identity, so link cycles end. An entry is refused whole when it is malformed, holds control or bidi
characters, is over 2,000 characters (never truncated), is past the 1,000th, claims lineage the host cannot resolve, fails the
secret, injection or B1 source-overlap scan, or belongs to no mapped project. An inactive source entry (`status:` other than
active) is skipped with no statement kept.

**Authority.** Every import is `legacy-import`, kind `fact`: served only in the optional pool, never protected. Metadata that
claims user authorship, approval, a type or a constraint is recorded as an inert claimed origin (`claimed-origin:` lineage), never
honoured. A `file:` anchor keeps the source's digest, so serving holds it for re-verification unless the file still matches.
Nothing updates, retargets or reactivates an existing item.

**Preview and apply.** A preview binds the source: each file's path, size and SHA-256, each entry's locator, exact statement,
disposition and lineage, and the mapping. Apply reads the source again and goes ahead only when that digest is unchanged. Each
entry is then an ordinary Gate decision and fenced durable append under the project's lease, one by one, not a batch: an
entry's id derives from the project, the mapped source and its statement, so applying again, or resuming after a crash, writes
nothing twice and never revives an item withdrawn or purged since. Its progress is a durable log per project (no statements in
it), which `/memory import status` reads.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import secrets
import stat
import time
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from context_engine import memory_gate
from context_engine.memory_contracts import MAX_STATEMENT_CHARS, HostVerdict, MemoryCandidate, MemoryNotice
from optimus.context import memory_serving
from optimus.context.memory_extraction import scans_pass, title_of

ENTRY_POINT: Final = "MEMORY.md"
MAX_FILE_BYTES: Final = 1024 * 1024
MAX_TOTAL_BYTES: Final = 16 * 1024 * 1024
MAX_ENTRIES: Final = 1000
PREVIEW_SECONDS: Final = 1800.0  # a preview older than this is stale: import the root again
RENEW_SECONDS: Final = 10.0  # the write lease (30 s) is renewed this often during a long apply
SHOWN: Final = 200  # entries listed in a preview; the counts cover the rest
TRUST: Final = "legacy-import"
KIND: Final = "fact"
CLAIM_PREFIX: Final = "claimed-origin:"

# Metadata whose claims are never honoured: recorded as the claimed origin, or ignored.
_AUTHORITY: Final = frozenset({"trust", "origin", "author", "authored-by", "approved", "approval", "approved-by", "constraint",
                               "protected", "pinned", "kind", "type", "priority"})
_LINEAGE: Final = frozenset({"lineage", "evidence", "derived-from", "depends-on"})
_ANCHORS: Final = frozenset({"file", "anchor"})
_USER_WORDS: Final = frozenset({"user", "user-authored", "human", "yours"})
_AGENT_WORDS: Final = frozenset({"agent", "agent-derived", "agent lesson"})
_BIDI: Final = frozenset(map(chr, (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))))  # bidi controls
_BULLET: Final = re.compile(r"^\s*[-*]\s+(.*?)\s*$")
_LINK: Final = re.compile(r"\[\[([^\[\]]*)\]\]")
_META: Final = re.compile(r"\s*\[([^\[\]]*:[^\[\]]*)\]\s*$")
_PAIR: Final = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(\S(?:.*\S)?)\s*$")
_ITEM_REF: Final = re.compile(r"(m-[0-9a-f]{16})@([1-9][0-9]{0,9})")
_REFERENCE: Final = re.compile(r"[A-Za-z0-9._:@/-]{1,128}")
_WORD: Final = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_./-]*")
_PREVIEW_ID: Final = re.compile(r"imp-[0-9a-f]{12}")
_REPARSE_POINT: Final = 0x400
_PLACEHOLDER: Final = "(no active items)"  # what an Optimus recovery copy lists when it holds no active item: not a note
_ITEM_REFUSALS: Final = frozenset({"VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT"})  # this entry only; any other stops the apply


class ImportRefused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SourceFile:
    path: str  # root-relative, as linked
    size: int
    sha256: str


@dataclass(frozen=True)
class Entry:
    """One source bullet and what happens to it. `disposition`: import, skipped or refused; a refused or skipped entry keeps
    no statement."""

    locator: str  # "<file>:<line>"
    disposition: str
    reason: str
    statement: str = ""
    lineage: tuple[str, ...] = ()
    claimed: str = "unavailable"  # the origin the source claims: user, agent or unavailable; never trusted

    def record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class Source:
    """What one reading of the root found: bound into the preview's digest."""

    root: str
    project: str
    mapped: str | None
    files: tuple[SourceFile, ...]
    entries: tuple[Entry, ...]
    gaps: tuple[tuple[str, str], ...]  # (link or file, why it was not read)

    @property
    def digest(self) -> str:
        body = {"root": self.root, "project": self.project, "mapped": self.mapped,
                "files": [dataclasses.asdict(f) for f in self.files], "entries": [e.record() for e in self.entries],
                "gaps": [list(g) for g in self.gaps]}
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Preview:
    id: str
    source: Source
    digest: str
    made: float  # time.monotonic() when made


def _linked(path: Path) -> Path | None:
    """The first existing component of `path` that is a link or reparse point."""
    for candidate in [path, *path.parents]:
        try:
            info = os.lstat(candidate)
        except FileNotFoundError:
            continue
        except OSError:
            return candidate
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            return candidate
    return None


def _target(link: str) -> tuple[str | None, str]:
    """A `[[link]]`'s root-relative file, or why it is not one this import reads."""
    text = link.strip()
    if not text or "\\" in text or ":" in text or text.startswith("/") or any(c in text for c in "\0\r\n"):
        return None, "not a root-relative path"
    if any(part in ("", ".", "..") for part in text.split("/")):
        return None, "a path with empty, `.` or `..` segments"
    name = text.rsplit("/", 1)[-1]
    if "." not in name:
        return text + ".md", ""
    if name.lower().endswith(".md"):
        return text, ""
    return None, "not a Markdown note (only Markdown is imported)"


def _unsafe(line: str) -> bool:
    return any(c in _BIDI or (unicodedata.category(c) == "Cc" and c != "\t") for c in line)


def _metadata(text: str) -> tuple[str, dict[str, str] | None]:
    """A bullet's words and its trailing `[key: value; ...]` metadata; None for metadata that is not well formed."""
    found = _META.search(text)
    if found is None:
        return text, {}
    pairs: dict[str, str] = {}
    for part in found.group(1).split(";"):
        matched = _PAIR.match(part)
        if matched is None or matched.group(1).lower() in pairs:
            return text, None
        pairs[matched.group(1).lower()] = matched.group(2)
    return text[: found.start()], pairs


def _claimed(meta: Mapping[str, str]) -> str:
    words = {meta[key].strip().lower() for key in ("origin", "trust", "author", "authored-by") if key in meta}
    if words & _USER_WORDS:
        return "user"
    if words & _AGENT_WORDS:
        return "agent"
    return "unavailable"


def normalized(statement: str) -> str:
    return " ".join(statement.split()).casefold()


class Reader:
    """One bounded reading of an import root, for one project and mapping."""

    def __init__(self, root: Path, *, project: str, mapped: str | None, sanitize: Callable[[str], str],
                 workspace: Path | None) -> None:
        self._root, self._project, self._mapped = root, project, mapped
        self._sanitize, self._workspace = sanitize, workspace
        self._files: list[SourceFile] = []
        self._gaps: list[tuple[str, str]] = []
        self._entries: list[Entry] = []
        self._extra: list[str] = []  # the text of linked non-Markdown files: B1 sources, never entries
        self._seen: set[tuple[int, int]] = set()
        self._policy: Any = None
        self._total = 0
        self._count = 0

    def read(self) -> Source:
        root = self._root
        if not root.is_absolute():
            raise ImportRefused("IMPORT_ROOT_RELATIVE", "Name the import folder by its absolute path. Nothing was read.")
        linked = _linked(root)
        if linked is not None:
            raise ImportRefused("IMPORT_ROOT_LINKED", f"{linked} is a link or reparse point, so the folder could be redirected. "
                                "Nothing was read.")
        if not root.is_dir():
            raise ImportRefused("IMPORT_ROOT_MISSING", f"{root} is not a folder. Nothing was read.")
        self._real = Path(os.path.realpath(root))
        default = self._default_project()
        queue, queued = [ENTRY_POINT], {ENTRY_POINT}
        notes: list[tuple[str, str]] = []
        while queue:  # first every reachable note and linked file, so each entry is scanned against all of them (B1)
            relative = queue.pop(0)
            text = self._file(relative)
            if text is None:
                if relative == ENTRY_POINT:
                    reason = next((why for name, why in self._gaps if name == ENTRY_POINT), "unreadable")
                    raise ImportRefused("IMPORT_ENTRY_POINT", f"{ENTRY_POINT} cannot be imported: {reason}. Nothing was read.")
                continue
            notes.append((relative, text))
            for link in _LINK.findall(text):
                target, why = _target(link)
                if target is None:
                    self._gap(f"[[{link}]]", why)
                    self._overlap_source(link)
                elif target not in queued:
                    queued.add(target)
                    queue.append(target)
        for relative, text in notes:
            for number, line in enumerate(text.split("\n"), start=1):
                bullet = _BULLET.match(line)
                if bullet is not None and not bullet.group(1).startswith("[["):
                    self._entry(f"{relative}:{number}", line, bullet.group(1), default)
        return Source(str(root), self._project, self._mapped, tuple(self._files), tuple(self._entries), tuple(self._gaps))

    def _gap(self, name: str, why: str) -> None:
        if (name, why) not in self._gaps:
            self._gaps.append((name, why))

    def _default_project(self) -> str | None:
        """An Optimus recovery generation names its project in its manifest; other sources name it per entry."""
        path = self._root / "manifest.json"
        try:
            if _linked(path) is not None or os.stat(path).st_size > MAX_FILE_BYTES:
                return None
            manifest = json.loads(path.read_text(encoding="utf-8"))
            project = manifest["metadata"]["project"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return project if isinstance(project, str) and _REFERENCE.fullmatch(project) else None

    def _open(self, relative: str) -> tuple[bytes | None, str]:
        path = self._root / relative
        if _linked(path) is not None:  # the root and its ancestors were checked first, so any link is inside the folder
            return None, "reached through a link or reparse point"
        try:
            real = Path(os.path.realpath(path))
            spelled = real.relative_to(self._real).as_posix()
        except (OSError, ValueError):
            return None, "outside the folder"
        if spelled != relative:
            return None, "an alias of another path (spelled differently from the file it reaches)"
        try:
            info = os.stat(path, follow_symlinks=False)
        except OSError:
            return None, "missing"
        if not stat.S_ISREG(info.st_mode):
            return None, "not a regular file"
        identity = (info.st_dev, info.st_ino)
        if identity in self._seen:
            return None, ""  # read once already: a cycle or a second link to it
        self._seen.add(identity)
        if info.st_size > MAX_FILE_BYTES:
            return None, "over 1 MiB"
        if self._total + info.st_size > MAX_TOTAL_BYTES:
            return None, "past the 16 MiB total"
        try:
            with open(path, "rb") as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
        except OSError:
            return None, "unreadable"
        if len(data) > MAX_FILE_BYTES:
            return None, "over 1 MiB"
        self._total += len(data)
        return data, ""

    def _file(self, relative: str) -> str | None:
        data, why = self._open(relative)
        if data is None:
            if why:
                self._gap(relative, why)
            return None
        self._files.append(SourceFile(relative, len(data), hashlib.sha256(data).hexdigest()))
        if b"\0" in data:
            self._gap(relative, "binary")
            return None
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            self._gap(relative, "not UTF-8")
            return None
        return text.removeprefix("\ufeff").replace("\r\n", "\n")

    def _overlap_source(self, link: str) -> None:
        """A linked non-Markdown file is never imported, but an entry copying it is source text (B1)."""
        relative = link.strip()
        if not relative or "\\" in relative or ":" in relative or relative.startswith("/") or ".." in relative.split("/"):
            return
        data, _why = self._open(relative)
        if data is not None and b"\0" not in data:
            self._extra.append(data.decode("utf-8", "replace"))

    def _named_files(self, statement: str) -> list[str]:
        """The workspace files a statement names, as the anchor policy lets them be read: B1 sources."""
        from optimus.guardrails.file_policy import FilePolicy, FilePurpose

        found: list[str] = []
        for word in dict.fromkeys(_WORD.findall(statement)):
            relative = word.rstrip(".")
            if self._workspace is None or ("." not in relative and "/" not in relative):
                continue
            if self._policy is None:
                self._policy = FilePolicy(self._workspace)  # one reading of the ignore files for the whole import
            policy = self._policy
            decision, content = policy.read(relative, purpose=FilePurpose.ANCHOR, max_bytes=memory_serving.MAX_HASHED_BYTES)
            if decision.allowed and content is not None:
                found.append(content.decode("utf-8", "replace"))
        return found

    def _entry(self, locator: str, line: str, text: str, default: str | None) -> None:
        def refused(reason: str) -> None:
            self._entries.append(Entry(locator, "refused", reason))

        self._count += 1
        if self._count > MAX_ENTRIES:
            return refused("past the 1,000-entry bound")
        if _unsafe(line):
            return refused("control or bidi characters")
        words, meta = _metadata(text)
        if meta is None:
            return refused("malformed metadata")
        statement = " ".join(words.split())
        if not statement:
            return refused("empty statement")
        if default is not None and statement == _PLACEHOLDER:
            self._entries.append(Entry(locator, "skipped", "an Optimus copy's placeholder for no active items"))
            return None
        if len(statement) > MAX_STATEMENT_CHARS:
            return refused(f"over {MAX_STATEMENT_CHARS} characters (refused whole, never cut)")
        status = meta.get("status", "active").strip().lower()
        if status != "active":
            self._entries.append(Entry(locator, "skipped", f"inactive at the source ({status[:40]})"))
            return None
        project = meta.get("project", default)
        if project is None:
            return refused("no project: unmapped")
        if "," in project or " " in project.strip():
            return refused("more than one project: ambiguous")
        if project not in (self._project, self._mapped):
            return refused("another project's entry")
        if _LINEAGE & meta.keys():
            return refused("lineage the host cannot resolve")
        lineage: list[str] = []
        for key in sorted(_ANCHORS & meta.keys()):
            path, _, claimed_digest = meta[key].strip().partition("@")
            reference = f"{memory_serving.FILE_PREFIX}{path}@{claimed_digest or 'unverified'}"
            if not path or not _REFERENCE.fullmatch(reference):
                return refused("malformed anchor")
            lineage.append(reference)  # serving re-verifies it: only a file still matching the source's digest is current
        claimed = _claimed(meta)
        lineage.append(CLAIM_PREFIX + claimed)
        if "id" in meta and _ITEM_REF.fullmatch(meta["id"].strip()) is None:
            return refused("malformed id")
        if "id" in meta:
            lineage.append("import-of:" + meta["id"].strip())
        sources = self._extra + self._named_files(statement)
        if not scans_pass(title_of(statement), statement, sanitize=self._sanitize, sources=sources):
            return refused("a secret, an instruction to the model, or copied source text (scan)")
        self._entries.append(Entry(locator, "import", "", statement, tuple(lineage), claimed))
        return None


# --- the durable progress log -------------------------------------------------------------------------------------------

class ImportLog:
    """The last apply's progress for one project: `<config>/memory-import/<project>.jsonl`, one line per entry outcome, never a
    statement. Lines are flushed as they happen, so a crash leaves what was recorded; a missing `settled` line is an
    interrupted apply."""

    def __init__(self, config_root: Path, project: str) -> None:
        self._path = config_root / "memory-import" / f"{project}.jsonl"

    def start(self, preview: Preview) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        counts = _counts(preview.source.entries)
        self._write({"apply": preview.id, "digest": preview.digest, "root": preview.source.root, "at_ms": int(time.time() * 1000),
                     "total": len(preview.source.entries), "planned": counts}, mode="w")

    def outcome(self, entry: Entry, outcome: str, **fields: Any) -> None:
        self._write({"locator": entry.locator, "outcome": outcome, **fields})

    def settled(self) -> None:
        self._write({"settled": int(time.time() * 1000)}, fsync=True)

    def _write(self, record: dict[str, Any], *, mode: str = "a", fsync: bool = False) -> None:
        with open(self._path, mode, encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
            handle.flush()
            if fsync:
                os.fsync(handle.fileno())

    def read(self) -> list[dict[str, Any]]:
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except ValueError:
                break  # a line cut by a crash: what follows is not known
        return records


def _counts(entries: Sequence[Entry]) -> dict[str, int]:
    found = {"import": 0, "skipped": 0, "refused": 0}
    for entry in entries:
        found[entry.disposition] += 1
    return found


# --- preview and apply --------------------------------------------------------------------------------------------------

class Importer:
    """One session's imports into its project's store. The newest preview is held in this session's RAM only."""

    def __init__(self, store: Any, log: ImportLog, *, keyed: Callable[[str], str], sanitize: Callable[[str], str],
                 workspace: Path | None, scope: str = "project", trusted: bool = True) -> None:
        self._store, self._log, self._keyed, self._sanitize = store, log, keyed, sanitize
        self._workspace, self._scope, self._trusted = workspace, scope, trusted
        self._preview: Preview | None = None

    def _read(self, root: Path, mapped: str | None) -> Source:
        return Reader(root, project=self._store.project, mapped=mapped, sanitize=self._sanitize, workspace=self._workspace).read()

    def preview(self, root: Path, mapped: str | None) -> Preview:
        if mapped is not None and (mapped == self._store.project or not _REFERENCE.fullmatch(mapped)):
            raise ImportRefused("IMPORT_MAPPING", "Map one other project by its id (`--map <project>`); this project's own "
                                "entries need no mapping. Nothing was read.")
        source = self._read(root, mapped)
        digest = source.digest
        self._preview = Preview("imp-" + secrets.token_hex(6), source, digest, time.monotonic())
        return self._preview

    def held(self, preview_id: str) -> Preview:
        """The preview `preview_id` names, if this session holds it and it is fresh: any other is refused."""
        held = self._preview
        if not _PREVIEW_ID.fullmatch(preview_id) or held is None or held.id != preview_id:
            raise ImportRefused("IMPORT_PREVIEW_UNKNOWN", f"This session holds no import preview `{preview_id[:20]}`. Run "
                                "`/memory import <folder>` here first. Nothing was changed.")
        if time.monotonic() - held.made > PREVIEW_SECONDS:
            self._preview = None
            raise ImportRefused("IMPORT_PREVIEW_STALE", "That preview is over 30 minutes old. Run `/memory import <folder>` "
                                "again. Nothing was changed.")
        return held

    def key(self, source: Source, entry: Entry) -> str:
        """The entry's identity in this project: its mapped source and its words, so a repeat or a resume names the same item."""
        return self._keyed(f"import\0{source.project}\0{source.mapped or source.project}\0{normalized(entry.statement)}")

    def apply(self, preview_id: str, digest: str) -> tuple[dict[str, int], list[tuple[MemoryNotice, str]]]:
        """Apply exactly the preview the user confirmed: one-shot (the preview is consumed first), refused if the source now
        reads differently. Returns the outcome counts and each change's notice."""
        from optimus.context.authored_memory import MemoryStoreRefused, MemoryStoreUnavailable

        preview = self.held(preview_id)
        self._preview = None  # one confirmation, one apply: a replay finds nothing
        if not self._trusted:
            raise ImportRefused("IMPORT_READ_ONLY", "Memory is read-only here: nothing was imported.")
        if digest != preview.digest:
            raise ImportRefused("IMPORT_PREVIEW_CHANGED", "That is not the preview you were shown. Nothing was changed.")
        source = preview.source
        again = self._read(Path(source.root), source.mapped)
        if again.digest != preview.digest:
            raise ImportRefused("IMPORT_SOURCE_CHANGED", "The folder changed since the preview, so nothing was imported. Run "
                                "`/memory import <folder>` again to see what it holds now.")
        counts = {"confirmed": 0, "uncertain": 0, "duplicate": 0, "skipped": 0, "refused": 0, "off": 0}
        notices: list[tuple[MemoryNotice, str]] = []
        self._log.start(preview)
        with self._store.lease() as token:
            renewed = time.monotonic()
            known = self._known()
            for entry in source.entries:
                if entry.disposition != "import":
                    counts[entry.disposition] += 1
                    self._log.outcome(entry, entry.disposition)
                    continue
                if time.monotonic() - renewed > RENEW_SECONDS:
                    self._store.renew(token)
                    renewed = time.monotonic()
                stop = False
                try:
                    outcome, fields, notice = self._one(token, source, entry, known)
                except MemoryStoreUnavailable:
                    outcome, fields, notice, stop = "uncertain", {}, None, True
                except MemoryStoreRefused as refused:
                    outcome, fields, notice = "refused", {"code": refused.code}, None
                    stop = refused.code not in _ITEM_REFUSALS  # the store refuses every write now: the rest stay remaining
                counts[outcome] += 1
                self._log.outcome(entry, outcome, **fields)
                if notice is not None:
                    notices.append((notice, title_of(entry.statement)))
                if stop:
                    counts["remaining"] = len(source.entries) - sum(counts.values())
                    return counts, notices  # unsettled: status says it was interrupted
        self._log.settled()
        return counts, notices

    def _known(self) -> dict[str, str]:
        """Every statement this scope holds or held that an import must not add again: live items' words, off records'
        titles and the earlier words of withdrawn or superseded items. Normalized words -> the item."""
        known: dict[str, str] = {}
        cursor = None
        while True:
            rows, cursor = self._store.items(self._scope, limit=100, cursor=cursor)
            for row in rows:
                event = row.event
                if event.statement:
                    known.setdefault(normalized(event.statement), event.item)
                elif event.trust == "off" and event.title:
                    known.setdefault(normalized(event.title), event.item)
                elif event.status in ("withdrawn", "superseded"):
                    versions, _more = self._store.history(event.item, limit=10)
                    for version in versions:
                        if version.get("statement"):
                            known.setdefault(normalized(version["statement"]), event.item)
            if cursor is None:
                return known

    def _one(self, token: int, source: Source, entry: Entry, known: dict[str, str]
             ) -> tuple[str, dict[str, Any], MemoryNotice | None]:
        words = normalized(entry.statement)
        if words in known:
            return "duplicate", {"item": known[words]}, None
        candidate = MemoryCandidate(source.project, self._scope, TRUST, KIND, "assertion", entry.statement, title_of(entry.statement),
                                    evidence=entry.lineage, idempotency_key=self.key(source, entry))
        verdict = HostVerdict(workspace_trusted=self._trusted, scope_valid=True, spans_verified=True, lineage_complete=True,
                              scans_passed=True)  # scanned when read; the source is re-read and unchanged
        decision = memory_gate.admit(candidate, verdict)
        if decision.outcome != "append" or decision.draft is None or decision.draft.action != "admit":
            return "refused", {"code": decision.reason}, None
        taken = self._store.read(decision.draft.item)
        if taken is not None:  # imported before: live (a repeat) or withdrawn or purged since, which stays so
            known[words] = taken.event.item
            return "duplicate", {"item": taken.event.item, "status": taken.event.status}, None
        result = self._store.append(token, candidate, decision.draft)
        known[words] = result.item
        notice = MemoryNotice.of(result, "admit")
        fields = {"item": result.item, "version": result.version, "event_id": result.event_id}
        return ("confirmed" if notice.saved else "uncertain"), fields, notice

    def status(self) -> str:
        records = self._log.read()
        if not records or "apply" not in records[0]:
            return "No import has been applied in this project yet."
        head = records[0]
        outcomes = [r for r in records[1:] if "outcome" in r]
        settled = any("settled" in r for r in records)
        counts: dict[str, int] = {}
        for record in outcomes:
            counts[record["outcome"]] = counts.get(record["outcome"], 0) + 1
        remaining = head["total"] - len(outcomes)
        when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(head["at_ms"] / 1000))
        words = [f"{counts.get(name, 0)} {label}" for name, label in
                 (("confirmed", "confirmed"), ("duplicate", "already present"), ("skipped", "skipped (inactive at the source)"),
                  ("off", "off"), ("refused", "refused"), ("uncertain", "uncertain (not confirmed on disk)"))]
        text = f"Last import `{head['apply']}` from {head['root']}, {when}: " + ", ".join(words) + f"; {max(remaining, 0)} remaining."
        if not settled:
            text += (" It was interrupted. Run `/memory import <folder>` and apply again: entries already saved are recognised and "
                     "skipped, never saved twice.")
        elif counts.get("uncertain"):
            text += " Apply the same folder again to finish the uncertain ones: a retry never saves anything twice."
        return text


def preview_text(preview: Preview, *, project: str) -> str:
    """What the user is shown before confirming: every file, entry disposition and gap, and the mapping."""
    from optimus.acp.memory_notices import escape_text

    source = preview.source
    counts = _counts(source.entries)
    mapping = (f"entries of project `{source.mapped}` are mapped into this project (`{project}`)" if source.mapped
               else f"only entries of this project (`{project}`) are taken; map one other project with `--map <project>`")
    lines = [f"Import preview `{preview.id}` of {escape_text(source.root, 200)}: {len(source.files)} file(s) read, "
             f"{counts['import']} to import as optional imported context (never as your own items), {counts['skipped']} skipped, "
             f"{counts['refused']} refused. Mapping: {mapping}. Nothing is saved until you run `/memory import apply {preview.id}` "
             "and confirm."]
    for entry in source.entries[:SHOWN]:
        shown = escape_text(title_of(entry.statement), 120) if entry.statement else ""
        what = {"import": "import", "skipped": "skip", "refused": "refuse"}[entry.disposition]
        lines.append(f"- {escape_text(entry.locator, 120)}: {what}" + (f" “{shown}”" if shown else "")
                     + (f" ({entry.reason})" if entry.reason else "")
                     + (f" · claims origin {entry.claimed}, kept as imported" if entry.claimed != "unavailable" else ""))
    if len(source.entries) > SHOWN:
        lines.append(f"- … {len(source.entries) - SHOWN} more entries (counted above)")
    if source.gaps:
        lines.append("Not read (coverage gaps): " + "; ".join(f"{escape_text(name, 80)}: {why}" for name, why in source.gaps[:50])
                     + (f"; and {len(source.gaps) - 50} more" if len(source.gaps) > 50 else ""))
    return "\n".join(lines)

