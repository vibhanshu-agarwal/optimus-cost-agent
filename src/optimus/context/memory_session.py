"""One ACP session's context index (Plan 12.10 Task 4; ADR-038): its background worker, and what each turn gets from it.

The worker runs while the session is open; closing the session pauses indexing. The scope is recomputed for each turn, so changing
branch moves to that branch's own line at once and the old branch's records are never current evidence. Anything short of a usable
index keeps today's context and says so. Turns never wait on the worker, beyond a short bounded nudge when a chosen file has changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

from context_engine.code_index import PARSER_VERSION, parse_file, path_id
from context_engine.context_pack import Pack, assemble_pack
from context_engine.index_worker import Embedder, IndexStorage, IndexWorker, StorageRefusedError, StorageUnavailableError, WorkerOutcome
from context_engine.repo_map import MapFile, RepoMap, build_repo_map
from context_engine.retrieval import RRF_K, WEIGHTS, CatalogueFile, Retrieval, Retriever, query_terms, read_catalogue, seed_files
from optimus.acp.trusted_paths import TrustedPathError, resolve_workspace_identity
from optimus.agent.workspace_context import (
    DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES,
    NO_HINTS,
    RankingHints,
    WorkspaceContextResult,
    WorkspaceReferenceDiagnostic,
    WorkspaceReferenceStatus,
    assemble_workspace_context_for_prompt,
    blocking_from_diagnostics,
    extract_file_references,
    on_disk,
    rank_ambiguity,
    resolve_task_references,
    verified_hints,
)
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.context_budget import POLICY_VERSION, BudgetPolicy
from optimus.context.index_tools import IndexTools
from optimus.context.memory_workspace import (
    EmbedderUnavailableError,
    FastembedEmbedder,
    GatewayIndexStorage,
    WorkspaceIndexSource,
    current_branch,
    index_scope,
)
from optimus.context.project_registry import ProjectRegistration, ProjectRegistry, ProjectRegistryError
from optimus.guardrails.file_policy import FilePolicy, FilePurpose
from optimus_security.memory_index_config import MemoryIndexConfig

PACK_SHARE: Final = 0.25  # of the route's usable input; history and evidence keep the rest
PACK_MAX_TOKENS: Final = 16_384  # agent-selected, frozen before evaluation
MANIFEST_SCHEMA: Final = "optimus.context-manifest.v2"  # Plan 12.14: v2 records the pack's budget policy; v1 reads as legacy or unknown
MAP_CHARS: Final = 12_000
RETRY_SECONDS: Final = 30.0
# During a build each publication is a new epoch and names barely change between them. A catalogue only suggests what to ask for, and every
# record is then asked for at the retrieval's own epoch, so an older one can miss a new file but cannot make a record current.
CATALOGUE_SECONDS: Final = 60.0
CATALOGUE_THREAD: Final = "context-catalogue"  # reads one page per 256 files, so never on a turn's thread
MAP_SECONDS: Final = 300.0  # the map sits in the cacheable prefix, so a build does not churn it
_RECONCILE_ATTEMPTS: Final = 2
_RECONCILE_WAIT_SECONDS: Final = 1.0
_MANIFESTS_KEPT: Final = 200
MAX_BUFFER_BYTES: Final = 8 * 1024 * 1024
MAX_BUFFERS: Final = 8
_MAP_CHECKS: Final = 4
_SYMBOL_OWNERS: Final = 8
_MAX_DIRTY_CHECKED: Final = 64
BRANCH_MOVED: Final = "BRANCH_MOVED"
_QUERY_CHARS: Final = 2_000
_MAX_SYMBOLS: Final = 8
_HINT_QUERIES: Final = 16  # shortcut: label queries for the first 16 candidates; the rest keep the map's symbols
# A name someone wrote as code: backticked, dotted, or with an inner capital or underscore. Ordinary words are not symbols.
_SYMBOL_WORD = re.compile(r"`([A-Za-z_][\w.]*)`|\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+|[a-z]+[A-Z]\w*|[A-Z][a-z0-9]+[A-Z]\w*|[a-z]+_\w+)\b")
_BACKTICKED = re.compile(r"`([A-Za-z_][\w.]*)`")
_LOG = logging.getLogger(__name__)


def named_symbols(text: str) -> tuple[str, ...]:
    found: dict[str, None] = {}
    for match in _SYMBOL_WORD.finditer(text):
        found.setdefault(match.group(1) or match.group(2))
        if len(found) == _MAX_SYMBOLS:
            break
    return tuple(found)


def _same_text(left: bytes, right: bytes) -> bool:
    """An editor normalizes line endings in its buffer, so a saved CRLF file must not read as an unsaved edit."""
    return left.replace(b"\r\n", b"\n") == right.replace(b"\r\n", b"\n")


@dataclass(frozen=True)
class GroundingReport:
    """What an answer cited and whether it exists in what was inspected. It never decides whether the answer is right."""

    resolved: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()  # files, checked against the disk now
    ambiguous: tuple[str, ...] = ()
    not_in_index: tuple[str, ...] = ()  # symbols with no definition in that generation: reading every file for each reply is not affordable
    generation: int | None = None

    def note(self) -> str | None:
        parts = []
        if self.unresolved:
            parts.append("not found in the inspected scope: " + ", ".join(self.unresolved))
        if self.not_in_index:
            parts.append(f"no definition in index generation {self.generation}, and the disk was not exhaustively checked: " + ", ".join(self.not_in_index))
        if self.ambiguous:
            parts.append("matches more than one file: " + ", ".join(self.ambiguous))
        return "; ".join(parts) or None


@dataclass
class _Scope:
    identity: str
    branch: str
    storage: IndexStorage


class _BranchPinned:
    """One pass's storage. Once the worktree has left the branch the pass belongs to, what it reads next is another branch's files, so it
    may not write them into this line."""

    def __init__(self, inner: IndexStorage, on_branch: Callable[[], bool]) -> None:
        self._inner = inner
        self._on_branch = on_branch

    def call(self, op: str, **fields: Any) -> dict[str, Any]:
        if op in {"batch", "generation"} and not self._on_branch():
            raise StorageRefusedError(BRANCH_MOVED)
        return self._inner.call(op, **fields)


class _RefreshCancelled(Exception):
    """A catalogue refresh's line was retired, or its session stopped, between two pages."""


