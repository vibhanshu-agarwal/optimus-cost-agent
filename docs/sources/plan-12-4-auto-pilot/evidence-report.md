# Plan 12.4 pilot: evidence report (2026-10-26, revised after Codex round 62)

Which per-turn judge should Auto mode use? Content-free: no prompt text appears here or in the manifest.

**Accepted by the operator on 2026-10-26:** arm H, recorded in ADR-028 (source S13). Paths such as `runs\...` and
`harness\...` are in the review kit, `optimus-handoff\sandbox-review-kit\plan12-4-auto\task3\`.

## The result

**The pre-registered rule selects arm H:** the hybrid. The free rules decide when they are confident (rule confidence
≥ 0.8); otherwise Jev's `choice` question decides. Any answer below confidence 0.95 routes one tier up.

- **B (Jev alone) and H both pass the gates and both beat the rules.** They are tied: H minus B penalty is +0.013,
  with a 95% interval of [−0.020, +0.060]. The rule breaks the tie on classifier cost: H $0.0222 per 1,000 against B
  $0.0238.
- **H is Jev in practice.** The rules decided alone on 4 of 150 test requests.
- **DSPy (D) is the most accurate judge (77%) but fails both gates.** It sends 10% of requests one tier too low,
  nearly all of them complex rated as medium, and 8.7% change answer across repeats. It is also 12× Jev's cost and
  5.6× its p95 latency.
- **This is a bounded pilot result.** H's under-route and flip rates are both 7 of 150 (4.7%), against a 5% gate,
  with Wilson upper bounds of 9.3%. The evidence supports H on this test split; it does not establish population
  rates below 5%. The rule decides on the pooled test split. The per-source and context-free views below are
  reported, not deciding, and none of them has a winner except the hand-written cases (C).
- **Codex round 62** (posted on #395) independently recomputed every metric, winner and interval and recommends
  accepting H, with the conditions this revision applies.

## What was tested

- **Arms:**
  - A: rules (keywords, structure);
  - B: Jev, in `choice` and `score` styles;
  - C: Haiku 5.5 with a hand-written prompt;
  - D: Haiku 5.5 tuned by DSPy 3.4.1, with three optimisers;
  - H: the hybrid of A and the best learned arm.

  All arms ran through the Gateway on the `evaluation` snapshot (`d8d0b90e…`).
- **The data:** 300 labelled requests: 60 hand-written, 120 of the operator's archived agent prompts, 60 SWE-bench
  Verified and 60 SWE-chat.
  - Two raters labelled them, Claude and Codex, with kappa 0.513 and 69% agreement. Disagreements took the higher label.
  - A grouped, stratified split gave 101 train / 49 dev / 150 test. The test labels are 28 easy, 80 medium and 42
    complex.
- **Separation:**
  - **Excluded from tuning:** test items were excluded from optimisation and from threshold selection. Every
    threshold, cut point, variant, program and H's backend was chosen on the 130 tuning items (dev, plus the
    non-hand-written train items), and frozen in `frozen-1` before any test call.
  - **D's training data:** D's optimisers trained on the hand-written train items only.
  - **Not unseen by the author:** the rule author (Claude) read every archived prompt during the confidentiality
    review, and wrote the hand-written cases, before writing A's rules. That exposure also applies to H's rule
    component.
  - **Loaded, but not used:** the harness loads the whole set and then filters by split.
- **The test:** 150 held-out requests × 3 repeats per arm, with caching off. 1,351 Gateway calls, all HTTP 200;
  1,800 predictions; no abstentions; a clean teardown.
- **H was not called separately.** It is reconstructed from the frozen A and B test rows, so its latency excludes the
  rules' own (local) processing time.

## Pooled test results (n = 150)

| Arm | Penalty (3×) | Under-route [95%] | Flip [95%] | Accuracy | Route-up | p95 s | $ per 1k classify | Gates |
|---|---|---|---|---|---|---|---|---|
| A rules | 0.753 | 12.0% [7.7, 18.2] | 0.0% [0.0, 2.5] | 51.3% | 96.7% | 0.00 | 0 | **fail** (under) |
| B Jev | 0.533 | 4.0% [1.8, 8.5] | 4.7% [2.3, 9.3] | 56.0% | 66.0% | 0.83 | 0.0238 | pass |
| C Haiku | 0.613 | 1.3% [0.4, 4.7] | 14.7% [9.9, 21.2] | 47.3% | 74.7% | 4.77 | 0.1210 | **fail** (flip) |
| D DSPy | **0.427** | 10.0% [6.2, 15.8] | 8.7% [5.1, 14.3] | **77.3%** | 0.0% | 4.68 | 0.2908 | **fail** (both) |
| **H hybrid** | 0.547 | 4.7% [2.3, 9.3] | 4.7% [2.3, 9.3] | 56.0% | 65.3% | 0.83 | **0.0222** | pass |

- **Penalty:** a route one tier too low costs 3 per tier, one too high costs 1; lower is better.
- **Which repeat counts:**
  - penalty, under-route, accuracy, route-up, cost, latency and calibration use each request's **first** repeat, on
    the final routed tier after any route-up;
  - flip uses all three repeats.
- **Intervals:** Wilson 95% for the rates.
- **Paired penalty against A** (95% bootstrap): B −0.220 [−0.400, −0.040]; H −0.207 [−0.387, −0.027]. D against B:
  −0.107 [−0.267, +0.060], so D's lower penalty is not significant.
- **The routed cost** at the `auto` registry's prices, for a nominal 10,000-in / 1,000-out turn, per 1,000 turns:
  - always-complex: $11.25;
  - H and B: $10.64;
  - C and D: $10.37;
  - A: $11.20;
  - perfect routing (the oracle): $9.71.

  Medium and complex share one model in today's `auto` list, so only easy turns save money now. The judge's tiers are
  model-independent; the saving changes with the model list, which is configuration.
- **The prices** come from the `auto` composition: Luna for easy, Gemini 3.8 Flash for medium and complex. They were
  dumped at `bece741e…` and are unchanged at the branch head's `b93d67ec…`.

## How each judge errs (first repeat, final tier; rows are the label)

| Label → routed | A | B | C | D | H |
|---|---|---|---|---|---|
| easy → easy / medium / complex | 1 / 23 / 4 | 10 / 16 / 2 | 14 / 5 / 9 | 15 / 13 / 0 | 10 / 16 / 2 |
| medium → easy / medium / complex | 0 / 52 / 28 | 1 / 37 / 42 | 2 / 15 / 63 | 1 / 73 / 6 | 1 / 38 / 41 |
| complex → easy / medium / complex | 0 / 18 / 24 | 0 / 5 / 37 | 0 / 0 / 42 | 0 / 14 / 28 | 0 / 6 / 36 |

- **Jev's raw judgement finds easy turns** (26 of 28 before route-up), but it is unconfident on most turns, so its
  low confidence routes two thirds of them up. That keeps under-routing low and gives up most of the easy saving.
- **D never routes up:** on the tuning data, routing up on its confidence never lowered the penalty, so its threshold
  was frozen at 0.
- **To the easy tier,** the only under-route with a quality cost today, B, D and H each send 1 request too low, C 2,
  and A none.

## Robustness: reported, not deciding

| View | n | Outcome under the same rule |
|---|---|---|
| **All test requests (deciding)** | 150 | **H** (tie with B; lower cost) |
| Under-route weight 2× | 150 | **B**: H's interval against A reaches 0 (−0.133 [−0.267, 0.000]) |
| Under-route weight 5× | 150 | **H** (tie with B; lower cost) |
| The operator's archived prompts | 60 | No winner: B and H flip on 4 of 60 (6.7%) |
| Hand-written cases | 30 | C (penalty 0.200, accuracy 87%) |
| SWE-bench Verified | 29 | No winner: no arm passes |
| SWE-chat | 31 | No winner: B and H pass but do not beat A |
| Without context-dependent requests | 77 | No winner: B under-routes 6.5% and flips 5.2% |

**The subsets are small,** so 2 requests in 30 already exceed a 5% gate. Full tables for every view are in
`runs\test-1\evidence-tables.md`.

## Exploratory, after the test (not deciding; not part of Codex round 62)

The operator asked whether combining judges improves accuracy. Two Jev + DSPy combinations were fixed before
computing, then scored from the existing rows with no new calls (`harness\combo_explore.py`):
- **MAX:** if the two agree, that tier; otherwise the higher one;
- **GATE:** Jev when its confidence is ≥ 0.95, otherwise DSPy.

The test split is no longer sealed, so these figures can only suggest what a fresh test should try.

| Judge | Penalty | Under-route | Flip | Accuracy | Gates |
|---|---|---|---|---|---|
| Jev alone (B) | 0.533 | 4.0% | 4.7% | 56.0% | pass |
| DSPy alone (D) | 0.427 | 10.0% | 8.7% | 77.3% | fail |
| MAX | **0.373** | 6.0% | 8.0% | 75.3% | fail |
| GATE | 0.440 | 10.7% | 8.0% | 77.3% | fail |

- **Both combinations fail the gates,** because the flips come from DSPy's own answers.
- **MAX** lowers the penalty against B (−0.160 [−0.287, −0.027]), and lowers under-routing from 10% to 6%.
- **On the tuning data, MAX** has penalty 0.392 against B's 0.446 (not significant) and under-routes 8.5%.

## Limitations

- **Labels:** kappa 0.513 is moderate agreement. The merged label (the higher on disagreement) is one defensible
  reference, not ground truth, and it favours judges that lean high.
- **Author exposure:** the rule author saw the archived prompts (see Separation above).
- **Context:** 73 of 150 test requests were flagged context-dependent by a rater. In the pilot, 295 of 300 items had no
  previous tier, so the contract's `previous_tier` signal went almost untested. Production passes it.
- **Repeats:** three repeats per request detect instability, but undercount its full rate. ADR-007's evidence already
  notes Jev's answers varying by up to 0.08 across calls.
- **Arm A** has only two tuned cut points, so its rules are simple; that is a limitation of A, not of the method.
- **Not measured:**
  - live turns through the IDE;
  - cost at real turn sizes;
  - recovery after a misroute. ADR-009's rung 2, escalation to a stronger model, is deferred to #397 and is not a
    present safeguard.

## Run integrity and spend

- **The cap:** $15. Spent: **$0.703490** reported by the Gateway, plus one **$0.001333** operator-approved provision
  that stays an unknown cost (`tune-C`, call 16). The test run cost $0.195621.
- **Every run's teardown was clean,** within its deadline.
- **Failed runs are kept as evidence, never pooled:**
  - `tune-C`: an empty reply at the 256-token cap, before N4;
  - `tune-D-mipro`: the optuna package was missing.
- **Reproducing every metric:** the manifest carries, per test item and arm, the three final tiers and the first
  repeat's raw tier, confidence, route-up flag, latency and billed cost. `evidence.json` records the identities: the
  SHA-256 of `frozen.json`, of each frozen DSPy program, of every harness file and of the pilot environment's lock,
  and the `evaluation` and `auto` hashes.
- **Hashes** (SHA-256, files on disk):
  - `runs\frozen-1\frozen.json`: `0a16c2ef0ddd44484799bf5e38d2ce6791395ec0167b3b7747b7e3ef8c81b80a`;
  - `runs\tune-D-mipro-2\program.json` (D's frozen program):
    `d9ec7a21ea1719b410d24de1909a359105c50dd99694a3c77a15988d52e9356b`;
  - `runs\test-1\predictions.jsonl`: `b0a2c6613896835a4322c2e878cc1573d3604eb8dda13eeb4a202a3c5d081273`;
  - `runs\test-1\calls.jsonl`: `c60fc8dc76cd9cbca5f728e7be73768c4696324a57a2d1f79c900098358a0849`;
  - `runs\test-1\evidence.json`: `b407516c317efecb66f4bf7c873198e5e716ee1fba1805af553cdda36cf50b75`;
  - `runs\test-1\manifest.jsonl` (300 entries; the content-free manifest):
    `076143fc9ff8c6a84b346c6ea457b5a5aa450b7f9e7c93ec49c744453a830534`.

  The original manifest, keyed by prompt digests, and `evidence.json` stay in the review kit, pinned by these
  hashes. The repository files a manifest keyed by item ID instead (manifest option (ii), approved by the operator on
  2026-10-26), from which the bundle's `tools/recompute.py` reproduces every view exactly.

## Deviations for the Plan 12.4 successor

1. **System One reply checks** (Task 1 design notes). Jev's endpoint has no router metadata, no finish status and no
   pipeline-stage record. Its adapter therefore checks the cost, the answers' types and values, and the model
   snapshot. **Carried forward as Jev's admission limitations:** the finish status, the router-attempt count and the
   pipeline stages cannot be observed on this endpoint.
2. **N3 / b1** (ADR-026, PR #422): exactly one unflagged guardrail stage is accepted on the exception routes.
   Operator-approved and merged.
3. **N4:** the classifier output reserve went from 256 to 1,024 in the `evaluation` profile (`d8d0b90e…`).
   Operator-approved. It changed the tested Haiku configuration, not the rule; it belongs to a text-producing
   classifier only.
4. **The pilot environment:** DSPy's `optuna` extra was added to the hash-locked harness environment. Six packages
   were added and no existing pin changed. It is recorded as an environment prerequisite for any re-run.
5. **Reporting changes after the test, with no effect on the decision** (Codex round 62, question 3):
   - the manifest gained each source's version and licence, and the first repeat's metric inputs;
   - `evidence.json` gained the identities;
   - the no-winner reason string now distinguishes "no arm passes" from "passing learned arms do not beat A" (only
     the SWE-chat view's text changed).

## Conditions before Auto ships (Codex round 62)

- **The `auto` composition**, before its hash is approved:
  - Jev's complete reviewed entry: prices, capabilities, reasoning setting, estimator, endpoint facts, admission
    evidence and limitations. The `evaluation` entry records a 262,144-token window, not ADR-007's historical 32K;
  - `classifier: [typesafe/jev-1.14]`;
  - a positive classifier reserve (256), which the current validator requires and Jev does not use;
  - the 8,192 estimated-token complete-request bound.

  The whole effective composition, with any operator override, is validated, then its new exact hash is approved.
  Neither existing hash covers it.
- **Production confidence handling:** the Gateway's parser checks the answers' values but not `confidence`
  (`upstream_client.py:372`). Phase B requires a finite confidence in [0, 1] and treats a missing or malformed one as
  an abstention.
- **Phase B** implements the frozen H exactly, with classifier-failure handling and the remaining production gates.

## Files (review kit, `plan12-4-auto\task3\`)

- **The harness:** `harness\`. The rule is in `metrics.py:decide`.
  - `extra_facts.py` produces the confusion and sensitivity figures (`runs\test-1\extra-facts.txt`).
  - `combo_explore.py` produces the exploratory combinations (`runs\test-1\combo-explore.txt`).
- **The records:** `tune-1-record.md` and `tune-2-3-record.md`.
- **The draft acceptance record:** `adr-007-acceptance-draft.md`.
- **The review:** `plan12-codex-cli\round-62-checkpoint-a-pilot-evidence\review.md` (#395, comment 6414706221).
