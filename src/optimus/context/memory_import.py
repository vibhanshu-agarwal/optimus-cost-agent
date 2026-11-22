"""Agent Memory Repo import (Plan 12.12 Task 2): `/memory import <root>`, `... apply <preview-id>` and `... status`.

**Source.** An [Agent Memory Repo](https://cognition.com/agent-memory-repo) is read as data only: `MEMORY.md` at the root, each
entry a one-line bullet with optional `[key: value; ...]` metadata, and `[[path]]` links relative to the root (`.md` omitted for
Markdown). Only Markdown reachable from `MEMORY.md` is read for entries; any other link target is a coverage gap, listed and never
followed. Nothing is executed, fetched, cloned or pushed, and nothing in the source carries authority: the model never sees it.

**Checks.** The root is absolute and reached without links; each file is a regular file inside it, spelled exactly as it resolves
(no `..`, case or short-name aliases, links or reparse points; a sync service's cloud placeholder is a file, not a link), opened
without following links and checked to be the file that was inspected, strict UTF-8 without NUL, at most 1 MiB, 16 MiB in all;
a file is read once by its identity, so link cycles end. At most 1,000 links are followed and 1,000 gaps listed. An entry is
refused whole when it is malformed (bad metadata, empty, or wrapped onto a following line, so a qualification is never cut),
holds control or bidi characters, is over 2,000 characters (never truncated), claims lineage the host cannot resolve, fails the
secret, injection or B1 source-overlap scan, or belongs to no mapped project; entries past the 1,000th are not read, and are
counted. Bullets inside fenced code are not entries. An inactive source entry (`status:` other than active) is skipped with no
statement kept.

**Optimus recovery copies.** A folder whose `manifest.json` names the Optimus copy format is read as one: its manifest, entries and
entry point must pass the host's generation checks (`memory_recovery.checked_generation`), within the same bounds, or every
entry is refused, since what they rest on cannot be established. A bullet's `id` must be in the copy's entries at that version;
its restrictive dependencies there (`file:` pins and a `branch:`) come with it, bound into the preview. The copy's own entries
and manifest are memory records, not source text for the B1 check. At apply, an entry naming an item this project's store holds
is refused unless the store still holds that very version with the same words: an old copy never revives an item deleted,
withdrawn or edited since.

**B1 sources.** An entry is checked for copied text against every linked non-Markdown file in the folder and every workspace file
it names. A linked file that cannot be read (too large, past the total, unreadable) refuses every entry: copying from it cannot
be ruled out. Known limit: text copied from a workspace file the entry does not name is not recognised. On a case-insensitive
file system that keeps the spelling it is given (macOS), a case alias is read under its alias spelling.

**Authority.** Every import is `legacy-import`, kind `fact`: served only in the optional pool, never protected. Metadata that
claims user authorship, approval, a type or a constraint is recorded as an inert claimed origin (`claimed-origin:` lineage), never
honoured. A `file:` anchor keeps the source's digest, so serving holds it for re-verification unless the file still matches.
Nothing updates, retargets or reactivates an existing item.

**Preview and apply.** A preview binds the source: each file's path, size and SHA-256, each entry's locator, exact statement,
disposition and lineage, and the mapping. Apply reads the source again and goes ahead only when that digest is unchanged. Each
entry is then an ordinary Gate decision and fenced durable append under the project's lease, one by one, not a batch: an
entry's id derives from the project, the entry's own source project and its statement, so applying again, with or without a
mapping, or resuming after a crash, writes nothing twice and never revives an item withdrawn or purged since. The preview lists
every entry in full, in pages; apply waits until every page was shown. Its progress is a durable log per project, written only
under the lease, each line stamped with its apply (no statements in it), which `/memory import status` reads: each entry is
logged as dispatched before its append and with its outcome after, and each confirmed commit's notice goes to the project's
durable notice backlog at once, so a host that dies mid-apply loses no notice. An item dispatched without a known outcome stays
unresolved, carried in each later apply's head line until an apply finds it in the store (its notice, from the stored event) or
finds it absent: a resume that itself fails never loses it.
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
from collections.abc import Callable, Collection, Mapping, Sequence
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
PAGE: Final = 50  # entries per preview page, each in full
MAX_LINKS: Final = 1000  # links followed; any more are counted, not followed
MAX_GAPS: Final = 1000  # gaps listed; any more are counted
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
_NOT_MARKDOWN: Final = "not a Markdown note (only Markdown is imported)"
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
    project: str = ""  # the entry's own source project: its identity, whatever the mapping

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
    shown: set[int] = dataclasses.field(default_factory=set)  # pages the user was shown

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.source.entries) // PAGE))

    @property
    def all_shown(self) -> bool:
        return self.shown >= set(range(1, self.pages + 1))


def _linked(path: Path) -> Path | None:
    """The first existing component of `path` that is a link or reparse point (a cloud placeholder is neither)."""
    from optimus.context.memory_backups import _cloud_placeholder

    for candidate in [path, *path.parents]:
        try:
            info = os.lstat(candidate)
        except FileNotFoundError:
            continue
        except OSError:
            return candidate
        if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & _REPARSE_POINT and not _cloud_placeholder(info)):
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
    return None, _NOT_MARKDOWN


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
    words = {meta[key].strip().lower() for key in ("origin", "trust", "author", "authored-by") if key in meta}  # "imported": none
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
        self._gap_set: set[tuple[str, str]] = set()
        self._more_gaps = 0
        self._entries: list[Entry] = []
        self._extra: list[str] = []  # the text of linked non-Markdown files: B1 sources, never entries
        self._sources_lost = False  # a linked file could not be read for the B1 check
        self._read_bytes: dict[str, bytes] = {}
        self._records: set[str] = set()  # an Optimus copy's own entries and manifest: memory records, not B1 sources
        self._generation: dict[str, dict[str, Any]] | None = None  # item -> its entry in a checked Optimus copy
        self._generation_refused: str | None = None
        self._default: str | None = None
        self._seen: set[tuple[int, int]] = set()
        self._policy: Any = None
        self._total = 0
        self._count = 0
        self._links = 0

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
        self._copy()
        default = self._default
        queue, queued = [ENTRY_POINT], {ENTRY_POINT}
        notes: list[tuple[str, list[str | None]]] = []
        skipped_links = 0
        while queue:  # first every reachable note and linked file, so each entry is scanned against all of them (B1)
            relative = queue.pop(0)
            text = self._file(relative)
            if text is None:
                if relative == ENTRY_POINT:
                    reason = next((why for name, why in self._gaps if name == ENTRY_POINT), "unreadable")
                    raise ImportRefused("IMPORT_ENTRY_POINT", f"{ENTRY_POINT} cannot be imported: {reason}. Nothing was read.")
                continue
            lines = _outside_fences(text.split("\n"))
            notes.append((relative, lines))
            for line in lines:
                for link in _LINK.findall(line or ""):
                    if self._links >= MAX_LINKS:
                        skipped_links += 1
                        continue
                    self._links += 1
                    target, why = _target(link)
                    if target is None:
                        self._gap(f"[[{link}]]", why)
                        if why == _NOT_MARKDOWN:
                            self._overlap_source(link)  # a well-formed link to another file: a B1 source
                    elif target not in queued:
                        queued.add(target)
                        queue.append(target)
        for relative, lines in notes:
            for number, line in enumerate(lines, start=1):
                bullet = _BULLET.match(line or "")
                if bullet is not None and not bullet.group(1).startswith("[["):
                    wrapped = number < len(lines) and _continues(lines[number])
                    self._entry(f"{relative}:{number}", line or "", bullet.group(1), default, wrapped=wrapped)
        if skipped_links:
            self._gap("links", f"{skipped_links} more not followed (the {MAX_LINKS:,}-link bound)", always=True)
        if self._count > MAX_ENTRIES:
            self._gap("entries", f"{self._count - MAX_ENTRIES} past the {MAX_ENTRIES:,}-entry bound, not read", always=True)
        if self._more_gaps:
            self._gaps.append(("gaps", f"{self._more_gaps} more not listed (the {MAX_GAPS:,}-gap bound)"))
        return Source(str(root), self._project, self._mapped, tuple(self._files), tuple(self._entries), tuple(self._gaps))

    def _gap(self, name: str, why: str, *, always: bool = False) -> None:
        if (name, why) in self._gap_set:
            return
        if len(self._gaps) >= MAX_GAPS and not always:
            self._more_gaps += 1
            return
        self._gap_set.add((name, why))
        self._gaps.append((name, why))

    def _copy(self) -> None:
        """Whether the folder is an Optimus recovery copy (its manifest names the copy format), read through the same bounded,
        identity-checked opening as every file and bound into the preview. A copy that fails the host's generation checks
        refuses every entry; a checked one names its project and holds each item's restrictive dependencies."""
        from optimus.context import memory_recovery as mr

        if not os.path.lexists(self._root / "manifest.json"):
            return
        manifest, why = self._open("manifest.json")
        if manifest is None:
            self._gap("manifest.json", why or "unreadable")
            return
        self._record("manifest.json", manifest)
        try:
            claimed = json.loads(manifest.decode("utf-8")).get("format")
        except (UnicodeDecodeError, ValueError, AttributeError):
            return
        if claimed != mr.FORMAT:
            return
        files = {name: self._open(name) for name in ("entries.jsonl", ENTRY_POINT)}
        missing = [f"{name}: {why or 'unreadable'}" for name, (data, why) in files.items() if data is None]
        if missing:
            self._generation_refused = "an Optimus recovery copy whose files cannot be read (" + "; ".join(missing) + ")"
            return
        body, entry_point = files["entries.jsonl"][0], files[ENTRY_POINT][0]
        assert body is not None and entry_point is not None
        self._record("entries.jsonl", body)
        try:
            checked, entries = mr.checked_generation(manifest, body, entry_point, self._real.name, None)
        except mr.RecoveryError as failure:
            self._generation_refused = f"an Optimus recovery copy that does not pass its checks ({failure.message})"
            return
        project = checked["metadata"].get("project")
        self._default = project if isinstance(project, str) and _REFERENCE.fullmatch(project) else None
        self._generation = {shaped["entry"]["item"]: shaped["entry"] for shaped in entries if isinstance(shaped["entry"].get("item"), str)}
        self._records |= {"manifest.json", "entries.jsonl"}

    def _record(self, relative: str, data: bytes) -> None:
        if all(f.path != relative for f in self._files):
            self._files.append(SourceFile(relative, len(data), hashlib.sha256(data).hexdigest()))

    def _open(self, relative: str) -> tuple[bytes | None, str]:
        if relative in self._read_bytes:  # read once; the same bytes for every later use
            return self._read_bytes[relative], ""
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
        try:  # opened without following a link, then checked to be the very file inspected above
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as handle:
                opened = os.fstat(handle.fileno())
                if (opened.st_dev, opened.st_ino) != identity or not stat.S_ISREG(opened.st_mode):
                    return None, "changed while it was read"
                data = handle.read(MAX_FILE_BYTES + 1)
        except OSError:
            return None, "unreadable"
        if len(data) > MAX_FILE_BYTES:
            return None, "over 1 MiB"
        self._total += len(data)
        self._read_bytes[relative] = data
        return data, ""

    def _file(self, relative: str) -> str | None:
        data, why = self._open(relative)
        if data is None:
            if why:
                self._gap(relative, why)
            return None
        self._record(relative, data)
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
        if relative in self._records:
            return  # a checked Optimus copy's own entries or manifest: the notes' own record, not raw source
        data, why = self._open(relative)
        if data is not None and b"\0" not in data:
            self._extra.append(data.decode("utf-8", "replace"))
        elif data is None and why not in ("", "missing", "not a regular file"):
            self._sources_lost = True  # it exists but cannot be checked: copying from it cannot be ruled out

    def _named_files(self, statement: str) -> list[str]:
        """The workspace files a statement names, as the anchor policy lets them be read: B1 sources."""
        from optimus.guardrails.file_policy import FilePolicy, FilePurpose

        found: list[str] = []
        for word in dict.fromkeys(_WORD.findall(statement.replace(chr(92), "/"))):  # `src\\app.py` names `src/app.py`
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

    def _entry(self, locator: str, line: str, text: str, default: str | None, *, wrapped: bool = False) -> None:
        def refused(reason: str) -> None:
            self._entries.append(Entry(locator, "refused", reason))

        self._count += 1
        if self._count > MAX_ENTRIES:
            return None  # counted; listed once as a gap
        if wrapped:
            return refused("continues on the next line (a wrapped entry is refused whole, never cut)")
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
        if self._generation_refused is not None:
            return refused(self._generation_refused + ", so what its notes rest on cannot be established")
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
        if self._generation is not None and "id" in meta:
            item, _, version = meta["id"].strip().partition("@")
            recorded = self._generation.get(item)
            if recorded is None or str(recorded.get("version")) != version:
                return refused("its id is not in the copy's entries at that version")
            restrictive = [ref for ref in recorded.get("lineage") or () if isinstance(ref, str)
                           and ref.startswith((memory_serving.FILE_PREFIX, memory_serving.BRANCH_PREFIX)) and _REFERENCE.fullmatch(ref)]
            lineage = restrictive + [ref for ref in lineage if ref not in restrictive]  # its pins and branch come with it
        if self._sources_lost:
            return refused("a linked file could not be read, so copying from it cannot be ruled out (scan)")
        sources = self._extra + self._named_files(statement)
        if not scans_pass(title_of(statement), statement, sanitize=self._sanitize, sources=sources):
            return refused("a secret, an instruction to the model, or copied source text (scan)")
        self._entries.append(Entry(locator, "import", "", statement, tuple(lineage), claimed, project))
        return None


