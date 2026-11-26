from __future__ import annotations

import hashlib
import ntpath
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

# Which files may be packed is the one includable-files policy (Plan 12.6, ADR-031): skipped folders, the runtime
# tree, secret files (#385) and aliases to any of them are denied before content is opened, then .gitignore and
# .optimusignore apply. RUNTIME_DIR_NAME stays importable here.
from context_engine.code_index import split_terms
from context_engine.repo_map import MapFile, neighbours
from context_engine.retrieval import lexical_terms, query_terms
from optimus.guardrails.file_policy import FilePolicy, FilePurpose, describe
from optimus.guardrails.runtime_tree import RUNTIME_DIR_NAME as RUNTIME_DIR_NAME
from optimus.guardrails.secret_paths import is_secret_path

DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES = 16 * 1024
_TRUNCATION_PREFIX = "--- omitted (size cap): "

_FILE_REFERENCE_RE = re.compile(  # segments may hold non-ASCII letters (#634); the extension stays ASCII
    r"(?<![\w./\\-])(?:[\w.-]+[\\/])*[\w.-]+\.[A-Za-z0-9]+(?![\w/\\-])"
)
# #634: a reference the pattern cut at a space or a non-ASCII symbol is the tail of a longer path; these may open that path.
_QUOTES = "`'\""
_PATH_OPENERS = frozenset(_QUOTES + "([<")
_WHOLE_PATH_WINDOW = 256  # shortcut: a whole path is looked for at most this far back on its line; raise it if longer ones are named
# Dotfiles, folder paths and key files the reference pattern misses (.env, config/.env, .pypirc, id_rsa): only secret
# ones become references, so naming one is refused visibly (#385). A bare prose word such as "token" never is, but a
# quoted or backticked one ("`credentials`") is marked as a file name.
_PATH_TOKEN_RE = re.compile(r"(?<![\w./\\-])[A-Za-z0-9_.\\/-]+(?![\w/\\-])")
_QUOTED_TOKEN_RE = re.compile(r"([`'\"])([A-Za-z0-9_.\\/-]+)\1")
_KEY_FILE_NAMES = frozenset({"id_rsa", "id_ed25519"})


class WorkspaceReferenceStatus(StrEnum):
    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    NOT_READABLE = "not_readable"
    TOO_LARGE = "too_large"


@dataclass(frozen=True)
class RankedCandidate:
    """One eligible target of an ambiguous reference and why it is where it is (Plan 12.13 #242). A suggestion: it authorizes nothing."""

    path: str
    task_terms: tuple[str, ...] = ()  # the task's own terms its folders or verified-current labels share, in lexical_terms' order
    near_task_path: bool = False  # one verified import away from a file the task names that resolved on its own
    verified_current: bool = False  # its index record matches the file's current bytes

    def reasons(self) -> str:
        said = [f"task terms: {', '.join(self.task_terms)}"] if self.task_terms else []
        said += ["linked by an import to a file the task names"] if self.near_task_path else []
        said += ["indexed and current"] if self.verified_current else []
        return "; ".join(said)


@dataclass(frozen=True)
class RankingHints:
    """Verified-current structural hints only. A file missing here contributes nothing; it is never removed."""

    verified: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # path -> its verified record's labels
    near: frozenset[str] = frozenset()


NO_HINTS = RankingHints()


@dataclass(frozen=True)
class WorkspaceReferenceDiagnostic:
    reference: str
    status: WorkspaceReferenceStatus
    candidates: tuple[str, ...] = ()
    reason: str | None = None  # the file policy's rule id for a refused reference
    ranked: tuple[RankedCandidate, ...] = ()  # an ambiguous reference's candidates, in `candidates` order


