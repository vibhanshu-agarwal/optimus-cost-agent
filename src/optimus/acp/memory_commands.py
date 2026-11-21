"""Host memory commands (Plan 12.11 v4 D10, ADR-044; design spec v4 §5): `/remember`, `/forget`, `/memory` and `/welcome`.

The user's fresh command is the only authority for a user item (D10). Commands are parsed from the user's own prompt text
before admission, classification or any model call, never from model, tool or document text, and they call no model. A
malformed command gets its usage text. Every change still goes through the Gate and the store's one fenced append, and what the
user is told comes from the store's commit result (`MemoryNotice`), so only an fsync-confirmed change says Remembered, Updated
or Forgotten.

A change to an existing item names the version it means (`<id>@<version>`, as `/memory` shows it), and is rechecked under the
project's lease: a stale version changes nothing, so a command never lands on a version its user did not see. Switch-on turns an
off record into a new item only from the exact source block this session still holds, unchanged and one whole sentence; it
never executes an update or a withdrawal a model proposed. Purge also needs a fresh one-shot confirmation the server asks for
(`session/request_permission`); this module prepares it and checks its binding.

D9's automatic-extraction boundary is unchanged: nothing here turns automatic user admission back on.

`/remember --branch <name>` limits an item to one branch. An item also rests on the workspace files its statement names, as they
were when it was saved. Both are host conditions in the item's lineage (`memory_serving`): an item is served only on its branch,
and an item whose file changed is not served until the user edits it.
"""

from __future__ import annotations

import dataclasses
import re
import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from context_engine import memory_gate
from context_engine.memory_contracts import (
    ADMITTING_ACTS,
    MAX_STATEMENT_CHARS,
    USER_KINDS,
    HostVerdict,
    MemoryCandidate,
    MemoryNotice,
    Span,
)
from context_engine.memory_projection import ItemState
from optimus.acp.memory_notices import escape_text, headline
from optimus.context import memory_serving
from optimus.context.memory_extraction import digest, scans_pass, sentence_bounds, title_of
from optimus.context.memory_workspace import current_branch
from optimus_security import memory_store_contract as msc

COMMANDS: Final = ("remember", "forget", "memory", "welcome")
DESCRIPTIONS: Final = {
    "remember": ("Save a rule or fact to this project's memory", "[--branch <name>] <statement>"),
    "forget": ("Withdraw a memory item (history is kept); --purge deletes its text", "<id>@<version> [--purge]"),
    "memory": ("List memory, or view, edit, switch on or forget one item; export or restore the recovery copy",
               "[view <id> | edit <id>@<version> <statement> | switch-on <id>@<version> | forget <id>@<version> | page <n> | "
               "export | restore [<generation>] | backup [configure <folder> [--cloud] | now | disable] | "
               "import <folder> [--map <project>] | import apply <preview> | import status]"),
    "welcome": ("Show the welcome-back brief for this project", ""),
}
PAGE_ITEMS: Final = 20
HISTORY_PAGE: Final = 10
PURGE_OPTION: Final = "memory-purge"
PURGE_CANCEL: Final = "memory-purge-cancel"
USAGE: Final = (
    "Memory commands:\n"
    "- `/remember <statement>` saves a rule or fact for this project; `/remember --branch <name> <statement>` saves one that "
    "applies only on that branch.\n"
    "- `/forget <id>@<version>` withdraws an item; its history is kept. Add `--purge` to delete its text, after you confirm.\n"
    "- `/memory` lists memory (`/memory page <n>` for more); `/memory view <id>` shows an item's history.\n"
    "- `/memory edit <id>@<version> <statement>` replaces one of your items.\n"
    "- `/memory switch-on <id>@<version>` saves an off item from your exact words, while this session still holds them.\n"
    "- `/welcome` shows the welcome-back brief.\n"
    "- `/memory export` saves the recovery copy now (the first time, you confirm where); `/memory restore` lists the copies and "
    "`/memory restore <generation>` restores one into an empty store; `/memory restore <generation> --map` restores an earlier "
    "registration's copy into this project, after you confirm.\n"
    "- `/memory import <folder>` previews an Agent Memory Repo's entries as optional imported context (`--map <project>` "
    "takes one other project's entries); `/memory import show <preview> <page>` shows each page; "
    "`/memory import apply <preview>` saves them after you confirm; "
    "`/memory import status` shows the last import.\n"
    "- `/memory backup` shows backups; `/memory backup configure <folder>` copies the recovery copy there daily (another drive; add `--cloud` for a synced folder), after you confirm; `/memory backup now` takes one now; `/memory backup disable` stops them.\n"
    "A change names the version you saw in `/memory`, for example `m-0123456789abcdef@2`."
)
NEEDS_VERSION: Final = "Name the version you mean, as `/memory` shows it: for example `{verb} {item}@2`. Nothing was changed."
READ_ONLY: Final = "Memory is read-only here: this workspace is not registered and trusted, so nothing can be saved or changed."
UNAVAILABLE: Final = ("The memory store did not answer, so this is not confirmed: it may or may not have been changed. `/memory` "
                      "shows what is stored, and running the same command again never makes a second change.")
_ITEM: Final = re.compile(r"m-[0-9a-f]{16}")  # the route's item id
_REF: Final = re.compile(r"(m-[0-9a-f]{16})@([1-9][0-9]{0,9})")
_GENERATION: Final = re.compile(r"gen-[0-9]{1,16}-[0-9a-f]{12}")
_COMMAND_KEY: Final = "command"  # command keys are their own family: never an automatic candidate's item


@dataclass(frozen=True)
class MemoryCommand:
    verb: str  # remember, forget, purge, list, view, edit, switch_on, welcome
    item: str | None = None
    version: int | None = None  # the version the user named; every change to an existing item has one
    statement: str | None = None
    start: int = 0  # where the statement starts in the prompt text, for its span
    page: int = 1
    before: int | None = None
    generation: str | None = None
    branch: str | None = None  # remember: the one branch the item applies on
    mapped: bool = False  # restore: an earlier registration's copy, mapped into this project once the user confirms
    target: str | None = None  # backup configure: the folder, exactly as typed
    cloud: bool = False  # backup configure: the user declares the folder synced
    encrypted: bool = False  # backup configure: an encrypted backup was asked for (unavailable)
    preview: str | None = None  # import apply: the preview id
    source: str | None = None  # import: the one other project whose entries are mapped into this one


@dataclass(frozen=True)
class Confirmation:
    """A recovery action waiting for the user's one-shot confirmation, bound to what it was shown and a host nonce."""

    kind: str  # "location" (where copies go, and sync consent), "restore" (one generation), "backup" (a backup folder) or
    # "import" (one preview, bound to its digest)
    title: str
    text: str
    meta: dict[str, Any]
    nonce: str

    @property
    def option(self) -> str:
        return f"memory-{self.kind}:{self.nonce}"


