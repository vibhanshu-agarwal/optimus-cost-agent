from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES = 16 * 1024
_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules", ".idea"})
_TRUNCATION_PREFIX = "--- omitted (size cap): "

_FILE_REFERENCE_RE = re.compile(
    r"(?<![\w./\\-])(?:[A-Za-z0-9_.-]+[\\/])*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+(?![\w/\\-])"
)


class WorkspaceReferenceStatus(StrEnum):
    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    NOT_READABLE = "not_readable"
    TOO_LARGE = "too_large"


@dataclass(frozen=True)
class WorkspaceReferenceDiagnostic:
    reference: str
    status: WorkspaceReferenceStatus
    candidates: tuple[str, ...] = ()


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

    references = _extract_file_references(task)
    candidate_paths = _list_includable_files(root)
    index = _build_eligible_file_index(candidate_paths, root)
    diagnostics: list[WorkspaceReferenceDiagnostic] = []
    prioritized_paths: list[str] = []
    seen_resolved: set[str] = set()

    for reference in references:
        diagnostic = _resolve_reference(reference, root, index)
        if diagnostic is None:
            continue
        diagnostics.append(diagnostic)

        if diagnostic.status is WorkspaceReferenceStatus.RESOLVED:
            resolved_path = diagnostic.candidates[0]
            if resolved_path not in seen_resolved:
                prioritized_paths.append(resolved_path)
                seen_resolved.add(resolved_path)

    diagnostic_tuple = tuple(diagnostics)
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
        )

    text, used_bytes, omitted_paths, pack_blocking = _pack_workspace_context(
        root,
        candidate_paths,
        max_total_bytes=max_total_bytes,
        priority_relative=tuple(prioritized_paths),
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
        )
    return WorkspaceContextResult(
        text=text,
        max_total_bytes=max_total_bytes,
        used_bytes=used_bytes,
        prioritized_paths=tuple(prioritized_paths),
        omitted_paths=omitted_paths,
        diagnostics=tuple(diagnostics),
    )


def _blocking_from_diagnostics(
    diagnostics: tuple[WorkspaceReferenceDiagnostic, ...],
) -> tuple[str | None, str | None]:
    for diagnostic in diagnostics:
        if diagnostic.status is WorkspaceReferenceStatus.AMBIGUOUS:
            candidates = ", ".join(diagnostic.candidates)
            return (
                "AMBIGUOUS_WORKSPACE_REFERENCE",
                (
                    f"Workspace reference '{diagnostic.reference}' is ambiguous. "
                    f"Candidates: {candidates}. Retry with one exact workspace-relative path."
                ),
            )
    for diagnostic in diagnostics:
        if diagnostic.status is WorkspaceReferenceStatus.NOT_READABLE:
            return (
                "WORKSPACE_REFERENCE_NOT_READABLE",
                f"Workspace reference '{diagnostic.reference}' cannot be read safely.",
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


def _extract_file_references(task: str) -> tuple[str, ...]:
    references: list[str] = []
    for match in _FILE_REFERENCE_RE.finditer(task):
        reference = match.group(0).replace("\\", "/")
        if reference not in references:
            references.append(reference)
    return tuple(references)


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
    root: Path,
    index: _EligibleFileIndex,
) -> WorkspaceReferenceDiagnostic | None:
    safe = _safe_relative_reference(reference)
    if safe is None:
        return None

    normalized = Path(*safe.parts)
    relative_posix = normalized.as_posix()

    if _should_skip_relative_path(normalized):
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.NOT_READABLE,
            candidates=(),
        )

    if "/" in reference.replace("\\", "/"):
        return _resolve_relative_path_reference(reference, relative_posix, root, index)

    return _resolve_basename_reference(reference, root, index)


def _resolve_relative_path_reference(
    reference: str,
    relative_posix: str,
    root: Path,
    index: _EligibleFileIndex,
) -> WorkspaceReferenceDiagnostic:
    if relative_posix in index.by_relative:
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.RESOLVED,
            candidates=(relative_posix,),
        )

    candidate_path = root / relative_posix
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
        )

    return WorkspaceReferenceDiagnostic(
        reference=reference,
        status=WorkspaceReferenceStatus.NOT_FOUND,
        candidates=(),
    )


def _resolve_basename_reference(
    reference: str,
    root: Path,
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

    candidate_path = root / reference
    if candidate_path.is_dir() or candidate_path.is_file():
        return WorkspaceReferenceDiagnostic(
            reference=reference,
            status=WorkspaceReferenceStatus.NOT_READABLE,
            candidates=(),
        )

    return WorkspaceReferenceDiagnostic(
        reference=reference,
        status=WorkspaceReferenceStatus.NOT_FOUND,
        candidates=(),
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


def _file_block(root: Path, path: Path) -> tuple[str, int]:
    relative = path.relative_to(root).as_posix()
    data = path.read_bytes()
    block = f"--- {relative} ---\n{data.decode('utf-8')}"
    return block, len(block.encode("utf-8"))


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
    root: Path,
    candidate_paths: list[Path],
    *,
    max_total_bytes: int,
    priority_relative: tuple[str, ...],
) -> tuple[str, int, tuple[str, ...], bool]:
    if not candidate_paths and not priority_relative:
        return "", 0, (), False

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
    for index, path in enumerate(priority_paths):
        block, block_bytes = _file_block(root, path)
        if index > 0:
            priority_bytes += 1
        priority_bytes += block_bytes
        priority_blocks.append(block)

    if priority_bytes > max_total_bytes:
        return "", 0, (), True

    lines = list(priority_blocks)
    used_bytes = len("\n".join(lines).encode("utf-8")) if lines else 0
    omitted: list[str] = []
    filler_relatives = [path.relative_to(root).as_posix() for path in filler_paths]

    for index, path in enumerate(filler_paths):
        relative_posix = path.relative_to(root).as_posix()
        try:
            data = path.read_bytes()
        except OSError:
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
            continue

        header_bytes = len(header.encode("utf-8")) + 1
        if remaining > header_bytes:
            truncated_text = _truncate_utf8(data, remaining - header_bytes)
            lines.append(f"{header}\n{truncated_text}")
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


def _list_includable_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if _should_skip_relative_path(relative):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if not data or b"\x00" in data:
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        paths.append(path)
    return paths


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


def _should_skip_relative_path(relative: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in relative.parts)