def rank_candidates(candidates: Sequence[str], *, task: str, reference: str, hints: RankingHints = NO_HINTS) -> tuple[RankedCandidate, ...]:
    """The frozen #242 order (`ranking-policy.json`): task-term relevance, dependency proximity, verified-current metadata, then path.
    The reference's own name and extension are not task terms. No score, gap or threshold: every candidate is kept."""
    own_name = set(query_terms(reference.replace("\\", "/").rsplit("/", 1)[-1]))
    wanted = [term for term in dict.fromkeys(lexical_terms(task)) if term not in own_name]
    ranked = []
    for path in candidates:
        folders = path.rsplit("/", 1)[0].split("/") if "/" in path else []
        verified = path in hints.verified
        known = set(split_terms(folders).split()) | (set(split_terms(hints.verified[path]).split()) if verified else set())
        ranked.append(RankedCandidate(path, tuple(term for term in wanted if term in known), path in hints.near, verified))
    return tuple(sorted(ranked, key=lambda item: (-len(item.task_terms), -item.near_task_path, -item.verified_current, item.path)))


def verified_hints(candidates: Sequence[str], resolved: Sequence[str], *, files: Sequence[MapFile], hashes: Mapping[str, str],
                   read: Callable[[str], bytes | None]) -> RankingHints:
    """Hints from an index map whose records match the files' current bytes. An edge needs the record that holds the import to be
    current, so a changed file links nothing; module names still resolve over every mapped file, as the map's own do."""
    def current(path: str) -> bool:
        data = read(path)
        return data is not None and path in hashes and hashlib.sha256(data).hexdigest() == hashes[path]

    by_path = {item.path: item for item in files}
    verified = {path: by_path[path].symbols for path in candidates if path in by_path and current(path)}
    anchors = [path for path in resolved if path in by_path and current(path)]
    trusted = set(verified) | set(anchors)
    linked = [item if item.path in trusted else MapFile(item.path) for item in files]
    return RankingHints(verified, frozenset(neighbours(linked, anchors)) & set(candidates) if anchors else frozenset())


def rank_ambiguity(diagnostics: tuple[WorkspaceReferenceDiagnostic, ...], task: str,
                   hints_for: Callable[[Sequence[str], Sequence[str]], RankingHints] | None = None) -> tuple[WorkspaceReferenceDiagnostic, ...]:
    """Each ambiguous reference's candidates in ranked order, for ordinary assembly and the index's alike. `task` is the person's own
    prompt: what the host itself said earlier (a stop's candidate list) never adds terms. `hints_for(candidates, resolved paths)`
    gives the index's verified hints, anchored on the paths the prompt itself resolves; without one only folder names count.

    An ambiguity that an exact path in the person's prompt settles is no longer one: they named which candidate they meant, as the
    stop asked (Plan 12.13 Task 4: a retry after a stop still carried the earlier bare name in its history, and stopped again). Only
    the prompt's own paths settle one, never a path from history, where the stop itself listed every candidate; the ranking never
    settles anything. A path from history is no dependency anchor either: it would rank a candidate as linked to a file the task
    names when the task does not name it (Codex CP3 review 1, finding 1)."""
    if not any(item.status is WorkspaceReferenceStatus.AMBIGUOUS for item in diagnostics):
        return diagnostics
    own = set(_extract_file_references(task, {item.reference for item in diagnostics}.__contains__))  # a whole path resolved already (#634)
    resolved = tuple(dict.fromkeys(item.candidates[0] for item in diagnostics
                                   if item.status is WorkspaceReferenceStatus.RESOLVED and item.reference in own))
    chosen = set(resolved)
    out = []
    for item in diagnostics:
        if item.status is WorkspaceReferenceStatus.AMBIGUOUS and set(item.candidates) & chosen:
            continue  # settled by the person's exact path, which is already selected
        if item.status is WorkspaceReferenceStatus.AMBIGUOUS:
            hints = NO_HINTS if hints_for is None else hints_for(item.candidates, resolved)
            ranked = rank_candidates(item.candidates, task=task, reference=item.reference, hints=hints)
            item = WorkspaceReferenceDiagnostic(item.reference, item.status, tuple(entry.path for entry in ranked), item.reason, ranked)
        out.append(item)
    return tuple(out)


