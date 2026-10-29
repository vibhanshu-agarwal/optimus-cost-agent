# Round 2 evidence tables (sealed test set, n = 150)

Rendered from `manifest.ndjson` by `tools/recompute.py`, which reproduces every view, winner, reason and metric in the review kit's `evidence2.json` (0 mismatches). ECE is not in `evidence2.json` (its report passed no confidences); it is computed here from the manifest's first-repeat confidences against the first repeat's final tier, as `ArmResult.summary()` computes it.

**The confidence behind each arm's ECE:**
- **A:** rule score.
- **B:** model confidence (Jev's stated confidence; none on an abstention).
- **D3:** model confidence (the vote share of D3's three calls; 0 on an abstention).
- **GATE:** mixture: Jev's confidence when it reaches the Jev threshold, else D3's vote share.
- **H:** mixture: the rule score when the rules answer, else Jev's confidence.
- **MAX:** mixture: the lower of Jev's confidence and D3's vote share; none when either abstains.

## all (n = 150)

**Rule outcome:** H — tie among ['B', 'H']: lower estimated total cost, then p95.

| Arm | Penalty (3×) | 2× | 5× | Under-route | Flip | Accuracy | Macro-F1 | Route-up | p50 s | p95 s | $/1k classify | $/1k total (R1(a) estimate) | ECE | Under-route 95% | Flip 95% | Passes gates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0.727 | 0.633 | 0.913 | 9.3% | 0.0% | 51.3% | 0.411 | 0.0% | 0.00 | 0.00 | 0.0000 | 2427.22 | 0.255 | [5.6%, 15.1%] | [0.0%, 2.5%] | no |
| B | 0.487 | 0.453 | 0.553 | 3.3% | 3.3% | 58.7% | 0.574 | 68.0% | 0.79 | 0.92 | 0.0223 | 2318.85 | 0.150 | [1.4%, 7.6%] | [1.4%, 7.6%] | yes |
| D3 | 0.453 | 0.347 | 0.667 | 10.7% | 6.7% | 76.0% | 0.697 | 0.0% | 3.78 | 6.53 | 0.8717 | 2331.75 | 0.200 | [6.7%, 16.6%] | [3.7%, 11.8%] | no |
| GATE | 0.473 | 0.353 | 0.713 | 12.0% | 8.0% | 76.7% | 0.723 | 0.0% | 4.51 | 7.48 | 0.7507 | 2271.41 | 0.193 | [7.7%, 18.2%] | [4.6%, 13.5%] | no |
| H | 0.507 | 0.467 | 0.587 | 4.0% | 3.3% | 58.0% | 0.566 | 67.3% | 0.79 | 0.92 | 0.0215 | 2306.81 | 0.160 | [1.8%, 8.5%] | [1.4%, 7.6%] | yes |
| MAX | 0.353 | 0.287 | 0.487 | 6.7% | 6.7% | 78.7% | 0.725 | 0.0% | 3.78 | 6.53 | 0.8940 | 2331.77 | 0.187 | [3.7%, 11.8%] | [3.7%, 11.8%] | no |

**Paired penalty difference against A (mean, 95% bootstrap):** B -0.240 [-0.413, -0.067]; H -0.220 [-0.393, -0.047].

**B minus H paired penalty difference (mean, 95% bootstrap):** -0.020 [-0.053, +0.000].

Oracle estimated total cost (routing every request at its label, R1(a)): $2150.23 per 1,000.

## without_context_dependent (n = 73)

**Rule outcome:** H — tie among ['B', 'H']: lower estimated total cost, then p95.

| Arm | Penalty (3×) | 2× | 5× | Under-route | Flip | Accuracy | Macro-F1 | Route-up | p50 s | p95 s | $/1k classify | $/1k total (R1(a) estimate) | ECE | Under-route 95% | Flip 95% | Passes gates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0.822 | 0.712 | 1.041 | 11.0% | 0.0% | 45.2% | 0.380 | 0.0% | 0.00 | 0.00 | 0.0000 | 2389.11 | 0.137 | [5.7%, 20.2%] | [0.0%, 5.0%] | no |
| B | 0.411 | 0.384 | 0.466 | 2.7% | 1.4% | 65.8% | 0.669 | 49.3% | 0.79 | 0.94 | 0.0254 | 2215.91 | 0.173 | [0.8%, 9.5%] | [0.2%, 7.4%] | yes |
| D3 | 0.425 | 0.329 | 0.616 | 9.6% | 8.2% | 76.7% | 0.754 | 0.0% | 3.93 | 7.56 | 0.9149 | 2241.55 | 0.187 | [4.7%, 18.5%] | [3.8%, 16.8%] | no |
| GATE | 0.384 | 0.288 | 0.575 | 9.6% | 8.2% | 80.8% | 0.816 | 0.0% | 4.52 | 8.35 | 0.6673 | 2167.06 | 0.147 | [4.7%, 18.5%] | [3.8%, 16.8%] | no |
| H | 0.452 | 0.411 | 0.534 | 4.1% | 1.4% | 64.4% | 0.646 | 47.9% | 0.79 | 0.93 | 0.0238 | 2191.17 | 0.193 | [1.4%, 11.4%] | [0.2%, 7.4%] | yes |
| MAX | 0.397 | 0.315 | 0.562 | 8.2% | 8.2% | 78.1% | 0.764 | 0.0% | 3.93 | 7.56 | 0.9403 | 2241.57 | 0.141 | [3.8%, 16.8%] | [3.8%, 16.8%] | no |

**Paired penalty difference against A (mean, 95% bootstrap):** B -0.411 [-0.658, -0.178]; H -0.370 [-0.603, -0.137].

**B minus H paired penalty difference (mean, 95% bootstrap):** -0.041 [-0.110, +0.000].

Oracle estimated total cost (routing every request at its label, R1(a)): $2116.90 per 1,000.

## source:archived (n = 60)

**Rule outcome:** A — no passing learned arm beats A; A passes.

| Arm | Penalty (3×) | 2× | 5× | Under-route | Flip | Accuracy | Macro-F1 | Route-up | p50 s | p95 s | $/1k classify | $/1k total (R1(a) estimate) | ECE | Under-route 95% | Flip 95% | Passes gates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0.600 | 0.550 | 0.700 | 5.0% | 0.0% | 56.7% | 0.373 | 0.0% | 0.00 | 0.00 | 0.0000 | 2463.35 | 0.387 | [1.7%, 13.7%] | [0.0%, 6.0%] | yes |
| B | 0.533 | 0.517 | 0.567 | 1.7% | 3.3% | 51.7% | 0.375 | 81.7% | 0.80 | 0.91 | 0.0195 | 2433.26 | 0.085 | [0.3%, 8.9%] | [0.9%, 11.4%] | yes |
| D3 | 0.533 | 0.417 | 0.767 | 11.7% | 8.3% | 70.0% | 0.443 | 0.0% | 3.72 | 5.73 | 0.8462 | 2434.09 | 0.256 | [5.8%, 22.2%] | [3.6%, 18.1%] | no |
| GATE | 0.583 | 0.450 | 0.850 | 13.3% | 10.0% | 68.3% | 0.435 | 0.0% | 4.52 | 6.53 | 0.8530 | 2403.99 | 0.272 | [6.9%, 24.2%] | [4.7%, 20.1%] | no |
| H | 0.533 | 0.517 | 0.567 | 1.7% | 3.3% | 51.7% | 0.375 | 81.7% | 0.80 | 0.91 | 0.0195 | 2433.26 | 0.085 | [0.3%, 8.9%] | [0.9%, 11.4%] | yes |
| MAX | 0.333 | 0.300 | 0.400 | 3.3% | 8.3% | 75.0% | 0.577 | 0.0% | 3.72 | 5.73 | 0.8657 | 2434.11 | 0.199 | [0.9%, 11.4%] | [3.6%, 18.1%] | no |

**Paired penalty difference against A (mean, 95% bootstrap):** B -0.067 [-0.317, +0.167]; H -0.067 [-0.317, +0.167].

**B minus H paired penalty difference (mean, 95% bootstrap):** +0.000 [+0.000, +0.000].

Oracle estimated total cost (routing every request at its label, R1(a)): $2102.06 per 1,000.

## source:handwritten (n = 30)

**Rule outcome:** H — tie among ['GATE', 'B', 'D3', 'H', 'MAX']: lower estimated total cost, then p95.

| Arm | Penalty (3×) | 2× | 5× | Under-route | Flip | Accuracy | Macro-F1 | Route-up | p50 s | p95 s | $/1k classify | $/1k total (R1(a) estimate) | ECE | Under-route 95% | Flip 95% | Passes gates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0.733 | 0.700 | 0.800 | 3.3% | 0.0% | 43.3% | 0.327 | 0.0% | 0.00 | 0.00 | 0.0000 | 2342.92 | 0.308 | [0.6%, 16.7%] | [0.0%, 11.4%] | yes |
| B | 0.067 | 0.067 | 0.067 | 0.0% | 0.0% | 93.3% | 0.927 | 6.7% | 0.80 | 0.89 | 0.0227 | 1861.22 | 0.049 | [0.0%, 11.4%] | [0.0%, 11.4%] | yes |
| D3 | 0.100 | 0.100 | 0.100 | 0.0% | 0.0% | 90.0% | 0.889 | 0.0% | 1.85 | 4.47 | 0.7022 | 2042.54 | 0.089 | [0.0%, 11.4%] | [0.0%, 11.4%] | yes |
| GATE | 0.000 | 0.000 | 0.000 | 0.0% | 0.0% | 100.0% | 1.000 | 0.0% | 0.80 | 3.25 | 0.0908 | 1861.29 | 0.008 | [0.0%, 11.4%] | [0.0%, 11.4%] | yes |
| H | 0.100 | 0.100 | 0.100 | 0.0% | 0.0% | 90.0% | 0.886 | 6.7% | 0.79 | 0.89 | 0.0195 | 1861.22 | 0.083 | [0.0%, 11.4%] | [0.0%, 11.4%] | yes |
| MAX | 0.100 | 0.100 | 0.100 | 0.0% | 0.0% | 90.0% | 0.889 | 0.0% | 1.85 | 4.47 | 0.7249 | 2042.57 | 0.082 | [0.0%, 11.4%] | [0.0%, 11.4%] | yes |

**Paired penalty difference against A (mean, 95% bootstrap):** B -0.667 [-0.967, -0.400]; D3 -0.633 [-0.933, -0.367]; GATE -0.733 [-1.033, -0.467]; H -0.633 [-0.933, -0.367]; MAX -0.633 [-0.933, -0.367].

**B minus H paired penalty difference (mean, 95% bootstrap):** -0.033 [-0.100, +0.000].

Oracle estimated total cost (routing every request at its label, R1(a)): $1861.20 per 1,000.

## source:swe-bench (n = 30)

**Rule outcome:** no winner — no arm passes.

| Arm | Penalty (3×) | 2× | 5× | Under-route | Flip | Accuracy | Macro-F1 | Route-up | p50 s | p95 s | $/1k classify | $/1k total (R1(a) estimate) | ECE | Under-route 95% | Flip 95% | Passes gates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0.833 | 0.667 | 1.167 | 16.7% | 0.0% | 50.0% | 0.320 | 0.0% | 0.00 | 0.00 | 0.0000 | 2403.13 | 0.175 | [7.3%, 33.6%] | [0.0%, 11.4%] | no |
| B | 0.600 | 0.533 | 0.733 | 6.7% | 0.0% | 53.3% | 0.317 | 76.7% | 0.79 | 1.19 | 0.0308 | 2463.38 | 0.203 | [1.8%, 21.3%] | [0.0%, 11.4%] | no |
| D3 | 0.500 | 0.367 | 0.767 | 13.3% | 13.3% | 76.7% | 0.520 | 0.0% | 4.97 | 8.21 | 1.1332 | 2404.27 | 0.156 | [5.3%, 29.7%] | [5.3%, 29.7%] | no |
| GATE | 0.500 | 0.367 | 0.767 | 13.3% | 13.3% | 76.7% | 0.520 | 0.0% | 5.78 | 9.03 | 1.1338 | 2404.27 | 0.154 | [5.3%, 29.7%] | [5.3%, 29.7%] | no |
| H | 0.667 | 0.567 | 0.867 | 10.0% | 0.0% | 53.3% | 0.322 | 73.3% | 0.79 | 1.08 | 0.0300 | 2403.16 | 0.202 | [3.5%, 25.6%] | [0.0%, 11.4%] | no |
| MAX | 0.500 | 0.367 | 0.767 | 13.3% | 13.3% | 76.7% | 0.520 | 0.0% | 4.97 | 8.21 | 1.1640 | 2404.30 | 0.256 | [5.3%, 29.7%] | [5.3%, 29.7%] | no |

**B minus H paired penalty difference (mean, 95% bootstrap):** -0.067 [-0.200, +0.000].

Oracle estimated total cost (routing every request at its label, R1(a)): $2463.35 per 1,000.

## source:swe-chat (n = 30)

**Rule outcome:** no winner — no arm passes.

| Arm | Penalty (3×) | 2× | 5× | Under-route | Flip | Accuracy | Macro-F1 | Route-up | p50 s | p95 s | $/1k classify | $/1k total (R1(a) estimate) | ECE | Under-route 95% | Flip 95% | Passes gates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0.867 | 0.700 | 1.200 | 16.7% | 0.0% | 50.0% | 0.270 | 0.0% | 0.00 | 0.00 | 0.0000 | 2463.35 | 0.283 | [7.3%, 33.6%] | [0.0%, 11.4%] | no |
| B | 0.700 | 0.633 | 0.833 | 6.7% | 10.0% | 43.3% | 0.313 | 93.3% | 0.79 | 0.86 | 0.0190 | 2403.15 | 0.458 | [1.8%, 21.3%] | [3.5%, 25.6%] | no |
| D3 | 0.600 | 0.433 | 0.933 | 16.7% | 3.3% | 73.3% | 0.581 | 0.0% | 3.78 | 6.95 | 0.8305 | 2343.75 | 0.289 | [7.3%, 33.6%] | [0.6%, 16.7%] | no |
| GATE | 0.700 | 0.500 | 1.100 | 20.0% | 6.7% | 70.0% | 0.540 | 0.0% | 4.54 | 7.74 | 0.8231 | 2283.52 | 0.321 | [9.5%, 37.3%] | [1.8%, 21.3%] | no |
| H | 0.700 | 0.633 | 0.833 | 6.7% | 10.0% | 43.3% | 0.313 | 93.3% | 0.79 | 0.86 | 0.0190 | 2403.15 | 0.458 | [1.8%, 21.3%] | [3.5%, 25.6%] | no |
| MAX | 0.500 | 0.367 | 0.767 | 13.3% | 3.3% | 76.7% | 0.652 | 0.0% | 3.78 | 6.95 | 0.8495 | 2343.77 | 0.348 | [5.3%, 29.7%] | [0.6%, 16.7%] | no |

**B minus H paired penalty difference (mean, 95% bootstrap):** +0.000 [+0.000, +0.000].

Oracle estimated total cost (routing every request at its label, R1(a)): $2222.49 per 1,000.

