# Plan 12.4 round 2: evidence report (2026-10-27, after Codex round 72)

## The result

**H stays.** On the fresh, sealed 150-item test split, only B (Jev alone) and H (the rules, then Jev) pass both gates (at most 5% of requests routed below their label, and at most 5% of items whose tier changes across the three decisions). Both beat A, the rules alone. B and H are statistically tied under the pre-registered test, and H's estimated total cost is lower, so under R1(a)'s tie-break H wins and stays (rule step 5). Codex round 72 accepted the result; the operator accepted it on 2026-10-27 (CR2, source S15) and closed #426 as not needed.

## What was tested

- **The arms:** A (the rules alone, re-tuned), B (Jev with round 1's frozen `choice` question, threshold re-tuned), H (frozen from round 1's `frozen-1`, never re-tuned), D3 (round 1's frozen DSPy program, three calls per decision with a majority, JSON fallback off), MAX (the higher of B's and D3's tiers with the lower confidence) and GATE (B when Jev's confidence reaches its threshold, else D3). **L and HL were dropped before any paid call (R4):** Luna Decisions' endpoint states no data-use policy and is not on the zero-retention list.
- **The rule (v9 Design 5):** gate every arm; a learned arm must beat A on the paired penalty; among those, the lowest penalty wins, and arms statistically tied with it (95% paired bootstrap interval containing 0) are broken by R1(a)'s estimated total cost per 1,000 turns, then p95 latency.
- **The data:** 150 fresh items, sealed before tuning: 60 archived (the operator's own prompts, 4 redacted), 30 SWE-bench Verified, 30 SWE-chat (2 redacted) and 30 hand-written by Codex. Merged labels 26 easy, 82 medium, 42 complex. Agreement between the two raters: κ 0.602 (0.753 raw); 77 items were flagged context-dependent by at least one rater. Exclusion across both rounds left 0 overlaps in group, text or rater ID.
- **Tuning:** the 280 round-1 items that are not hand-written training items, using round 1's rows plus 260 new D calls (N7: one reused round-1 row counts as one call's answer, for tuning only).
- **Costs:** R1(a)'s estimate uses N6's turn sizes (the operator's Claude Code transcripts, usage counts only: median input 3,243,333 and output 8,226 tokens per typed-prompt turn, cache charged as input) at the `auto` composition's prices. These are approved counterfactual assumptions, not measured Optimus savings.

## Results (all 150 items)

| Arm | Penalty | Under-routes | Items that flip | Exact | Route-up | ECE | $/1k classify | $/1k total (est.) | Gates |
|---|---|---|---|---|---|---|---|---|---|
| A | 0.727 | 14 (9.3%) | 0 | 51.3% | 0% | 0.255 | 0 | 2,427.22 | fail |
| B | 0.487 | 5 (3.3%) | 5 (3.3%) | 58.7% | 68.0% | 0.150 | 0.022 | 2,318.85 | pass |
| **H** | 0.507 | 6 (4.0%) | 5 (3.3%) | 58.0% | 67.3% | 0.160 | 0.022 | **2,306.81** | **pass** |
| D3 | 0.453 | 16 (10.7%) | 10 (6.7%) | 76.0% | 0% | 0.200 | 0.872 | 2,331.75 | fail |
| MAX | 0.353 | 10 (6.7%) | 10 (6.7%) | 78.7% | 0% | 0.187 | 0.894 | 2,331.77 | fail |
| GATE | 0.473 | 18 (12.0%) | 12 (8.0%) | 76.7% | 0% | 0.193 | 0.751 | 2,271.41 | fail |

- **Against A:** B −0.240 [−0.413, −0.067]; H −0.220 [−0.393, −0.047].
- **B against H (published here; `evidence2.json` did not retain it):** H minus B is 0.020 [0.000, 0.053]. **The lower bound is exactly 0, so the tie holds only because the pre-registered test is inclusive (`low <= 0`).** B and H differ on 2 of the 150 items, H the higher penalty on both.
- **Every other view** is in `evidence-tables.md`. Without the context-dependent items (n = 73) the winner is again H by the same tie. By source: archived selects A (passing learned arms do not significantly beat it), hand-written selects H, and neither SWE source has a passing arm.
- **Sensitivity (penalty weights 2× and 5×, `extra-facts.txt`):** the outcome is the same. The gates do not depend on the weights; B and H still both beat A (at 5×, B −0.360 [−0.627, −0.100] and H −0.327 [−0.587, −0.073]); and H minus B still has a lower bound of exactly 0 (0.013 [0.000, 0.033] at 2×, 0.033 [0.000, 0.093] at 5×), so they stay tied.
- **How the judges err (`extra-facts.txt`):** B and H route most medium items up to complex (41 of 82); D3, MAX and GATE under-route mostly complex items to medium (9 to 15 each).
- **Cost:** always-complex is $2,463.35 per 1,000 and always-easy $656.89; routing every request at its label would be $2,150.23. H's estimate is about 6.35% below always-complex, and almost all of its advantage over B comes from one more request left on the easy tier.

## What this does not establish (Codex round 72)

- The sampling unit is 150 requests, not 1,800 observations. First-repeat outcomes determine penalty, under-routing, accuracy, cost and route-up; all three decisions determine flips.
- Passing the gates does not establish population rates below 5%: B's under-route and flip intervals reach about 7.6%, H's under-route interval 8.5%.
- "Tied" means insufficient evidence of a difference, not demonstrated equivalence.
- D3's threshold froze at 0.0, a legitimate tuning result (no confidence route-up); MAX froze at 0.0 and GATE inherits D3's. Their higher accuracy cannot override failed gates, and changing thresholds now would need fresh confirmation data.
- D3, MAX and GATE latency is modelled as concurrent production calls from sequential measurements; it does not demonstrate a working concurrent mechanism.
- Calibration is poor for every arm (ECE 0.15–0.26): the confidences are routing heuristics, not probabilities. ECE scores each first-repeat confidence against its final tier; A's and H's are rule scores in part.
- The labels: κ 0.602, 77 context flags, source-specific agreement, and the disclosed rater and tuner exposure (the main session saw aggregate statistics and once printed three lines of opaque IDs and tiers from a label file). Complete label blindness is not claimed.

## Run integrity and spend

- **The steps** (`task6\run-round2.sh`, stopping at the first failure): `start` (ledger offset 3,753 rows, prefix SHA-256 `bdbc0f15e55632ff62366d1b827dc523b6552b1f610e9447747f55e6326ab2cc`), `probe2` (skipped: no Luna), `smoke2` (passed every check), `collect2 D`, `freeze2`, `test2`, `report2`. No step failed.
- **The test:** 150 items × (3 B + 9 D calls) = 1,800 rows, every call answered 200 with its own Gateway request ID and a known cost, no cache hit, no abstention or malformed answer.
- **The seal:** opened only by `test2` and `report2`, after checking the freeze's identities and the sealed files' pinned hashes, and closed after each (the harness's self-checks exercise every refusal).
- **Spend:** smoke $0.007506300, tuning $0.079022600, test $0.401541654: **round $0.488070554 of $5**. The pilot's known total is **$1.191560232 of $15**, plus the still-unknown $0.001333 provision ($1.192893232 with it).

## Deviations (approved before the paid calls; recorded in Plan 12.4 v10)

- **R4:** L and HL dropped; the `evaluation` profile and its hash `d8d0b90e…` unchanged; no Luna probe.
- **N6:** the turn sizes from the operator's Claude Code transcripts instead of the Optimus Gateway's logs (which held 20 test turns).
- **N7:** the one two-call round-1 D row reused as one answer, for tuning only.
- **D3's JSON fallback off:** the frozen program's bytes are unchanged; the adapter no longer makes a second call on an unparseable reply.

## Files (review kit, `plan12-4-auto\task6\`)

- `runs\round-start.json`, `runs\smoke-2\`, `runs\tune2-D\`, `runs\freeze-2\frozen2.json`, `runs\test-2\` (`predictions.jsonl`, `outcome.json`, `evidence2.json`), `runs\logs\`;
- `runs\arms.json` (`db1b3476…`) and `runs\turn-sizes.json` (`9db52161…`);
- `harness\round2.py` and `harness\selfcheck_round2.py` (hashes in `README.md`);
- `round2-data-record.md` (the set's sourcing, exclusion and labelling record);
- `repo-bundle-scripts\` (the scripts that built this bundle).