@dataclass(frozen=True)
class WorkspaceContextResult:
    text: str
    max_total_bytes: int
    used_bytes: int
    prioritized_paths: tuple[str, ...]
    omitted_paths: tuple[str, ...]
    diagnostics: tuple[WorkspaceReferenceDiagnostic, ...]
    blocking_stop_reason: str | None = None
    blocking_message: str | None = None
    # Path -> sha256 of the bytes each shown file had when it was read, whole or truncated (#407).
    file_sha256s: Mapping[str, str] = field(default_factory=dict)
    # Every file the text shows anything of, a signature or description alone included, for memory lineage (Plan 12.11).
    shown_paths: tuple[str, ...] = ()
    # Coverage: the file policy revision, and how many workspace files each rule excluded (never their content).
    policy_revision: str = ""
    excluded_counts: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _EligibleFileIndex:
    by_relative: dict[str, Path]
    by_basename: dict[str, tuple[str, ...]]


def gather_workspace_context_for_prompt(
    workspace_root: Path,
    *,
    max_total_bytes: int = DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES,
) -> str:
    """Compatibility wrapper for existing string-only callers and tests."""
    return assemble_workspace_context_for_prompt(
        workspace_root,
        task="",
        max_total_bytes=max_total_bytes,
    ).text


def assemble_workspace_context_for_prompt(
    workspace_root: Path,
    *,
    task: str,
    max_total_bytes: int = DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES,
    prompt: str | None = None,
) -> WorkspaceContextResult:
    """
    Assembles a context representation of a workspace for use in generating prompts. This function evaluates
    the files in a given workspace directory, prioritizes paths based on references derived from the task
    description, and attempts to pack the file contents into a text buffer while adhering to a maximum size
    limit. Any unresolved references or files that cannot be packed due to size constraints are flagged
    appropriately.

    :param workspace_root: The root directory of the workspace from which to assemble the context.
    :type workspace_root: Path
    :param task: A description of the task to drive prioritization of workspace files.
    :type task: str
    :param max_total_bytes: The maximum number of bytes allowed for the assembled context buffer. Falls back to
       DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES if not provided.
    :type max_total_bytes: int
    :param prompt: The person's own current prompt, when `task` also carries earlier turns: an ambiguous reference's candidates are
       ranked on it alone (Plan 12.13). Defaults to `task`.
    :type prompt: str | None
    :return: A `WorkspaceContextResult` containing the assembled context, the list of prioritized and omitted
       file paths, diagnostics regarding file reference resolutions, and any blocking reasons if context
       assembly fails.
    :rtype: WorkspaceContextResult
    """
    root = workspace_root.resolve()
    empty = WorkspaceContextResult(
        text="",
        max_total_bytes=max_total_bytes,
        used_bytes=0,
        prioritized_paths=(),
        omitted_paths=(),
        diagnostics=(),
    )
    if not root.is_dir():
        return empty

    policy = FilePolicy(root)
    decisions = list(policy.walk(purpose=FilePurpose.AUTOMATIC))
    candidate_paths = [root / decision.relative_path for decision in decisions if decision.allowed]
    excluded_counts: dict[str, int] = {}
    for decision in decisions:
        if not decision.allowed:
            excluded_counts[decision.reason] = excluded_counts.get(decision.reason, 0) + 1
    index = _build_eligible_file_index(candidate_paths, root)
    references = _extract_file_references(task, _exists_in(root, index))
    diagnostics: list[WorkspaceReferenceDiagnostic] = []
    prioritized_paths: list[str] = []
    seen_resolved: set[str] = set()

    for reference in references:
        diagnostic = _resolve_reference(reference, policy, index)
        if diagnostic is None:
            continue
        diagnostics.append(diagnostic)

        if diagnostic.status is WorkspaceReferenceStatus.RESOLVED:
            resolved_path = diagnostic.candidates[0]
            if resolved_path not in seen_resolved:
                prioritized_paths.append(resolved_path)
                seen_resolved.add(resolved_path)

    diagnostic_tuple = rank_ambiguity(tuple(diagnostics), task if prompt is None else prompt)
    blocking_stop_reason, blocking_message = _blocking_from_diagnostics(diagnostic_tuple)

    if blocking_stop_reason is not None:
        return WorkspaceContextResult(
            text="",
            max_total_bytes=max_total_bytes,
            used_bytes=0,
            prioritized_paths=(),
            omitted_paths=(),
            diagnostics=diagnostic_tuple,
            blocking_stop_reason=blocking_stop_reason,
            blocking_message=blocking_message,
            policy_revision=policy.revision(),
            excluded_counts=excluded_counts,
        )

    file_sha256s: dict[str, str] = {}
    refused: dict[str, str] = {}
    text, used_bytes, omitted_paths, pack_blocking = _pack_workspace_context(
        policy,
        candidate_paths,
        max_total_bytes=max_total_bytes,
        priority_relative=tuple(prioritized_paths),
        file_sha256s=file_sha256s,
        refused=refused,
    )
    for reason in refused.values():
        excluded_counts[reason] = excluded_counts.get(reason, 0) + 1
    if any(relative in refused for relative in prioritized_paths):
        # A required file that became unavailable after listing stops preparation; it is never silently dropped.
        unavailable_diagnostics = _mark_resolved_refused(diagnostic_tuple, refused)
        blocking_stop_reason, blocking_message = _blocking_from_diagnostics(unavailable_diagnostics)
        return WorkspaceContextResult(
            text="",
            max_total_bytes=max_total_bytes,
            used_bytes=0,
            prioritized_paths=(),
            omitted_paths=(),
            diagnostics=unavailable_diagnostics,
            blocking_stop_reason=blocking_stop_reason,
            blocking_message=blocking_message,
            policy_revision=policy.revision(),
            excluded_counts=excluded_counts,
        )
    if pack_blocking:
        too_large_diagnostics = _mark_first_resolved_too_large(diagnostic_tuple)
        blocking_stop_reason, blocking_message = _blocking_from_diagnostics(too_large_diagnostics)
        return WorkspaceContextResult(
            text="",
            max_total_bytes=max_total_bytes,
            used_bytes=0,
            prioritized_paths=(),
            omitted_paths=(),
            diagnostics=too_large_diagnostics,
            blocking_stop_reason=blocking_stop_reason,
            blocking_message=blocking_message,
            policy_revision=policy.revision(),
            excluded_counts=excluded_counts,
        )
    return WorkspaceContextResult(
        text=text,
        max_total_bytes=max_total_bytes,
        used_bytes=used_bytes,
        prioritized_paths=tuple(prioritized_paths),
        omitted_paths=omitted_paths,
        diagnostics=diagnostic_tuple,  # settled ambiguities are gone (Plan 12.13 Task 4)
        file_sha256s=file_sha256s,
        policy_revision=policy.revision(),
        excluded_counts=excluded_counts,
    )


