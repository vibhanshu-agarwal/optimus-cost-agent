"""Plan 12.13 `/why`: what this session's last turn was prepared with, from the facts the turn itself recorded.

One immutable snapshot per terminal preparation attempt, taken when the turn ends, from what assembly, serving and dispatch
actually did: retrieval is never rerun and memory never reread. It holds metadata only (paths, symbol names, ranks,
reasons, counts and digests), never a body, signature, prompt, memory statement or hidden reasoning. Rendering applies
the session's workspace-aware sanitizer, today's disclosure denials and Markdown/control escaping, and pages
deterministically within fixed bounds; nothing is cut without saying so. Answering calls no model, index, store or
extractor: the snapshot is already in RAM.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from optimus.acp.memory_notices import escape_text
from optimus.agent.workspace_context import RankedCandidate, WorkspaceReferenceStatus

COMMAND: Final = "why"
DESCRIPTION: Final = "Explain the context the last turn was prepared with"
HINT: Final = "[page]"
MAX_ENTRIES: Final = 40  # per page, frozen at CP1 (ruling 6)
MAX_PAGE_BYTES: Final = 12 * 1024  # UTF-8, header, navigation and markers included
MAX_PAGE: Final = 1000
WAIT_SECONDS: Final = 5.0  # rendering asks the file policy about each path, which may read ignore files
USAGE: Final = "`/why` explains the context of this session's last turn; `/why <n>` shows page n of the explanation."
NO_SNAPSHOT: Final = "No context explanation is available for this session yet."
NO_SNAPSHOT_ON_DISK: Final = ("Diagnostic manifests from earlier sessions may be on disk, but they cannot establish this session's last "
                              "turn, so none of them is shown.")
UNPREPARED_TEXT: Final = "The explanation could not be prepared. Nothing was changed; `/why` asks again."
HISTORICAL: Final = ("This is what the turn was prepared with when it ran. It does not show that those files, ranks or memory "
                     "items are still current.")
WITHHELD: Final = "(a file not disclosed now)"
_REFERENCE_WORDS: Final = {
    WorkspaceReferenceStatus.NOT_FOUND: "not found",
    WorkspaceReferenceStatus.NOT_READABLE: "not readable",
    WorkspaceReferenceStatus.TOO_LARGE: "too large for the context",
}


def parse(text: str, *, attachments: bool) -> int | str | None:
    """None: not `/why`. A page number (0 included: its answer names the valid range, frozen case E12), or the usage text for a
    malformed one."""
    words = text.split()
    if not words or words[0] != f"/{COMMAND}":
        return None
    if attachments or len(words) > 2:
        return USAGE
    if len(words) == 1:
        return 1
    word = words[1]
    if not (word.isascii() and word.isdigit() and len(word) <= len(str(MAX_PAGE))):  # "²" is a digit int() refuses
        return USAGE
    page = int(word)
    return page if page <= MAX_PAGE else USAGE


@dataclass(frozen=True)
class ContextFacts:
    """One automatic context the turn attached: today's workspace selection or the index's pack."""

    used_bytes: int
    max_bytes: int
    required: tuple[str, ...]
    shown: tuple[str, ...]
    omitted: tuple[str, ...]
    stop: str | None
    references: tuple[tuple[str, str], ...]  # (reference, what became of it) for those that did not resolve
    ranked: tuple[tuple[str, tuple[RankedCandidate, ...]], ...]  # an ambiguous reference and its ranked candidates


@dataclass(frozen=True)
class MemoryFacts:
    read: str  # how the store read ended: "served", "timeout", "error", or "not read" before the turn ended
    served: tuple[str, ...]  # id@version
    complete: bool
    omitted_protected: int
    omitted_optional: int
    reverify: int
    elsewhere: int
    watermarks: tuple[str, ...]


Dispatch = tuple[int, int, int | None, int | None]


@dataclass(frozen=True)
class Snapshot:
    run_id: str
    turn_seq: int
    outcome: str
    stop: str | None
    index: str  # "used", "not answering" or "not configured"
    contexts: tuple[ContextFacts, ...] | None  # None: this launch records no context
    # Each main model request the host sent, retries included: (estimated tokens, usable input, planning round, attempt in that
    # round); the round and attempt are None for a request outside the planning loop.
    dispatches: tuple[Dispatch, ...] | None
    rounds: int | None
    reads: tuple[int, ...] | None  # bytes each planning read returned
    limits: tuple[int, int]  # planning observation and new-read serialized limits, bytes
    manifest: str | None  # the index's own manifest for this turn, canonical JSON (paths, symbols, ranks, reasons)
    memory: MemoryFacts | None  # None: no memory store this turn


def _facts(result: Any) -> ContextFacts:
    references = tuple((item.reference, _REFERENCE_WORDS[item.status]) for item in result.diagnostics if item.status in _REFERENCE_WORDS)
    ranked = tuple((item.reference, tuple(item.ranked) or tuple(RankedCandidate(path) for path in item.candidates))
                   for item in result.diagnostics if item.status is WorkspaceReferenceStatus.AMBIGUOUS)
    return ContextFacts(result.used_bytes, result.max_total_bytes, tuple(result.prioritized_paths), tuple(getattr(result, "shown_paths", ())),
                        tuple(result.omitted_paths), result.blocking_stop_reason, references, ranked)


def capture(*, run_id: str, turn_seq: int, outcome: str, stop: str | None, index: str, contexts: Sequence[Any] | None,
            dispatches: Sequence[tuple[int, int] | Dispatch] | None, rounds: int | None, reads: Sequence[int] | None, limits: tuple[int, int],
            manifest: Mapping[str, Any] | None,
            served: Any, memory_read: str | None) -> Snapshot:
    """The turn's facts, copied now: nothing in the snapshot can change after the turn."""
    memory = None
    if memory_read is not None:
        memory = MemoryFacts(memory_read, tuple(f"{item.item}@{item.version}" for item in served.items), served.complete, served.omitted_protected,
                             served.omitted_optional, len(served.reverify), len(served.elsewhere), tuple(str(mark) for mark in served.watermarks))
    return Snapshot(
        run_id=run_id, turn_seq=turn_seq, outcome=outcome, stop=stop, index=index,
        contexts=None if contexts is None else tuple(_facts(result) for result in contexts),
        dispatches=None if dispatches is None else tuple(cast(Dispatch, (*item, None, None)[:4]) for item in dispatches),
        rounds=rounds,
        reads=None if reads is None else tuple(reads),
        limits=limits,
        manifest=json.dumps(manifest, sort_keys=True, ensure_ascii=True) if manifest else None,
        memory=memory,
    )