@dataclass(frozen=True)
class PurgeRequest:
    """One purge waiting for the user's confirmation: bound to the item, the version named and a host nonce."""

    item: str
    version: int
    title: str
    nonce: str

    @property
    def option(self) -> str:
        return f"{PURGE_OPTION}:{self.nonce}"


@dataclass(frozen=True)
class MemoryAnswer:
    text: str
    notices: tuple[tuple[MemoryNotice, str], ...] = ()  # each confirmed or uncertain change and its label
    purge: PurgeRequest | None = None  # ask the user before anything is destroyed
    confirm: Confirmation | None = None  # ask the user before a recovery location is set or a generation restored


def _one_line(statement: str) -> bool:
    """A statement is one line the store can keep whole: never clipped, since its condition may be at the end."""
    return 0 < len(statement) <= MAX_STATEMENT_CHARS and not any(ord(c) < 32 and c != "\t" for c in statement)


def _ref(word: str) -> tuple[str, int] | None:
    match = _REF.fullmatch(word)
    if match is None or int(match.group(2)) > msc.MAX_VERSION:
        return None
    return match.group(1), int(match.group(2))


def _versioned(verb: str, shown: str, word: str, **fields: Any) -> MemoryCommand | str:
    ref = _ref(word)
    if ref is not None:
        return MemoryCommand(verb, item=ref[0], version=ref[1], **fields)
    if _ITEM.fullmatch(word):
        return NEEDS_VERSION.format(verb=shown, item=word)
    return USAGE


def _statement_after(text: str, head: int) -> tuple[str, int] | None:
    statement = text[head:].strip()
    if not _one_line(statement):
        return None
    return statement, text.index(statement, head)


def parse_command(text: str, *, attachments: bool) -> MemoryCommand | str | None:
    """None: not a memory command (an ordinary prompt). A `MemoryCommand`, or the usage text for a malformed one."""
    stripped = text.lstrip()
    words = stripped.split()
    if not words or words[0] not in {f"/{name}" for name in COMMANDS}:
        return None
    if attachments:
        return USAGE
    verb, rest = words[0][1:], words[1:]
    lead = len(text) - len(stripped) + len(words[0])
    if verb == "remember":
        branch = None
        if rest and rest[0] == "--branch":
            if len(rest) < 3 or memory_serving.branch_ref(rest[1]) is None:
                return USAGE
            branch = rest[1]
            lead = text.index(branch, text.index("--branch", lead) + len("--branch")) + len(branch)
        said = _statement_after(text, lead)
        return USAGE if said is None else MemoryCommand("remember", statement=said[0], start=said[1], branch=branch)
    if verb == "welcome":
        return MemoryCommand("welcome") if not rest else USAGE
    if verb == "forget":
        if len(rest) == 1:
            return _versioned("forget", "/forget", rest[0])
        if len(rest) == 2 and rest[1] == "--purge":
            return _versioned("purge", "/forget", rest[0])
        return USAGE
    if not rest:
        return MemoryCommand("list")
    if rest == ["export"]:
        return MemoryCommand("export")
    if rest[0] == "backup":
        return _backup_command(text, rest[1:])
    if rest[0] == "import":
        return _import_command(text, rest[1:])
    if rest[0] == "restore" and len(rest) <= 3:
        if len(rest) == 1:
            return MemoryCommand("restore")
        if not _GENERATION.fullmatch(rest[1]) or (len(rest) == 3 and rest[2] != "--map"):
            return USAGE
        return MemoryCommand("restore", generation=rest[1], mapped=len(rest) == 3)
    if rest[0] == "page" and len(rest) == 2 and rest[1].isdigit() and 1 <= int(rest[1]) <= 1000:
        return MemoryCommand("list", page=int(rest[1]))
    if rest[0] == "view" and len(rest) in (2, 4):
        item = rest[1] if _ITEM.fullmatch(rest[1]) else (_ref(rest[1]) or (None, 0))[0]
        if item is None:
            return USAGE
        if len(rest) == 2:
            return MemoryCommand("view", item=item)
        if rest[2] == "older" and rest[3].isdigit() and 2 <= int(rest[3]) <= msc.MAX_VERSION:
            return MemoryCommand("view", item=item, before=int(rest[3]))
        return USAGE
    if rest[0] == "forget" and len(rest) == 2:
        return _versioned("forget", "/memory forget", rest[1])
    if rest[0] == "switch-on" and len(rest) == 2:
        return _versioned("switch_on", "/memory switch-on", rest[1])
    if rest[0] == "edit" and len(rest) >= 3:
        said = _statement_after(text, text.index(rest[1], text.index("edit", lead)) + len(rest[1]))
        return USAGE if said is None else _versioned("edit", "/memory edit", rest[1], statement=said[0], start=said[1])
    return USAGE


def _backup_command(text: str, rest: list[str]) -> MemoryCommand | str:
    """`/memory backup`, `... now`, `... disable`, or `... configure <folder> [--cloud] [--encrypted]` (the folder as typed,
    spaces kept)."""
    if not rest:
        return MemoryCommand("backup_status")
    if rest in (["now"], ["disable"]):
        return MemoryCommand(f"backup_{rest[0]}")
    if rest[0] != "configure" or len(rest) < 2:
        return USAGE
    flags = set()
    words = list(rest[1:])
    while words and words[-1] in ("--cloud", "--encrypted"):
        flags.add(words.pop())
    if not words:
        return USAGE
    head = text.index("configure", text.index("backup")) + len("configure")
    folder = text[head:].strip()
    while folder.endswith(("--cloud", "--encrypted")):
        folder = folder.removesuffix("--cloud").removesuffix("--encrypted").strip()
    folder = folder.strip()
    if not folder or "\n" in folder:
        return USAGE
    return MemoryCommand("backup_configure", target=folder, cloud="--cloud" in flags, encrypted="--encrypted" in flags)


def _import_command(text: str, rest: list[str]) -> MemoryCommand | str:
    """`/memory import status`, `... apply <preview>`, or `... <absolute folder> [--map <project>]` (the folder as typed)."""
    if rest == ["status"]:
        return MemoryCommand("import_status")
    if len(rest) == 2 and rest[0] == "apply":
        return MemoryCommand("import_apply", preview=rest[1])
    if len(rest) == 3 and rest[0] == "show" and rest[2].isdigit() and 1 <= int(rest[2]) <= 100:
        return MemoryCommand("import_show", preview=rest[1], page=int(rest[2]))
    if not rest or rest[0] in ("apply", "show", "status"):  # a malformed sub-command is never read as a folder
        return USAGE
    folder = text[text.index("import", text.index("/memory")) + len("import"):].strip()
    mapped = None
    if len(rest) >= 3 and rest[-2] == "--map":
        mapped = rest[-1]
        folder = folder[: folder.rindex("--map")].strip()
    if not folder or "\n" in folder or "--map" in folder.split():
        return USAGE
    return MemoryCommand("import", target=folder, source=mapped)


