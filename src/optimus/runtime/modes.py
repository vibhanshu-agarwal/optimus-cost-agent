from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath


class ExecutionMode(StrEnum):
    PLAN = "PLAN"
    CHAT = "CHAT"
    AGENT = "AGENT"


class GenerationScope(StrEnum):
    INLINE_SNIPPET = "INLINE_SNIPPET"
    PATCH_PROPOSAL = "PATCH_PROPOSAL"
    FILE_MUTATION = "FILE_MUTATION"
    MULTI_FILE_CHANGESET = "MULTI_FILE_CHANGESET"


def classify_generation_scope(
    *,
    generated_line_count: int,
    modified_paths: list[str],
    created_paths: list[str],
    deleted_paths: list[str],
    touches_core_package: bool,
) -> GenerationScope:
    # Scope names are specified by the architecture. The line-count and root
    # heuristics are conservative Phase 1 implementation decisions.
    changed_paths = [*modified_paths, *created_paths, *deleted_paths]
    if touches_core_package or _distinct_roots(changed_paths) > 1:
        return GenerationScope.MULTI_FILE_CHANGESET
    if created_paths or deleted_paths:
        return GenerationScope.FILE_MUTATION
    if modified_paths:
        return GenerationScope.PATCH_PROPOSAL
    if generated_line_count < 15:
        return GenerationScope.INLINE_SNIPPET
    return GenerationScope.PATCH_PROPOSAL


def _distinct_roots(paths: list[str]) -> int:
    roots: set[str] = set()
    for path in paths:
        parts = PurePosixPath(path.replace("\\", "/")).parts
        if parts:
            roots.add(parts[0])
    return len(roots)
