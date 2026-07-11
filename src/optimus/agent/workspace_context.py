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
    blocking_stop_reason: str | None = None
    blocking_message: str | None = None

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
            continue

        if diagnostic.status is WorkspaceReferenceStatus.AMBIGUOUS:
            blocking_stop_reason = "AMBIGUOUS_WORKSPACE_REFERENCE"
            candidates = ", ".join(diagnostic.candidates)
            blocking_message = (
                f"Workspace reference '{diagnostic.reference}' is ambiguous. "
                f"Candidates: {candidates}. Retry with one exact workspace-relative path."
            )
            break

        if diagnostic.status is WorkspaceReferenceStatus.NOT_READABLE:
            blocking_stop_reason = "WORKSPACE_REFERENCE_NOT_READABLE"
            blocking_message = (
                f"Workspace reference '{diagnostic.reference}' cannot be read safely."
            )

    if blocking_stop_reason is not None:
        return WorkspaceContextResult(
            text="",
            max_total_bytes=max_total_bytes,
            used_bytes=0,
            prioritized_paths=(),
            omitted_paths=(),
            diagnostics=tuple(diagnostics),
            blocking_stop_reason=blocking_stop_reason,
            blocking_message=blocking_message,
        )

    text, used_bytes, omitted_paths = _pack_workspace_context(
        root,
        candidate_paths,
        max_total_bytes=max_total_bytes,
        priority_relative=tuple(prioritized_paths),
    )
    return WorkspaceContextResult(
        text=text,
        max_total_bytes=max_total_bytes,
        used_bytes=used_bytes,
        prioritized_paths=tuple(prioritized_paths),
        omitted_paths=omitted_paths,
        diagnostics=tuple(diagnostics),
    )


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


def _pack_workspace_context(
    root: Path,
    candidate_paths: list[Path],
    *,
    max_total_bytes: int,
    priority_relative: tuple[str, ...],
) -> tuple[str, int, tuple[str, ...]]:
    if not candidate_paths and not priority_relative:
        return "", 0, ()

    path_by_relative = {path.relative_to(root).as_posix(): path for path in candidate_paths}
    priority_set = set(priority_relative)
    ordered_paths: list[Path] = []
    for relative in priority_relative:
        path = path_by_relative.get(relative)
        if path is not None:
            ordered_paths.append(path)
    for path in candidate_paths:
        relative = path.relative_to(root).as_posix()
        if relative not in priority_set:
            ordered_paths.append(path)

    if not ordered_paths:
        return "", 0, ()

    lines: list[str] = []
    used_bytes = 0
    omitted: list[str] = []

    for index, path in enumerate(ordered_paths):
        relative = path.relative_to(root)
        relative_posix = relative.as_posix()
        try:
            data = path.read_bytes()
        except OSError:
            continue

        header = f"--- {relative_posix} ---"
        block = f"{header}\n{data.decode('utf-8')}"
        block_bytes = len(block.encode("utf-8"))

        pending_omitted = [
            ordered_paths[i].relative_to(root).as_posix() for i in range(index + 1, len(ordered_paths))
        ]
        truncation_line = _truncation_line(pending_omitted)
        reserve_bytes = _reserve_bytes(truncation_line)
        remaining = max_total_bytes - used_bytes - reserve_bytes

        if remaining <= 0:
            omitted = [ordered_paths[i].relative_to(root).as_posix() for i in range(index, len(ordered_paths))]
            break

        if block_bytes <= remaining:
            lines.append(block)
            used_bytes += block_bytes + 1
            continue

        header_bytes = len(header.encode("utf-8")) + 1
        if remaining > header_bytes:
            truncated_text = _truncate_utf8(data, remaining - header_bytes)
            lines.append(f"{header}\n{truncated_text}")
            used_bytes = max_total_bytes
            omitted = pending_omitted
            break

        omitted = [ordered_paths[i].relative_to(root).as_posix() for i in range(index, len(ordered_paths))]
        break

    if not lines and not omitted:
        return "", 0, ()

    if omitted:
        lines.append(_truncation_line(omitted))

    text = "\n".join(lines)
    return text, len(text.encode("utf-8")), tuple(omitted)


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
