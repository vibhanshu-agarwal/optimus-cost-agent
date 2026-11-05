"""The bounded repository map (Plan 12.10 Task 3; ADR-037): files ranked by what they are observed to import, then their symbols.

Neutral and pure. Structure here is only what was parsed: an import that resolves to an indexed file is an edge, and nothing is inferred.
A smaller budget gives a prefix of the same order, so the map is a stable part of a cacheable prompt prefix.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

_DAMPING: Final = 0.85
_ITERATIONS: Final = 20
_IMPORTS_PREFIX: Final = "imports: "


@dataclass(frozen=True)
class MapFile:
    path: str
    imports: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepoMap:
    text: str
    files_included: int
    files_total: int
    paths: tuple[str, ...] = ()  # the files the text names, in its order

    @property
    def truncated(self) -> bool:
        return self.files_included < self.files_total


def imports_of(description: str | None) -> tuple[str, ...]:
    """The observed imports a file record's description lists."""
    if not description or not description.startswith(_IMPORTS_PREFIX):
        return ()
    return tuple(description[len(_IMPORTS_PREFIX):].split())


def _module_paths(files: Sequence[MapFile]) -> Mapping[str, str]:
    """Every dotted suffix of each file's module name, longest match kept by later lookup. Ambiguous suffixes resolve to nothing."""
    owners: dict[str, set[str]] = {}
    for item in files:
        stem = item.path.rsplit(".", 1)[0].replace("/", ".")
        if stem.endswith(".__init__"):
            stem = stem[: -len(".__init__")]
        parts = stem.split(".")
        for start in range(len(parts)):
            owners.setdefault(".".join(parts[start:]), set()).add(item.path)
    return {name: next(iter(paths)) for name, paths in owners.items() if len(paths) == 1}


def _edges(files: Sequence[MapFile]) -> dict[str, set[str]]:
    modules = _module_paths(files)
    edges: dict[str, set[str]] = {item.path: set() for item in files}
    for item in files:
        for name in item.imports:
            target = modules.get(name)
            if target is not None and target != item.path:
                edges[item.path].add(target)
    return edges


def neighbours(files: Sequence[MapFile], paths: Sequence[str]) -> list[str]:
    """What the given files import, then what imports them, each in path order. Only observed edges, so a file nothing links to has none."""
    edges = _edges(files)
    chosen = set(paths)
    imported = sorted({target for path in paths for target in edges.get(path, ())} - chosen)
    importers = sorted({source for source, targets in edges.items() if targets & chosen} - chosen - set(imported))
    return imported + importers


def rank(files: Sequence[MapFile]) -> dict[str, float]:
    """PageRank over observed imports. Deterministic: sorted iteration and a fixed number of rounds."""
    edges = _edges(files)
    paths = sorted(edges)
    if not paths:
        return {}
    share = 1.0 / len(paths)
    scores = dict.fromkeys(paths, share)
    for _ in range(_ITERATIONS):
        dangling = sum(scores[path] for path in paths if not edges[path])
        following = dict.fromkeys(paths, (1.0 - _DAMPING) * share + _DAMPING * dangling * share)
        for path in paths:
            targets = edges[path]
            if targets:
                gift = _DAMPING * scores[path] / len(targets)
                for target in sorted(targets):
                    following[target] += gift
        scores = following
    return scores


def build_repo_map(files: Sequence[MapFile], *, budget_chars: int, focus: Sequence[str] = ()) -> RepoMap:
    """Named files first, then by rank, ties by path. A file that does not fit is left out whole; the result says how many were."""
    scores = rank(files)
    named = {path: index for index, path in enumerate(focus)}
    ordered = sorted(files, key=lambda item: (named.get(item.path, len(named)), -round(scores.get(item.path, 0.0), 12), item.path))
    lines: list[str] = []
    paths: list[str] = []
    used = 0
    for item in ordered:
        line = item.path + (": " + ", ".join(item.symbols) if item.symbols else "")
        if used + len(line) + 1 > budget_chars:
            break
        lines.append(line)
        paths.append(item.path)
        used += len(line) + 1
    return RepoMap("\n".join(lines), len(lines), len(files), tuple(paths))