class _Cancellable:
    """A refresh's storage: once its line is retired it asks for nothing more."""

    def __init__(self, inner: IndexStorage, cancelled: Callable[[], bool]) -> None:
        self._inner = inner
        self._cancelled = cancelled

    def call(self, op: str, **fields: Any) -> dict[str, Any]:
        if self._cancelled():
            raise _RefreshCancelled
        return self._inner.call(op, **fields)


@dataclass
class _Cached:
    identity: str = ""
    epoch: int = 0
    at: float = 0.0
    files: list[CatalogueFile] = field(default_factory=list)
    complete: bool = False


@dataclass
class _CachedMap:
    identity: str
    at: float
    files: list[MapFile]
    hashes: dict[str, str]
    epoch: int = 0  # the generation the hashes and symbols are from


class MemorySession:
    def __init__(self, *, policy: FilePolicy, registration: ProjectRegistration, storage_for: Callable[[str], IndexStorage], embedder_for: Callable[[], Embedder],
                 embedding_identity: str, parser_version: str, manifest_root: Path, clock: Callable[[], float] = time.monotonic,
                 branch_of: Callable[[Path], str] = current_branch) -> None:
        self._policy = policy
        self._registration = registration
        self._storage_for = storage_for
        self._embedder_for = embedder_for
        self._embedding_identity = embedding_identity
        self._parser_version = parser_version
        self._manifest_root = manifest_root
        self._clock = clock
        self._branch_of = branch_of
        self._source = WorkspaceIndexSource(FilePolicy(policy.root))  # the worker's thread has its own, so neither sees the other's ignore files move
        self._embedder: Embedder | None = None
        self._unusable: str | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._cancel = threading.Event()
        self._busy = threading.Event()
        self._lock = threading.Lock()
        self._priority: list[str] = []
        self._thread: threading.Thread | None = None
        self._last_outcome: WorkerOutcome | None = None
        self._indexed_revision: tuple[str, bool] | None = None
        self._indexed_changes: tuple[tuple[str, int, int], ...] | None = None  # Git's changed files at the last complete pass
        self._branch_asks = 0
        self._branch_answered = 0
        self._scope = self._new_scope(self._branch_of(policy.root))
        self._catalogue = _Cached()
        self._catalogue_wanted: tuple[_Scope, int, bool] | None = None
        self._catalogue_thread: threading.Thread | None = None
        self._catalogue_idle = threading.Event()
        self._catalogue_idle.set()
        self._map: _CachedMap | None = None
        self._listed: tuple[str, ...] | None = None
        self._unlisted = 0

    # --- the worker ---------------------------------------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="context-index", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Pause indexing without waiting: the worker stops at its next step and releases its leases, which also expire on their own."""
        self._stop.set()
        with self._lock:
            self._cancel.set()
        self._wake.set()

    def close(self) -> None:
        self.stop()
        if self._thread is not None:
            self._thread.join(10)
        self._catalogue_idle.wait(10)  # a refresh stops at its next page

    def _on_branch(self, branch: str) -> Callable[[], bool]:
        return lambda: self._branch_of(self._policy.root) == branch

    def _new_scope(self, branch: str) -> _Scope:
        identity = index_scope(self._registration, branch=branch, embedding=self._embedding_identity, parser_version=self._parser_version)
        return _Scope(identity, branch, self._storage_for(identity))

    def _current_scope(self) -> _Scope:
        """The scope for this moment. A new branch cancels whatever pass the old one has running and starts its own. Git can stall and the
        event loop takes this lock to stop a session, so the branch is asked for outside it, and an older answer never undoes a newer one."""
        with self._lock:
            self._branch_asks += 1
            ask = self._branch_asks
        branch = self._branch_of(self._policy.root)
        found = self._new_scope(branch)
        with self._lock:
            if ask > self._branch_answered:
                self._branch_answered = ask
                if branch != self._scope.branch:
                    self._scope = found
                    self._catalogue = _Cached()
                    self._map = None
                    self._indexed_revision = None
                    self._cancel.set()
                    self._wake.set()
            return self._scope

    def request_pass(self, priority: Sequence[str] = ()) -> None:
        with self._lock:
            self._priority = list(dict.fromkeys((*priority, *self._priority)))
        self._wake.set()

    def _priorities(self) -> Sequence[str]:
        with self._lock:
            return tuple(self._priority)

    def _priorities_and_changes(self) -> Sequence[str]:
        """What a person is looking at, then what Git says they changed, so an edit is written before the tree is walked."""
        return (*self._priorities(), *(self._source.dirty_paths() or ()))

    def _loop(self) -> None:
        """A failure here must not leave a thread dead behind a status that still says building, so it ends indexing and says why."""
        try:
            self._embedder = self._embedder_for()
            self._passes()
        except EmbedderUnavailableError as exc:
            self._unusable = exc.code
        except Exception as exc:  # a native model has no error contract
            self._unusable = f"INDEX_WORKER_FAILED:{type(exc).__name__}"
            _LOG.warning("context index worker stopped: %s", type(exc).__name__)

    def _passes(self) -> None:
        assert self._embedder is not None
        self._wake.set()
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            self._current_scope()  # a switch no turn has noticed yet
            with self._lock:  # against stop() and a branch change: a cancel meant for this pass must land on this pass's event
                if self._stop.is_set():
                    return
                self._cancel = threading.Event()
                scope = self._scope
            # Size and time are a hint. A file a turn proved has changed gets its pass even if they say nothing moved. A named file, or a
            # Git change not seen at the last complete pass, goes straight to the worker, which takes the revision itself: scanning it here
            # as well put a whole-tree stat (3 s on 10,255 files) before the edit was written.
            changed = self._source.changed_facts()
            if not self._priorities() and changed == self._indexed_changes and self._source.revision() == self._indexed_revision:
                continue
            storage = _BranchPinned(self._storage_for(scope.identity), self._on_branch(scope.branch))
            worker = IndexWorker(self._source, storage, self._embedder, owner=secrets.token_hex(16), priority=self._priorities_and_changes, foreground_busy=self._busy.is_set)
            outcome = worker.run(self._cancel)
            self._last_outcome = outcome
            if outcome.detail == BRANCH_MOVED:
                self._wake.set()
                continue
            if outcome.state == "complete":
                with self._lock:
                    self._priority = []
                    if scope is self._scope:  # two branches at one commit read as one revision, so this must not vouch for the new line
                        self._indexed_revision, self._indexed_changes = worker.revision, changed
                if outcome.epoch is not None:  # the next turn's suggestions, read now rather than when it asks
                    self._catalogue_for(scope, outcome.epoch, True)
            elif outcome.state in {"paused", "held", "refused"} and not self._stop.is_set():
                self._wake.wait(RETRY_SECONDS)
                self._wake.set()

    @contextmanager
    def _foreground(self) -> Iterator[None]:
        """A person's turn is doing index work: the worker gives way between its steps."""
        self._busy.set()
        try:
            yield
        finally:
            self._busy.clear()

    # --- what a turn sees ---------------------------------------------------------------------------------------------

    def status(self) -> str:
        """One line for a person. Nothing here names a file or holds any content."""
        if self._unusable is not None:
            return f"Context index: not updating ({self._unusable}). Turns use what is already indexed, or today's context if nothing is."
        try:
            current = self._current_scope().storage.call("coverage").get("current")
        except StorageRefusedError as exc:
            if str(exc) != "SCOPE_UNKNOWN":  # the route knows a scope from its first batch, so a new one is still building
                _LOG.warning("context index: the route refused: %s", exc)
                return "Context index: cannot be reached right now. This turn uses today's context."
            current = None
        except StorageUnavailableError as exc:
            _LOG.warning("context index: the route did not answer: %s (%s)", exc, type(exc.__cause__).__name__)
            return "Context index: cannot be reached right now. This turn uses today's context."
        if not current:
            return "Context index: building, nothing published yet. This turn uses today's context."
        coverage = current["coverage"]
        state = "ready" if coverage.get("complete") else "building"
        return f"Context index: {state}, {coverage.get('files_indexed', 0)} of {coverage.get('files_total', 0)} files."

    def _read(self, path: str) -> bytes | None:
        decision, data = self._policy.read(path, purpose=FilePurpose.AUTOMATIC)
        return data if decision.allowed else None

    def _catalogue_for(self, scope: _Scope, epoch: int, complete: bool) -> list[CatalogueFile] | None:
        """A turn's suggestions, or None. A turn never pages the catalogue or waits for it: without one it may use, it asks for one in
        the background and goes without, and its retrieval says so."""
        cached = self._catalogue
        if cached.identity == scope.identity and (cached.epoch == epoch or (not complete and not cached.complete and self._clock() - cached.at < CATALOGUE_SECONDS)):
            return cached.files
        with self._lock:  # a stopped session's refresh asks for nothing: its storage refuses first
            if scope is not self._scope:  # a retired line never displaces the current one's want
                return None
            wanted = self._catalogue_wanted
            if wanted is None or wanted[0] is not scope or epoch > wanted[1]:  # nor an older epoch a newer one
                self._catalogue_wanted = (scope, epoch, complete)
            if self._catalogue_thread is None:
                self._catalogue_idle.clear()
                self._catalogue_thread = threading.Thread(target=self._refresh_catalogues, name=CATALOGUE_THREAD, daemon=True)
                self._catalogue_thread.start()
        return None

    def _refresh_catalogues(self) -> None:
        """One read at a time; wants that arrive meanwhile collapse into the newest."""
        while True:
            with self._lock:
                wanted, self._catalogue_wanted = self._catalogue_wanted, None
                if wanted is None:
                    self._catalogue_thread = None
                    self._catalogue_idle.set()
                    return
            scope, epoch, complete = wanted
            started = self._clock()
            try:
                files = read_catalogue(_Cancellable(scope.storage, lambda: self._stop.is_set() or scope is not self._scope), epoch)  # noqa: B023 - used before the next loop
            except _RefreshCancelled:
                continue
            except Exception as exc:  # a turn's suggestions are optional; the next turn asks again
                _LOG.info("context index catalogue not read: %s", getattr(exc, "code", type(exc).__name__))
                continue
            self._publish_catalogue(scope, epoch, started, files, complete)

    def _publish_catalogue(self, scope: _Scope, epoch: int, at: float, files: list[CatalogueFile], complete: bool) -> None:
        """Only the current line's, and never an older epoch over a newer one."""
        with self._lock:
            held = self._catalogue
            if scope is self._scope and (held.identity != scope.identity or epoch >= held.epoch):
                self._catalogue = _Cached(scope.identity, epoch, at, files, complete)

    def wait_for_catalogue(self, timeout: float) -> bool:
        """True once no catalogue read is wanted or running. For measurement and tests: a turn never waits for one."""
        return self._catalogue_idle.wait(timeout)

    def turn(self, *, cancelled: Callable[[], bool] = lambda: False) -> MemoryTurn:
        self._policy.forget_ignore_files()
        scope = self._current_scope()
        self.request_pass()
        retriever = Retriever(scope.storage, self._embedder, catalogue=lambda epoch, complete: self._catalogue_for(scope, epoch, complete), cancelled=cancelled)
        overlay: dict[str, bytes] = {}

        def read(path: str) -> bytes | None:
            """The policy judges now, so unsaved text it has since refused goes as the file on disk would."""
            disk = self._read(path)
            if path not in overlay:
                return disk
            if disk is None:
                del overlay[path]
                return None
            return overlay[path]

        def unsaved_symbols(name: str) -> list[str]:
            wanted = set(query_terms(name))
            parsed = [(path, data) for path in list(overlay) if (data := read(path)) is not None]
            return [
                f"{path}:{record.start_line}-{record.end_line} {record.symbol}: {' '.join((record.signature or '').split())[:240]} (unsaved)"
                for path, data in parsed
                for record in parse_file(path, data).records
                if record.symbol and (record.symbol == name or wanted & set(query_terms(record.symbol)))
            ]

        def changed(path: str) -> None:
            if path not in overlay:  # the index is not wrong about a file whose unsaved text merely differs
                self.request_pass((path,))

        # A tool answers about the disk as it is now: a person or the agent may have just made the file being asked about.
        tools = IndexTools(retriever=retriever, storage=scope.storage, read=read, listing=lambda: self.listing(fresh=True), cancelled=cancelled, clock=self._clock,
                           unlisted=lambda: self._unlisted, unsaved_symbols=unsaved_symbols, before_each=self._policy.forget_ignore_files, changed=changed)
        return MemoryTurn(self, scope, retriever, tools, cancelled, overlay, read)

    def listing_for(self, references: Sequence[str]) -> Sequence[str]:
        """A listing current enough to resolve these. The cached one will do only for exact paths with a folder in them and still admitted:
        a bare name's owners can change without it, even when one of them sits at the root."""
        listed = self.listing()
        known = set(listed)
        admits = self._policy.admitter()
        if all("/" in reference.replace("\\", "/") and reference in known and admits(reference) for reference in references):
            return listed
        return self.listing(fresh=True)

    def repo_map(self, scope: _Scope) -> str:
        """The stable prefix. During a build its input is refreshed at most once per `MAP_SECONDS`; a failure gives no map, never a failed
        turn. What it renders is checked each time, because a cache's age never makes a record true."""
        self._policy.forget_ignore_files()
        cached = self._map if self._map is not None and self._map.identity == scope.identity else None
        if cached is None or self._clock() - cached.at >= MAP_SECONDS:
            try:
                current = scope.storage.call("coverage").get("current")
                if current:
                    catalogue = read_catalogue(scope.storage, current["epoch"])  # exactly this epoch: its hashes are what the symbols below are checked against
                    self._publish_catalogue(scope, current["epoch"], self._clock(), catalogue, bool(current["coverage"].get("complete")))  # the turn's retrieval needs the same pages
                    cached = _CachedMap(scope.identity, self._clock(), seed_files(scope.storage, current["epoch"], catalogue), {item.path: item.file_hash for item in catalogue},
                                        current["epoch"])
                    self._map = cached
                elif cached is None:
                    _LOG.info("context index map empty: no generation published yet")
                    return ""
            except (StorageRefusedError, StorageUnavailableError) as exc:
                if cached is None:  # the turn goes on without a map; the cause is kept (Plan 12.14: G2 run 2's first map came back empty unexplained)
                    _LOG.warning("context index map empty: the store did not answer: %s", getattr(exc, "code", None) or str(exc) or type(exc).__name__)
                    return ""
        return self._verified_map(cached).text

    def _verified_map(self, cached: _CachedMap) -> RepoMap:
        """What the text would name, against the policy and the disk: a file now refused or gone leaves the map, and one that changed keeps
        its path and loses its symbols. Only rendered files are checked, so this costs the map's size and not the repository's."""
        files = cached.files
        admits = self._policy.admitter()
        for _ in range(_MAP_CHECKS):
            built = build_repo_map(files, budget_chars=MAP_CHARS)
            shown = set(built.paths)
            kept: list[MapFile] = []
            changed = False
            for item in files:
                if item.path not in shown:
                    kept.append(item)
                elif not admits(item.path):
                    changed = True
                elif not item.symbols:
                    kept.append(item)
                elif (data := self._read(item.path)) is not None and hashlib.sha256(data).hexdigest() == cached.hashes.get(item.path):
                    kept.append(item)
                else:
                    kept.append(MapFile(item.path))
                    changed = True
                    if data is not None:
                        self.request_pass((item.path,))
                        cached.at = float("-inf")  # read the repaired generation next time, or this asks for a pass on every turn until the map ages out
            if not changed:
                return built
            files = kept
        return RepoMap("", 0, len(files))

    def hints_for(self, scope: _Scope) -> Callable[[Sequence[str], Sequence[str]], RankingHints]:
        """An ambiguous reference's verified hints (Plan 12.13 #242), from this scope's map. A turn assembles before its prompt reads the
        map, so the first ambiguity of a session reads it here, once (Task 4's real-index run found the hints missing). None can be read:
        no hints. A label comes from the map's own generation, and only for a file whose bytes still match it; a failed query falls
        back to the map."""

        def held() -> _CachedMap | None:
            return self._map if self._map is not None and self._map.identity == scope.identity else None

        def hints(candidates: Sequence[str], resolved: Sequence[str]) -> RankingHints:
            cached = held()
            if cached is None:
                self.repo_map(scope)  # the turn's prompt reads the same map next, from this cache
                cached = held()
            if cached is None:
                return NO_HINTS
            files = {item.path: item for item in cached.files}
            for path in [path for path in candidates if path in files][:_HINT_QUERIES]:
                try:
                    reply = scope.storage.call("query", mode="path", epoch=cached.epoch, path_id=path_id(path), k=20, kinds=["symbol", "section"])
                except (StorageRefusedError, StorageUnavailableError):
                    continue
                labels = sorted({record.get("symbol") or record.get("label") or "" for record in reply.get("records", ())} - {""})
                files[path] = MapFile(path, files[path].imports, tuple(labels))
            return verified_hints(candidates, resolved, files=list(files.values()), hashes=cached.hashes, read=self._read)

        return hints

    def write_manifest(self, run_id: str, document: Mapping[str, Any]) -> None:
        """An explanation of one turn's selection, never a historical pack: paths, hashes, symbols, ranks and reasons. Failing to
        write it never fails the turn; the oldest beyond the limit are removed."""
        folder = self._manifest_root / self._scope.identity[:16]
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)[:80]
        try:
            folder.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(document, handle, indent=2, sort_keys=True, ensure_ascii=True)
            os.replace(temporary, folder / f"{safe}.json")
            kept = sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True)
            for old in kept[_MANIFESTS_KEPT:]:
                old.unlink(missing_ok=True)
        except OSError:
            return

    def listing(self, *, fresh: bool = False) -> Sequence[str]:
        """The files disk tools may see, judged by name. Not the index's own eligibility: a file too large to index can still be read or named."""
        if fresh or self._listed is None:
            self._listed, self._unlisted = self._policy.names()
        return self._listed

    def disk_facts(self) -> tuple[str, int]:
        """What a generation's revision would be now, and how many files are too large to index. This thread's own source and policy."""
        return WorkspaceIndexSource(self._policy).disk_facts()

    def dirty_paths(self) -> tuple[str, ...] | None:
        return WorkspaceIndexSource(self._policy).dirty_paths()

    @property
    def policy(self) -> FilePolicy:
        return self._policy

    def foreground(self) -> Any:
        return self._foreground()


