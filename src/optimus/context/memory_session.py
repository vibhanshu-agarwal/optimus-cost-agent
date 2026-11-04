"""One ACP session's context index (Plan 12.10 Task 4; ADR-038): its background worker, and what each turn gets from it.

The worker runs while the session is open; closing the session pauses indexing. The scope is recomputed for each turn, so changing
branch moves to that branch's own line at once and the old branch's records are never current evidence. Anything short of a usable
index keeps today's context and says so. Turns never wait on the worker, beyond a short bounded nudge when a chosen file has changed.
"""

from __future__ import annotations

import json
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

from context_engine.code_index import PARSER_VERSION
from context_engine.context_pack import Pack, assemble_pack
from context_engine.index_worker import Embedder, IndexStorage, IndexWorker, StorageRefusedError, StorageUnavailableError, WorkerOutcome
from context_engine.repo_map import RepoMap
from context_engine.retrieval import RRF_K, WEIGHTS, CatalogueFile, Retrieval, Retriever, read_catalogue, seed_map
from optimus.acp.trusted_paths import resolve_workspace_identity
from optimus.agent.workspace_context import (
    DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES,
    WorkspaceContextResult,
    WorkspaceReferenceDiagnostic,
    WorkspaceReferenceStatus,
    assemble_workspace_context_for_prompt,
    blocking_from_diagnostics,
    extract_file_references,
    resolve_task_references,
)
from optimus.config.gateway import OptimusGatewaySettings
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
MAP_CHARS: Final = 12_000
RETRY_SECONDS: Final = 30.0
CATALOGUE_SECONDS: Final = 60.0  # during a build each publication is a new epoch; names barely change between them
MAP_SECONDS: Final = 300.0  # the map sits in the cacheable prefix, so a build does not churn it
_RECONCILE_ATTEMPTS: Final = 2
_RECONCILE_WAIT_SECONDS: Final = 1.0
_MANIFESTS_KEPT: Final = 200
_QUERY_CHARS: Final = 2_000
_MAX_SYMBOLS: Final = 8
# A name someone wrote as code: backticked, dotted, or with an inner capital or underscore. Ordinary words are not symbols.
_SYMBOL_WORD = re.compile(r"`([A-Za-z_][\w.]*)`|\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+|[a-z]+[A-Z]\w*|[A-Z][a-z0-9]+[A-Z]\w*|[a-z]+_\w+)\b")
_BACKTICKED = re.compile(r"`([A-Za-z_][\w.]*)`")


def named_symbols(text: str) -> tuple[str, ...]:
    found: dict[str, None] = {}
    for match in _SYMBOL_WORD.finditer(text):
        found.setdefault(match.group(1) or match.group(2))
        if len(found) == _MAX_SYMBOLS:
            break
    return tuple(found)


@dataclass(frozen=True)
class GroundingReport:
    """What an answer cited and whether it exists in what was inspected. It never decides whether the answer is right."""

    resolved: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    ambiguous: tuple[str, ...] = ()

    def note(self) -> str | None:
        parts = []
        if self.unresolved:
            parts.append("not found in the inspected scope: " + ", ".join(self.unresolved))
        if self.ambiguous:
            parts.append("matches more than one file: " + ", ".join(self.ambiguous))
        return "; ".join(parts) or None


@dataclass
class _Scope:
    identity: str
    branch: str
    storage: IndexStorage


