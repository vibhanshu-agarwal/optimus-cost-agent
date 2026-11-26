"""Optional-packing policies (Plan 12.14, ranking design; D2). Pure: the same inputs always choose the same items.

They decide only which optional items fill a disclosure phase's room. Ranking, fusion, the quota and required evidence are not theirs:
the ranked order and recall at five stay exactly as retrieval gave them, and the pack still renders what it chose in fused order.

- baseline: M1's greedy fill in fused order.
- density: score * (1 + marginal_terms / max(1, task_terms)) / max(1, own tokens).
- coverage: the same numerator, undivided.

Marginal terms are the task's lexical terms a candidate's own text adds to what this phase has already admitted, recomputed after each
choice. Quota places are considered first, in their existing order; the rest follow by policy key, ties by fused ordinal.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from .code_index import split_terms

POLICIES: Final = ("baseline", "density", "coverage")


@dataclass(frozen=True)
class Candidate:
    """One optional item as this phase would render it: its own signature line or excerpt block."""

    id: str
    text: str
    score: float
    ordinal: int  # its place in the fused order


def terms_of(text: str) -> frozenset[str]:
    """Folded the way the lexical channel folds a task, without the route's term cap."""
    return frozenset(term for word in text.split() for term in split_terms([word]).split())


def marginal_terms(candidate: Candidate, covered: Iterable[str], task: frozenset[str]) -> int:
    return len((terms_of(candidate.text) & task) - set(covered))


def select(header: str, candidates: Sequence[Candidate], *, room: int, estimate: Callable[[str], int], policy: str,
           task_terms: Sequence[str], protected: frozenset[str]) -> list[Candidate]:
    """The candidates this phase admits, in the order chosen. Fit is the whole phase as rendered: header, then the chosen in fused order."""
    if policy not in POLICIES:
        raise ValueError(f"unknown packing policy {policy!r}")
    chosen: list[Candidate] = []

    def fits(item: Candidate) -> bool:
        lines = [c.text for c in sorted([*chosen, item], key=lambda c: c.ordinal)]
        return estimate("\n".join([header, *lines])) <= room

    if policy == "baseline":
        for item in candidates:
            if fits(item):
                chosen.append(item)  # noqa: PERF401 - fits() reads chosen, so each append changes the next test
        return chosen

    task = frozenset(task_terms)
    denominator = max(1, len(task))
    covered: set[str] = set()

    def admit(item: Candidate) -> None:
        chosen.append(item)
        covered.update(terms_of(item.text) & task)

    for item in candidates:
        if item.id in protected and fits(item):
            admit(item)
    remaining = [item for item in candidates if item not in chosen]
    costs = {item.id: max(1, estimate(item.text)) for item in remaining}

    def key(item: Candidate) -> tuple[float, int]:
        value = item.score * (1 + marginal_terms(item, covered, task) / denominator)
        if policy == "density":
            value /= costs[item.id]
        return (-round(value, 15), item.ordinal)

    while remaining:
        for item in sorted(remaining, key=key):
            if fits(item):
                admit(item)
                remaining.remove(item)
                break
        else:
            break
    return chosen
