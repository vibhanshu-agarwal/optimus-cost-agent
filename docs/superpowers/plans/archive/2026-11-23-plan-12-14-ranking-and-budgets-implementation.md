# Plan 12.14: Ranking refinements and model-aware context budgets (memory M2b)

## Operator-facing summary

Finish M2b after M2a: measure optional packing, qualify one route's model-aware budget and preserve required evidence. Send required files whole when they fit; only explicit summary tasks beyond the hard ceiling may receive a disclosed outline.

Preserve M2a ambiguity, /why lifetime and observation/read partition. No mid-turn retrieval, outline cache, online learning, production reranker, semantic serving, plan caching or encryption.

~~~mermaid
flowchart LR
    A[Delivered M2a] --> P[Measured optional packing]
    R[Route bound before preparation] --> B[One budget]
    P --> E[Whole evidence or disclosed overflow]
    B --> E
    E --> W[Context and /why]
    W --> Q[Released product-matched evaluation]
~~~

Mechanisms/values below are agent recommendations.

| Open decision | Recommendation |
|---|---|
| D1 — Filing | New kind:plan issue under #235, handler:claude; #243 child and issue-only registry pointer. |
| D2 — Ranking | Baseline versus two pack-only alternatives; preserve fusion/quota. R is a data point; production reranker stays Gated. |
| D3 — Budget | Entry/hash named via Role.EASY, USD 0.008192 estimator-input target; applies whenever bound implementer. Others omit/legacy; #243 unestablished. |
| D4 — Outline | Only R>C and fresh explicit summary form; otherwise whole file. Retain Agent ranged reads. |
| D5 — Shipping | Stage D3's defaults.yaml entry for Q; ship that identical composition after qualification and fresh hash approvals. |
| D6 — Paid Q | 48 intended (36 if U=B) / maximum 96 physical attempts, USD 6.00, including cache observations; separate release. |
| D7 — Paid R | Four intended / maximum 12 physical attempts, USD 0.50; separate release. |

Hash approval releases no paid run. Total maximum USD 6.50; allowances never transfer.

Propose priority:high, handler:claude, difficulty:high, estimate:13d; agree/authorize labels. Difficulty: interacting route/evidence/identity/accounting boundaries. Estimate: 11–13 working days, rounded to 13d, excluding waits; re-estimate at checkpoints.

## Goal and authority

**Version:** complete v3 replacing unapproved v2; File unchanged as directed.

**File:** docs/superpowers/plans/2026-11-23-plan-12-14-ranking-and-budgets-implementation.md

**Goal:** qualify #243 on D3's route/target: “Budget changes are model-aware, cost-attributed, injection-safe, measured against the null baseline, and never silently omit required evidence.”

Claude (Opus) implements/owns chat; Codex authors/reviews read-only. Fable 5.2 reviews this complex plan before Claude. Exact SHA-256/decisions approval precedes Task 1; approved bytes use a docs-only PR to main, merged when green under the 2026-11-23 filing authority.

Each container, Zed session, keyring write outside isolated tests and paid run needs its own release. Other GitHub writes except review posts, and implementation push/PR/merge, need operator OK. No hook bypass.

**Source inspected at main 8e56b3c plus Plan 12.13's filing.** Clean supplied branch agent/claude/p1213-plan, git:387be2f.

