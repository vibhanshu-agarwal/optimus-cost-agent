"""Recompute every view of Plan 12.4 round 2's evidence from this bundle's manifest alone, with no review-kit file.

Uses ``metrics.py`` beside it: round 1's metrics, with the single-letter variable ``l`` renamed for this repository's
lint and no other change. Ports round 2's rule (``decide2``) and R1(a)'s estimated total cost (``turn_cost_fn``)
unchanged from the review kit's ``task6/harness/round2.py``, with the frozen turn sizes and the ``auto`` tier prices
as constants. Prints each view's rule outcome, each arm's main metrics, the B-against-H paired penalty interval (the
test ``decide2`` applies between tied contenders) and each arm's calibration (ECE), which match
``../evidence-tables.md``. Standard library only.

Usage: python -I recompute.py
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import ArmResult, paired_bootstrap  # noqa: E402

BUNDLE = Path(__file__).resolve().parent.parent
# The frozen turn sizes (the review kit's task6/runs/turn-sizes.json): the median typed-prompt turn, in tokens.
INPUT_TOKENS_MEDIAN, OUTPUT_TOKENS_MEDIAN, REASONING_SHARE_OF_OUTPUT = 3243333, 8226, 0
# The auto composition's per-tier prices, USD per million input and output tokens (task6/runs/auto-facts-f11dc3ab.json).
PRICES = {"easy": ("0.20", "1.00"), "medium": ("0.75", "3.75"), "complex": ("0.75", "3.75")}
# What each arm's first-repeat confidence is. ECE scores it against the first repeat's final tier (after any route-up),
# as ArmResult.summary() does; the tier before route-up is not what the metric checks.
CONFIDENCE_KIND = {
    "A": "rule score",
    "B": "model confidence (Jev's stated confidence; none on an abstention)",
    "D3": "model confidence (the vote share of D3's three calls; 0 on an abstention)",
    "GATE": "mixture: Jev's confidence when it reaches the Jev threshold, else D3's vote share",
    "H": "mixture: the rule score when the rules answer, else Jev's confidence",
    "MAX": "mixture: the lower of Jev's confidence and D3's vote share; none when either abstains",
}


def turn_cost(tier: str) -> float:
    """R1(a): the routed turn's estimated cost at the frozen sizes and the auto prices. Reasoning counts as output at
    its measured share; no cache discount."""
    tokens_in = Decimal(str(INPUT_TOKENS_MEDIAN))
    tokens_out = Decimal(str(OUTPUT_TOKENS_MEDIAN)) * (1 + Decimal(str(REASONING_SHARE_OF_OUTPUT)))
    price_in, price_out = PRICES[tier]
    return float((Decimal(price_in) * tokens_in + Decimal(price_out) * tokens_out) / 1_000_000)


def decide2(results: list[ArmResult], total_cost: dict[str, float], *, baseline: str = "A") -> dict[str, Any]:
    """Round 2's complete rule (Design 5), with R1(a)'s tie-break: round2.decide2, unchanged."""
    summaries = {r.name: r.summary() for r in results}
    for name in summaries:
        summaries[name]["total_cost_per_1000_usd"] = total_cost[name]
    by_name = {r.name: r for r in results}
    passing = [n for n, s in summaries.items() if s["passes_gates"]]
    contenders = []
    for name in passing:
        if name == baseline:
            continue
        mean, low, high = paired_bootstrap(by_name[name].penalties(), by_name[baseline].penalties())
        summaries[name]["vs_A_penalty"] = (mean, low, high)
        if high < 0:
            contenders.append(name)
    if not contenders:
        if baseline in passing:
            return {"winner": baseline, "reason": "no passing learned arm beats A; A passes", "summaries": summaries}
        return {"winner": None, "reason": "passing learned arms do not beat A, and A fails the gates" if passing else "no arm passes", "summaries": summaries}
    contenders.sort(key=lambda n: summaries[n]["penalty_mean"])
    best, tied = contenders[0], [contenders[0]]
    for name in contenders[1:]:
        _, low, high = paired_bootstrap(by_name[name].penalties(), by_name[best].penalties())
        if low <= 0 <= high:
            tied.append(name)
    winner = min(tied, key=lambda n: (total_cost[n], summaries[n]["latency_p95_s"]))
    reason = "lowest penalty" if len(tied) == 1 else f"tie among {tied}: lower estimated total cost, then p95"
    return {"winner": winner, "reason": reason, "summaries": summaries}


def load() -> list[dict[str, Any]]:
    return [json.loads(line) for line in (BUNDLE / "manifest.ndjson").read_text(encoding="utf-8").splitlines()]


def views(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out = {"all": entries, "without_context_dependent": [entry for entry in entries if not entry["context_dependent"]]}
    for source in sorted({entry["source"] for entry in entries}):
        out[f"source:{source}"] = [entry for entry in entries if entry["source"] == source]
    return out


def results_for(subset: list[dict[str, Any]], arms: list[str]) -> list[ArmResult]:
    results = []
    for arm in arms:
        first = [entry["first_repeat"][arm] for entry in subset]
        results.append(ArmResult(
            arm, tuple(entry["label"] for entry in subset), tuple(tuple(entry["predictions"][arm]) for entry in subset),
            tuple(row["confidence"] for row in first), tuple(row["routed_up"] for row in first),
            tuple(row["latency_s"] for row in first), tuple(float(row["cost_usd"]) for row in first),
        ))
    return results


def recompute(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every view's rule outcome and summaries, as round2.report2 computes them, plus the B-against-H interval and the
    oracle's estimated total cost. Each summary's ``ece`` uses the manifest's first-repeat confidences."""
    arms = sorted(entries[0]["predictions"])
    out = {}
    for view, subset in views(entries).items():
        results = results_for(subset, arms)
        total = {r.name: 1000 * (sum(r.costs_usd) + sum(turn_cost(f[0]) for f in r.finals)) / len(subset) for r in results}
        decision = decide2(results, total)
        decision["n"] = len(subset)
        by_name = {r.name: r for r in results}
        decision["b_vs_h_penalty"] = paired_bootstrap(by_name["B"].penalties(), by_name["H"].penalties())
        decision["oracle_total_cost_per_1000_usd"] = 1000 * sum(turn_cost(entry["label"]) for entry in subset) / len(subset)
        out[view] = decision
    return out


