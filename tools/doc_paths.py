"""Find repository documents by file name, wherever the archive convention has put them.

Every docs folder keeps its current documents at its root and everything else in an
``archive/`` subfolder beside them. Moving a document into (or out of) ``archive/`` must not
require editing tests, tools or the frozen documents that mention it, so nothing should
hard-code which of the two places a document lives in:

* ``doc_path("X.md")`` returns the one tracked file under ``docs/`` named ``X.md``;
* ``resolves_with_archive(path)`` and ``link_resolves(document, target)`` accept a reference
  to a document that has since moved between a folder's root and its ``archive/``.

Document file names under ``docs/`` are unique; ``doc_path`` fails loudly otherwise. Folder
guides named ``README.md`` and the ``docs/sources/`` publication bundles (which share generic
file names) are not looked up by name.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
ARCHIVE_DIRNAME = "archive"
_UNINDEXED_PREFIXES = ("docs/sources/",)
_UNINDEXED_NAMES = frozenset({"README.md"})  # folder guides, always addressed by path


@lru_cache(maxsize=1)
def _docs_by_name() -> dict[str, tuple[Path, ...]]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "docs"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\0")
    index: dict[str, list[Path]] = {}
    for relative in tracked:
        if not relative or relative.startswith(_UNINDEXED_PREFIXES):
            continue
        if relative.rsplit("/", 1)[-1] in _UNINDEXED_NAMES:
            continue
        path = REPO_ROOT / relative
        if path.is_file():
            index.setdefault(path.name, []).append(path)
    return {name: tuple(paths) for name, paths in index.items()}


def doc_path(reference: str | PurePosixPath | Path) -> Path:
    """Return the tracked document named like ``reference``.

    ``reference`` may be a bare file name or any repository path to the document, with or
    without an ``archive/`` segment; only the file name is used.
    """
    name = PurePosixPath(str(reference).replace("\\", "/")).name
    matches = _docs_by_name().get(name, ())
    if len(matches) != 1:
        found = [path.relative_to(REPO_ROOT).as_posix() for path in matches]
        raise LookupError(f"expected exactly one tracked document named {name!r} under docs/, found {found}")
    return matches[0]


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def archive_twins(path: Path) -> tuple[Path, ...]:
    """Where ``path`` would be had it (or a folder above it) moved across an ``archive/`` boundary.

    A document or a whole folder (for example a ``docs/sources/`` publication bundle) moves
    into the ``archive/`` beside it, or back out, so an ``archive`` segment is inserted before,
    or removed from, any one component below ``docs/``.
    """
    try:
        relative = path.relative_to(DOCS_ROOT)
    except ValueError:
        return ()
    parts = relative.parts
    twins: list[Path] = []
    for index in range(len(parts)):
        if parts[index] == ARCHIVE_DIRNAME:
            twins.append(DOCS_ROOT.joinpath(*parts[:index], *parts[index + 1 :]))
        else:
            twins.append(DOCS_ROOT.joinpath(*parts[:index], ARCHIVE_DIRNAME, *parts[index:]))
    return tuple(twins)


def resolves_with_archive(path: Path) -> bool:
    """True if ``path`` exists, or exists on the other side of an ``archive/`` boundary."""
    return path.exists() or any(twin.exists() for twin in archive_twins(path))


def link_resolves(document: Path, target: str) -> bool:
    """True if relative link ``target`` in ``document`` reaches an existing file.

    Allows for the target having moved between its folder root and ``archive/``, and for the
    linking document itself having moved into ``archive/`` without its links being rewritten.
    """
    bases = [document.parent]
    if document.parent.name == ARCHIVE_DIRNAME:
        bases.append(document.parent.parent)
    return any(resolves_with_archive((base / target).resolve()) for base in bases)
