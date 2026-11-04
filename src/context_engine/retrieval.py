"""Hybrid retrieval over one index line (Plan 12.10 Task 4; ADR-038). Neutral: storage and the embedder are the worker's own ports.

One retrieval pins one published epoch, so everything it returns is one coherent generation. Channels are fused by reciprocal rank,
then stable ties. A rank says how channels agreed and is not confidence. A channel that cannot answer is reported as such and the
others carry on; nothing here raises for an outage, so a person's turn never fails because the index did. No generative call is made.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from .code_index import path_id, split_terms
from .index_worker import Embedder, IndexStorage, StorageRefusedError, StorageUnavailableError
from .repo_map import MapFile, RepoMap, build_repo_map, imports_of, neighbours, rank

RRF_K: Final = 60
# Agent-selected and frozen before evaluation. Structure means the person or the task named it, so it counts most; recency only nudges.
WEIGHTS: Final = {"lexical": 1.0, "dense": 1.0, "structure": 1.5, "recency": 0.25, "memory": 1.0}
CHANNEL_K: Final = 40
MAX_TERMS: Final = 64
MAX_SYMBOL_CHARS: Final = 256  # the route's limit, and no real symbol is longer
MAX_NAMED: Final = 8
MAP_SYMBOL_FILES: Final = 48
MAP_SYMBOLS_PER_FILE: Final = 12
_RECENT_FILES: Final = 8
_CATALOGUE_PAGE: Final = 256
_ATTEMPTS: Final = 2  # an epoch can expire while it is read; a second try sees the newer one
_MOVED: Final = frozenset({"EPOCH_EXPIRED", "NOT_PUBLISHED"})
_KIND_ORDER: Final = {"symbol": 0, "section": 1, "file": 2}


@dataclass(frozen=True)
class Hit:
    id: str
    kind: str
    path: str
    file_hash: str
    language: str = "unsupported"
    symbol: str | None = None
    signature: str | None = None
    description: str | None = None
    prose: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    modified: int | None = None

    @classmethod
    def from_wire(cls, record: Mapping[str, Any]) -> Hit:
        return cls(id=record["id"], kind=record["kind"], path=record["path"], file_hash=record["file_hash"], language=record.get("language", "unsupported"),
                   symbol=record.get("symbol") or None, signature=record.get("signature") or None, description=record.get("description") or None,
                   prose=record.get("prose") or None, start_line=record.get("start_line"), end_line=record.get("end_line"), modified=record.get("modified"))


@dataclass(frozen=True)
class Ranked:
    hit: Hit
    score: float
    ranks: Mapping[str, int]


@dataclass(frozen=True)
class CatalogueFile:
    path: str
    file_hash: str
    language: str
    modified: int | None
    description: str | None


@dataclass(frozen=True)
class Retrieval:
    """`state` is ok, unpublished (nothing indexed yet), unavailable or expired. `channels` says what each channel did."""

    state: str
    epoch: int | None = None
    coverage: Mapping[str, Any] = field(default_factory=dict)
    revision: str | None = None
    ranked: tuple[Ranked, ...] = ()
    channels: Mapping[str, str] = field(default_factory=dict)


def query_terms(text: str) -> list[str]:
    """Search terms for a person's words, folded the way records are, in first-seen order. The route refuses anything else."""
    seen: dict[str, None] = {}
    for word in text.split():
        for term in split_terms([word]).split():
            seen.setdefault(term)
    return list(seen)[:MAX_TERMS]


def fuse(channels: Mapping[str, Sequence[Hit]], *, named: Iterable[str] = (), weights: Mapping[str, float] = WEIGHTS, k: int = RRF_K) -> tuple[Ranked, ...]:
    """Reciprocal rank fusion. Ties go to a named file, then to symbols over sections over files, then path and line, so the same input
    always gives the same order."""
    chosen = set(named)
    hits: dict[str, Hit] = {}
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for channel in sorted(channels):
        for position, hit in enumerate(channels[channel], start=1):
            hits.setdefault(hit.id, hit)
            scores[hit.id] = scores.get(hit.id, 0.0) + weights.get(channel, 0.0) / (k + position)
            ranks.setdefault(hit.id, {}).setdefault(channel, position)

    def order(identity: str) -> tuple[float, bool, int, str, int, str]:
        hit = hits[identity]
        return (-round(scores[identity], 12), hit.path not in chosen, _KIND_ORDER.get(hit.kind, 3), hit.path, hit.start_line or 0, identity)

    return tuple(Ranked(hits[identity], scores[identity], ranks[identity]) for identity in sorted(hits, key=order))


def read_catalogue(storage: IndexStorage, epoch: int) -> list[CatalogueFile]:
    """Every file of a published epoch, without its contents. It costs one call per page, so the caller keeps it per epoch."""
    files: list[CatalogueFile] = []
    cursor = None
    while True:
        page = storage.call("catalogue", epoch=epoch, limit=_CATALOGUE_PAGE, **({} if cursor is None else {"cursor": cursor}))
        files.extend(CatalogueFile(item["path"], item["file_hash"], item.get("language", "unsupported"), item.get("modified"), item.get("description")) for item in page["files"])
        cursor = page.get("cursor")
        if cursor is None:
            return files