@dataclass
class _Cached:
    epoch: int = 0
    at: float = 0.0
    files: list[CatalogueFile] = field(default_factory=list)
    complete: bool = False


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
        self._source = WorkspaceIndexSource(policy)
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
        self._scope = self._new_scope()
        self._catalogue = _Cached()
        self._map: tuple[str, float, RepoMap] | None = None

    # --- the worker ---------------------------------------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="context-index", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Pause indexing without waiting: the worker stops at its next step and releases its leases, which also expire on their own."""
        self._stop.set()
        self._cancel.set()
        self._wake.set()

    def close(self) -> None:
        self.stop()
        if self._thread is not None:
            self._thread.join(10)

    def _new_scope(self) -> _Scope:
        branch = self._branch_of(self._policy.root)
        identity = index_scope(self._registration, branch=branch, embedding=self._embedding_identity, parser_version=self._parser_version)
        return _Scope(identity, branch, self._storage_for(identity))

    def _current_scope(self) -> _Scope:
        """The scope for this moment. A new branch cancels whatever pass the old one has running and starts its own."""
        with self._lock:
            if self._branch_of(self._policy.root) != self._scope.branch:
                self._scope = self._new_scope()
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

    def _loop(self) -> None:
        try:
            self._embedder = self._embedder_for()
        except EmbedderUnavailableError as exc:
            self._unusable = exc.code
            return
        self._wake.set()
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            if self._stop.is_set():
                return
            self._cancel = threading.Event()
            scope = self._scope
            revision = self._source.revision()
            if revision == self._indexed_revision:
                with self._lock:
                    self._priority = []
                continue
            worker = IndexWorker(self._source, self._storage_for(scope.identity), self._embedder, owner=secrets.token_hex(16), priority=self._priorities, foreground_busy=self._busy.is_set)
            outcome = worker.run(self._cancel)
            self._last_outcome = outcome
            if outcome.state == "complete":
                self._indexed_revision = revision
                with self._lock:
                    self._priority = []
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
            return f"Context index: unavailable ({self._unusable}). This session keeps today's context."
        try:
            current = self._current_scope().storage.call("coverage").get("current")
        except (StorageRefusedError, StorageUnavailableError):
            return "Context index: cannot be reached right now. This turn uses today's context."
        if not current:
            return "Context index: building, nothing published yet. This turn uses today's context."
        coverage = current["coverage"]
        state = "ready" if coverage.get("complete") else "building"
        return f"Context index: {state}, {coverage.get('files_indexed', 0)} of {coverage.get('files_total', 0)} files."

    def _read(self, path: str) -> bytes | None:
        decision, data = self._policy.read(path, purpose=FilePurpose.AUTOMATIC)
        return data if decision.allowed else None

    def _catalogue_for(self, epoch: int) -> list[CatalogueFile]:
        cached = self._catalogue
        if cached.epoch and (cached.epoch == epoch or (not cached.complete and self._clock() - cached.at < CATALOGUE_SECONDS)):
            return cached.files
        files = read_catalogue(self._scope.storage, epoch)
        self._catalogue = _Cached(epoch, self._clock(), files)
        return files

    def turn(self, *, cancelled: Callable[[], bool] = lambda: False) -> MemoryTurn:
        scope = self._current_scope()
        self.request_pass()
        retriever = Retriever(scope.storage, self._embedder, catalogue=self._catalogue_for, cancelled=cancelled)
        tools = IndexTools(retriever=retriever, storage=scope.storage, read=self._read, listing=self._source.listing, cancelled=cancelled, clock=self._clock)
        return MemoryTurn(self, scope, retriever, tools, cancelled)

    def repo_map(self, scope: _Scope) -> str:
        """The stable prefix. During a build it changes at most once per `MAP_SECONDS`; a failure gives no map, never a failed turn."""
        cached = self._map
        if cached is not None and cached[0] == scope.identity and self._clock() - cached[1] < MAP_SECONDS:
            return cached[2].text
        try:
            current = scope.storage.call("coverage").get("current")
            if not current:
                return ""
            built = seed_map(scope.storage, current["epoch"], self._catalogue_for(current["epoch"]), budget_chars=MAP_CHARS)
        except (StorageRefusedError, StorageUnavailableError):
            return cached[2].text if cached is not None and cached[0] == scope.identity else ""
        self._map = (scope.identity, self._clock(), built)
        return built.text

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

    def listing(self) -> Sequence[str]:
        return self._source.listing()

    @property
    def policy(self) -> FilePolicy:
        return self._policy

    def foreground(self) -> Any:
        return self._foreground()


