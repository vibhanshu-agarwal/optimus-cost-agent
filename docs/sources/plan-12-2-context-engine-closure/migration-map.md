# Plan 12.2 requirement and implementation migration map

Reviewed local filing candidate, 2026-10-04; observed clean implementation cf9bb9d73ac6c8c3be508966245e0db7cdaaa503. Codex has made no implementation-repository edits. Historical dea4624 observations remain in earlier sealed editions; current disposition is below.

## 1. Governing-document succession

| Authoritative predecessor | Complete draft successor | Affected predecessor pages | New normative section |
|---|---|---|---|
| Architecture v2.18, 13 pages | Architecture v2.19, 15 pages | 2,3,4,6,7,8,9,10,11,12,13; new cover | §14 |
| LLD v2.41, 40 pages | LLD v2.42, 44 pages | 2,3,4,10,11,12,14,15,16,17,18,19,20,21,30,33,36,38,39; new cover | §13 |
| Guardrails v1.3, 16 pages | Guardrails v1.4, 18 pages | 2,4,6,7,10,11,12,14,15,16; new cover | §14 |
| Test Strategy v1.7, 14 pages | Test Strategy v1.8, 18 pages | 2,3,4,6,7,8,9,13,14; new cover | §15 and replaced §8A |

`sources/build-manifest.json` maps every original page to physical successor ranges and hashes. `sources/replacement-audit.json` preserves historical v1 edit provenance; v2 structural/source changes and disposition are recorded separately; `sources/page-updates.json` contains full replaced bodies, including full rewrites of affected diagrams and raster-code pages. Unaffected diagrams/code bodies are carried forward, not reconstructed from failed raster text extraction. Baseline PDFs are included unchanged for review/rebuild. All original page positions are represented once. Draft versions must be rechecked against then-current predecessors before filing.

Key in-place retirements: Haiku triage/HAIKU-PRO routing and 100k/150k/250k context caps; product BudgetExhausted/remaining-money decisions; budget-bearing Gateway/system diagrams and stop tests. Retain independent security, trust, capacity, approval, finite-work and evaluation limits. Historical independently capped evaluation cost examples remain labelled as such. The diagram replacements preserve boundary actors/edges and make the fixed-model path explicit; future Auto/review behavior is not claimed as delivered.

## 2. Requirement-to-target and observed-state trace

| Requirement / decision | Draft target | Observed baseline and remaining obligation |
|---|---|---|
| ADR-001/002 authority and operating modes | HLD §7,14.1/14.3; LLD §4A,13.1/13.3/13.8; Guardrails §2,14.1 | Existing exact approval and effect projections retained. Recheck Task 2 proof on actual attached test/production base; no model-created authority. |
| ADR-003 history/output sizing completion | HLD §14.2/14.4; LLD §13.1–13.4; numeric ADR draft | Numeric values adopted under the reported offline release and verified by Task 12. D7 verbatim transcript filing remains pending. Production activation and shipped Haiku-default removal remain held. Percentage ceiling is not delayed-trigger behavior. |
| ADR-004 registry roles and shared policy | HLD §6,14.4; LLD §13.4; contract §4 | Neutral snapshot and strict YAML exist offline. Packaged production enforcement remains inactive; production activation and shipped Haiku-default removal remain held. Luna estimator evidence is incomplete and Qwen remains unqualified. Auto/classifier/reviewer requirements retain their existing future owners; no full ADR-004 completion claim. |
| ADR-005 accounting/D6 | HLD §14.5; LLD §13.5–13.6; Guardrails §14.4; policy ADR draft | Exactly-once foundation exists; product dollar stops removed on cf9bb9d, with independent evaluation caps and actual/unknown accounting retained. Missing cost remains unknown, no retry/latch; alerts configured explicitly. |
| ADR-006 optional engine/strategies | HLD §14.1–14.3; LLD §13.1–13.3/13.7 | Engine/host seams exist; no production `ContextAttachment` constructor. Proposed ephemeral test composition proves only named configuration. |
| ADR-007/008/009/012 deferred mechanisms | HLD §14.4–14.6; LLD §13.6/13.8; retained exceptions | Auto/classifier, review, savings and future check-in/resume work are not implemented or accepted by this package. Preserve sole-backlog custody. |
| ADR-010/011 and security boundaries | Carried source/security sections; Guardrails §3–6,14.1/14.5 | Preserve existing redaction, controlled tools, Gateway-only inference, independent tool origins and provider keys outside CORE. No security relaxation. |
| ADR-013 effect producer repair | LLD §13.8; Test §15.2/15.5 | Historical Package A proof retained; actual base/cancellation evidence remains activation prerequisite, not fake synthetic promotion. |
| ADR-014 all-session floor/request guard | HLD §14.4; LLD §13.4; Test §15.3 | Full-floor fit is mathematically incompatible with the universal byte fallback; proposed named D7 exception retains storage floor and capacity guard. Route-specific conservative proof remains missing. |
| ADR-015 sequencing and interim work bounds | HLD §14.5; LLD §13.6; Guardrails §7/14.4 | Default 3 rounds/30 minutes/repeated failures 2 remain; Chat one call; optional capped evaluation remains. Task 11 removes product money checks on the reviewed branch; no new loop mechanism is introduced. |
| ADR-016/017 historical dispositions | Predecessor records retained; new records only | No new waiver or rewrite. ADR-017 does not grant general coverage skipping. Recheck decision index before allocating new IDs. |
| C1 exact refusal/fallback/recovery text | Contract/spec complete successors preserve exact existing messages; LLD §13.2–13.3 | Accepted offline at dea4624. No code redo. Unavailable/version mismatch mean no summarizer invocation; actual failed work may charge. |
| C2 dual token/byte whole-turn packing | Contract/spec; LLD §13.1–13.2; Test §15.2 | Accepted offline. Required summary byte field, subadditive estimator precondition and complete-input backstop retained; no engine estimator redesign. |
| C3 ceiling/cost wording and edition provenance | In-place PDF clauses, full plan/spec/contract successors | Technical correction accepted. Three historical-edition references still need exact closure wording; sealed notes remain unchanged. |
| Per-package 80% floors | Test §8A/15.1, plan Task 12/13; section 4 below | Earlier run meets context/policy floors. CI and final CP4 gates enforce the new reports at cf9bb9d; the interim hook remains Optimus-only; aggregate cannot replace either floor. |
| Cancellation diagnostic residual | LLD §13.2; closure record in existing Plan 12 status/evidence | Engine can internally label a cancelled summary as failed while ACP shows cancelled. Nonblocking known limitation; no new code commissioned. |
| Oversized-turn availability | HLD §14.2; Guardrails §14.2; closure proposal §1 | Even a large reply can create an indivisible turn. Recovery is conditional; neither 18-call limit nor 128 KiB prompt reservation eliminates this limitation. |

