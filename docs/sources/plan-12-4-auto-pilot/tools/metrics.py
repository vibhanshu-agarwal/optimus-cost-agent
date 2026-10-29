"""The pilot's metrics and its pre-registered decision rule (Plan 12.4 v7 Design 3). Standard library only.

Every metric is computed on the final routed tier, after any route-up, with requests as the sampling unit. Run
``python -I metrics.py`` for the self-checks.
"""

from __future__ import annotations

import dataclasses
import math
import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass

TIERS = ("easy", "medium", "complex")
RANK = {tier: index for index, tier in enumerate(TIERS)}
UNDER_WEIGHT, OVER_WEIGHT = 3, 1
GATE_UNDER, GATE_FLIP = 0.05, 0.05
BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED = 10_000, 20261026


def route(predicted: str | None, confidence: float | None, threshold: float) -> tuple[str, bool]:
    """The final tier and whether it was routed up. Low confidence routes one tier up (ADR-007). An abstention (no
    tier) routes one tier above the ordinary default, medium: complex."""
    if predicted not in RANK:
        return "complex", True
    if confidence is not None and confidence < threshold:
        return TIERS[min(RANK[predicted] + 1, 2)], RANK[predicted] < 2
    return predicted, False


def penalty(label: str, final: str, *, under_weight: int = UNDER_WEIGHT) -> int:
    gap = RANK[label] - RANK[final]
    return under_weight * gap if gap > 0 else OVER_WEIGHT * -gap


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    expected = sum((a.count(t) / n) * (b.count(t) / n) for t in TIERS)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def macro_f1(labels: Sequence[str], predictions: Sequence[str]) -> float:
    scores = []
    for tier in TIERS:
        tp = sum(lab == tier and p == tier for lab, p in zip(labels, predictions, strict=True))
        fp = sum(lab != tier and p == tier for lab, p in zip(labels, predictions, strict=True))
        fn = sum(lab == tier and p != tier for lab, p in zip(labels, predictions, strict=True))
        scores.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return sum(scores) / len(scores)


def ece(confidences: Sequence[float], correct: Sequence[bool], bins: int = 10) -> float:
    total, n = 0.0, len(confidences)
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [i for i, c in enumerate(confidences) if (low < c <= high) or (index == 0 and c == 0)]
        if members:
            accuracy = sum(correct[i] for i in members) / len(members)
            mean_confidence = sum(confidences[i] for i in members) / len(members)
            total += len(members) / n * abs(accuracy - mean_confidence)
    return total


def percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED) -> tuple[float, float, float]:
    """Mean of a − b over requests, with a 95% percentile interval from resampling requests."""
    n = len(a)
    differences = [x - y for x, y in zip(a, b, strict=True)]
    rng = random.Random(seed)
    means = [sum(differences[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)]
    return (sum(differences) / n, percentile(means, 0.025), percentile(means, 0.975))


@dataclass(frozen=True)
class ArmResult:
    """One frozen configuration on the test split: per request, the 3 repeats' final tiers, plus the first repeat's
    confidence, route-up, latency and cost."""

    name: str
    labels: tuple[str, ...]
    finals: tuple[tuple[str, ...], ...]
    confidences: tuple[float | None, ...]
    routed_up: tuple[bool, ...]
    latencies_s: tuple[float, ...]
    costs_usd: tuple[float, ...]

    def penalties(self, under_weight: int = UNDER_WEIGHT) -> list[int]:
        return [penalty(label, final[0], under_weight=under_weight) for label, final in zip(self.labels, self.finals, strict=True)]

    def summary(self) -> dict[str, object]:
        n = len(self.labels)
        first = [final[0] for final in self.finals]
        under = sum(RANK[f] < RANK[lab] for lab, f in zip(self.labels, first, strict=True))
        flips = sum(len(set(final)) > 1 for final in self.finals)
        confident = [(c, f == lab) for c, f, lab in zip(self.confidences, first, self.labels, strict=True) if c is not None]
        return {
            "arm": self.name,
            "n": n,
            "penalty_mean": sum(self.penalties()) / n,
            "penalty_mean_2x": sum(self.penalties(2)) / n,
            "penalty_mean_5x": sum(self.penalties(5)) / n,
            "under_route_rate": under / n,
            "under_route_wilson": wilson(under, n),
            "flip_rate": flips / n,
            "flip_wilson": wilson(flips, n),
            "accuracy": sum(f == lab for lab, f in zip(self.labels, first, strict=True)) / n,
            "macro_f1": macro_f1(self.labels, first),
            "route_up_rate": sum(self.routed_up) / n,
            "latency_p50_s": percentile(self.latencies_s, 0.5) if self.latencies_s else 0.0,
            "latency_p95_s": percentile(self.latencies_s, 0.95) if self.latencies_s else 0.0,
            "cost_per_1000_usd": 1000 * sum(self.costs_usd) / n,
            "ece": ece([c for c, _ in confident], [k for _, k in confident]) if confident else None,
            "passes_gates": under / n <= GATE_UNDER and flips / n <= GATE_FLIP,
        }


def decide(arms: Sequence[ArmResult], *, baseline: str = "A") -> dict[str, object]:
    """The pre-registered rule: gates for every arm; the lowest mean penalty among passing arms; a learned arm must
    beat A with a paired interval excluding zero; ties by measured cost per 1,000 requests, then p95 latency."""
    summaries = {arm.name: arm.summary() for arm in arms}
    by_name = {arm.name: arm for arm in arms}
    passing = [name for name, s in summaries.items() if s["passes_gates"]]
    base = by_name.get(baseline)
    contenders = []
    for name in passing:
        if name == baseline:
            continue
        if base is None:
            contenders.append(name)
            continue
        mean, low, high = paired_bootstrap(by_name[name].penalties(), base.penalties())
        summaries[name]["vs_A_penalty"] = (mean, low, high)
        if high < 0:
            contenders.append(name)
    if not contenders:
        winner = baseline if baseline in passing else None
        reason = "no learned arm passes and beats A" if winner else "passing learned arms do not beat A, and A fails the gates" if passing else "no arm passes"
        return {"winner": winner, "reason": reason, "summaries": summaries}
    contenders.sort(key=lambda name: summaries[name]["penalty_mean"])
    best = contenders[0]
    tied = [best]
    for name in contenders[1:]:
        _, low, high = paired_bootstrap(by_name[name].penalties(), by_name[best].penalties())
        if low <= 0 <= high:
            tied.append(name)
    key: Callable[[str], tuple[float, float]] = lambda name: (summaries[name]["cost_per_1000_usd"], summaries[name]["latency_p95_s"])  # noqa: E731
    winner = min(tied, key=key)
    return {"winner": winner, "reason": "lowest penalty" if len(tied) == 1 else f"tie among {tied}: lower cost, then p95", "summaries": summaries}


def _selfcheck() -> None:
    assert route("easy", 0.9, 0.5) == ("easy", False)
    assert route("easy", 0.4, 0.5) == ("medium", True)
    assert route("complex", 0.1, 0.5) == ("complex", False)
    assert route(None, None, 0.5) == ("complex", True)
    assert penalty("complex", "easy") == 6 and penalty("easy", "complex") == 2 and penalty("medium", "medium") == 0
    assert penalty("complex", "medium", under_weight=5) == 5
    low, high = wilson(0, 150)
    assert low < 1e-12 and 0.02 < high < 0.03, (low, high)
    assert abs(cohen_kappa(["easy", "medium", "complex"] * 4, ["easy", "medium", "complex"] * 4) - 1) < 1e-12
    assert abs(cohen_kappa(["easy", "easy", "medium", "medium"], ["easy", "medium", "easy", "medium"])) < 1e-12
    assert macro_f1(["easy", "medium", "complex"], ["easy", "medium", "complex"]) == 1.0
    assert ece([1.0, 1.0], [True, True]) == 0.0 and abs(ece([0.9, 0.9], [False, False]) - 0.9) < 1e-12
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    mean, low, high = paired_bootstrap([0.0] * 50, [1.0] * 50, resamples=200)
    assert mean == -1 and low == high == -1
    labels = tuple(["easy", "medium", "complex"] * 10)
    perfect = ArmResult("C", labels, tuple((lab, lab, lab) for lab in labels), (0.9,) * 30, (False,) * 30, (1.0,) * 30, (0.001,) * 30)
    upward = ArmResult("A", labels, tuple(("complex",) * 3 for _ in labels), (None,) * 30, (False,) * 30, (0.0,) * 30, (0.0,) * 30)
    flippy = ArmResult("B", labels, tuple((lab, "complex", lab) for lab in labels), (0.9,) * 30, (False,) * 30, (1.0,) * 30, (0.0,) * 30)
    result = decide([perfect, upward, flippy])
    assert result["winner"] == "C", result
    assert result["summaries"]["B"]["passes_gates"] is False and result["summaries"]["A"]["passes_gates"] is True
    under = ArmResult("C", labels, tuple(("easy",) * 3 for _ in labels), (0.9,) * 30, (False,) * 30, (1.0,) * 30, (0.0,) * 30)
    assert decide([under, upward])["winner"] == "A"
    assert decide([under])["winner"] is None
    # A fails the flip gate with a perfect first repeat; B passes but cannot beat it: no winner, and the reason says so.
    unbeaten = decide([dataclasses.replace(flippy, name="A"), dataclasses.replace(upward, name="B")])
    assert unbeaten["winner"] is None and unbeaten["reason"].startswith("passing learned arms"), unbeaten
    twin = ArmResult("D", labels, perfect.finals, perfect.confidences, perfect.routed_up, (2.0,) * 30, (0.0005,) * 30)
    tie = decide([perfect, twin, upward])
    assert tie["winner"] == "D" and "tie" in tie["reason"], tie
    assert statistics.median([1, 3]) == 2
    print("metrics self-checks passed")


if __name__ == "__main__":
    _selfcheck()