Read Plan 12.13 v3 (#545) first, hex:26653bbc2123e66d990d37977f9ab81a6ded9121de7594e358b0c9fdad31ffa0. Its governing inputs apply: discovery v12 M2/evaluation/O24/Q13/Q26/Gated; specifications/decision index, ADR-003/005/025/031–035/038–041/044, #243/#463 and Plan 12.11 paid discipline.

Discovery: C:\worktrees\optimus-cost-agent-worktrees\optimus-handoff\plan-12-discovery\2026-10-22-claude-memory-feature-scope-suggestions_v12.md, hex:33670c6b84aceccd629437c14f03609ba4293d70cde95b242dd93a2b0ad4fb14; provenance only.

**Predecessor:** authoring/review/approved filing/Task 0 read-only checks may precede M2a closure. Implementation/calibration/paid work waits for M2a closure/merge. Verify delivered snapshot/privacy, ambiguity, partition/serializers, qualification/Zed and merged-source/cache identities/holds. This tree contains its plan only. M2 precedes remaining M3 security; preserve M2a's separate 16 KiB observation/read ceiling.

## Scope and Explicit Exceptions

Everything not expressly excluded remains in scope, including ranking/budget/outline qualification, paid answer/citation/null/cache observations, real boundaries/UI and delivery evidence.

| Explicit Exception | Owner/custody |
|---|---|
| Initial /why, ambiguity, fixed partition | Claude / #545, #242/#245; Plan 12.13 |
| #243 outside D3's entry/hash/target | Claude / #243 under #235; Role.EASY only names entry. Others omit field/retain legacy; claims unestablished and #243 open pending evidence/releases. |
| Actual second-model continuity | Claude / #491; controlled bindings do not qualify it |
| Production learned/model reranker, further campaign/training | #235 Gated reranker; R is development evidence only; no E |
| Outcome learning | #235 / M6 |
| Q21 subagent, semantic serving, plan caching | #235 deferred/Gated |
| Broad vendor/native campaigns, population claims, B2/B3 integration | #463; this plan owns narrow producer contract/results |
| Encryption/handoff/rotation/encrypted restore | Claude / #491 security remainder |
| Other slices/defects | Existing owning issues; new independent work needs approved custody |

Refused releases leave claims UNRUN; incomplete closure needs explicit operator disposition/named custody.

## Design choices

### Ranking

Preserve RRF_K=60, WEIGHTS, depth 100, quota/stable ties and M2a ambiguity authority. Utility changes optional packing only: ranked output/recall-at-five remain equal. Required files are untouched; no invented dependency closure/refusal.

Use lexical_terms(task), including stop-word fallback; task_terms is its count. Marginal coverage counts new task terms in current admitted/hash-verified candidate material within each disclosure phase. Compare exactly:

1. M1 greedy fill in fused order.
2. Density: RRF score * (1 + marginal_terms/max(1, task_terms)) / max(1, candidate_tokens).
3. Coverage: the same numerator without division, followed by greedy fit.

Cost is the candidate's own serialized signature/excerpt/framing. Preserve 25% optional signatures, remainder bodies. Each phase considers fitting quota-protected candidates in existing order, then policy-ranked remainder; recompute marginal coverage after selection. Tie by fused ordinal/path/range/ID. Preserve named/structural quota suppression. No cross-project learning/trust promotion; served/cited/supported differ.

M1 already measured channel/depth/stop-word ablations, RRF confirmations and fusion forms. Keep quota adoption and rejected k=10/dense=2. Replay consumed held-outs separately, including earlier failures and fresh2's historical results.

Freeze three real-index development repetitions using paired captured channel inputs; select baseline/one candidate before fresh qualification. Fresh set: >=40 family-separated requirements, distinct from 12 paid cases. Development and fresh sets each include a different short term-stuffed poisoned document with relevant positive control.

Utility ships only with evidence-in-context >=baseline in every repetition/historical/fresh set, strict development/fresh improvement, irrelevant estimated tokens <=baseline and <=16,000, zero stale/denied/wrong-scope evidence and at-five equality. Incomplete repetitions are inconclusive; no replacement/tuning against qualification.

### One preparation-time budget

Compute once for bind_attachment()'s route before preparation. Auto escalation retains pack, admission/digest/history/parameters; no re-retrieval or new refusal. Existing estimator/capacity/history-limit swap and fit()/Gateway checks guard the actual target. /why separates preparation/dispatch readings and says “budget computed for the pre-escalation route”; this does not qualify that target.

Retain 262,144 total ceiling/reserve once. Host usable input=min(configured endpoint windows,policy ceiling)-reserve; Gateway requires verified endpoints. Positive-decimal ModelEntry.context_budget.input_target_usd is omitted canonically when absent, preserving hashes/legacy min(floor(0.25*usable_input),16,384). Configure D3's entry only; applies across implementer roles, never summarizers.

~~~text
C = min(floor(0.25 * usable_input), 32768)
T = floor(1,000,000 * input_target_usd / effective_input_price)
~~~

effective_input_price: price × optimus_model_policy.registry.CACHE_WRITE_INPUT_MULTIPLIER=1.25 for possible writes, else price. Host/Gateway import it; test_prompt_cache.py checks agreement. No read discount; zero price T=C; estimator tokens, not spend.

Give assemble_pack budget_tokens=C; proposed optional target_tokens/overview_path default to legacy. Serialize required text once inside it, measure R. R<=C means whole text, V=R. Otherwise only an eligible outline may set V to its serialized cost; failure preserves TOO_LARGE/unreadable handling and Agent ranged reads.

~~~text
chosen_budget = min(C, max(V + min(1024, C-V), T))
optional_room = chosen_budget - V
~~~

Required evidence wins over the soft target; floor uses available room only. No circular headroom term. Existing history fit/Gateway guard, protected history, stored-plan binding and engine-absent behavior remain.

Forecast T=13,107 with write treatment/16,384 without; C=32,768. Verify. CP1 records R/T/C/allocation and pack bytes/digest per budget case. All four paid budget cases must change substantive F/U pack bytes: >=two ordinary-fit allocation changes and two R values in (16,384,C]. Predeclare forced refusals; exclude their superiority/cost wins. On gate failure remove field/restore prior pins, prove pre-change effective-hash equality, and record candidate-hash approvals unused. No target tuning after qualification.

### Overflow outline

Permit only for R>C and fresh direct task `Summarize "<exact workspace-relative path>"`, uniquely resolved. If the required set fits C, include the whole file even for that request. Parse only direct task input; nested quoted/pasted text, history, model/tool content or additional edit/exact-evidence intent cannot enable it. Permission expires with the turn. Do not implicitly summarize other required files.

Generate from freshly admitted/read/hashed bytes using existing signatures/structure or document headings/excerpts, <=2,048 estimated tokens within C. Unsupported extraction retains TOO_LARGE. No generative summary, cache or persistent outline text; recompute each turn, including after edits and for current unsaved buffers.

Place disclosure entirely inside the dynamic pack, after the breakpoint: “Outline only; full file not included. Read exact ranges before relying on omitted details.” Include source hash/length, included ranges and omissions. Retain Agent ranged reads. An outline never satisfies an exact quotation, edit, approval, diff/error/test-evidence or correctness requirement; require fresh exact evidence for those tasks.

Extend body-free /why metadata with outline disclosure, generator version, source/representation hashes, omission information and reread requirement. New manifests use optimus.context-manifest.v2 with config.budget_policy_version=m2b-v1 and explicit legacy/model-aware policy. Read v1 as legacy/unknown without rewriting it.

### Identity and accounting

For identical map/tools/evidence limits, indexed_chat_prefix() and indexed_planner_prefix() remain byte-identical to delivered M2a; test prefix digest and cache_prefix_chars. Put outline/budget disclosure only in the pack; no static grammar/version change.

Stage defaults.yaml for Q; ship unchanged on acceptance. Re-pin SHIPPED_DEFAULTS_HASH, attached/qualification/evaluation/Auto/consumers; renew ordinary/Auto hash approvals. Q uses the shipping ordinary hash, never overrides/test profiles; later changes need equivalence or fresh released evidence. Field omission preserves canonical hashes; dynamic pack/request digests may change after the unchanged breakpoint. Re-pin current executable/import identities as required; historical custody fixtures stay unchanged.

Reuse Gateway capture/settlement; no new ledger. Attribute all attempts/overhead/resends/failures/late/unknown receipts by existing IDs; retain usage/cache/billing/route/price fields. Apply ADR-012/034/035: distinguish actual charges from uncached repricing, count overhead once, retain unknowns/negative savings and the missing durable cache-write-count qualification.

## Prerequisites

Task 0 resolves unknowns first; capability renews no release.

| Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| M1 pack/escalation/accounting | yes | Claude | Existing inspected paths. |
| Delivered M2a closed/merged/evidenced | no | Claude/operator #545 | genuinely absent — finish predecessor. |
| Exact v2 hash/decisions/issue-label writes | no | Operator/Claude | merely unauthorized — approval pending. |
| Latest-main checkout/overlap/frozen environment | unknown | Claude | merely unauthorized — establish authority/identities. |
| Specs/decisions/M2a interface reconciliation | unknown | Claude/Codex | genuinely absent — produce verified manifest. |
| Development/fresh >=40 requirements/12 paid cases | no | Claude/Codex | genuinely absent — author/seal first. |
| Dedicated index/artifact/live services | unknown | Operator/Claude | merely unauthorized — inspect/release resources. |
| Easy-route prices/hashes/attempt topology | unknown | Operator/Claude | merely unauthorized — verify/approve configuration. |
| Windows/WSL Ubuntu-24.04/Zed/acpx capability | yes | Operator/Claude | Plan 12.12 used them 2026-11-21, acpx 0.12.0; refresh versions. |
| Isolated zero-paid first-prompt procedure | yes | Operator/Claude | Established; release fresh port/session. |
| Container/Zed/keyring/Q/R operations | no | Operator | merely unauthorized — release individually. |
| Support-review/adjudication availability | unknown | Reviewers/operator | merely unauthorized — arrange CP3/adjudication. |

Capability evidence: reports/plan12-memory-m3-part2/platforms.json and zed-ui.json; resources cleaned up. No genuinely hard blocker assumed.

## Files and inventories

Read before editing. New paths are proposed:

- Packing: src/context_engine/context_pack.py; new pack_utility.py and file_outline.py beside it; reuse retrieval.py/code_index.py.
- Budget/config: new src/optimus/context/context_budget.py; src/optimus_model_policy/registry.py, validation.py, defaults.yaml, experimental.py, test_profiles.py and affected pins.
- Integration: src/optimus/context/memory_session.py, assembly.py; src/optimus/agent/runner.py; M2a context_why.py/readers; prompts.py prefix tests.
- Evaluation: new tools/plan12_memory/m2b_evaluate.py and focused tests named below; existing scoring/contracts/Gateway receipts.
- Live/docs: tests/integration/context/test_memory_session.py/conftest.py, reports/plan12-memory-m2b/, user docs, new ADR/index and issue-only plan pointer.

Join every inventory in Plan 12.13 §Files and inventories, plus registry/prompt/source pins. Record changes/non-applicability; no new route/op/marker/walker/launcher/command planned. New ADR preserves operator provenance/agent choices; frozen records stay unchanged.

## Tasks

TDD: discriminating failure -> minimum implementation -> focused pass -> class sweep/revert. Checkboxes require passed verification; no per-task reviews.

### Task 0 — Authority/contracts

- [ ] Record approval/decisions, worktree choice, releases, labels and issue custody; verify HEAD/status/registry/overlap/drift/environment. Branch from latest main.
- [ ] Verify predecessor bytes/evidence and all prerequisite unknowns/spec conflicts. Maintain gitignored docs/superpowers/reviews/plan-12-14-review-checkpoints.md; Claude owns it, never stages it.
- [ ] Freeze cases/provenance/cutoffs/seals, selector/rubric, forced-refusal/comparable cohorts and expected attempts; obtain operator sampling approval. Agree #463's narrow producer contract and custody, without adding a savings reader.

Verify: git status --porcelain=v1 --untracked-files=all; git rev-parse HEAD; git worktree list --porcelain; Get-FileHash -Algorithm SHA256; focused docs checks after filing.

### Task 1 — Calibration/evaluator

- [ ] Test attribution, refusal/UNKNOWN, selector and receipt controls; run three development repetitions and freeze baseline/one utility candidate before qualification.
- [ ] Record R/T/C/allocation, four substantive budget-case differences, full-input fit and prefix identity; otherwise stop CP1. Test controlled window/price/estimator/cache variants, zero price, equality/one-over, required-over-target and field omission.
- [ ] Freeze arm order, tariff, script/selector digests, caps, intended composition and production-equivalence test; verify reservations/resends/no unintended calls. Task 2 must prove integrated byte equality before Q.

~~~bash
uv run --no-sync pytest --no-cov tests/unit/tools/test_plan12_memory_m2b.py tests/unit/context_engine/test_pack_utility.py tests/unit/context/test_context_budget.py -q
uv run --no-sync python -m tools.plan12_memory.m2b_evaluate --config reports/plan12-memory-m2b/run-config.json --phase calibration --output reports/plan12-memory-m2b/calibration.json
~~~

CP1 freezes new interfaces/configuration/commands.

### Task 2 — Packing/budget

- [ ] Implement qualified packing/field; test phase/quota/ties, own-size/stuffing, untouched required evidence and fused order. Test registry validation/omission/pins and one required serialization.
- [ ] Test pre-preparation binding, escalation retaining pack/digest without retrieval/new refusal, target fit and protected history/plan binding. Add versioned metadata/readers; preserve cancellation, buffers/index fallback and no-config behavior.
- [ ] Prove every F prompt equals actual production builders/bindings at the tested head.

~~~bash
uv run --no-sync pytest --no-cov tests/unit/context_engine tests/unit/context/test_context_budget.py tests/unit/context/test_memory_tools_and_turns.py tests/unit/agent/test_context_plan_binding.py tests/unit/acp/test_auto_escalation.py tests/unit/acp/test_auto_escalation_end_to_end.py tests/unit/model_policy -q
~~~

### Task 3 — Outline/explanation

- [ ] Implement overflow-only direct-task outline; test fits-whole-first, ambiguity/spoofing/exact-edit exclusions, disclosed omissions, ranged/exact follow-up, edit/rename/delete/policy/buffer freshness and cancellation. No cached/persisted body.
- [ ] Test /why versions/privacy/lifetime/lineage/zero calls and unchanged M2a prefixes.

~~~bash
uv run --no-sync pytest --no-cov tests/unit/context_engine/test_file_outline.py tests/unit/context/test_context_why.py tests/unit/acp/test_memory_wiring.py tests/unit/agent/test_workspace_context.py tests/unit/agent/test_prompts.py tests/unit/optimus_gateway/test_prompt_cache.py -q
~~~

### Task 4 — Qualification/boundaries

- [ ] Open fresh qualification once; replay historical sets separately. Pass deterministic gates before separately released Q/R.
- [ ] Exercise real dedicated index Redis, Gateway/filesystem/artifact; any served-memory claim needs its separately released real store. Fakes establish unit behavior only.
- [ ] Independent real acpx verifies /why/outline-to-exact-reread. See disclosure, allocation/overflow, follow-up, no-snapshot/restart live in Zed with correlated screenshots/ACP/debug evidence.
- [ ] Each zero-paid Zed session needs its own released Gateway port/config; first-prompt gate verifies attach/local upstream/no paid egress, including classifier/maintenance/extraction/fallback.
- [ ] Windows/WSL check separators/spaces/non-ASCII/escaping, denial and outline freshness after edits. Reproduce new platform-shaped failures on the alternate OS.
- [ ] Revert utility, whole/outline eligibility, reserve/target, escalation retention, hash/scope, prefix/registry and attempt/claim checks in disposable checkouts. Oracles must fail; restore bytes.

~~~bash
uv run --no-sync pytest --no-cov -m requires_plan12_index_redis tests/integration/context/test_memory_session.py -q
uv run --no-sync python -m tools.plan12_memory.m2b_evaluate --config reports/plan12-memory-m2b/run-config.json --phase qualification --output reports/plan12-memory-m2b/qualification.json
~~~

Freeze live nodes/guards/client/platform commands; collection/skips/passive runs prove no live acceptance.

### Task 5 — Final gates/delivery

- [ ] Sweep affected context/agent/ACP/escalation, registry/cache/capacity, accounting/sanitizer classes and every applicable M2a inventory suite; freeze exact expanded commands before running. Run applicable hooks/Ruff.
- [ ] Audit all current-state claims, including untouched README/roadmap/registry/issues/user docs/index/reports; repeat before merge.
- [ ] Freeze clean final code head; exactly one planned Windows full suite with coverage from PowerShell. Preserve failure; later executable fixes invalidate acceptance and need disposition before another broad run.
- [ ] Complete CP4/operator disposition, obtain implementation push/PR/merge authority, resolve main drift intentionally, inspect actual-tested-SHA Linux PR CI and retain evidence before authorized cleanup.

~~~bash
uv run --no-sync pytest --no-cov tests/unit/docs -q
uv run --no-sync python -m ruff check .
~~~

~~~powershell
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
~~~

Require configured floors, >=80% aggregate production coverage, no safety-critical regression. CP1–CP3 use focused coverage-free checks; retain actual broad-run counts.

## Evaluation and releases

### Product-matched Q

Twelve cases: four ranking, four budget, four outline/required-file. Fresh zero-tool Chat turns, no memory/history; matched source/route/reasoning/output/stopping rule.

- N: actual engine-absent assemble_workspace_context_for_prompt(root, task=task), unchanged default 16 KiB bytes/order/truncation/diagnostics, existing non-indexed Chat builder, no map.
- B: delivered M2a packing/fusion/legacy budget, indexed map.
- U: selected utility, B budget/builder/map; U=B if baseline retained. Identical per-case prompts share one recorded attempt/receipts and arm aliases: Q intends 36.
- F: U plus qualified budget/overflow outline, actual production builder/fit/binding.

evaluation-contract.json pins blobs/task bytes/parameters/builders/lengths/digests. Verify N against fallback, F byte-for-byte against production; B/U are evaluator controls.

Complete input/output caps: 65,536/2,048 estimated tokens. CP1 proves budget cases fit C+map+framing; failed preflight stops before paid prompts. No post-result cap increase. evaluation-contract.json maps each category's four cases once to N/B/U/F, B/U/F/N, U/F/N/B, F/N/B/U; record cache warmth/order/timing.

Freeze scoring-script AND claim-selector digests before prompts. Deterministic fixture/fact/citation path-range-hash/prohibited-claim checks decide pass/fail; all applicable checks must pass, UNKNOWN is incomplete. CP3 reviewers audit unsupported claims, not blind-grade answers; unresolved material support holds acceptance for operator disposition. No paid grader/repair.

### Adoption and cost gates

- Utility passes its >=40-requirement gate; at-five unchanged.
- Budgets: zero silent required omissions; required coverage >=U on deterministic budget/qualification sets; ordinary-fit cohort uncached-repriced input cost <=U with one strict saving; all four budget cases change substantive pack bytes.
- Paid F loses no B/U-success case, has success count >=N, and has zero safety/unsupported-material-claim failures.
- Report fully loaded uncached-repriced cost per success for all arms beside actual charges/denominators/coverage. Comparable-cohort F must cost <=B and <=U. Zero-success ratios are unavailable; missing comparable evidence holds cost acceptance.

Predeclare baseline-forced refusals: report their overflow successes separately, excluding superiority/comparable-cost wins. One stochastic sample establishes no population superiority.

Freeze one dated uncached D3 tariff. Reprice reported tokens consistently, cached input at ordinary input price and reasoning nested; include overhead/resends once. Label estimates under ADR-034; unknown categories stay unpriced, actual charges separate.

Q supplies new cache observations: reported cache usage/charges, prefix/request digests and order. Report cold/warm observations without attributing order discounts to policy. Zero-paid tests prove budget-only prefix identity; ADR-039 already proved changed-question reuse. No separate C/changed-map request or production-hit-rate/causal-cache-savings claim.

### Releases

| Release | Measures | Intended/max physical attempts | USD | Stop / refused release |
|---|---|---:|---:|---|
| Q | 12 x four synthesis/citation arms, null/repriced cost/cache observations | 48 (36 if U=B)/96 | 6.00 | Stop on unreservable request, safety, unknown cost/attempt coverage, drift or attribution failure; no replacement. Refused: paid/null/cache evidence UNRUN, qualified #243 acceptance held. |
| R | One configured top-12 reranker, four development cases: placement/schema/latency/overhead | 4/12 | 0.50 | First invalid permutation/safety/accounting failure or reservation limit stops calls; no tuning/repair. Refused: UNRUN, #235 Gated custody. |

R caps: 16,384 input/512 output estimated tokens. Candidates must be current/admitted/inert; output must permute supplied IDs exactly. No added evidence/ambiguity authority. Compare identical deterministic placement, retain all results/costs; production stays Gated. No E/activation cost-per-success gate.

Release each run's source/effective hash/configuration/prices/caps/expected attempts; models live in configuration/evidence. Reserve all Gateway physical attempts, including safe resends/write premiums, before each logical request. Q's 96 is a run ceiling; retries may prevent completing intended requests. No host retry/fallback/classifier/extraction/maintenance/repair/replacement. Unbounded topology/USD: no launch.

Follow reports/plan12-memory-m3/paid-attempts.json: freeze initial state/mode, multiplicity, attribution windows, script/selector/rubric and actual serving against independent expected attempts. Retain late/discarded/failed/unknown receipts and breaches; no allowance transfer.

## Checkpoints

Four coarse checkpoints only; Fable 5.2 first, then consolidated Codex CLI read-only. No per-task reviews.

| Checkpoint | Package |
|---|---|
| CP1 — Contracts | Tasks 0–1: predecessor/seals, candidate, exercised budgets, evaluator/hash/release contracts |
| CP2 — Integration | Tasks 2–3: packing/escalation/outline/why, production bytes and focused checks |
| CP3 — Qualification | Task 4: fresh/replayed sets, Q/R/support audit, real dependencies/clients/Zed/platforms/reversions |
| CP4 — Acceptance | Task 5: final head/freshness/Ruff, one planned Windows coverage run, delivery |

~~~bash
codex exec -m gpt-6.1-sol -c 'model_reasoning_effort="high"' -s read-only
~~~

Specify model/effort every call/resume; no substitution on failure. Claude posts verbatim attributed reviews/maintains log. Only operator approves. Disclose tested heads/fix deltas; assess affected evidence and obtain releases before rerunning changed bytes.

## Definition of Done

Records under reports/plan12-memory-m2b/ reference retained sanitized artifacts by digest.

| Claim | Evidence |
|---|---|
| Authority/predecessor/prerequisites/route custody/source | manifest.json |
| Cases/seals/provenance/selector/tariff/releases | cases.json, evaluation-contract.json |
| Calibration/replays/fresh >=40 requirements/budget gates/dispositions | qualification.json |
| Whole/outline/reread/why/escalation/prefix/registry | policy-checks.json |
| Q/R attempts/receipts/scores/actual-repriced cost/cache | paid-attempts.json |
| Real dependencies/acpx/Zed/Windows-WSL | boundaries.json |
| Reversions/inventories/final source/Ruff/coverage/Linux CI | final-gates.json |
| Freshness/terminal state/remaining owners | closure.json |

Missing evidence holds its claim. D3's #243 tranche needs all five acceptance elements; other routes remain unestablished, #243 open.

## Evidence discipline

Follow AGENTS, Plan 11.28's design/current holds and evidence policy: attributable source/command/platform, unchanged measured trees, one coverage writer, separate OS environments, valid active records and retained failures/skips/UNKNOWN/UNRUN. Archive before cleanup; private provenance is no dependency.

JSON: `hex:<digest>`, `git:<sha>`, ensure_ascii=True. Separate actual/repriced/incomplete results; COMPLETE is not acceptance.

## Closure

After CP4/operator acceptance/authorized delivery:

- [ ] Record terminal disposition; archive frozen bytes, repair mutable links/update docs/README.md.
- [ ] Close Plan 12.14 issue/remove status: label.
- [ ] Disposition D3 evidence; keep #243 open for other routes/targets with owner/next gate. Failed/refused obligations require approved successor/disposition.
- [ ] M2 stays open for that remainder. #235 keeps route qualification/deferred/Gated/later slices; #463 broader campaigns/report integration; #491 security/continuity.
- [ ] Preserve R measured/UNRUN custody; re-audit freshness before merge and distinguish PR/merge/CI identities.

Not commissioned: outline cache, mid-turn reassembly, E/C, production reranking or broad benchmarks; implementation/live/paid results remain UNRUN.
Risk: one-route/target qualification and small answer samples; outlines cannot establish omitted details.