## 3. Verified product-policy implementation

Task 11 is implemented and tested at cf9bb9d. Product max_cost_usd/max_budget_usd defaults are None; non-ACP is not implicitly evaluation and the old $0.01 fallback is gone. Remaining-dollar planner inputs, positive-dollar requirements, BudgetExhaustedError/retry kind and product termination branches are removed. Prompt/logging pins and manifest are coordinated. Product telemetry omits stop-bearing keys without a cap; actual cost receipts and incomplete accounting remain. An explicit independently capped evaluation still stops. The three former strict xfails pass and their markers are removed. Agent defaults retain 3 rounds/30 minutes/repeated failures 2; the goal loop retains its existing separate iteration bound. Do not broaden ACP loop activation.

## 4. Implemented shared coverage policy

The complete gate definition is Test Strategy section 8A. At cf9bb9d tools/check_product_coverage.py inventories tracked source files from Git, validates exactly one product group per package including namespace roots, measures unloaded files and reports one full-suite dataset. Optimus group members are optimus/optimus_gateway/optimus_security/optimus_model_policy; context_engine and optimus_model_policy have independent 80% checks. Evidence Handoff is informational at its 80% threshold; aggregate is informational.

Comparison retains coverage.py/pytest-cov precision 0 rounding: 79.5% compares as 80% and passes. Both measured and compared values are shown. Windows measured required values: 89.4393/95.9243/96.9880%; WSL: 88.9078/95.9243/96.9880%. All exceed the floor before rounding. Evidence Handoff: 68.4165/65.9629%, BELOW informational.

Run mode launches exactly one sys.executable -m pytest with --cov --cov-branch --cov-fail-under=0 --cov-report=term-missing -q. Report mode requires --data-file and --run-record; it checks the dataset hash, reads the same coverage sources and never reruns. Its sidecar records HEAD/dirty flag/command/times/true exit/hash, not a dirty-tree/configuration digest or authenticated selection. Only reuse with corresponding reviewed full-run log/run context and unchanged source/configuration. Current sealed final datasets were independently checked against clean cf9bb9d. Required failures and nonzero pytest exit fail; informational below-floor rows do not create a wrapper failure. There are no per-row subprocess exits: reporting uses coverage’s API.