def resolve_task_references(task: str, policy: FilePolicy, listed: Sequence[str]) -> tuple[WorkspaceReferenceDiagnostic, ...]:
    """What the task names, resolved against an already known listing of admitted files, by the rules a full walk uses."""
    index = _build_eligible_file_index([policy.root / path for path in listed], policy.root)
    found = (_resolve_reference(reference, policy, index) for reference in _extract_file_references(task, _exists_in(policy.root, index)))
    return tuple(item for item in found if item is not None)


def extract_file_references(text: str, exists: Callable[[str], bool] | None = None) -> tuple[str, ...]:
    return _extract_file_references(text, exists)


def blocking_from_diagnostics(diagnostics: tuple[WorkspaceReferenceDiagnostic, ...]) -> tuple[str | None, str | None]:
    return _blocking_from_diagnostics(diagnostics)


def _blocking_from_diagnostics(
    diagnostics: tuple[WorkspaceReferenceDiagnostic, ...],
) -> tuple[str | None, str | None]:
    for diagnostic in diagnostics:
        if diagnostic.status is WorkspaceReferenceStatus.AMBIGUOUS:
            if not any(item.reasons() for item in diagnostic.ranked):  # nothing tells them apart: today's path order and words
                listed = f"Candidates: {', '.join(diagnostic.candidates)}."
            else:
                listed = ("Candidates, most likely first: "
                          + "; ".join(f"{item.path} ({item.reasons()})" if item.reasons() else item.path for item in diagnostic.ranked)
                          + ". The order is a suggestion and chose nothing.")
            return (
                "AMBIGUOUS_WORKSPACE_REFERENCE",
                f"Workspace reference '{diagnostic.reference}' is ambiguous. {listed} Retry with one exact workspace-relative path.",
            )
    for diagnostic in diagnostics:
        if diagnostic.status is WorkspaceReferenceStatus.NOT_READABLE:
            because = f": {describe(diagnostic.reason)}" if diagnostic.reason else ""
            return (
                "WORKSPACE_REFERENCE_NOT_READABLE",
                f"Workspace reference '{diagnostic.reference}' cannot be read safely{because}.",
            )
    for diagnostic in diagnostics:
        if diagnostic.status is WorkspaceReferenceStatus.TOO_LARGE:
            return (
                "REQUIRED_WORKSPACE_FILE_TOO_LARGE",
                (
                    f"Workspace reference '{diagnostic.reference}' exceeds the available "
                    "context budget. Retry with a smaller scope."
                ),
            )
    return None, None


