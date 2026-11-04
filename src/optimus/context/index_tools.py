"""The four read-only index tools (Plan 12.10 Task 4; ADR-038): SEARCH, OUTLINE, SYMBOLS and LIST.

Every answer states what it covered, so "not found" means not found in what was searched. Files pass the file policy when they are
read, and an index record whose file has changed is dropped and counted, never shown. Bytes, results and time are bounded, a cancel
stops a scan, and nothing here writes: a literal SEARCH reads disk at query time and its lines stay in this process's memory.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Sequence
from typing import Final

from context_engine.code_index import parse_file
from context_engine.index_worker import IndexStorage, StorageRefusedError, StorageUnavailableError
from context_engine.retrieval import MAX_SYMBOL_CHARS, Hit, Retrieval, Retriever, query_terms

MAX_RESULT_BYTES: Final = 8 * 1024
SEARCH_RESULTS: Final = 10
SYMBOL_RESULTS: Final = 20
LIST_ENTRIES: Final = 200
OUTLINE_ENTRIES: Final = 200
LITERAL_SECONDS: Final = 2.0
LITERAL_BYTES: Final = 64 * 1024 * 1024
LITERAL_RESULTS: Final = 20
_LINE_CHARS: Final = 240

TOOL_NAMES: Final = {"SEARCH": "index_search", "OUTLINE": "index_outline", "SYMBOLS": "index_symbols", "LIST": "index_list"}


def _bounded(lines: Sequence[str]) -> str:
    """Whole lines up to the byte limit, saying how many did not fit."""
    kept: list[str] = []
    size = 0
    for index, line in enumerate(lines):
        size += len(line.encode("utf-8")) + 1
        if size > MAX_RESULT_BYTES - 64:
            kept.append(f"... {len(lines) - index} more lines left out by the size limit")
            break
        kept.append(line)
    return "\n".join(kept)


def _where(hit: Hit) -> str:
    return f"{hit.path}:{hit.start_line}-{hit.end_line}" if hit.start_line is not None else hit.path


class IndexTools:
    def __init__(self, *, retriever: Retriever, storage: IndexStorage, read: Callable[[str], bytes | None], listing: Callable[[], Sequence[str]],
                 cancelled: Callable[[], bool] = lambda: False, clock: Callable[[], float] = time.monotonic, unlisted: Callable[[], int] = lambda: 0,
                 unsaved_symbols: Callable[[str], Sequence[str]] = lambda _name: (), before_each: Callable[[], None] = lambda: None) -> None:
        self._before_each = before_each
        self._unlisted = unlisted
        self._unsaved_symbols = unsaved_symbols
        self._retriever = retriever
        self._storage = storage
        self._read = read
        self._listing = listing
        self._cancelled = cancelled
        self._clock = clock

    def run(self, tool: str, argument: str) -> str:
        self._before_each()
        return _bounded({"SEARCH": self.search, "OUTLINE": self.outline, "SYMBOLS": self.symbols, "LIST": self.list}[tool](argument))

    def _current(self, hit: Hit, seen: dict[str, str | None]) -> bool:
        if hit.path not in seen:
            data = self._read(hit.path)
            seen[hit.path] = None if data is None else hashlib.sha256(data).hexdigest()
        return seen[hit.path] == hit.file_hash

    @staticmethod
    def _coverage(result: Retrieval) -> str:
        if result.state != "ok":
            return f"Scope: the index could not answer ({result.state}), so this says nothing about the workspace. Use a quoted SEARCH, OUTLINE or LIST, which read disk."
        coverage = result.coverage
        state = "complete" if coverage.get("complete") else "still building"
        silent = [f"{name} {outcome}" for name, outcome in sorted(result.channels.items()) if outcome.startswith(("refused", "unavailable"))]
        missing = f" These searches did not answer, so they found nothing either way: {', '.join(silent)}." if silent else ""
        return f"Scope: index generation {result.epoch}, {state}, {coverage.get('files_indexed', 0)} of {coverage.get('files_total', 0)} files. Not finding something covers only this scope.{missing}"

    def search(self, query: str) -> list[str]:
        text = query.strip()
        if len(text) >= 2 and text[0] == text[-1] == '"':
            return self._literal(text[1:-1])
        result = self._retriever.retrieve(text)
        lines = [self._coverage(result)]
        seen: dict[str, str | None] = {}
        stale = 0
        shown = 0
        for item in result.ranked:
            if shown == SEARCH_RESULTS:
                break
            if not self._current(item.hit, seen):
                stale += 1
                continue
            summary = item.hit.signature or item.hit.description or item.hit.prose or ""
            lines.append(f"{_where(item.hit)} {item.hit.symbol or item.hit.kind}: {' '.join(summary.split())[:_LINE_CHARS]}")
            shown += 1
        if shown == 0 and result.state == "ok":
            lines.append("No matches in this scope.")
        if stale:
            lines.append(f"{stale} indexed results were left out because their files changed since they were indexed.")
        return lines

    def _literal(self, needle: str) -> list[str]:
        if not needle:
            return ["A quoted SEARCH needs some text between the quotes."]
        paths = list(self._listing())
        found: list[str] = []
        scanned = 0
        unread = 0
        spent = 0
        started = self._clock()
        why_stopped = ""
        for path in paths:
            if self._cancelled():
                why_stopped = "the turn was cancelled"
                break
            if self._clock() - started > LITERAL_SECONDS:
                why_stopped = "the time limit"
                break
            if spent > LITERAL_BYTES:
                why_stopped = "the size limit"
                break
            data = self._read(path)
            if data is None:
                unread += 1
                continue
            spent += len(data)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                unread += 1
                continue
            scanned += 1
            if needle not in text:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if needle in line:
                    found.append(f"{path}:{number}: {line.strip()[:_LINE_CHARS]}")
                    if len(found) == LITERAL_RESULTS:
                        why_stopped = "the result limit"
                        break
            if why_stopped:
                break
        scope = f"Scope: read {scanned} of {len(paths)} admitted files now" + (f", stopped by {why_stopped}." if why_stopped else ".")
        if unread:
            scope += f" {unread} are binary, empty or could not be read."
        scope += self._unseen_folders()
        return [scope, *(found or ["No matches in this scope."])]

    def _unseen_folders(self) -> str:
        count = self._unlisted()
        return f" {count} folders could not be listed, so what they hold is not covered." if count else ""

    def outline(self, path: str) -> list[str]:
        data = self._read(path)
        if data is None:
            return [f"{path} cannot be read: it does not exist or the file policy refuses it."]
        parsed = parse_file(path, data)
        entries = sorted((record for record in parsed.records if record.kind != "file"), key=lambda record: (record.start_line or 0, record.symbol or ""))
        if not entries:
            return [f"{path}: read now, language {parsed.language}, no symbols or sections this parser understands."]
        lines = [f"{path}: read now, language {parsed.language}, {len(entries)} entries."]
        lines.extend(f"{record.start_line}-{record.end_line} {record.symbol or record.kind}: {' '.join((record.signature or record.description or '').split())[:_LINE_CHARS]}" for record in entries[:OUTLINE_ENTRIES])
        return lines

    def symbols(self, name: str) -> list[str]:
        """The exact name first, then symbols that share its terms."""
        try:
            current = self._storage.call("coverage").get("current")
            if not current:
                return ["The index has published nothing yet, so this says nothing about the workspace. Use a quoted SEARCH."]
            epoch = current["epoch"]
            hits = [Hit.from_wire(record) for record in self._storage.call("query", mode="symbol", epoch=epoch, symbol=name, k=SYMBOL_RESULTS)["records"]] if len(name) <= MAX_SYMBOL_CHARS else []
            terms = query_terms(name)
            if terms:
                known = {hit.id for hit in hits}
                hits.extend(hit for hit in (Hit.from_wire(record) for record in self._storage.call("query", mode="lexical", epoch=epoch, terms=terms, k=SYMBOL_RESULTS, kinds=["symbol"])["records"]) if hit.id not in known)
        except (StorageRefusedError, StorageUnavailableError):
            return ["The index could not answer, so this says nothing about the workspace. Use a quoted SEARCH."]
        coverage = current["coverage"]
        state = "complete" if coverage.get("complete") else "still building"
        lines = [f"Scope: index generation {epoch}, {state}, {coverage.get('files_indexed', 0)} of {coverage.get('files_total', 0)} files."]
        seen: dict[str, str | None] = {}
        fresh = [hit for hit in hits if self._current(hit, seen)]
        unsaved = list(self._unsaved_symbols(name))
        lines.extend(unsaved)
        lines.extend(f"{_where(hit)} {hit.symbol}: {' '.join((hit.signature or '').split())[:_LINE_CHARS]}" for hit in fresh[:SYMBOL_RESULTS])
        if not fresh and not unsaved:
            lines.append("No matching symbols in this scope.")
        if len(fresh) < len(hits):
            lines.append(f"{len(hits) - len(fresh)} results were left out because their files changed since they were indexed.")
        return lines

    def list(self, folder: str) -> list[str]:
        prefix = "" if folder.strip() in {"", ".", "./"} else folder.strip().replace("\\", "/").strip("/") + "/"
        paths = self._listing()
        folders: dict[str, int] = {}
        files: list[str] = []
        for path in paths:
            if not path.startswith(prefix):
                continue
            head, separator, _rest = path[len(prefix):].partition("/")
            if separator:
                folders[head] = folders.get(head, 0) + 1
            else:
                files.append(head)
        if not folders and not files:
            return [f"Nothing the file policy admits is listed under {prefix or '.'}. Excluded files are not shown here.{self._unseen_folders()}"]
        entries = [f"{name}/ ({count} files)" for name, count in sorted(folders.items())] + sorted(files)
        lines = [f"Scope: {prefix or '.'} as the file policy admits it, {len(entries)} entries. Excluded files are not shown.{self._unseen_folders()}"]
        lines.extend(entries[:LIST_ENTRIES])
        if len(entries) > LIST_ENTRIES:
            lines.append(f"... {len(entries) - LIST_ENTRIES} more entries left out")
        return lines
