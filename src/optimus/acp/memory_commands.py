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
"""

from __future__ import annotations

import dataclasses
import re
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
from optimus.context.memory_extraction import digest, scans_pass, sentence_bounds, title_of
from optimus_security import memory_store_contract as msc

COMMANDS: Final = ("remember", "forget", "memory", "welcome")
DESCRIPTIONS: Final = {
    "remember": ("Save a rule or fact to this project's memory", "<statement>"),
    "forget": ("Withdraw a memory item (history is kept); --purge deletes its text", "<id>@<version> [--purge]"),
    "memory": ("List memory, or view, edit, switch on or forget one item",
               "[view <id> | edit <id>@<version> <statement> | switch-on <id>@<version> | forget <id>@<version> | page <n>]"),
    "welcome": ("Show the welcome-back brief for this project", ""),
}
PAGE_ITEMS: Final = 20
HISTORY_PAGE: Final = 10
PURGE_OPTION: Final = "memory-purge"
PURGE_CANCEL: Final = "memory-purge-cancel"
USAGE: Final = (
    "Memory commands:\n"
    "- `/remember <statement>` saves a rule or fact for this project.\n"
    "- `/forget <id>@<version>` withdraws an item; its history is kept. Add `--purge` to delete its text, after you confirm.\n"
    "- `/memory` lists memory (`/memory page <n>` for more); `/memory view <id>` shows an item's history.\n"
    "- `/memory edit <id>@<version> <statement>` replaces one of your items.\n"
    "- `/memory switch-on <id>@<version>` saves an off item from your exact words, while this session still holds them.\n"
    "- `/welcome` shows the welcome-back brief.\n"
    "A change names the version you saw in `/memory`, for example `m-0123456789abcdef@2`."
)
NEEDS_VERSION: Final = "Name the version you mean, as `/memory` shows it: for example `{verb} {item}@2`. Nothing was changed."
READ_ONLY: Final = "Memory is read-only here: this workspace is not registered and trusted, so nothing can be saved or changed."
UNAVAILABLE: Final = ("The memory store did not answer, so this is not confirmed: it may or may not have been changed. `/memory` "
                      "shows what is stored, and running the same command again never makes a second change.")
_ITEM: Final = re.compile(r"m-[0-9a-f]{16}")  # the route's item id
_REF: Final = re.compile(r"(m-[0-9a-f]{16})@([1-9][0-9]{0,9})")
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
        said = _statement_after(text, lead)
        return USAGE if said is None else MemoryCommand("remember", statement=said[0], start=said[1])
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
                 source_digest: Callable[[str], str] | None = None, recovery: Callable[[], str] | None = None,
                 brief: Callable[[], str] | None = None) -> None:
        self._store, self._trusted, self._sanitize, self._keyed = store, trusted, sanitize, keyed
        self._scope = scope
        self._source = source
        self._source_digest = source_digest
        self._recovery = recovery
        self._brief = brief

    @property
    def project(self) -> str:
        return str(self._store.project)

    # --- dispatch ------------------------------------------------------------------------------------------------------

    def run(self, command: MemoryCommand, *, block: str) -> MemoryAnswer:
        """The answer to one command; never raises for a store state. `block` is the host id of the prompt's raw text."""
        from optimus.context.authored_memory import MemoryStoreRefused, MemoryStoreUnavailable

        try:
            if command.verb == "list":
                return MemoryAnswer(self._list(command.page))
            if command.verb == "view":
                assert command.item is not None
                return MemoryAnswer(self._view(command.item, command.before))
            if command.verb == "welcome":
                return MemoryAnswer(self._brief() if self._brief is not None else "No welcome-back brief is available for this project yet.")
            if not self._trusted:
                return MemoryAnswer(READ_ONLY)
            if command.verb == "remember":
                assert command.statement is not None
                return self._remember(command.statement, Span(block, command.start, command.start + len(command.statement)))
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

    def _remember(self, statement: str, span: Span) -> MemoryAnswer:
        title = title_of(statement)
        key = self._keyed(f"{_COMMAND_KEY}\0remember\0{self.project}\0{self._scope}\0{statement}")
        candidate = MemoryCandidate(self.project, self._scope, "user-authored", "fact", "assertion", statement, title, spans=(span,),
                                    idempotency_key=key)
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
            candidate = MemoryCandidate(self.project, target.scope, "user-authored", target.kind, "assertion", statement, title,
                                        spans=(span,), target=item, idempotency_key=key)
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
                reply = self._store.purge(token, request.item, self._keyed(f"{_COMMAND_KEY}\0purge\0{self.project}\0{request.item}"))
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
            line = (f"- `{event.item}@{event.version}` · {_ORIGIN_WORDS[event.trust]} · {_STATUS_WORDS[event.status]}"
                    f" · {title}")
            state = _state(stored)
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
        recovery = self._recovery() if self._recovery is not None else "Recovery copy: not available in this version."
        return f"\n\n{recovery}\nItems never expire through inactivity. `/memory view <id>` shows one item's history."

    def _view(self, item: str, before: int | None) -> str:
        stored = self._store.read(item)
        if stored is None:
            return f"No memory item `{item}` in this project."
        versions, more = self._store.history(item, limit=HISTORY_PAGE, before=before)
        event = stored.event
        lines = [f"**`{item}@{event.version}`** · {_ORIGIN_WORDS[event.trust]} · {_STATUS_WORDS[event.status]}"]
        if event.trust != "off" and event.status == "active":
            lines.append(f"Cited as `[memory:{item}@{event.version}]`.")
        for version in versions:
            text = escape_text(version["statement"] or version["title"], MAX_STATEMENT_CHARS) if version["text"] == "kept" else ""
            shown = text or ("(text deleted)" if event.status == "purged" else "(no text)")
            lines.append(f"- v{version['version']} {version['action']}: {shown}")
        if more and versions:
            lines.append(f"Older: `/memory view {item} older {versions[-1]['version']}`.")
        return "\n".join(lines)


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
}


def _refused(code: str) -> str:
    return _REFUSALS.get(code, f"The memory store refused this ({code}). Nothing was changed.")