def _state(stored: Any) -> ItemState | None:
    if stored is None:
        return None
    event = stored.event
    return ItemState(event.project, event.item, event.version, event.trust, event.status, event.kind, event.title, event.statement,
                     event.scope, event.anchors, event.lineage, event.valid_from_ms, event.valid_until_ms)


@dataclass(frozen=True)
class Locator:
    """What an off record says about its source (D10), parsed from its payload-free references."""

    origin: str | None
    act: str | None
    target: str | None
    spans: tuple[tuple[str, int, int], ...]
    digests: dict[str, str]

    @classmethod
    def of(cls, state: ItemState) -> Locator:
        tags = dict(reference.split(":", 1) for reference in state.lineage if ":" in reference)
        digests = {}
        for reference in state.lineage:
            if reference.startswith("src:"):
                block, _, value = reference[4:].rpartition("@")
                digests[block] = value
        spans = []
        for anchor in state.anchors:
            block, _, bounds = anchor.rpartition(":")
            start, _, end = bounds.partition("-")
            if block and start.isdigit() and end.isdigit():
                spans.append((block, int(start), int(end)))
        return cls(tags.get("origin"), tags.get("act"), tags.get("target"), tuple(spans), digests)


_STATUS_WORDS: Final = {"active": "active", "reverify": "needs re-verification", "conflicted": "conflicted",
                        "superseded": "superseded", "withdrawn": "forgotten (history kept)", "purged": "deleted"}
_ORIGIN_WORDS: Final = {"user-authored": "yours", "agent-derived": "agent lesson", "legacy-import": "imported", "off": "off (not used)"}