def _extract_file_references(task: str, exists: Callable[[str], bool] | None = None) -> tuple[str, ...]:
    """What the text names. `exists` says whether a workspace-relative path is there; without it only a quoted path is read whole."""
    found: list[tuple[int, str]] = []
    for match in _FILE_REFERENCE_RE.finditer(task):
        whole = _whole_path(task, match.start(), match.end(), exists)
        if whole is None:
            found.append((match.start(), match.group(0).replace("\\", "/")))
        else:  # the earlier matches inside it are pieces of the one path, not files of their own (Codex review 1, finding 1)
            found = [item for item in found if item[0] < whole[0]] + [whole]
    references = list(dict.fromkeys(reference for _, reference in found))
    for match in _PATH_TOKEN_RE.finditer(task):
        token = match.group(0).replace("\\", "/").rstrip(".")
        names_a_file = token.startswith(".") or "/" in token or token.lower() in _KEY_FILE_NAMES
        if names_a_file and is_secret_path(token) and token not in references:
            references.append(token)
    for match in _QUOTED_TOKEN_RE.finditer(task):
        token = match.group(2).replace("\\", "/")
        if is_secret_path(token) and token not in references:
            references.append(token)
    return tuple(references)


def _whole_path(text: str, start: int, end: int, exists: Callable[[str], bool] | None) -> tuple[int, str] | None:
    """#634: where the path starts that ends where a reference ends and has a space or a non-ASCII character before it, and the path,
    so the reference is not taken for its tail. The longest one that exists wins. One that is not there is read whole only for a bare
    name, inside quotes, glued to a word that holds a folder ("docs/ops guide.md"): a quoted sentence ("Look at legacy.py", as every
    prompt in a history envelope is) and unquoted prose ("Fix the bug in guide.md") cannot be told from a path that is not there."""
    low = max(0, start - _WHOLE_PATH_WINDOW)
    newline = text.rfind("\n", low, start)
    first = newline + 1 if newline >= 0 else low
    for at in range(first, start):
        opened = at == 0 or text[at - 1].isspace() or text[at - 1] in _PATH_OPENERS
        if not opened or text[at].isspace() or text[at] in _QUOTES:
            continue
        if not any(char.isspace() or not char.isascii() for char in text[at:start]):
            continue
        span = text[at:end].replace("\\", "/")
        if exists is not None and _safe_relative_reference(span) is not None and exists(span):
            return at, span
    quote = text[end:end + 1]
    if not quote or quote not in _QUOTES or any(char in "/\\" for char in text[start:end]):
        return None  # an exact relative path cannot bind another file's basename, so it reads as before (finding 4)
    opened_at = text.rfind(quote, first, start)
    if opened_at < 0:
        return None
    head = text[opened_at + 1:start]
    tail = head.rstrip()
    word = tail.split()[-1] if tail.split() else ""
    glued = tail != head or not text[start - 1].isascii()  # a space, or a non-ASCII symbol, joins the word to the reference
    if not glued or not any(char in word for char in "/\\") or word[-1] in "/\\" or _FILE_REFERENCE_RE.fullmatch(word):
        return None
    at = opened_at + 1 + len(tail) - len(word)
    return at, text[at:end].replace("\\", "/")