def _outside_fences(lines: list[str]) -> list[str | None]:
    """The lines, with those inside fenced code (``` or ~~~) and the fences themselves as None: never entries or links."""
    kept: list[str | None] = []
    fence: str | None = None
    for line in lines:
        mark = line.lstrip()[:3]
        if fence is None and mark in ("```", "~~~"):
            fence = mark
            kept.append(None)
        elif fence is not None:
            if mark == fence:
                fence = None
            kept.append(None)
        else:
            kept.append(line)
    return kept


def _continues(line: str | None) -> bool:
    """Whether a line after a bullet continues it (Markdown's indented or lazy continuation), rather than starting a new
    bullet, a heading, a fence or a blank line."""
    if line is None or not line.strip():
        return False
    return _BULLET.match(line) is None and not line.lstrip().startswith("#")


# --- the durable progress log -------------------------------------------------------------------------------------------

class ImportLog:
    """The last apply's progress for one project: `<config>/memory-import/<project>.jsonl`, one line per entry outcome, never a
    statement. Lines are flushed as they happen, so a crash leaves what was recorded; a missing `settled` line is an
    interrupted apply."""

    def __init__(self, config_root: Path, project: str) -> None:
        self._path = config_root / "memory-import" / f"{project}.jsonl"

    def start(self, preview: Preview, carried: Collection[str] = ()) -> None:
        """A new apply's head line, replacing the last apply's record: called only under the project's write lease. `carried`:
        the items earlier applies sent without a known outcome, kept here until reconciled (Codex CP2 review 2, finding 1)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        counts = _counts(preview.source.entries)
        self._apply = preview.id
        head = {"apply": preview.id, "digest": preview.digest, "root": preview.source.root, "at_ms": int(time.time() * 1000),
                "total": len(preview.source.entries), "planned": counts, "carried": sorted(carried)}
        # written whole beside the log, then swapped in: the last apply's record stays until the new head is on disk (Codex CP2
        # review 3, finding 2), so a crash or a failed write never loses an unresolved dispatch
        staged = self._path.with_name(f"{self._path.name}.{secrets.token_hex(6)}.tmp")
        try:
            with open(staged, "x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(head, ensure_ascii=True, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged, self._path)
        finally:
            staged.unlink(missing_ok=True)

    def reconciled(self, item: str, *, found: bool) -> None:
        """A carried item settled: found in the store (its notice sent from the stored event) or never written."""
        self._write({"apply": self._apply, "reconciled": item, "found": found})

    def dispatch(self, entry: Entry, item: str) -> None:
        """Before an append: an entry whose dispatch has no outcome line was sent with its result unknown."""
        self._write({"apply": self._apply, "locator": entry.locator, "dispatch": item})

    def outcome(self, entry: Entry, outcome: str, **fields: Any) -> None:
        self._write({"apply": self._apply, "locator": entry.locator, "outcome": outcome, **fields})

    def settled(self) -> None:
        self._write({"apply": self._apply, "settled": int(time.time() * 1000)}, fsync=True)

    def _write(self, record: dict[str, Any], *, fsync: bool = False) -> None:
        with open(self._path, "a", encoding="utf-8", newline="\n") as handle:
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


def _unresolved(records: Sequence[dict[str, Any]]) -> set[str]:
    """The items sent without a known result: carried from earlier applies, or dispatched by the logged apply with no decided
    outcome after it (an `uncertain` outcome, or none: the host stopped in between), less those this apply reconciled."""
    if not records or "apply" not in records[0]:
        return set()
    apply = records[0]["apply"]
    mine = [r for r in records[1:] if r.get("apply") == apply]
    decided = {r["locator"] for r in mine if "outcome" in r and r["outcome"] != "uncertain"}
    sent = {r["dispatch"] for r in mine if "dispatch" in r and r.get("locator") not in decided}
    reconciled = {r["reconciled"] for r in mine if "reconciled" in r}
    return (set(records[0].get("carried") or ()) | sent) - reconciled


def _notice_record(notice: MemoryNotice) -> dict[str, Any]:
    """The notice backlog's record (`optimus.acp.spec._notice_record`), marked as an import's so a replayed card says "Imported"."""
    return {"imported": True, "event_id": notice.event_id, "item": notice.item, "version": notice.version, "action": notice.action,
            "durable_state": notice.durable_state, "projection_state": notice.projection_state}


def _counts(entries: Sequence[Entry]) -> dict[str, int]:
    found = {"import": 0, "skipped": 0, "refused": 0}
    for entry in entries:
        found[entry.disposition] += 1
    return found


# --- preview and apply --------------------------------------------------------------------------------------------------

class Importer:
    """One session's imports into its project's store. The newest preview is held in this session's RAM only."""

    def __init__(self, store: Any, log: ImportLog, *, keyed: Callable[[str], str], sanitize: Callable[[str], str],
                 workspace: Path | None, scope: str = "project", trusted: bool = True, backlog: Any = None) -> None:
        self._store, self._log, self._keyed, self._sanitize = store, log, keyed, sanitize
        self._backlog = backlog  # the project's durable notice backlog (`memory_recovery.NoticeBacklog`), or None
        self._workspace, self._scope, self._trusted = workspace, scope, trusted
        self._preview: Preview | None = None

    def _read(self, root: Path, mapped: str | None) -> Source:
        return Reader(root, project=self._store.project, mapped=mapped, sanitize=self._sanitize, workspace=self._workspace).read()

    def page(self, preview_id: str, number: int) -> str:
        """Page `number` of the preview this session holds, marked shown."""
        held = self.held(preview_id)
        if not 1 <= number <= held.pages:
            raise ImportRefused("IMPORT_PAGE", f"That preview has pages 1 to {held.pages}.")
        return preview_text(held, project=self._store.project, page=number)

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
        """The entry's identity in this project: its own source project and its words, so a repeat, a resume, or the same
        entry imported again with another mapping names the same item (Fable CP2 review 1, finding 1)."""
        return self._keyed(f"import\0{source.project}\0{entry.project}\0{normalized(entry.statement)}")

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
        if not preview.all_shown:
            raise ImportRefused("IMPORT_PREVIEW_UNSEEN", "Not every page of that preview was shown. Nothing was changed.")
        source = preview.source
        again = self._read(Path(source.root), source.mapped)
        if again.digest != preview.digest:
            raise ImportRefused("IMPORT_SOURCE_CHANGED", "The folder changed since the preview, so nothing was imported. Run "
                                "`/memory import <folder>` again to see what it holds now.")
        counts = {"confirmed": 0, "uncertain": 0, "duplicate": 0, "skipped": 0, "refused": 0, "off": 0}
        notices: list[tuple[MemoryNotice, str]] = []

        def stopped(why: str) -> tuple[dict[str, int], list[tuple[MemoryNotice, str]]]:
            counts["remaining"] = len(source.entries) - sum(counts.values())
            counts["stopped"] = why  # type: ignore[assignment]
            return counts, notices  # what was committed keeps its notice; status says the apply was interrupted

        from optimus.context.memory_recovery import RecoveryError

        def kept(notice: MemoryNotice, label: str) -> str | None:
            """The notice, kept durably at once: a host that dies before answering still shows it later."""
            notices.append((notice, label))
            if self._backlog is None or not notice.saved:
                return None
            try:
                self._backlog.add([_notice_record(notice)])
            except (OSError, RecoveryError):
                return "the notice backlog could not be written"
            return None

        with self._store.lease() as token:
            earlier = self._log.read()  # read under the lease, before this apply replaces it
            carried = _unresolved(earlier)
            try:
                self._log.start(preview, carried)  # the unresolved items stay recorded until each is settled
            except OSError:
                return stopped("the progress log could not be written")
            reconciled: set[str] = set()
            try:
                for item in sorted(carried):
                    stored = self._store.read(item)
                    event = stored.event if stored is not None else None
                    if event is not None and (event.version, event.trust, event.status) == (1, TRUST, "active"):
                        why = kept(MemoryNotice(event.event_id, event.item, 1, "admit", "confirmed", "current"), event.title)
                        if why:
                            return stopped(why)
                        reconciled.add(item)
                    self._log.reconciled(item, found=event is not None)
                known = self._known()
            except OSError:
                return stopped("the progress log could not be written")
            except (MemoryStoreUnavailable, MemoryStoreRefused):
                return stopped("the store stopped answering")
            renewed = time.monotonic()  # after the listing, which may take a while
            for entry in source.entries:
                try:
                    if entry.disposition != "import":
                        counts[entry.disposition] += 1
                        self._log.outcome(entry, entry.disposition)
                        continue
                    if time.monotonic() - renewed > RENEW_SECONDS:
                        self._store.renew(token)
                        renewed = time.monotonic()
                except OSError:
                    return stopped("the progress log could not be written")
                except (MemoryStoreUnavailable, MemoryStoreRefused):
                    return stopped("the project's write lease could not be kept")
                stop = None
                try:
                    outcome, fields, notice = self._one(token, source, entry, known, reconciled)
                except OSError:
                    return stopped("the progress log could not be written")  # before the append: nothing was sent
                except MemoryStoreUnavailable:
                    outcome, fields, notice, stop = "uncertain", {}, None, "the store stopped answering"
                except MemoryStoreRefused as refused:
                    outcome, fields, notice = "refused", {"code": refused.code}, None
                    if refused.code not in _ITEM_REFUSALS:  # the store refuses every write now: the rest stay remaining
                        stop = "the store stopped accepting writes"
                counts[outcome] += 1
                if notice is not None:
                    lost = kept(notice, title_of(entry.statement))
                    if lost:  # no terminal outcome: the dispatch stays unresolved, so a later apply rebuilds its notice
                        return stopped(lost)
                try:
                    self._log.outcome(entry, outcome, **fields)
                except OSError:
                    return stopped("the progress log could not be written")
                if stop:
                    return stopped(stop)
            try:
                self._log.settled()
            except OSError:
                return stopped("the progress log could not be written")
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

    def _one(self, token: int, source: Source, entry: Entry, known: dict[str, str], reconciled: Collection[str] = ()
             ) -> tuple[str, dict[str, Any], MemoryNotice | None]:
        words = normalized(entry.statement)
        candidate = MemoryCandidate(source.project, self._scope, TRUST, KIND, "assertion", entry.statement, title_of(entry.statement),
                                    evidence=entry.lineage, idempotency_key=self.key(source, entry))
        verdict = HostVerdict(workspace_trusted=self._trusted, scope_valid=True, spans_verified=True, lineage_complete=True,
                              scans_passed=True)  # scanned when read; the source is re-read and unchanged
        decision = memory_gate.admit(candidate, verdict)
        if decision.outcome != "append" or decision.draft is None or decision.draft.action != "admit":
            return "refused", {"code": decision.reason}, None
        named = next((ref[len("import-of:"):] for ref in entry.lineage if ref.startswith("import-of:")), None)
        if named is not None:  # an entry from a copy naming an item: never older than the store's own state of it
            item, _, version = named.partition("@")
            current = self._store.read(item)
            if current is not None:
                event = current.event
                if (event.version, event.status, normalized(event.statement)) != (int(version), "active", words):
                    return "refused", {"code": "STALE_SOURCE", "item": item, "status": event.status, "version": event.version}, None
                return "duplicate", {"item": item}, None
        if decision.draft.item in reconciled:  # an earlier apply's unheard commit, found and noticed at this apply's start
            return "confirmed", {"item": decision.draft.item, "version": 1, "reconciled": True}, None
        if words in known:
            return "duplicate", {"item": known[words]}, None
        taken = self._store.read(decision.draft.item)
        if taken is not None:  # imported before: live (a repeat) or withdrawn or purged since, which stays so
            known[words] = taken.event.item
            return "duplicate", {"item": taken.event.item, "status": taken.event.status}, None
        if words in known:
            return "duplicate", {"item": known[words]}, None
        self._log.dispatch(entry, decision.draft.item)
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
        mine = [r for r in records[1:] if r.get("apply") == head["apply"]]
        settled = any("settled" in r for r in mine)
        counts: dict[str, int] = {}
        for record in mine:
            if record.get("outcome") not in (None, "uncertain"):
                counts[record["outcome"]] = counts.get(record["outcome"], 0) + 1
        counts["uncertain"] = len(_unresolved(records))  # sent with no known result, this apply's or carried from earlier ones
        remaining = head["total"] - len({r["locator"] for r in mine if "locator" in r})
        when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(head["at_ms"] / 1000))
        words = [f"{counts.get(name, 0)} {label}" for name, label in
                 (("confirmed", "confirmed"), ("duplicate", "already present"), ("skipped", "skipped (inactive at the source)"),
                  ("off", "off"), ("refused", "refused"), ("uncertain", "uncertain (not confirmed on disk)"))]
        from optimus.acp.memory_notices import escape_text

        text = (f"Last import `{head['apply']}` from {escape_text(str(head['root']), 200)}, {when}: " + ", ".join(words)
                + f"; {max(remaining, 0)} remaining.")
        if not settled:
            text += (" It was interrupted. Run `/memory import <folder>` and apply again: entries already saved are recognised and "
                     "skipped, never saved twice.")
        elif counts.get("uncertain"):
            text += " Apply the same folder again to finish the uncertain ones: a retry never saves anything twice."
        return text


