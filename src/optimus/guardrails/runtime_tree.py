"""The reserved runtime tree, `<workspace>/.optimus/`: one rule shared by automatic workspace context and by every
model-issued file access through the guard (Plan 12.2 READ + W).

Every launch writes its runtime state there (debug trace, launch audit, Gateway log, telemetry, the Stage C ledger).
It is never workspace context, and a model never reads or writes it: at any depth, under any casing NTFS treats as the
same name, nor through a file alias or junction whose target lies in one.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUNTIME_DIR_NAME = ".optimus"
_WINDOWS = sys.platform == "win32"  # NTFS is case-insensitive, so the reserved name is compared casefolded there


def has_runtime_component(parts: tuple[str, ...]) -> bool:
    """Whether any path component is the reserved runtime directory name."""
    if _WINDOWS:
        return any(part.casefold() == RUNTIME_DIR_NAME for part in parts)
    return RUNTIME_DIR_NAME in parts


def resolve_target(path: Path) -> Path | None:
    """A path's real target, or None when it cannot be resolved. Resolution is not strict: a strict resolve would
    reject every file on a Windows filesystem without final-path support (there, a best-effort path is used and the
    lexical rule still applies). A caller treats None as unresolvable and never reads the path."""
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def target_reserved(target: Path, root: Path) -> bool:
    """Whether a resolved target lies in a runtime tree, judged from path metadata alone (its content is never
    opened). A target inside the workspace is judged by its workspace-relative parts, so a workspace under an
    ancestor that happens to share the reserved name keeps its files; a target outside it by its absolute parts."""
    try:
        parts = target.relative_to(root).parts
    except ValueError:
        parts = target.parts
    return has_runtime_component(parts)