def on_disk(root: Path) -> Callable[[str], bool]:
    """Whether a workspace-relative path is on disk. Only a path whose first part is an entry of the root is looked up, so prose costs
    one listing of the root, and a rooted or drive spelling is never looked up outside the workspace (Codex review 1, findings 5, 6)."""
    entries: set[str] | None = None

    def exists(relative: str) -> bool:
        nonlocal entries
        if _safe_relative_reference(relative) is None:
            return False
        if entries is None:
            try:
                entries = set(os.listdir(root))
            except OSError:
                entries = set()
        return relative.split("/", 1)[0] in entries and (root / relative).exists()

    return exists


def _exists_in(root: Path, index: _EligibleFileIndex) -> Callable[[str], bool]:
    """Listed, or on disk: a path the policy refuses is still the one named, and is refused by name, never replaced (#634)."""
    disk = on_disk(root)
    return lambda relative: relative in index.by_relative or disk(relative)


def _safe_relative_reference(reference: str) -> Path | None:
    candidate = Path(reference)
    if candidate.is_absolute() or ".." in candidate.parts or ":" in reference:
        return None
    if any(char in reference for char in "*?[]"):
        return None
    return candidate


def _build_eligible_file_index(candidate_paths: list[Path], root: Path) -> _EligibleFileIndex:
    by_relative: dict[str, Path] = {}
    basename_map: dict[str, list[str]] = {}
    for path in candidate_paths:
        relative = path.relative_to(root).as_posix()
        by_relative[relative] = path
        basename = path.name
        basename_map.setdefault(basename, []).append(relative)
    by_basename = {
        basename: tuple(sorted(relative_paths))
        for basename, relative_paths in basename_map.items()
    }
    return _EligibleFileIndex(by_relative=by_relative, by_basename=by_basename)


def _resolve_reference(
    reference: str,
    policy: FilePolicy,
    index: _EligibleFileIndex,
) -> WorkspaceReferenceDiagnostic | None:
    safe = _safe_relative_reference(reference)
    if safe is None:
        return None
    if ntpath.isreserved(reference):  # #590: a device or a second name for a file, refused by name and never looked up
        return WorkspaceReferenceDiagnostic(reference=reference, status=WorkspaceReferenceStatus.NOT_READABLE, candidates=())

    normalized = Path(*safe.parts)
    relative_posix = normalized.as_posix()

    denial = policy.path_denial(relative_posix)
    if denial is not None:
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.NOT_READABLE,
            candidates=(),
            reason=denial,
        )

    if "/" in reference.replace("\\", "/"):
        return _resolve_relative_path_reference(reference, relative_posix, policy, index)

    return _resolve_basename_reference(reference, policy, index)


def _resolve_relative_path_reference(
    reference: str,
    relative_posix: str,
    policy: FilePolicy,
    index: _EligibleFileIndex,
) -> WorkspaceReferenceDiagnostic:
    if relative_posix in index.by_relative:
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.RESOLVED,
            candidates=(relative_posix,),
        )

    candidate_path = policy.root / relative_posix
    if candidate_path.is_dir():
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.NOT_READABLE,
            candidates=(),
        )
    if candidate_path.is_file():
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.NOT_READABLE,
            candidates=(),
            reason=policy.decide(relative_posix, purpose=FilePurpose.AUTOMATIC).reason,
        )

    return WorkspaceReferenceDiagnostic(
        reference=reference,
        status=WorkspaceReferenceStatus.NOT_FOUND,
        candidates=(),
    )