class MemoryCommands:
    """One session's memory commands against its project's store. Synchronous: the server runs it on a thread of its own.

    `store` is the session's `GatewayMemoryStore`; `trusted` says whether the host registered and trusts the workspace;
    `sanitize` is the session's persistence sanitizer, so a statement it would change (something secret-shaped) is refused.
    `source` and `source_digest` are the session extractor's RAM copy of its raw user blocks, for switch-on."""

    def __init__(self, store: Any, *, trusted: bool, sanitize: Callable[[str], str], keyed: Callable[[str], str] = digest,
                 scope: str = "project", source: Callable[[str], str | None] = lambda _block: None,
                 source_digest: Callable[[str], str] | None = None, recovery: Any = None, workspace: Path | None = None,
                 brief: Callable[[memory_serving.ServedSet], str] | None = None, registry_recovery: Any = None,
                 backups: Any = None, imports: Any = None, backlog: Any = None) -> None:
        self._store, self._trusted, self._sanitize, self._keyed = store, trusted, sanitize, keyed
        self._scope = scope
        self._source = source
        self._source_digest = source_digest
        self._recovery = recovery  # the project's `memory_recovery.Recovery`, or None
        self._workspace = workspace  # the session's trusted worktree, where a first recovery location goes
        self._brief = brief
        self._registry_recovery = registry_recovery  # set when the project registry is lost: only its repair is available
        self._backups = backups  # the project's `memory_backups.Backups`, or None
        self._importer: Any = None
        if imports is not None and store is not None:  # the project's `memory_import.ImportLog`
            from optimus.context.memory_import import Importer

            self._importer = Importer(store, imports, keyed=keyed, sanitize=sanitize, workspace=workspace, scope=scope,
                                      trusted=trusted, backlog=backlog)

    @property
    def project(self) -> str:
        return str(self._store.project)

    @property
    def store(self) -> Any:
        return self._store

    @property
    def sanitize(self) -> Callable[[str], str]:
        """The sanitizer statements are saved under, so serving shows them as they were saved."""
        return self._sanitize

    def served(self) -> memory_serving.ServedSet:
        """What a turn is served now: the project's servable items whose conditions hold in this workspace on its current
        branch. A store error raises."""
        branch = current_branch(self._workspace) if self._workspace is not None else None
        return memory_serving.from_store(self._store, self._scope, root=self._workspace, branch=branch)

    def _conditions(self, lineage: Sequence[str], *, live: bool) -> str:
        """How `/memory` shows an item's host conditions: its branch, and a pinned file that changed."""
        words = []
        branch = memory_serving.branch_of(lineage)
        if branch is not None:
            words.append(f"only on branch `{branch}`")  # a host reference: no backtick or markup can occur
        changed = memory_serving.changed_file(lineage, self._workspace) if live else None
        if changed is not None:
            words.append(f"needs re-verification: `{changed}` changed since it was saved; "
                         "`/memory edit` saves it again")
        return "".join(f" · {word}" for word in words)

    def label(self, item: str) -> str:
        """An item's title for its card, from the store; empty when it cannot be read (the card still names the item)."""
        from optimus.context.authored_memory import MemoryStoreRefused, MemoryStoreUnavailable

        try:
            stored = self._store.read(item)
        except (MemoryStoreUnavailable, MemoryStoreRefused):
            return ""
        return "" if stored is None else str(stored.event.title)

    # --- dispatch ------------------------------------------------------------------------------------------------------

    def run(self, command: MemoryCommand, *, block: str) -> MemoryAnswer:
        """The answer to one command; never raises for a store state. `block` is the host id of the prompt's raw text."""
        from optimus.context.authored_memory import MemoryStoreRefused, MemoryStoreUnavailable

        if self._registry_recovery is not None:
            return self._registry_command(command)
        try:
            if command.verb == "list":
                return MemoryAnswer(self._list(command.page))
            if command.verb == "view":
                assert command.item is not None
                return MemoryAnswer(self._view(command.item, command.before))
            if command.verb == "welcome":
                return MemoryAnswer(self._brief(self.served()) if self._brief is not None
                                    else "No welcome-back brief is available for this project yet.")
            if command.verb in ("export", "restore"):
                return self._recovery_command(command)
            if command.verb.startswith("backup"):
                return self._backup_command(command)
            if command.verb.startswith("import"):
                return self._import_command(command)
            if not self._trusted:
                return MemoryAnswer(READ_ONLY)
            if command.verb == "remember":
                assert command.statement is not None
                return self._remember(command.statement, Span(block, command.start, command.start + len(command.statement)),
                                      command.branch)
            assert command.item is not None and command.version is not None
            if command.verb == "forget":
                return self._forget(command.item, command.version)
            if command.verb == "edit":
                assert command.statement is not None
                return self._edit(command.item, command.version, command.statement,
                                  Span(block, command.start, command.start + len(command.statement)))
            if command.verb == "switch_on":
                return self._switch_on(command.item, command.version)
            if command.verb == "purge":
                return self._prepare_purge(command.item, command.version)
        except MemoryStoreUnavailable:
            return MemoryAnswer(UNAVAILABLE)
        except MemoryStoreRefused as refused:
            return MemoryAnswer(_refused(refused.code))
        raise AssertionError(f"unhandled memory command {command.verb}")

    # --- changes -------------------------------------------------------------------------------------------------------

    def _verdict(self, title: str, statement: str) -> HostVerdict:
        return HostVerdict(workspace_trusted=self._trusted, scope_valid=True, spans_verified=True, lineage_complete=True,
                           scans_passed=scans_pass(title, statement, sanitize=self._sanitize, sources=()))

    def _lineage(self, statement: str, branch: str | None) -> tuple[str, ...]:
        limited = memory_serving.branch_ref(branch) if branch is not None else None
        return ((limited,) if limited else ()) + memory_serving.file_refs(statement, self._workspace)

    def _remember(self, statement: str, span: Span, branch: str | None = None) -> MemoryAnswer:
        title = title_of(statement)
        lineage = self._lineage(statement, branch)
        key = self._keyed(f"{_COMMAND_KEY}\0remember\0{self.project}\0{self._scope}\0{statement}"
                          + (f"\0{chr(0).join(lineage)}" if lineage else ""))
        candidate = MemoryCandidate(self.project, self._scope, "user-authored", "fact", "assertion", statement, title, spans=(span,),
                                    evidence=lineage, idempotency_key=key)
        verdict = self._verdict(title, statement)
        if not verdict.scans_passed:
            return MemoryAnswer(_SCAN_REFUSED)
        with self._store.lease() as token:
            return self._admit_new(token, candidate, verdict, title)

    def _admit_new(self, token: int, candidate: MemoryCandidate, verdict: HostVerdict, title: str) -> MemoryAnswer:
        """Admit a new item. Its id is derived from its key, so the same words again replay the first save; an id held by a
        withdrawn or purged item walks to the next free one along its chain."""
        decision = memory_gate.admit(candidate, verdict)
        while decision.outcome == "append" and decision.draft is not None:
            taken = self._store.read(decision.draft.item)
            if taken is None or taken.event.status in ("active", "reverify", "conflicted"):
                break
            candidate = dataclasses.replace(candidate, idempotency_key=self._keyed(f"{candidate.idempotency_key}\0{taken.event.version}"))
            decision = memory_gate.admit(candidate, verdict)
        return self._appended(token, candidate, decision, title)

    def _named(self, item: str, version: int) -> tuple[ItemState | None, str | None]:
        """The item at exactly the version the user named, or why not: nothing is ever retargeted to a newer version."""
        target = _state(self._store.read(item))
        if target is None:
            return None, f"No memory item `{item}` in this project."
        if target.version != version:
            return None, (f"`{item}` is at version {target.version} now, not {version}, so nothing was changed. Look at it with "
                          f"`/memory view {item}` and name the version you mean.")
        return target, None

    def _edit(self, item: str, version: int, statement: str, span: Span) -> MemoryAnswer:
        title = title_of(statement)
        with self._store.lease() as token:
            target, why = self._named(item, version)
            if target is None:
                return MemoryAnswer(why or "")
            if target.trust != "user-authored":
                # an edit never promotes an agent lesson or an off record to the user's own item
                return MemoryAnswer(f"`{item}` is not one of your items, so it cannot be edited. Forget it with "
                                    f"`/forget {item}@{version}` and save your own with `/remember`.")
            if not target.live:
                return MemoryAnswer(f"`{item}` is {_STATUS_WORDS[target.status]}, so it cannot be edited.")
            key = self._keyed(f"{_COMMAND_KEY}\0edit\0{self.project}\0{item}\0{version}\0{statement}")
            # an edit keeps the item's branch and pins the files the new words name, as they are now
            lineage = self._lineage(statement, memory_serving.branch_of(target.lineage))
            candidate = MemoryCandidate(self.project, target.scope, "user-authored", target.kind, "assertion", statement, title,
                                        spans=(span,), evidence=lineage, target=item, idempotency_key=key)
            verdict = self._verdict(title, statement)
            if not verdict.scans_passed:
                return MemoryAnswer(_SCAN_REFUSED)
            return self._appended(token, candidate, memory_gate.admit(candidate, verdict, target), title)

    def _withdraw(self, token: int, target: ItemState, label: str) -> MemoryAnswer:
        key = self._keyed(f"{_COMMAND_KEY}\0forget\0{self.project}\0{target.item}\0{target.version}")
        candidate = MemoryCandidate(self.project, target.scope, "user-authored", "fact", "retraction", "", "", target=target.item,
                                    idempotency_key=key)
        verdict = HostVerdict(workspace_trusted=self._trusted, scope_valid=True, spans_verified=True, lineage_complete=True,
                              scans_passed=True)  # nothing is persisted from the command's words
        return self._appended(token, candidate, memory_gate.admit(candidate, verdict, target), label)

    def _forget(self, item: str, version: int) -> MemoryAnswer:
        with self._store.lease() as token:
            target, why = self._named(item, version)
            if target is None:
                return MemoryAnswer(why or "")
            if not target.live:
                return MemoryAnswer(f"`{item}` is already {_STATUS_WORDS[target.status]}.")
            return self._withdraw(token, target, target.title)

    def _switch_on(self, item: str, version: int) -> MemoryAnswer:
        """An off record becomes a new item of the user's own, only from its exact source block, which this session must still
        hold unchanged, and only when that block is one whole sentence the record proposed as a rule. It never executes an
        update or a withdrawal: those need `/memory edit` or `/forget`. The off record is then withdrawn."""
        with self._store.lease() as token:
            target, why = self._named(item, version)
            if target is None:
                return MemoryAnswer(why or "")
            if target.trust != "off" or not target.live:
                return MemoryAnswer(f"`{item}` is not an item that is off, so there is nothing to switch on.")
            locator = Locator.of(target)
            said, refusal = self._exact_source(locator)
            if said is None:
                return MemoryAnswer(f"`{item}` cannot be switched on: {refusal} Nothing was changed. To save it, use "
                                    "`/remember` with your exact words.")
            block, text, start = said
            kind = target.kind if target.kind in USER_KINDS else "fact"
            key = self._keyed(f"{_COMMAND_KEY}\0switch-on\0{self.project}\0{item}\0{version}\0{text}")
            title = title_of(text)
            candidate = MemoryCandidate(self.project, target.scope, "user-authored", kind, "assertion", text, title,
                                        spans=(Span(block, start, start + len(text)),), idempotency_key=key)
            verdict = self._verdict(title, text)
            if not verdict.scans_passed:
                return MemoryAnswer(_SCAN_REFUSED)
            saved = self._admit_new(token, candidate, verdict, title)
            if not saved.notices or not saved.notices[0][0].saved:
                return saved
            retired = self._withdraw(token, target, "")
            if retired.notices and retired.notices[0][0].saved:
                return MemoryAnswer(saved.text + f" The off record `{item}` is retired.", saved.notices)
            return MemoryAnswer(saved.text + f" The off record `{item}` could not be retired yet; it stays listed as off.", saved.notices)

    def _exact_source(self, locator: Locator) -> tuple[tuple[str, str, int] | None, str]:
        """The one source sentence an off record points at, recovered mechanically, or why it cannot be."""
        if locator.origin != "user-authored":
            return None, "it was not proposed from your words (an agent lesson that went off stays off)."
        if locator.act not in ADMITTING_ACTS or locator.target is not None:
            return None, "it was proposed as a change to another item or as a withdrawal, which switch-on never executes."
        blocks = {block for block, _start, _end in locator.spans}
        if len(blocks) != 1:
            return None, "its source is not one message of yours."
        block = next(iter(blocks))
        text = self._source(block)
        if text is None or self._source_digest is None:
            return None, "its source is no longer held by this session."
        if locator.digests.get(block) != self._source_digest(text):
            return None, "its source has changed."
        sentences = [(start, end) for start, end in sentence_bounds(text) if text[start:end].strip()]
        if len(sentences) != 1:
            return None, "its source holds more than one sentence, so the exact rule cannot be told apart mechanically."
        start, end = sentences[0]
        whole = text[start:end].strip()
        if not _one_line(whole) or any(not (start <= s and e <= end) for _b, s, e in locator.spans):
            return None, "its source is not one whole line."
        return (block, whole, text.index(whole, start)), ""

    def _appended(self, token: int, candidate: MemoryCandidate, decision: memory_gate.GateDecision, label: str) -> MemoryAnswer:
        from optimus.context.authored_memory import MemoryStoreRefused

        if decision.outcome != "append" or decision.draft is None or decision.draft.action == "off":
            return MemoryAnswer(f"Nothing was changed ({decision.reason}).")
        try:
            result = self._store.append(token, candidate, decision.draft)
        except MemoryStoreRefused as refused:
            return MemoryAnswer(_refused(refused.code))
        notice = MemoryNotice.of(result, decision.draft.action)
        return MemoryAnswer(_said(notice, label), ((notice, label),))

    # --- purge ---------------------------------------------------------------------------------------------------------

    def _prepare_purge(self, item: str, version: int) -> MemoryAnswer:
        target, why = self._named(item, version)
        if target is None:
            return MemoryAnswer(why or "")
        if target.status == "purged":
            return self._purge_report(item, self._store.purge_status(item))
        title = target.title or self._earlier_title(item)
        return MemoryAnswer("", purge=PurgeRequest(item, version, title, secrets.token_hex(16)))

    def purge(self, request: PurgeRequest) -> MemoryAnswer:
        """After the user chose Purge for exactly `request`: recheck the version confirmed, withdraw a live item first (its
        exclusion never waits on the deletion), then purge. A change since the question needs a fresh confirmation."""
        from optimus.context.authored_memory import MemoryStoreRefused, MemoryStoreUnavailable

        notices: list[tuple[MemoryNotice, str]] = []
        try:
            with self._store.lease() as token:
                target = _state(self._store.read(request.item))
                if target is None or target.version != request.version:
                    return MemoryAnswer(f"`{request.item}` changed after you were asked, so nothing was deleted. Run "
                                        f"`/forget {request.item}@<version> --purge` again with its current version.")
                if target.live:
                    withdrawn = self._withdraw(token, target, request.title)
                    if not withdrawn.notices or not withdrawn.notices[0][0].saved:
                        return MemoryAnswer(withdrawn.text + " Nothing was deleted.", withdrawn.notices)
                    notices += withdrawn.notices
                if self._recovery is not None:
                    self._recovery.purging(request.item)  # durable before dispatch: a lost journal then still blocks a restore
                try:
                    reply = self._store.purge(token, request.item, self._keyed(f"{_COMMAND_KEY}\0purge\0{self.project}\0{request.item}"))
                except MemoryStoreRefused:
                    if self._recovery is not None:
                        self._recovery.purge_refused(request.item)  # answered no: nothing was purged
                    raise
        except MemoryStoreUnavailable:
            return MemoryAnswer(UNAVAILABLE, tuple(notices))
        except MemoryStoreRefused as refused:
            return MemoryAnswer(_refused(refused.code), tuple(notices))
        notice = MemoryNotice(reply["event_id"], reply["item"], reply["version"], "tombstone", reply["durable_state"],
                              reply["projection_state"])
        notices.append((notice, request.title))
        return MemoryAnswer(self._purge_report(request.item, reply).text, tuple(notices))

    def _purge_report(self, item: str, reply: dict[str, Any]) -> MemoryAnswer:
        state = reply.get("purge_state")
        if reply.get("durable_state") == "unconfirmed":
            return MemoryAnswer(f"Deletion of `{item}` is not confirmed on disk yet; it is excluded from use. Run the same purge "
                                "again to finish it.")
        if state == "completed-within-declared-boundary":
            return MemoryAnswer(f"Deleted `{item}`: its text is gone from the memory store and its disk files. Copies outside "
                                "the store (synced folders, recycle bins, other copies) cannot be checked.")
        return MemoryAnswer(f"`{item}` is deleted from use; removing its text from the store's disk files is still pending. "
                            "Running the same purge again checks it.")

    def _earlier_title(self, item: str) -> str:
        versions, _more = self._store.history(item, limit=msc.MAX_HISTORY)
        return next((version["title"] for version in versions if version["title"]), "")

    # --- reading -------------------------------------------------------------------------------------------------------

    def _list(self, page: int) -> str:
        cursor: str | None = None
        rows: Sequence[Any] = []
        for _ in range(page):
            rows, cursor = self._store.items(self._scope, limit=PAGE_ITEMS, cursor=cursor)
            if cursor is None:
                break
        if not rows:
            text = "No memory items yet in this project." if page == 1 else f"No memory items on page {page}."
            return text + self._footer()
        lines = [f"**Memory** (page {page})"]
        for stored in rows:
            event = stored.event
            title = escape_text(event.title or "(no text kept)", 80)
            archived = event.trust == "off" and event.status == "superseded"  # the overflow archive: kept, never used
            status = "archived: too many off items, kept but never used" if archived else _STATUS_WORDS[event.status]
            state = _state(stored)
            line = f"- `{event.item}@{event.version}` · {_ORIGIN_WORDS[event.trust]} · {status}"
            line += self._conditions(event.lineage, live=state is not None and state.servable) + f" · {title}"
            if event.trust == "off" and state is not None and state.live:
                line += f" · {self._availability(Locator.of(state))}"
            lines.append(line)
        if cursor is not None:
            lines.append(f"More: `/memory page {page + 1}`.")
        return "\n".join(lines) + self._footer()

    def _availability(self, locator: Locator) -> str:
        """Whether switch-on could find this off record's source: shown, never acted on, and never a prompt to approve it."""
        said, why = self._exact_source(locator)
        return "source held: `/memory switch-on` can save it" if said is not None else f"cannot be switched on: {why}"

    def _footer(self) -> str:
        recovery = self._recovery.status_line() if self._recovery is not None else "Recovery copy: not available for this session."
        if self._recovery is not None and self._recovery.recovery_required():
            recovery = ("**Recovery required:** the memory store holds nothing for this project although it held memory before. "
                        "Nothing is served or saved until you restore it: `/memory restore` lists the copies.\n" + recovery)
        backups = f"\n{self._backups.status_line()}" if self._backups is not None else ""
        return f"\n\n{recovery}{backups}\nItems never expire through inactivity. `/memory view <id>` shows one item's history."

    def _view(self, item: str, before: int | None) -> str:
        stored = self._store.read(item)
        if stored is None:
            return f"No memory item `{item}` in this project."
        versions, more = self._store.history(item, limit=HISTORY_PAGE, before=before)
        event = stored.event
        state = _state(stored)
        lines = [f"**`{item}@{event.version}`** · {_ORIGIN_WORDS[event.trust]} · {_STATUS_WORDS[event.status]}"
                 + self._conditions(event.lineage, live=state is not None and state.servable)]
        if event.trust != "off" and event.status == "active":
            lines.append(f"Cited as `[memory:{item}@{event.version}]`.")
        for version in versions:
            text = escape_text(version["statement"] or version["title"], MAX_STATEMENT_CHARS) if version["text"] == "kept" else ""
            shown = text or ("(text deleted)" if event.status == "purged" else "(no text)")
            lines.append(f"- v{version['version']} {version['action']}: {shown}")
        if more and versions:
            lines.append(f"Older: `/memory view {item} older {versions[-1]['version']}`.")
        return "\n".join(lines)


    # --- the recovery copy -----------------------------------------------------------------------------------------------

    def _recovery_command(self, command: MemoryCommand) -> MemoryAnswer:
        from optimus.context import memory_recovery as mr

        recovery = self._recovery
        if recovery is None or not self._trusted:
            return MemoryAnswer("The recovery copy is not available here: this workspace is not registered and trusted.")
        try:
            state = recovery.state()
            if command.verb == "export":
                if state.destination is None:
                    if self._workspace is None:
                        return MemoryAnswer("The recovery copy is not available for this session.")
                    return MemoryAnswer("", confirm=self._location_question(mr.location(self._workspace)))
                if not Path(state.destination).is_dir() and self._workspace is not None:
                    # the location was removed: never silently replaced, so the user confirms a move (Codex CP3 review 1)
                    return MemoryAnswer("", confirm=self._location_question(mr.location(self._workspace), moved_from=state.destination))
                generation = recovery.export()
                return MemoryAnswer(f"Saved the recovery copy `{generation.name}`: {generation.count} items, deletion frontier "
                                    f"{generation.deletions}. {recovery.status_line()}")
            # a project with no location yet (a new registration of this workspace) still reads its worktree's default one
            place = Path(state.destination) if state.destination else mr.location(self._workspace) if self._workspace else None
            if place is None or (not state.destination and not place.is_dir()):
                return MemoryAnswer("No recovery location is set up for this project, so there is nothing to restore.")
            found = mr.generations(place)
            backup_place: Path | None = None
            backup_all: list[mr.Generation] = []
            backup_note = ""
            if self._backups is not None:
                from optimus.context import memory_backups as mb

                try:  # damaged backup settings never take the recovery copy's restore down with them
                    backup_place = self._backups.place()
                    backup_all = self._backups.generations(mapping=True) if backup_place else []
                except mb.BackupError as failure:
                    backup_place, backup_note = None, f" (Backups unavailable: {failure.message})"
            backed = [g for g in backup_all if g.name not in {f.name for f in found}]
            if command.generation is None:
                if backed:
                    found = found + backed
                if not found:
                    return MemoryAnswer(f"No recovery copies are in {place}.{backup_note}")
                lines = [f"Recovery copies in {place} (newest first). Restore one with `/memory restore <generation>`; "
                         "nothing chooses for you when they differ:"]
                lines += [f"- `{g.name}`: {g.count} items, head {g.head}, {g.deletions} withdrawn or deleted, saved "
                          f"{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(g.created_ms / 1000))}"
                          + (f" · backup in {backup_place}" if g in backed else "")
                          + ("" if g.project == self.project else f" · written for project `{g.project}`: `/memory restore {g.name} "
                             "--map` maps it to this project") for g in found[:10]]
                return MemoryAnswer("\n".join(lines) + backup_note)
            chosen = next((g for g in found if g.name == command.generation), None)
            from_backup = None
            twin = next((g for g in backup_all if g.name == command.generation), None)
            if chosen is not None and twin is not None and backup_place is not None and not command.mapped:
                try:  # the recovery copy's own files are damaged: the backup of the same generation is offered instead
                    recovery.read_generation(chosen.name)
                except mr.RecoveryError:
                    chosen, from_backup = twin, backup_place
            if chosen is None and backup_place is not None:
                chosen = next((g for g in backed if g.name == command.generation), None)
                from_backup = backup_place if chosen is not None else None
            if chosen is None:
                return MemoryAnswer(f"There is no recovery copy `{command.generation}` in {place}.")
            if command.mapped:
                mapped_place = from_backup if from_backup is not None else place
                source = recovery.mapping_source(chosen.name, mapped_place)  # the same registry-key and ambiguity checks
                text = (f"Map project `{source}` to this project (`{self.project}`) and restore `{chosen.name}` ({chosen.count} "
                        f"items, {chosen.deletions} withdrawn or deleted) into its memory store? `{source}` was an earlier "
                        "registration of this workspace. Only an empty store is restored into; deletions recorded since, in "
                        "either project, still apply.")
                return MemoryAnswer("", confirm=Confirmation("restore", f"Map {source} and restore {chosen.name}?", text,
                                                             {"project": self.project, "generation": chosen.name, "seal": chosen.seal,
                                                              "source": source, "place": str(mapped_place)}, secrets.token_hex(16)))
            if chosen.project != self.project:
                return MemoryAnswer(f"`{chosen.name}` was written for project `{chosen.project}`. To restore it into this project, "
                                    f"map it: `/memory restore {chosen.name} --map`. Nothing was changed.")
            text = (f"Restore `{chosen.name}` ({chosen.count} items, head {chosen.head}, {chosen.deletions} withdrawn or deleted) into "
                    "this project's memory store? Only an empty store is restored into; deletions recorded since still apply."
                    + (f" It is read from the backup in {from_backup}." if from_backup is not None else ""))
            meta = {"project": self.project, "generation": chosen.name, "seal": chosen.seal}
            if from_backup is not None:
                meta["backup"] = str(from_backup)
            return MemoryAnswer("", confirm=Confirmation("restore", f"Restore memory from {chosen.name}?", text, meta,
                                                         secrets.token_hex(16)))
        except mr.RecoveryError as failure:
            return MemoryAnswer(failure.message)

    def _backup_command(self, command: MemoryCommand) -> MemoryAnswer:
        """`/memory backup ...`: host-only file actions on the recovery copy's generations; no model call, no Gateway path."""
        from optimus.context import memory_backups as mb
        from optimus.context import memory_recovery as mr

        backups = self._backups
        if backups is None or not self._trusted:
            return MemoryAnswer("Backups are not available here: this workspace is not registered and trusted.")
        try:
            if command.verb == "backup_status":
                return MemoryAnswer(backups.status_line())
            if command.verb == "backup_disable":
                backups.disable()
                return MemoryAnswer("Backups are off for this project. Existing backups are kept and still listed. "
                                    + backups.status_line())
            if command.verb == "backup_now":
                generation = backups.backup(explicit=True)  # the user's own write: also releases held synced cleanup
                return MemoryAnswer(f"Backed up `{generation.name}`: {generation.count} items. {backups.status_line()}")
            if command.encrypted:
                return MemoryAnswer(f"Not set up: {mb.ENCRYPTION_UNAVAILABLE} Nothing was written.")
            assert command.target is not None
            assessed = backups.assess(Path(command.target), declared_sync=command.cloud)
        except mb.BackupError as failure:
            return MemoryAnswer(failure.message)
        except mr.RecoveryError as failure:
            return MemoryAnswer(failure.message)
        domain = {"separate": f"It is on a separate physical disk ({assessed['reason']}).",
                  "same": f"WARNING: it is on the same physical disk as the memory store or the recovery copy ({assessed['reason']}), "
                          "so it does not protect against losing that drive.",
                  "unknown": f"Whether it is on a separate drive is unknown ({assessed['reason']})."}[assessed["domain"]]
        text = (f"Back up this project's memory to {assessed['target']} once a day while Optimus runs, keeping 30 days? {domain} "
                f"{mb.ENCRYPTION_UNAVAILABLE} Copies of later-withdrawn items are removed after a clean backup, where Optimus can reach "
                "them.")
        if assessed["synced"]:
            text += (f" This folder is synced ({assessed['synced']}): the sync service may keep copies, including of later-withdrawn "
                     "items, that Optimus cannot erase. Confirming also consents to that; each backup there is taken only by "
                     "`/memory backup now`.")
        return MemoryAnswer("", confirm=Confirmation("backup", "Set up memory backups?", text,
                                                     {"project": self.project, **assessed}, secrets.token_hex(16)))

    def _backup_confirmed(self, confirmation: Confirmation) -> MemoryAnswer:
        from optimus.context import memory_backups as mb
        from optimus.context import memory_recovery as mr

        if self._backups is None:
            return MemoryAnswer("Backups are not available for this session.")
        assessed = {name: confirmation.meta[name] for name in ("target", "synced", "domain", "reason", "anchor")}
        try:
            self._backups.configure(assessed, consent=bool(assessed["synced"]))
            if assessed["synced"]:
                return MemoryAnswer(f"Backups now go to {assessed['target']}. Take each one with `/memory backup now`.")
            generation = self._backups.backup()
        except mb.BackupError as failure:
            return MemoryAnswer(failure.message)
        except mr.RecoveryError as failure:
            return MemoryAnswer(failure.message)
        return MemoryAnswer(f"Backups now go to {assessed['target']}. Backed up `{generation.name}`: {generation.count} items.")

    def _import_command(self, command: MemoryCommand) -> MemoryAnswer:
        """`/memory import ...`: the host reads the folder as data (no model, no execution); only a confirmed apply writes."""
        from optimus.context import memory_import as mi

        importer = self._importer
        if importer is None or not self._trusted:
            return MemoryAnswer("Import is not available here: this workspace is not registered and trusted.")
        try:
            if command.verb == "import_status":
                return MemoryAnswer(importer.status())
            if command.verb == "import_show":
                assert command.preview is not None
                return MemoryAnswer(importer.page(command.preview, command.page))
            if command.verb == "import_apply":
                assert command.preview is not None
                held = importer.held(command.preview)
                if not held.all_shown:
                    unseen = sorted(set(range(1, held.pages + 1)) - held.shown)
                    return MemoryAnswer(f"Not yet: see every page of the preview first (not shown: "
                                        f"{', '.join(map(str, unseen[:20]))}) with `/memory import show {held.id} <page>`. "
                                        "Nothing was changed.")
                counts = {"import": 0, "skipped": 0, "refused": 0}
                for entry in held.source.entries:
                    counts[entry.disposition] += 1
                text = (f"Import {counts['import']} entries from {escape_text(held.source.root, 200)} into this project's memory as "
                        f"optional imported context (preview `{held.id}`)? They are never saved as your own items. "
                        f"{counts['skipped']} skipped and {counts['refused']} refused entries are not saved. Each entry is saved "
                        "on its own; a repeat saves nothing twice.")
                return MemoryAnswer("", confirm=Confirmation("import", "Import memory entries?", text,
                                                             {"project": self.project, "preview": held.id, "digest": held.digest},
                                                             secrets.token_hex(16)))
            assert command.target is not None
            preview = importer.preview(Path(command.target), command.source)
            return MemoryAnswer(mi.preview_text(preview, project=self.project))
        except mi.ImportRefused as refused:
            return MemoryAnswer(refused.message)

    def _import_confirmed(self, confirmation: Confirmation) -> MemoryAnswer:
        from optimus.context import memory_import as mi

        if self._importer is None or confirmation.meta.get("project") != self.project:
            return MemoryAnswer("That import was prepared for another project or session. Nothing was changed.")
        try:
            counts, notices = self._importer.apply(confirmation.meta["preview"], confirmation.meta["digest"])
        except mi.ImportRefused as refused:
            return MemoryAnswer(refused.message)
        text = (f"Imported: {counts['confirmed']} saved, {counts['duplicate']} already present, {counts['skipped']} skipped, "
                f"{counts['refused']} refused, {counts['uncertain']} uncertain.")
        if "stopped" in counts:
            text += (f" It stopped because {counts['stopped']}, so {counts['remaining']} were not tried; "
                     "`/memory import status` shows where it stopped. What was saved is kept.")
        return MemoryAnswer(text, tuple(notices))

    def _location_question(self, destination: Path, *, moved_from: str | None = None) -> Confirmation:
        from optimus.context import memory_recovery as mr

        synced = mr.sync_root(self._workspace) if self._workspace is not None else None  # the location lies in the worktree
        text = (f"Keep this project's plaintext recovery copy in {destination}? It is same-drive plaintext, not a backup: active items "
                "only, kept out of Git and out of the model's reach, but readable by authorized TEST or shell commands.")
        if moved_from is not None:
            text = (f"The recovery location {moved_from} is gone. " + text + " The old location stays listed until no copy is "
                    "left in it.")
        if synced:
            text += (f" This folder is synced ({synced}): the sync service may keep copies, including of later-withdrawn items, that "
                     "Optimus cannot erase. Confirming also consents to that.")
        return Confirmation("location", "Move the memory recovery copy?" if moved_from else "Set up the memory recovery copy?", text,
                            {"project": self.project, "destination": str(destination), "synced": synced or "",
                             "moved_from": moved_from or ""}, secrets.token_hex(16))

    def _registry_command(self, command: MemoryCommand) -> MemoryAnswer:
        """The project registry is lost: only a confirmed repair from an authenticated recovery copy is offered."""
        from optimus.context import memory_recovery as mr

        repair = self._registry_recovery
        found = repair.generations()
        if command.verb == "restore" and command.generation is not None:
            chosen = next((g for g in found if g.name == command.generation), None)
            if chosen is None:
                return MemoryAnswer(f"There is no recovery copy `{command.generation}` in this worktree.")
            try:
                manifest, _entries = repair.read(chosen.name)
            except mr.RecoveryError as failure:
                return MemoryAnswer(failure.message)
            text = (f"This project's registry is lost. Restore it from `{chosen.name}` (project {manifest['metadata']['project']}, "
                    f"{chosen.count} items), and restore the memory store from it if the store is empty?")
            return MemoryAnswer("", confirm=Confirmation("registry", "Repair the project registry?", text,
                                                         {"generation": chosen.name, "seal": chosen.seal,
                                                          "project": manifest["metadata"]["project"]}, secrets.token_hex(16)))
        lines = ["**Recovery required:** this project's registry is lost, so memory is unavailable until it is repaired from a "
                 "recovery copy. Restore one with `/memory restore <generation>`:"]
        lines += [f"- `{g.name}`: {g.count} items, head {g.head}" for g in found[:10]] or ["- (no recovery copy in this worktree)"]
        return MemoryAnswer("\n".join(lines))

    def confirmed(self, confirmation: Confirmation) -> MemoryAnswer:
        """After the user chose to go ahead with exactly `confirmation`."""
        from optimus.context import memory_recovery as mr
        from optimus.context.authored_memory import MemoryStoreRefused, MemoryStoreUnavailable

        if confirmation.kind == "registry" and self._registry_recovery is not None:
            try:
                return MemoryAnswer(self._registry_recovery.recover(confirmation.meta["generation"], seal=confirmation.meta["seal"]))
            except mr.RecoveryError as failure:
                return MemoryAnswer(failure.message)
            except (MemoryStoreUnavailable, MemoryStoreRefused):
                return MemoryAnswer(UNAVAILABLE)
        if confirmation.kind == "import":
            try:
                return self._import_confirmed(confirmation)
            except MemoryStoreUnavailable:
                return MemoryAnswer(UNAVAILABLE)
            except MemoryStoreRefused as refused:
                return MemoryAnswer(_refused(refused.code))
        recovery = self._recovery
        if recovery is None:
            return MemoryAnswer("The recovery copy is not available for this session.")
        if confirmation.kind == "backup":
            return self._backup_confirmed(confirmation)
        try:
            if confirmation.kind == "location":
                recovery.confirm(Path(confirmation.meta["destination"]), sync_consent=bool(confirmation.meta["synced"]))
                generation = recovery.export()
                return MemoryAnswer(f"Recovery copies now go to {confirmation.meta['destination']}. Saved `{generation.name}`: "
                                    f"{generation.count} items.")
            source = confirmation.meta.get("source")
            directory = (Path(confirmation.meta["place"]) / confirmation.meta["generation"] if source else
                         Path(confirmation.meta["backup"]) / confirmation.meta["generation"] if confirmation.meta.get("backup") else None)
            reply = recovery.restore(confirmation.meta["generation"], seal=confirmation.meta["seal"], source=source,
                                     directory=directory, workspace=self._workspace)  # exactly what was confirmed
            # In the order the restore did them: the mapping was confirmed, the pins were validated, the deletions applied.
            steps = [f"Project `{source}` is mapped to this one."] if source else []
            anchors = reply.get("anchors") or {}
            if anchors.get("held"):
                steps.append("Pinned files hold for " + ", ".join(f"`{item}@{version}`" for item, version in anchors["held"]) + ".")
            steps += [f"`{item}@{version}` needs re-verification: `{path}` changed." for item, version, path in anchors.get("changed", ())]
            if reply.get("purged"):
                steps.append(f"{len(reply['purged'])} were deleted since and stay deleted.")
            return MemoryAnswer(" ".join([f"Restored `{confirmation.meta['generation']}`{' into this project' if source else ''}: "
                                          f"{reply.get('restored', 0)} items, {reply.get('durable_state')} on disk.", *steps]))
        except mr.RecoveryError as failure:
            return MemoryAnswer(failure.message)
        except MemoryStoreUnavailable:
            return MemoryAnswer(UNAVAILABLE)
        except MemoryStoreRefused as refused:
            return MemoryAnswer(_refused(refused.code))


