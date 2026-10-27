"""Recompute every view of the Plan 12.4 pilot's evidence from this bundle's manifest alone, with no review-kit file.

Uses ``metrics.py`` beside it: the pilot's metrics and pre-registered rule, with the single-letter variable ``l``
renamed for this repository's lint and no other change. Prints each view's rule outcome and each arm's main metrics,
which match ``../evidence-tables.md``. Standard library only.

Usage: python -I recompute.py
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import ArmResult, decide  # noqa: E402

BUNDLE = Path(__file__).resolve().parent.parent
# The auto composition's per-tier prices (USD per million tokens, input and output) and the nominal routed turn
# (10,000 input and 1,000 output tokens) behind the report's registry-weighted cost.
PRICES = {"easy": ("0.20", "1.00"), "medium": ("0.75", "3.75"), "complex": ("0.75", "3.75")}
NOMINAL_INPUT, NOMINAL_OUTPUT = 10_000, 1_000


def turn_cost(tier: str) -> float:
    price_in, price_out = PRICES[tier]
    return float((Decimal(price_in) * NOMINAL_INPUT + Decimal(price_out) * NOMINAL_OUTPUT) / 1_000_000)


def main() -> None:
    entries = [json.loads(line) for line in (BUNDLE / "manifest.ndjson").read_text(encoding="utf-8").splitlines()]
    test = [entry for entry in entries if entry["split"] == "test"]
    arms = sorted(test[0]["predictions"])
    views = {"all": test, "without_context_dependent": [entry for entry in test if not entry["context_dependent"]]}
    for source in sorted({entry["source"] for entry in test}):
        views[f"source:{source}"] = [entry for entry in test if entry["source"] == source]
    for view, subset in views.items():
        results = []
        for arm in arms:
            first = [entry["first_repeat"][arm] for entry in subset]
            results.append(ArmResult(
                arm, tuple(entry["label"] for entry in subset), tuple(tuple(entry["predictions"][arm]) for entry in subset),
                tuple(row["confidence"] for row in first), tuple(row["routed_up"] for row in first),
                tuple(row["latency_s"] for row in first), tuple(float(row["cost_usd"]) for row in first),
            ))
        outcome = decide(results)
        oracle = 1000 * sum(turn_cost(entry["label"]) for entry in subset) / len(subset)
        print(f"== {view} (n = {len(subset)}): {outcome['winner'] or 'no winner'}: {outcome['reason']}; oracle ${oracle:.2f}/1k")
        for arm in arms:
            s = outcome["summaries"][arm]
            routed = 1000 * sum(turn_cost(entry["predictions"][arm][0]) for entry in subset) / len(subset)
            interval = s.get("vs_A_penalty")
            versus = f"  vs A {interval[0]:+.3f} [{interval[1]:+.3f}, {interval[2]:+.3f}]" if interval else ""
            print(f"  {arm}: penalty {s['penalty_mean']:.3f}  under {s['under_route_rate']:.1%}  flip {s['flip_rate']:.1%}  "
                  f"accuracy {s['accuracy']:.1%}  gates {'pass' if s['passes_gates'] else 'fail'}  "
                  f"classify ${s['cost_per_1000_usd']:.4f}/1k  routed ${routed:.2f}/1k{versus}")


if __name__ == "__main__":
    main()