def pack_limits(pack_budget: BudgetPolicy | None, usable_input_tokens: int) -> tuple[int, int | None]:
    """The pack's budget and soft target (Plan 12.14): the route's own, computed once before preparation; without one, M1's legacy budget."""
    if pack_budget is None:
        return min(int(usable_input_tokens * PACK_SHARE), PACK_MAX_TOKENS), None
    return pack_budget.ceiling, pack_budget.target


class MemoryTurn:
    """One turn's view: one scope, and the same read path for the pack and the tools."""

    def __init__(self, session: MemorySession, scope: _Scope, retriever: Retriever, tools: IndexTools, cancelled: Callable[[], bool], overlay: dict[str, bytes], read: Callable[[str], bytes | None]) -> None:
        self._overlay = overlay  # the selected files' unsaved text: this turn's RAM only, never indexed, embedded or written
        self._read = read
        self._session = session
        self._scope = scope
        self._retriever = retriever
        self.tools = tools
        self._cancelled = cancelled
        self.manifest: dict[str, Any] = {}
        self._run_id = ""
        self.on_tool: Callable[[str, str, str, str], None] | None = None  # the host's live tool cards
        self.read_buffer: Callable[[str], str | None] | None = None  # set only when the client advertised it can read its own buffers
        self.seen_requests: set[tuple[str, str]] = set()

    def repo_map(self) -> str:
        return self._session.repo_map(self._scope)

    def status(self) -> str:
        return self._session.status()

    def assemble(self, *, run_id: str, task: str, selection_text: str, model_id: str, estimate: Callable[[str], int], usable_input_tokens: int,
                 pack_budget: BudgetPolicy | None = None, overview_path: str | None = None) -> WorkspaceContextResult:
        """The turn's context. Blocking conditions are today's own, so each mode's handling of them is unchanged. An index that cannot
        answer gives today's context plus a line saying so; required evidence that does not fit is never quietly dropped. `overview_path`
        is the file a direct summary task asked for (file_outline.summary_target): with a model-aware budget, the pack may outline it when
        it alone is required and too large (Plan 12.14, D4), built from this turn's read, so an edit or unsaved buffer is current."""
        self._run_id = run_id
        policy = self._session.policy
        policy.forget_ignore_files()
        budget, target = pack_limits(pack_budget, usable_input_tokens)
        chosen = pack_budget or BudgetPolicy("legacy", budget, None)  # the policy this turn was prepared with, recorded on every manifest
        with self._session.foreground():
            named = extract_file_references(selection_text, on_disk(policy.root))  # whole paths decide whether the cached listing will do (#634)
            diagnostics = resolve_task_references(selection_text, policy, self._session.listing_for(named))
            diagnostics = rank_ambiguity(diagnostics, task, self._session.hints_for(self._scope))
            stop_reason, message = blocking_from_diagnostics(diagnostics)
            if stop_reason is not None:
                return self._blocked(diagnostics, stop_reason, message)
            required = tuple(dict.fromkeys(item.candidates[0] for item in diagnostics if item.status is WorkspaceReferenceStatus.RESOLVED))
            self._capture_buffers(required)
        retrieval, pack = self._retrieve(selection_text, required, estimate, budget, task, target, overview_path)
        if retrieval.state != "ok" or pack is None:
            return self._today(task=selection_text, retrieval=retrieval, prompt=task, policy=chosen)
        if not pack.complete:
            return self._incomplete(diagnostics, pack)
        coverage_line = self._coverage_line(retrieval, pack)
        text = f"{pack.text}\n{coverage_line}" if pack.text else coverage_line
        self.manifest = self._manifest(retrieval, pack, model_id=model_id, policy=chosen, task_terms=len(task.split()))
        self._session.write_manifest(run_id, self.manifest)
        omitted = tuple(dict.fromkeys(item.path for item in pack.selected if item.disclosure == "omitted"))
        shown = tuple(dict.fromkeys(item.path for item in pack.selected if item.disclosure != "omitted"))  # Codex CP2 review 3, finding 3
        return WorkspaceContextResult(text=text, max_total_bytes=DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES, used_bytes=len(text.encode("utf-8")), prioritized_paths=required, omitted_paths=omitted,
                                      diagnostics=diagnostics, file_sha256s=dict(pack.file_sha256s), shown_paths=shown, policy_revision=policy.revision())

    def _capture_buffers(self, required: Sequence[str]) -> None:
        """The editor's text for the files this task names, where it differs from disk. The policy decides first, so a denied file is
        never asked for. Only the selected files, so there is no search across unsaved work, and an editor that does not answer costs
        one wait and leaves this turn on disk."""
        self._overlay.clear()
        if self.read_buffer is None:
            return
        for path in required[:MAX_BUFFERS]:
            if self._cancelled():
                return
            disk = self._session._read(path)
            if disk is None:
                continue
            text = self.read_buffer(str(self._session.policy.root / path))
            if text is None or self._cancelled():
                return
            data = text.encode("utf-8", errors="replace")
            if not _same_text(data, disk) and b"\x00" not in data and len(data) <= MAX_BUFFER_BYTES:
                self._overlay[path] = data

    def _retrieve(self, text: str, required: Sequence[str], estimate: Callable[[str], int], budget: int, task: str, target: int | None = None,
                  overview_path: str | None = None) -> tuple[Retrieval, Pack | None]:
        query = text[:_QUERY_CHARS]
        symbols = named_symbols(task)
        pack: Pack | None = None
        for attempt in range(_RECONCILE_ATTEMPTS + 1):
            with self._session.foreground():
                retrieval = self._retriever.retrieve(query, named_paths=required, named_symbols=symbols)
                if retrieval.state != "ok":
                    return retrieval, None
                pack = assemble_pack(required=required, ranked=retrieval.ranked, read=self._read, estimate=estimate, budget_tokens=budget, target_tokens=target,
                                     overview_path=overview_path)
            # The wait below is outside: the worker gives way to a busy turn, so it could not do this repair while one was waiting for it.
            if not pack.stale_paths or attempt == _RECONCILE_ATTEMPTS or self._cancelled():
                return retrieval, pack
            self._session.request_pass(pack.stale_paths)
            time.sleep(_RECONCILE_WAIT_SECONDS)
        raise AssertionError("unreachable")

    def _today(self, *, task: str, retrieval: Retrieval, prompt: str | None = None, policy: BudgetPolicy | None = None) -> WorkspaceContextResult:
        self._overlay.clear()  # today's selection reads disk, so nothing else this turn may see other text
        result = assemble_workspace_context_for_prompt(self._session.policy.root, task=task, prompt=prompt)
        line = f"Context index: no usable generation ({retrieval.state}). These files are today's selection, not a ranked search."
        self.manifest = {"schema": MANIFEST_SCHEMA, "run_id": self._run_id, "retrieval": {"state": retrieval.state, "channels": dict(retrieval.channels)}}
        if policy is not None:  # no pack was built, but the turn's budget policy is still its own (Codex CP2 A3)
            self.manifest["config"] = {"budget_policy_version": POLICY_VERSION, "budget_policy": asdict(policy)}
        self._session.write_manifest(self._run_id, self.manifest)
        return WorkspaceContextResult(**{**vars(result), "text": f"{result.text}\n{line}" if result.text else line}) if result.blocking_stop_reason is None else result

    def _blocked(self, diagnostics: tuple[WorkspaceReferenceDiagnostic, ...], stop_reason: str, message: str | None) -> WorkspaceContextResult:
        return WorkspaceContextResult(text="", max_total_bytes=DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES, used_bytes=0, prioritized_paths=(), omitted_paths=(), diagnostics=diagnostics,
                                      blocking_stop_reason=stop_reason, blocking_message=message, policy_revision=self._session.policy.revision())

    def _incomplete(self, diagnostics: tuple[WorkspaceReferenceDiagnostic, ...], pack: Pack) -> WorkspaceContextResult:
        """Required evidence missing: an unreadable file is reported as one; otherwise the first is too large, which Agent turns into ranged reads."""
        unreadable = pack.text != "" or not any(item.disclosure == "required" for item in pack.selected)
        marked = []
        pending = set(pack.missing_required)
        first_large = True
        for item in diagnostics:
            path = item.candidates[0] if item.status is WorkspaceReferenceStatus.RESOLVED else None
            if path in pending and unreadable:
                marked.append(WorkspaceReferenceDiagnostic(item.reference, WorkspaceReferenceStatus.NOT_READABLE))
            elif path in pending and first_large:
                marked.append(WorkspaceReferenceDiagnostic(item.reference, WorkspaceReferenceStatus.TOO_LARGE, item.candidates))
                first_large = False
            else:
                marked.append(item)
        result = tuple(marked)
        stop_reason, message = blocking_from_diagnostics(result)
        return self._blocked(result, stop_reason or "REQUIRED_WORKSPACE_FILE_TOO_LARGE", message)

    def _coverage_line(self, retrieval: Retrieval, pack: Pack) -> str:
        coverage = retrieval.coverage
        state = "complete" if coverage.get("complete") else "still building"
        over = sum(1 for item in pack.selected if item.reason == "over the budget")
        parts = [f"--- scope: index generation {retrieval.epoch}, {state}, {coverage.get('files_indexed', 0)} of {coverage.get('files_total', 0)} files; "
                 f"{coverage.get('unsupported', 0)} in languages only listed, not parsed; channels: "
                 + ", ".join(f"{name} {outcome}" for name, outcome in sorted(retrieval.channels.items()))]
        if over:
            parts.append(f"{over} results left out by the budget")
        if pack.stale_paths:
            parts.append(f"incomplete: {len(pack.stale_paths)} files changed since they were indexed and are not shown")
        if self._overlay:
            parts.append(f"shown from the editor's unsaved text, which differs from disk: {', '.join(sorted(self._overlay))}")
        return "; ".join(parts) + ". Saying something is absent covers only this scope. ---"

    def _manifest(self, retrieval: Retrieval, pack: Pack, *, model_id: str, policy: BudgetPolicy, task_terms: int) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "run_id": self._run_id,
            "route": {"model_id": model_id},
            "config": {"rrf_k": RRF_K, "weights": dict(WEIGHTS), "embedding": self._session._embedding_identity, "pack_share": PACK_SHARE, "pack_max_tokens": PACK_MAX_TOKENS,
                       "budget_policy_version": POLICY_VERSION, "budget_policy": asdict(policy)},
            "retrieval": {"state": retrieval.state, "generation": retrieval.epoch, "revision": retrieval.revision, "coverage": dict(retrieval.coverage), "channels": dict(retrieval.channels)},
            "budget": {"tokens": pack.tokens, "budget_tokens": pack.budget_tokens, "task_words": task_terms},
            "selected": [asdict(item) for item in pack.selected],
            "stale_paths": list(pack.stale_paths),
            "unsaved_buffers": sorted(self._overlay),
            "outline": None if pack.outline is None else dict(pack.outline),
            "grounding": None,
        }

    def ground(self, answer: str) -> GroundingReport:
        """Check what an answer cited against what exists now. An intended new file is #258's; here it only reads as not found."""
        self._session.policy.forget_ignore_files()
        references = extract_file_references(answer, on_disk(self._session.policy.root))  # a whole path, never its tail (#634)
        listed = list(self._session.listing_for(references))
        names: dict[str, list[str]] = {}
        for path in listed:
            names.setdefault(path.rsplit("/", 1)[-1], []).append(path)
        known = set(listed)
        resolved: dict[str, None] = {}
        unresolved: dict[str, None] = {}
        ambiguous: dict[str, None] = {}
        not_in_index: dict[str, None] = {}
        for reference in references:
            if len(names.get(reference, ())) > 1:  # a bare name, even if one of its owners sits at the root
                ambiguous.setdefault(reference)
            elif reference in known:
                resolved.setdefault(reference)
            elif len(names.get(reference, ())) == 1:
                resolved.setdefault(names[reference][0])
            else:
                unresolved.setdefault(reference)
        proved: list[tuple[tuple[int, Any], bool]] = []  # asked for at most once a reply, only if something looks absent, and good only for that generation

        def generation_is_the_disk(current: Mapping[str, Any]) -> bool:
            generation = (current["epoch"], current.get("revision"))
            if not proved:
                proved.append((generation, self._generation_is_the_disk(current)))
            return proved[0] == (generation, True)

        for symbol in dict.fromkeys(_BACKTICKED.findall(answer)):
            if symbol in resolved or symbol in unresolved or symbol in ambiguous or symbol in not_in_index:
                continue
            found = self._symbol_state(symbol, generation_is_the_disk)
            if found == "found":
                resolved.setdefault(symbol)
            elif found == "ambiguous":
                ambiguous.setdefault(symbol)
            elif found == "absent":
                not_in_index.setdefault(symbol)
        report = GroundingReport(tuple(resolved), tuple(unresolved), tuple(ambiguous), tuple(not_in_index), proved[0][0][0] if proved and not_in_index else None)
        if self.manifest:
            self.manifest["grounding"] = asdict(report)
            self._session.write_manifest(self._run_id, self.manifest)
        return report

    def _generation_is_the_disk(self, current: Mapping[str, Any]) -> bool:
        """Whether a generation may be reported as having no definition of a name. Size and time are only a hint, so every file Git calls
        changed is compared by its bytes. For the rest this is as sure as Git is, which is why the report names the generation and says the
        disk was not exhaustively checked rather than saying the name is absent."""
        session = self._session
        coverage = current["coverage"]
        if not coverage.get("complete") or coverage.get("unsupported") or session.disk_facts() != (current.get("revision"), 0):
            return False
        dirty = session.dirty_paths()
        if dirty is None or len(dirty) > _MAX_DIRTY_CHECKED:
            return False
        for path in dirty:
            data = session._read(path)
            if data is None:
                continue  # gone or refused, and so not something a symbol could be in
            try:
                records = self._scope.storage.call("query", mode="path", epoch=current["epoch"], path_id=path_id(path), k=1, kinds=["file"])["records"]
            except (StorageRefusedError, StorageUnavailableError):
                return False
            if not records or records[0]["file_hash"] != hashlib.sha256(data).hexdigest():
                session.request_pass((path,))
                return False
        return True

    def _symbol_state(self, symbol: str, generation_is_the_disk: Callable[[Mapping[str, Any]], bool]) -> str | None:
        """found, ambiguous or absent from the generation, judged on verified records and this turn's unsaved text, which replaces what the
        index holds for its file. None when nothing can be said: that takes a complete generation of what is on disk now, as far as size,
        time and Git can tell, with nothing in a language the parser cannot see and no file too large for it to have read."""
        owners: set[str] = set()
        for path in list(self._overlay):
            data = self._read(path)
            if data is not None and any(record.symbol == symbol for record in parse_file(path, data).records):
                owners.add(path)
        stale = False
        try:
            current = self._scope.storage.call("coverage").get("current")
            records = [] if not current else self._scope.storage.call("query", mode="symbol", epoch=current["epoch"], symbol=symbol, k=_SYMBOL_OWNERS)["records"]
        except (StorageRefusedError, StorageUnavailableError):
            current, records = None, []
        for record in records:
            if record["path"] in self._overlay:
                stale = True  # the generation has it and the unsaved text does not, so "not in this generation" would be false
                continue
            data = self._read(record["path"])
            if data is not None and hashlib.sha256(data).hexdigest() == record["file_hash"]:
                owners.add(record["path"])
            else:
                stale = True
                if data is not None:
                    self._session.request_pass((record["path"],))
        if owners:
            return "ambiguous" if len(owners) > 1 else "found"
        if stale or not current:
            return None
        return "absent" if generation_is_the_disk(current) else None