_SCAN_REFUSED: Final = ("Not saved: the statement looks like it holds a secret or an instruction to the model, so it was refused. "
                        "Nothing was stored.")


def _said(notice: MemoryNotice, label: str) -> str:
    named = f" “{escape_text(label, 80)}”" if label else ""
    if notice.saved:
        return f"{headline(notice)}{named} `[memory:{notice.item}@{notice.version}]`."
    if notice.durable_state == "unconfirmed":
        return f"{headline(notice)}{named}. Run the same command again: a retry finishes this change and never makes a second one."
    return f"{headline(notice)}{named}."


_REFUSALS: Final = {
    "MEMORY_FULL": "Not saved: this project's memory is full. Existing items are kept; forget some to make room.",
    "MEMORY_NOT_ADMITTING": "Not saved: the memory store is not accepting new saves right now (it cannot prove writes reach disk). "
                            "Existing items are kept.",
    "OFF_RECORDS_FULL": "Not saved: too many items that are off are kept for this project.",
    "VERSION_CONFLICT": "Nothing was changed: the item changed meanwhile. Look at it with `/memory view <id>` and try again.",
    "LEASE_HELD": "Nothing was changed: another session is writing this project's memory. Try again in a moment.",
    "LEASE_LOST": "Nothing was changed: another session took over this project's memory meanwhile. Try again.",
    "ITEM_PURGED": "Nothing was changed: that item was deleted.",
    "ITEM_UNKNOWN": "No such memory item in this project.",
    "MEMORY_CONTENDED": "Nothing was changed: the store was busy. Try again.",
    "IDEMPOTENCY_CONFLICT": "Nothing was changed: this change conflicts with an earlier one under the same command.",
    "RECOVERY_REQUIRED": ("Nothing was saved: this project's memory store is empty although it held memory before. Restore it "
                          "first: `/memory restore` lists the recovery copies."),
    "RESTORE_TARGET_NOT_EMPTY": "Not restored: the memory store already holds this project's memory. Nothing was changed.",
    "RESTORE_DELETION_UNCERTAIN": ("Not restored: a deletion is unfinished. Run the same purge again to finish it, then restore. "
                                   "Nothing was changed."),
    "RESTORE_GENERATION_INVALID": "Not restored: that copy is incomplete or was altered. Nothing was changed.",
    "RESTORE_ENTRY_INVALID": "Not restored: that copy holds an entry the store did not write. Nothing was changed.",
    "MEMORY_RECOVERY_UNAVAILABLE": "The recovery copy is not available: the store's credential is not set up.",
    "RESTORE_DELETION_UNKNOWN": ("Not restored: the deletion journal is damaged or shorter than when this copy was written, so a "
                                 "deletion could be undone. Nothing was changed."),
}


def _refused(code: str) -> str:
    return _REFUSALS.get(code, f"The memory store refused this ({code}). Nothing was changed.")