class MemoryTurn:
    """One turn's view: one scope, and the same read path for the pack and the tools."""

    def __init__(self, session: MemorySession, scope: _Scope, retriever: Retriever, tools: IndexTools, cancelled: Callable[[], bool]) -> None:
        self._session = session
        self._scope = scope
        self._retriever = retriever
        self.tools = tools
        self._cancelled = cancelled
        self.manifest: dict[str, Any] = {}
        self._run_id = ""
        self.on_tool: Callable[[str, str, str, str], None] | None = None  # the host's live tool cards
        self.seen_requests: set[tuple[str, str]] = set()

    def repo_map(self) -> str:
        return self._session.repo_map(self._scope)

    def status(self) -> str:
        return self._session.status()

    def assemble(self, *, run_id: str, task: str, selection_text: str, model_id: str, estimate: Callable[[str], int], usable_input_tokens: int) -> WorkspaceContextResult:
        """The turn's context. Blocking conditions are today's own, so each mode's handling of them is unchanged. An index that cannot
        answer gives today's context plus a line saying so; required evidence that does not fit is never quietly dropped."""
        self._run_id = run_id
        policy = self._session.policy
        budget = min(int(usable_input_tokens * PACK_SHARE), PACK_MAX_TOKENS)
        with self._session.foreground():
            diagnostics = resolve_task_references(selection_text, policy, self._session.listing())
            stop_reason, message = blocking_from_diagnostics(diagnostics)
            if stop_reason is not None:
                return self._blocked(diagnostics, stop_reason, message)
            required = tuple(dict.fromkeys(item.candidates[0] for item in diagnostics if item.status is WorkspaceReferenceStatus.RESOLVED))
            retrieval, pack = self._retrieve(selection_text, required, estimate, budget, task)
        if retrieval.state != "ok" or pack is None:
            return self._today(task=selection_text, retrieval=retrieval)
        if not pack.complete:
            return self._incomplete(diagnostics, pack)
        coverage_line = self._coverage_line(retrieval, pack)
        text = f"{pack.text}\n{coverage_line}" if pack.text else coverage_line
        self.manifest = self._manifest(retrieval, pack, model_id=model_id, budget=budget, task_terms=len(task.split()))
        self._session.write_manifest(run_id, self.manifest)
        omitted = tuple(dict.fromkeys(item.path for item in pack.selected if item.disclosure == "omitted"))
        return WorkspaceContextResult(text=text, max_total_bytes=DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES, used_bytes=len(text.encode("utf-8")), prioritized_paths=required, omitted_paths=omitted,
                                      diagnostics=diagnostics, file_sha256s=dict(pack.file_sha256s), policy_revision=policy.revision())

    def _retrieve(self, text: str, required: Sequence[str], estimate: Callable[[str], int], budget: int, task: str) -> tuple[Retrieval, Pack | None]:
        query = text[:_QUERY_CHARS]
        symbols = named_symbols(task)
        pack: Pack | None = None
        for attempt in range(_RECONCILE_ATTEMPTS + 1):
            retrieval = self._retriever.retrieve(query, named_paths=required, named_symbols=symbols)
            if retrieval.state != "ok":
                return retrieval, None
            pack = assemble_pack(required=required, ranked=retrieval.ranked, read=self._session._read, estimate=estimate, budget_tokens=budget)
            if not pack.stale_paths or attempt == _RECONCILE_ATTEMPTS or self._cancelled():
                return retrieval, pack
            self._session.request_pass(pack.stale_paths)
            time.sleep(_RECONCILE_WAIT_SECONDS)
        raise AssertionError("unreachable")

    def _today(self, *, task: str, retrieval: Retrieval) -> WorkspaceContextResult:
        result = assemble_workspace_context_for_prompt(self._session.policy.root, task=task)
        line = f"Context index: no usable generation ({retrieval.state}). These files are today's selection, not a ranked search."
        self.manifest = {"schema": "optimus.context-manifest.v1", "run_id": self._run_id, "retrieval": {"state": retrieval.state, "channels": dict(retrieval.channels)}}
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

    @staticmethod
    def _coverage_line(retrieval: Retrieval, pack: Pack) -> str:
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
        return "; ".join(parts) + ". Saying something is absent covers only this scope. ---"

    def _manifest(self, retrieval: Retrieval, pack: Pack, *, model_id: str, budget: int, task_terms: int) -> dict[str, Any]:
        return {
            "schema": "optimus.context-manifest.v1",
            "run_id": self._run_id,
            "route": {"model_id": model_id},
            "config": {"rrf_k": RRF_K, "weights": dict(WEIGHTS), "embedding": self._session._embedding_identity, "pack_share": PACK_SHARE, "pack_max_tokens": PACK_MAX_TOKENS},
            "retrieval": {"state": retrieval.state, "generation": retrieval.epoch, "revision": retrieval.revision, "coverage": dict(retrieval.coverage), "channels": dict(retrieval.channels)},
            "budget": {"tokens": pack.tokens, "budget_tokens": pack.budget_tokens, "task_words": task_terms},
            "selected": [asdict(item) for item in pack.selected],
            "stale_paths": list(pack.stale_paths),
            "grounding": None,
        }

    def ground(self, answer: str) -> GroundingReport:
        """Check what an answer cited against what exists now. An intended new file is #258's; here it only reads as not found."""
        listed = list(self._session.listing())
        names: dict[str, list[str]] = {}
        for path in listed:
            names.setdefault(path.rsplit("/", 1)[-1], []).append(path)
        known = set(listed)
        resolved: dict[str, None] = {}
        unresolved: dict[str, None] = {}
        ambiguous: dict[str, None] = {}
        for reference in extract_file_references(answer):
            if reference in known:
                resolved.setdefault(reference)
            elif len(names.get(reference, ())) == 1:
                resolved.setdefault(names[reference][0])
            elif len(names.get(reference, ())) > 1:
                ambiguous.setdefault(reference)
            else:
                unresolved.setdefault(reference)
        for symbol in dict.fromkeys(_BACKTICKED.findall(answer)):
            if symbol in resolved or symbol in unresolved or symbol in ambiguous:
                continue
            found = self._symbol_exists(symbol)
            if found is True:
                resolved.setdefault(symbol)
            elif found is False:
                unresolved.setdefault(symbol)
        report = GroundingReport(tuple(resolved), tuple(unresolved), tuple(ambiguous))
        if self.manifest:
            self.manifest["grounding"] = asdict(report)
            self._session.write_manifest(self._run_id, self.manifest)
        return report

    def _symbol_exists(self, symbol: str) -> bool | None:
        """None when the index cannot say, or is still building and so cannot prove absence."""
        try:
            current = self._scope.storage.call("coverage").get("current")
            if not current:
                return None
            records = self._scope.storage.call("query", mode="symbol", epoch=current["epoch"], symbol=symbol, k=1)["records"]
        except (StorageRefusedError, StorageUnavailableError):
            return None
        if records:
            return True
        return False if current["coverage"].get("complete") else None


def session_factory(*, memory_root: Path, config_root: Path, settings: OptimusGatewaySettings, config: MemoryIndexConfig, artifact_directory: str) -> Callable[[Path], MemorySession | None]:
    """How a launch with an approved, ready index opens one per session. A workspace that cannot be registered simply has none."""
    registry = ProjectRegistry(config_root)
    identity = f"{config.embedding.model}@{config.embedding.revision[:12]}"

    def open_session(workspace: Path) -> MemorySession | None:
        try:
            registration = registry.resolve(resolve_workspace_identity(workspace), create=True)
        except (ProjectRegistryError, OSError, ValueError):
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