def session_factory(*, memory_root: Path, config_root: Path, settings: OptimusGatewaySettings, config: MemoryIndexConfig, artifact_directory: str) -> Callable[[Path], MemorySession | None]:
    """How a launch with an approved, ready index opens one per session. A workspace that cannot be registered simply has none."""
    registry = ProjectRegistry(config_root)
    identity = f"{config.embedding.model}@{config.embedding.revision[:12]}"

    def open_session(workspace: Path) -> MemorySession | None:
        try:
            registration = registry.resolve(resolve_workspace_identity(workspace), create=True)
        except (ProjectRegistryError, OSError, ValueError) as exc:
            # These two carry codes and fixed details. Any other error's text may hold a path, so only its type is logged.
            said = str(exc) if isinstance(exc, ProjectRegistryError | TrustedPathError) else type(exc).__name__
            _LOG.warning("context index: this workspace cannot be registered: %s %s", said, getattr(exc, "diagnostics", ()))
            return None
        return MemorySession(
            policy=FilePolicy(workspace),
            registration=registration,
            storage_for=lambda scope: GatewayIndexStorage(settings, scope=scope),
            embedder_for=lambda: FastembedEmbedder(memory_root, config.embedding, directory=artifact_directory),
            embedding_identity=identity,
            parser_version=PARSER_VERSION,
            manifest_root=memory_root / "manifests",
        )

    return open_session


__all__ = ["GroundingReport", "MemorySession", "MemoryTurn", "named_symbols", "session_factory"]