# --- rendering ---------------------------------------------------------------------------------------------------------


def _entries(snapshot: Snapshot, show: Callable[[Any], str], path: Callable[[str], str], name: Callable[[str], str]) -> list[str]:
    """Every line of the explanation, in order. Every recorded value goes through `show` (sanitized and escaped), `path` (that, after
    today's disclosure check of a file) or `name` (that, after today's check of a name a person typed); only the fixed words are the
    host's own."""
    lines = ["**Identity and delivery**", f"- outcome: {show(snapshot.outcome)}" + (f"; stop: {show(snapshot.stop)}" if snapshot.stop else "")]
    lines.append("- prepared context: unavailable (this launch does not record it)" if snapshot.contexts is None
                 else f"- prepared context: {len(snapshot.contexts)} time(s)")
    # "Main": an Auto classifier call is not one of these (Codex CP3 review 1, finding 4)
    if snapshot.dispatches is None:
        lines.append("- main model requests sent: unavailable")
    elif not snapshot.dispatches:
        lines.append("- main model requests sent: none, so this context was prepared and never sent as a main model request")
    else:
        lines.append(f"- main model requests sent: {len(snapshot.dispatches)}" + ("" if snapshot.rounds is None else f"; planning rounds: {snapshot.rounds}"))
        if all(item[2] is not None for item in snapshot.dispatches):  # frozen case E09: per round, from the request's own round
            for number in sorted({item[2] for item in snapshot.dispatches if item[2] is not None}):
                sent = [item for item in snapshot.dispatches if item[2] == number]
                retries = sum((item[3] or 1) > 1 for item in sent)
                lines.append(f"  - round {number}: {len(sent)} request(s) sent" + (f", {retries} of them a retry" if retries else ""))
            lines.append("  - the Gateway's own route attempts inside one request are not host requests and are not counted")

    lines.append("**Choices**")
    first_choice = len(lines)
    manifest = json.loads(snapshot.manifest) if snapshot.manifest else None
    selected = (manifest or {}).get("selected") or []
    for number, item in enumerate(selected, start=1):
        ranks = ", ".join(f"{show(channel)} {show(rank)}" for channel, rank in sorted((item.get("ranks") or {}).items()))
        symbol = f" {show(item['symbol'])}" if item.get("symbol") and path(item["path"]) != WITHHELD else ""
        lines.append(f"- {number}. {path(item['path'])}{symbol}: {show(item.get('disclosure', 'unknown'))}"
                     + (f"; ranks: {ranks}" if ranks else "") + (f"; {show(item['reason'])}" if item.get("reason") else ""))
    for facts in snapshot.contexts or ():
        for reference, ranked in facts.ranked:
            lines.append(f"- {name(reference)} was ambiguous, so nothing was chosen; candidates, most likely first:")
            # a reason names the candidate's own folders, so it is withheld with the path
            lines += [f"  - {path(item.path)}" + (f" ({show(item.reasons())})" if item.reasons() and path(item.path) != WITHHELD else "")
                      for item in ranked]
        lines += [f"- required: {path(item)}" for item in facts.required]
        if not selected:
            lines += [f"- shown: {path(item)}" for item in facts.shown if item not in facts.required]
        lines += [f"- left out for size: {path(item)}" for item in facts.omitted]
    if len(lines) == first_choice:
        lines.append("- none recorded")

    lines.append("**Fit**")
    for facts in snapshot.contexts or ():
        lines.append(f"- automatic context: {facts.used_bytes} of {facts.max_bytes} bytes")
        if facts.stop:
            lines.append(f"- required evidence: stopped with {show(facts.stop)}")
    budget = (manifest or {}).get("budget")
    lines.append(f"- index pack: {show(budget['tokens'])} of {show(budget['budget_tokens'])} tokens" if budget else "- index pack: unavailable")
    if snapshot.dispatches:
        tokens, capacity = max((item[0], item[1]) for item in snapshot.dispatches)
        lines.append(f"- largest request: about {tokens} of {capacity} usable input tokens")
    observation, read = snapshot.limits
    lines.append(f"- planning limits: observations {observation} bytes, new reads {read} bytes (serialized)")
    lines.append("- planning reads: unavailable" if snapshot.reads is None
                 else f"- planning reads: {len(snapshot.reads)}, returning {sum(snapshot.reads)} bytes")

    lines.append("**Grounding and scope**")
    lines.append(f"- context index: {show(snapshot.index)}")
    retrieval = (manifest or {}).get("retrieval")
    if retrieval:
        coverage = retrieval.get("coverage") or {}
        channels = ", ".join(f"{show(name)} {show(state)}" for name, state in sorted((retrieval.get("channels") or {}).items()))
        lines.append(f"- retrieval: {show(retrieval.get('state'))}"
                     + (f"; generation {show(retrieval['generation'])}" if "generation" in retrieval else "")
                     + (f", {show(coverage.get('files_indexed', 0))} of {show(coverage.get('files_total', 0))} files" if coverage else "")
                     + (f"; channels: {channels}" if channels else ""))
    for facts in snapshot.contexts or ():
        lines += [f"- {name(reference)}: {state}" for reference, state in facts.references]
    grounding = (manifest or {}).get("grounding")
    if grounding:
        for key, words in (("unresolved", "cited but not found"), ("ambiguous", "cited and ambiguous"), ("not_in_index", "not in the index")):
            if grounding.get(key):
                lines.append(f"- {words}: {len(grounding[key])} symbol(s), not named here (no single file is known to admit them)")
    elif manifest is not None and selected:
        lines.append("- answer grounding: unavailable")
    lines += [f"- unsaved editor text: {path(item)}" for item in (manifest or {}).get("unsaved_buffers") or ()]
    lines += [f"- changed since indexed, not shown: {path(item)}" for item in (manifest or {}).get("stale_paths") or ()]

    lines.append("**Memory**")
    memory = snapshot.memory
    if memory is None:
        lines.append("- memory: none this turn (no memory store)")
    elif memory.read == "not read":
        lines.append("- memory: not read before this turn ended")
    elif memory.read != "served":
        lines.append(f"- memory: the store's read ended with {show(memory.read)}, so whether memory exists is unknown")
    else:
        lines.append("- served: " + (", ".join(show(item) for item in memory.served) if memory.served else "nothing"))
        lines.append(f"- read: {'complete' if memory.complete else 'partial'}; left out: {memory.omitted_protected} yours, "
                     f"{memory.omitted_optional} agent lessons; needing re-verification: {memory.reverify}; for another branch: {memory.elsewhere}")
        if memory.watermarks:
            lines.append("- read at: " + ", ".join(show(mark) for mark in memory.watermarks))
    lines.append(HISTORICAL)
    return lines