def _resolve_basename_reference(
    reference: str,
    policy: FilePolicy,
    index: _EligibleFileIndex,
) -> WorkspaceReferenceDiagnostic:
    matches = index.by_basename.get(reference, ())
    if len(matches) == 1:
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.RESOLVED,
            candidates=(matches[0],),
        )
    if len(matches) > 1:
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.AMBIGUOUS,
            candidates=matches,
        )

    candidate_path = policy.root / reference
    if candidate_path.is_dir() or candidate_path.is_file():
        reason = policy.decide(reference, purpose=FilePurpose.AUTOMATIC).reason if candidate_path.is_file() else None
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.NOT_READABLE,
            candidates=(),
            reason=reason,
        )

    return WorkspaceReferenceDiagnostic(
        reference=reference,
        status=WorkspaceReferenceStatus.NOT_FOUND,
        candidates=(),
    )


def _mark_resolved_refused(
    diagnostics: tuple[WorkspaceReferenceDiagnostic, ...], refused: Mapping[str, str]
) -> tuple[WorkspaceReferenceDiagnostic, ...]:
    return tuple(
        WorkspaceReferenceDiagnostic(
            reference=diagnostic.reference,
            status=WorkspaceReferenceStatus.NOT_READABLE,
            candidates=(),
            reason=refused[diagnostic.candidates[0]],
        )
        if diagnostic.status is WorkspaceReferenceStatus.RESOLVED and diagnostic.candidates[0] in refused
        else diagnostic
        for diagnostic in diagnostics
    )


def _mark_first_resolved_too_large(
    diagnostics: tuple[WorkspaceReferenceDiagnostic, ...],
) -> tuple[WorkspaceReferenceDiagnostic, ...]:
    updated: list[WorkspaceReferenceDiagnostic] = []
    marked = False
    for diagnostic in diagnostics:
        if not marked and diagnostic.status is WorkspaceReferenceStatus.RESOLVED:
            updated.append(
                WorkspaceReferenceDiagnostic(
                    reference=diagnostic.reference,
                    status=WorkspaceReferenceStatus.TOO_LARGE,
                    candidates=diagnostic.candidates,
                )
            )
            marked = True
            continue
        updated.append(diagnostic)
    return tuple(updated)



def _truncation_line_fitting_budget(
    used_bytes: int,
    max_total_bytes: int,
    *,
    needs_separator: bool,
    omitted_candidates: list[str],
) -> tuple[str, list[str]]:
    separator_bytes = 1 if needs_separator else 0
    available = max_total_bytes - used_bytes - separator_bytes
    if available <= 0 or not omitted_candidates:
        return "", []

    for count in range(len(omitted_candidates), 0, -1):
        omitted = omitted_candidates[:count]
        marker = _truncation_line(omitted)
        if len(marker.encode("utf-8")) <= available:
            return marker, omitted
    return "", []