def preview_text(preview: Preview, *, project: str, page: int = 1) -> str:
    """One page of what the user is shown before confirming: the counts and mapping, that page's entries in full with their
    dispositions, and (on the first page) the gaps. The page is marked shown."""
    from optimus.acp.memory_notices import escape_text

    source = preview.source
    counts = _counts(source.entries)
    mapping = (f"entries of project `{source.mapped}` are mapped into this project (`{project}`)" if source.mapped
               else f"only entries of this project (`{project}`) are taken; map one other project with `--map <project>`")
    lines = [f"Import preview `{preview.id}` of {escape_text(source.root, 200)}, page {page} of {preview.pages}: "
             f"{len(source.files)} file(s) read, {counts['import']} to import as optional imported context (never as your own "
             f"items), {counts['skipped']} skipped, {counts['refused']} refused. Mapping: {mapping}. Nothing is saved until you "
             f"have seen every page and run `/memory import apply {preview.id}` and confirm."]
    for entry in source.entries[(page - 1) * PAGE:page * PAGE]:
        shown = escape_text(entry.statement, MAX_STATEMENT_CHARS) if entry.statement else ""
        what = {"import": "import", "skipped": "skip", "refused": "refuse"}[entry.disposition]
        lines.append(f"- {escape_text(entry.locator, 120)}: {what}" + (f" “{shown}”" if shown else "")
                     + (f" ({entry.reason})" if entry.reason else "")
                     + (f" · claims origin {entry.claimed}, kept as imported" if entry.claimed != "unavailable" else ""))
    preview.shown.add(page)
    unseen = sorted(set(range(1, preview.pages + 1)) - preview.shown)
    if unseen:
        lines.append(f"Pages not shown yet: {', '.join(map(str, unseen[:20]))}{' …' if len(unseen) > 20 else ''}. See each with "
                     f"`/memory import show {preview.id} <page>`.")
    if source.gaps and page == 1:
        lines.append("Not read (coverage gaps): " + "; ".join(f"{escape_text(name, 80)}: {why}" for name, why in source.gaps[:50])
                     + (f"; and {len(source.gaps) - 50} more" if len(source.gaps) > 50 else ""))
    return "\n".join(lines)