def main() -> None:
    outcomes = recompute(load())
    print("Confidence behind each arm's ECE:")
    for arm, kind in CONFIDENCE_KIND.items():
        print(f"  {arm}: {kind}")
    for view, outcome in outcomes.items():
        mean, low, high = outcome["b_vs_h_penalty"]
        print(f"== {view} (n = {outcome['n']}): {outcome['winner'] or 'no winner'}: {outcome['reason']}; "
              f"B minus H penalty {mean:+.3f} [{low:+.3f}, {high:+.3f}]; oracle ${outcome['oracle_total_cost_per_1000_usd']:.2f}/1k")
        for arm, s in sorted(outcome["summaries"].items()):
            interval = s.get("vs_A_penalty")
            versus = f"  vs A {interval[0]:+.3f} [{interval[1]:+.3f}, {interval[2]:+.3f}]" if interval else ""
            ece = "n/a" if s["ece"] is None else f"{s['ece']:.3f}"
            print(f"  {arm}: penalty {s['penalty_mean']:.3f}  under {s['under_route_rate']:.1%}  flip {s['flip_rate']:.1%}  "
                  f"accuracy {s['accuracy']:.1%}  macro-F1 {s['macro_f1']:.3f}  route-up {s['route_up_rate']:.1%}  "
                  f"p95 {s['latency_p95_s']:.2f}s  classify ${s['cost_per_1000_usd']:.4f}/1k  total ${s['total_cost_per_1000_usd']:.2f}/1k  "
                  f"ECE {ece}  gates {'pass' if s['passes_gates'] else 'fail'}{versus}")


if __name__ == "__main__":
    main()