def _clip(line: str, limit: int) -> str:
    """A line within `limit` bytes, saying so when it had to be cut."""
    if len(line.encode("utf-8")) <= limit:
        return line
    marker = f" [cut: {len(line.encode('utf-8'))} bytes is more than a page]"
    kept = line.encode("utf-8")[: limit - len(marker.encode("utf-8"))].decode("utf-8", errors="ignore")
    return kept + marker


def refusal_note(turn_seq: int) -> str:
    return f"A later prompt was refused before its context was prepared, so this still explains turn {turn_seq}."


def pages(snapshot: Snapshot, *, sanitize: Callable[[str], str], admits: Callable[[str], bool], refused_after: bool = False,
          admits_name: Callable[[str], bool] | None = None) -> list[str]:
    """The explanation as pages of at most `MAX_ENTRIES` lines and `MAX_PAGE_BYTES` bytes, header and navigation included. A later
    refusal's notice is page 1's first entry, so it is never left out for room."""
    def show(value: Any) -> str:
        return escape_text(sanitize(str(value)), MAX_PAGE_BYTES)

    def path(value: str) -> str:
        return show(value) if admits(value) else WITHHELD

    def name(value: str) -> str:
        return show(value) if (admits_name or admits)(value.replace("\\", "/")) else WITHHELD

    lines = ([refusal_note(snapshot.turn_seq)] if refused_after else []) + _entries(snapshot, show, path, name)
    # the run id is the host's own (session id and turn), so it is escaped but never masked as if it were content
    head = f"Context explanation for turn {snapshot.turn_seq} of this session (run {escape_text(snapshot.run_id, MAX_PAGE_BYTES)})"
    worst_head = f"{head}, page {len(lines)} of {len(lines)}:\n"
    worst_foot = f"\nPage {len(lines)} of {len(lines)}. `/why {len(lines)}` shows the next page."
    room = MAX_PAGE_BYTES - len(worst_head.encode("utf-8")) - len(worst_foot.encode("utf-8"))
    grouped: list[list[str]] = [[]]
    used = 0
    for line in (_clip(line, room - 1) for line in lines):
        size = len(line.encode("utf-8")) + 1
        if grouped[-1] and (len(grouped[-1]) == MAX_ENTRIES or used + size > room):
            grouped.append([])
            used = 0
        grouped[-1].append(line)
        used += size
    total = len(grouped)
    out = []
    for number, group in enumerate(grouped, start=1):
        foot = f"\nPage {number} of {total}. `/why {number + 1}` shows the next page." if number < total else (
            f"\nPage {number} of {total}." if total > 1 else "")
        out.append(f"{head}, page {number} of {total}:\n" + "\n".join(group) + foot)
    return out


def answer(snapshot: Snapshot | None, page: int, *, sanitize: Callable[[str], str], admits: Callable[[str], bool],
           refused_after: bool, manifests_on_disk: bool, admits_name: Callable[[str], bool] | None = None) -> str:
    """`/why [page]`'s whole text."""
    if snapshot is None:
        return NO_SNAPSHOT + (f" {NO_SNAPSHOT_ON_DISK}" if manifests_on_disk else "")
    shown = pages(snapshot, sanitize=sanitize, admits=admits, refused_after=refused_after, admits_name=admits_name)
    if page < 1:
        return f"Pages start at 1: the explanation has {len(shown)} page(s), `/why 1` to `/why {len(shown)}`."
    if page > len(shown):
        return f"The explanation has {len(shown)} page(s); `/why {len(shown)}` shows the last."
    return shown[page - 1]