def seed_map(storage: IndexStorage, epoch: int, catalogue: Sequence[CatalogueFile], *, budget_chars: int) -> RepoMap:
    """The repository map: every file ranked by its observed imports, with symbols for the best-ranked. It takes no focus, so it is the
    same text for every prompt of a generation and belongs in a cacheable prefix."""
    bare = [MapFile(item.path, imports_of(item.description)) for item in catalogue]
    scores = rank(bare)
    best = sorted(bare, key=lambda item: (-round(scores.get(item.path, 0.0), 12), item.path))[:MAP_SYMBOL_FILES]
    symbols: dict[str, tuple[str, ...]] = {}
    for item in best:
        reply = storage.call("query", mode="path", epoch=epoch, path_id=path_id(item.path), k=MAP_SYMBOLS_PER_FILE, kinds=["symbol"])
        symbols[item.path] = tuple(sorted(record["symbol"] for record in reply["records"] if record.get("symbol")))
    return build_repo_map([MapFile(item.path, item.imports, symbols.get(item.path, ())) for item in bare], budget_chars=budget_chars)


class Retriever:
    def __init__(self, storage: IndexStorage, embedder: Embedder | None, *, catalogue: Callable[[int], Sequence[CatalogueFile]] | None = None, cancelled: Callable[[], bool] = lambda: False) -> None:
        self._storage = storage
        self._embedder = embedder
        self._catalogue = catalogue or (lambda epoch: read_catalogue(storage, epoch))
        self._cancelled = cancelled

    def retrieve(self, text: str, *, named_paths: Sequence[str] = (), named_symbols: Sequence[str] = (), memory: Sequence[Hit] = ()) -> Retrieval:
        for _ in range(_ATTEMPTS):
            try:
                return self._once(text, named_paths, named_symbols, memory)
            except StorageRefusedError as exc:
                if exc.code not in _MOVED:
                    return Retrieval("unpublished" if exc.code == "SCOPE_UNKNOWN" else "unavailable", channels={"all": f"refused:{exc.code}"})
            except StorageUnavailableError:
                return Retrieval("unavailable", channels={"all": "unavailable"})
        return Retrieval("expired", channels={"all": "the generation moved during every attempt"})

    def _once(self, text: str, named_paths: Sequence[str], named_symbols: Sequence[str], memory: Sequence[Hit]) -> Retrieval:
        current = self._storage.call("coverage").get("current")
        if not current:
            return Retrieval("unpublished", channels={"all": "nothing has been published"})
        epoch: int = current["epoch"]
        channels: dict[str, list[Hit]] = {"memory": list(memory)}
        report: dict[str, str] = {"memory": f"{len(memory)} results" if memory else "no authorized source"}

        def run(name: str, ask: Callable[[], list[Hit]]) -> None:
            if self._cancelled():
                report[name] = "not asked: the turn was cancelled"
                return
            try:
                channels[name] = ask()
                report[name] = f"{len(channels[name])} results"
            except StorageRefusedError as exc:
                if exc.code in _MOVED:
                    raise
                report[name] = f"refused:{exc.code}"
            except StorageUnavailableError:
                report[name] = "unavailable"

        run("lexical", lambda: self._lexical(text, epoch))
        if self._embedder is None:
            report["dense"] = "no embedding artifact"
        else:
            run("dense", lambda: self._dense(text, epoch))
        run("structure", lambda: self._structure(named_paths, named_symbols, epoch))
        run("recency", lambda: self._recent(epoch))
        ranked = fuse(channels, named=named_paths)
        return Retrieval("ok", epoch, current["coverage"], current.get("revision"), ranked, report)

    def _ask(self, epoch: int, **query: Any) -> list[Hit]:
        return [Hit.from_wire(record) for record in self._storage.call("query", epoch=epoch, **query)["records"]]

    def _lexical(self, text: str, epoch: int) -> list[Hit]:
        terms = query_terms(text)
        return self._ask(epoch, mode="lexical", terms=terms, k=CHANNEL_K) if terms else []

    def _dense(self, text: str, epoch: int) -> list[Hit]:
        assert self._embedder is not None
        try:
            embedded = self._embedder.embed([text])[0]
        except Exception as exc:  # a native model has no error contract, and a person's turn never fails because the index did
            raise StorageUnavailableError("the embedder failed") from exc
        return self._ask(epoch, mode="dense", vector=base64.b64encode(embedded).decode("ascii"), k=CHANNEL_K)

    def _structure(self, named_paths: Sequence[str], named_symbols: Sequence[str], epoch: int) -> list[Hit]:
        """Only what was named or observed: the named files, the named symbols, then what the named files import or are imported by."""
        hits: list[Hit] = []
        for symbol in [name for name in named_symbols if len(name) <= MAX_SYMBOL_CHARS][:MAX_NAMED]:
            hits.extend(self._ask(epoch, mode="symbol", symbol=symbol, k=MAX_NAMED))
        chosen = list(named_paths[:MAX_NAMED])
        for path in chosen:
            hits.extend(self._ask(epoch, mode="path", path_id=path_id(path), k=CHANNEL_K))
        if chosen:
            files = [MapFile(item.path, imports_of(item.description)) for item in self._catalogue(epoch)]
            for path in neighbours(files, chosen)[:MAX_NAMED]:
                hits.extend(self._ask(epoch, mode="path", path_id=path_id(path), k=MAX_NAMED, kinds=["file", "symbol"]))
        return hits

    def _recent(self, epoch: int) -> list[Hit]:
        dated = [item for item in self._catalogue(epoch) if item.modified is not None]
        dated.sort(key=lambda item: (-(item.modified or 0), item.path))
        hits: list[Hit] = []
        for item in dated[:_RECENT_FILES]:
            hits.extend(self._ask(epoch, mode="path", path_id=path_id(item.path), k=1, kinds=["file"]))
        return hits