Until the profiles lane lands, the hook entry is unchanged and keeps pyproject fail_under=80 (an Optimus-only interim floor). Only CI switches to --run-full-suite. The profiles lane later moves the hook to commit with no coverage gate. The final CP4 gate also uses run mode. Preserve optimus-pytest-coverage and existing ADR-016 skip custody; no new waiver. CI JSON upload is not implemented; rows remain in its log.

## 5. Historical documentation corrections and filing

Roadmap's PR #214 entry must identify the historical filed edition and PR separately from the new local editions awaiting publication. The backlog's 2026-10-02 acceptance must link the archived first Task 1 contract and complete v2 implementation plan. Plan v3's acceptance sentences must attribute the 2026-10-02 acceptance to those historical editions; acceptance does not propagate to v3/v4 by a current link. The complete v4 draft restores this history while keeping all original tasks.

New complete draft repository paths are under `repository-drafts/docs/`: design `_v3`, contracts `_v3`, implementation `_v4`; unallocated ADR-next numeric/exception completion and ADR-next-plus-one Task 1/D6 mechanism record. Recheck main and concurrent tier drafts before allocating real IDs; ADR-018 is not reserved by this package. No published ADR is edited or claimed wholly superseded when deferred requirements remain.

After reviewed acceptance/direct filing release, Claude archives the predecessors byte-for-byte, places accepted latest PDFs/spec/plan in their normal governed locations, updates current indexes/roadmap/authoritative tracking venue according to actual Plan 11.29 cutover and records exact scope/remaining holds. Do not copy private raw handoff evidence into runtime/build dependencies. Baseline PDF copies and builder here are reviewer-local provenance/rebuild inputs; accepted repository build inputs must be filed in the repository's approved document-source location, not read from this chat's absolute path. Review packet sources are not executable product configuration.

## 6. Required closing evidence and custody

Use the existing CP4 checkpoint rather than starting another per-task loop. Final product changes receive applicable focused checks/hooks, exact-candidate full default suite/coverage where required, Fable and one consolidated Codex review. The existing full WSL run before finalization remains unchanged, with environment intake and exact selection/candidate/exit recorded. Quote actual pass/skip/deselect/xfail/UNRUN counts and exits, retaining failed seals. C1/C2's earlier acceptance and existing full-suite/focused-delta results are historical evidence, not a release of new work. Do not add Evidence Handoff tests for informational coverage or import another lane's cadence proposal as already implemented Plan 12 behavior.

Public metadata/tokenizer evidence, qualified summary receipt, trusted test composition, actual acpx/Zed/Redis/Gateway claims and capacity/finish proofs remain separately named. A stub, seeded session or synthetic ratio establishes only its stated claim. Publish no production activation or broad Plan 12 completion claim while an accepted required item remains held. Existing deferred owners and the authoritative tracking venue according to actual Plan 11.29 cutover retain future optimization, Auto/review/savings, sanitizer and persistence work.


## 7. Offline closure disposition

Main a929aab was integrated locally via 739b3dc. Final candidate cf9bb9d is clean. Windows and WSL final gates pass with zero failures, on that exact clean candidate; failed final-gate-1, wrong-path no-ops and the stopped tools run remain non-passing. Limits/wheel proofs are at cc6959b and carried only for unchanged src/pyproject/lock inputs. No new full-suite rerun follows from this document correction.

V3 uses ViewLimits.maintenance_calls_remaining, preserving StrategyParameters/checkpoint identity and whole-plan zero-callback refusal. V1 maps only known INPUT_EXCEEDS_CAPACITY, reports complete request capacity/once-per-session 80% warning and separately labels storage. Meter dispatch is to the local Gateway and not proof of provider delivery. Task 12 checks actual HostMaintenance-wrapped complete input/framing/output and a refusal genuinely requiring a second repack.

Fable findings and five Codex rulings are in review-disposition.md. Test composition is source-owned and the host owns its Gateway child; no run-gateway profile flag. Historical Plan 9.88 evidence validates its frozen prompt while the runner refuses new capture after prompt drift. Secret-scan fixes use a separate new test file and five comment-only identity-pin markers; no baseline or hook waiver.

Codex supplies corrected complete sources and PDFs; Claude files/verifies under the existing local filing release, including historical PR #214/2026-10-02 references and cancellation note. ADR IDs remain unallocated pending the live index/concurrent proposals; the D7 exact-word record awaits the saved transcript. Immutable predecessors/evidence stay unchanged.

Documentation filing alone does not close CP4. Luna route/estimator proof, genuine summary-quality receipt and real Task 13 remain UNRUN and required unless separately disposed by the operator. Paid/live, push/PR/merge, activation, shipped default removal and sandbox synchronization remain held.