def _pack_workspace_context(
    policy: FilePolicy,
    candidate_paths: list[Path],
    *,
    max_total_bytes: int,
    priority_relative: tuple[str, ...],
    file_sha256s: dict[str, str],
    refused: dict[str, str],
) -> tuple[str, int, tuple[str, ...], bool]:
    """``file_sha256s`` receives the digest of every file whose bytes the text shows (#407). Each file is read
    through the policy, which rechecks its identity; ``refused`` receives the rule for any file that became
    unavailable since listing. A refused required file ends packing at once; the caller stops preparation."""
    if not candidate_paths and not priority_relative:
        return "", 0, (), False
    root = policy.root

    path_by_relative = {path.relative_to(root).as_posix(): path for path in candidate_paths}
    priority_set = set(priority_relative)
    priority_paths = [
        path_by_relative[relative]
        for relative in priority_relative
        if relative in path_by_relative
    ]
    filler_paths = [
        path
        for path in candidate_paths
        if path.relative_to(root).as_posix() not in priority_set
    ]

    priority_blocks: list[str] = []
    priority_bytes = 0
    for path in priority_paths:
        relative_posix = path.relative_to(root).as_posix()
        decision, data = policy.read(relative_posix, purpose=FilePurpose.AUTOMATIC)
        if data is None:
            refused[relative_posix] = decision.reason
            return "", 0, (), False
        block = f"--- {relative_posix} ---\n{data.decode('utf-8')}"
        if priority_blocks:
            priority_bytes += 1
        priority_bytes += len(block.encode("utf-8"))
        priority_blocks.append(block)
        file_sha256s[relative_posix] = hashlib.sha256(data).hexdigest()

    if priority_bytes > max_total_bytes:
        return "", 0, (), True

    lines = list(priority_blocks)
    used_bytes = len("\n".join(lines).encode("utf-8")) if lines else 0
    omitted: list[str] = []
    filler_relatives = [path.relative_to(root).as_posix() for path in filler_paths]

    for index, path in enumerate(filler_paths):
        relative_posix = path.relative_to(root).as_posix()
        decision, data = policy.read(relative_posix, purpose=FilePurpose.AUTOMATIC)
        if data is None:
            refused[relative_posix] = decision.reason
            continue

        header = f"--- {relative_posix} ---"
        block = f"{header}\n{data.decode('utf-8')}"
        block_bytes = len(block.encode("utf-8"))
        separator_bytes = 1 if lines else 0

        omitted_if_skip_current = filler_relatives[index:]
        marker_if_skip, _ = _truncation_line_fitting_budget(
            used_bytes,
            max_total_bytes,
            needs_separator=bool(lines),
            omitted_candidates=omitted_if_skip_current,
        )
        reserve_if_skip = _reserve_bytes(marker_if_skip)
        remaining_if_skip = max_total_bytes - used_bytes - reserve_if_skip - separator_bytes
        if remaining_if_skip <= 0:
            _, omitted = _truncation_line_fitting_budget(
                used_bytes,
                max_total_bytes,
                needs_separator=bool(lines),
                omitted_candidates=omitted_if_skip_current,
            )
            break

        pending_omitted = filler_relatives[index + 1 :]
        marker_if_include, _ = _truncation_line_fitting_budget(
            used_bytes,
            max_total_bytes,
            needs_separator=bool(lines),
            omitted_candidates=pending_omitted,
        )
        reserve_if_include = _reserve_bytes(marker_if_include)
        remaining = max_total_bytes - used_bytes - reserve_if_include - separator_bytes

        if block_bytes <= remaining:
            lines.append(block)
            used_bytes += separator_bytes + block_bytes
            file_sha256s[relative_posix] = hashlib.sha256(data).hexdigest()
            continue

        header_bytes = len(header.encode("utf-8")) + 1
        if remaining > header_bytes:
            truncated_text = _truncate_utf8(data, remaining - header_bytes)
            lines.append(f"{header}\n{truncated_text}")
            file_sha256s[relative_posix] = hashlib.sha256(data).hexdigest()
            _, omitted = _truncation_line_fitting_budget(
                used_bytes + separator_bytes + len(f"{header}\n{truncated_text}".encode("utf-8")),
                max_total_bytes,
                needs_separator=bool(lines),
                omitted_candidates=pending_omitted,
            )
            break

        _, omitted = _truncation_line_fitting_budget(
            used_bytes,
            max_total_bytes,
            needs_separator=bool(lines),
            omitted_candidates=omitted_if_skip_current,
        )
        break

    if not lines and not omitted:
        return "", 0, (), False

    if omitted:
        marker, omitted = _truncation_line_fitting_budget(
            used_bytes,
            max_total_bytes,
            needs_separator=bool(lines),
            omitted_candidates=omitted,
        )
        if marker:
            lines.append(marker)

    text = "\n".join(lines)
    return text, len(text.encode("utf-8")), tuple(omitted), False



def _reserve_bytes(truncation_line: str) -> int:
    if not truncation_line:
        return 0
    return len(truncation_line.encode("utf-8")) + 1


def _truncation_line(omitted: list[str]) -> str:
    if not omitted:
        return ""
    return f"{_TRUNCATION_PREFIX}{', '.join(omitted)} ---"


def _truncate_utf8(data: bytes, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    truncated = data[:max_bytes]
    try:
        return truncated.decode("utf-8")
    except UnicodeDecodeError:
        return truncated.decode("utf-8", errors="ignore")


