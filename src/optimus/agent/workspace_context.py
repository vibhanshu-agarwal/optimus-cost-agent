from __future__ import annotations

from pathlib import Path

DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES = 16 * 1024
_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules", ".idea"})
_TRUNCATION_PREFIX = "--- omitted (size cap): "


def gather_workspace_context_for_prompt(
    workspace_root: Path,
    *,
    max_total_bytes: int = DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES,
) -> str:
    """Return inner workspace file blocks for the planner prompt (no outer header/footer)."""
    root = workspace_root.resolve()
    if not root.is_dir():
        return ""

    candidate_paths = _list_includable_files(root)
    if not candidate_paths:
        return ""

    lines: list[str] = []
    used_bytes = 0
    omitted: list[str] = []

    for index, path in enumerate(candidate_paths):
        relative = path.relative_to(root)
        relative_posix = relative.as_posix()
        try:
            data = path.read_bytes()
        except OSError:
            continue

        header = f"--- {relative_posix} ---"
        block = f"{header}\n{data.decode('utf-8')}"
        block_bytes = len(block.encode("utf-8"))

        pending_omitted = [candidate_paths[i].relative_to(root).as_posix() for i in range(index + 1, len(candidate_paths))]
        truncation_line = _truncation_line(pending_omitted)
        reserve_bytes = _reserve_bytes(truncation_line)
        remaining = max_total_bytes - used_bytes - reserve_bytes

        if remaining <= 0:
            omitted = [candidate_paths[i].relative_to(root).as_posix() for i in range(index, len(candidate_paths))]
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

        omitted = [candidate_paths[i].relative_to(root).as_posix() for i in range(index, len(candidate_paths))]
        break

    if not lines and not omitted:
        return ""

    if omitted:
        lines.append(_truncation_line(omitted))

    return "\n".join(lines)


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
