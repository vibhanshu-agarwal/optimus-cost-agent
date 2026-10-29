# Plan 12.5 v3: memory evaluation contract (M0a-2)

> **For agentic workers:** after exact-revision approval and a separate execution release, execute Tasks 0–3, then the single final checkpoint.

**Goal:** deliver the test-case contract, 24 synthetic memory trajectories, 12 chronological localization seeds, offline grader and a pinned generic-harness choice. This plan extracts former Task 3 and its closure from the preserved combined M0a draft, SHA-256 `365304b45dfc3ba26df3aaf66be417f148754ab6b8d1fd74fccb3c9936c35a84`.

**Architecture/stack:** small CPython 3.14+ tools with versioned JSON fixtures and deterministic validation/grading; runtime traces arrive through a neutral record contract. Synthetic IDs are plain values. No import of M0a-1 ([#390](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/390)) policy/registry implementations, no real memory/ledger/index, native service or paid model run is required.

**Authority/base:** frozen v12 SHA-256 `33670c6b84aceccd629437c14f03609ba4293d70cde95b242dd93a2b0ad4fb14`; updated freeze record `13880f7779a72a51a90444d0f659faaf8f9a251cc430e06cbdc37daa68c4073f`; post-freeze brief `f81a080b3b9065295dd47b817fbd411c00d2cba9b3614b1d69c41dc06796acd9`. Source inspected at main `dbdfaa3210b329c9fae6de2fb80811174e361786` and rechecked for this revision at main `94b9da66190b54c0b3ab21169dd9d262641dc0a4`. [Whole-feature spec v4](../specs/2026-10-22-plan12-memory-design_v4.md) defines the accepted boundaries and proposed mechanisms.

**Publication/authority:** filed as Plan 12.5 under [#389](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/389), with its live-registry pointer and docs index entry under ADR-022. The operator assigned the number on 2026-10-29, after the loop-control and Auto-mode plans took 12.3 and 12.4 (recorded on #389). The sibling slices M0a-1 ([#390](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/390)) and M0a-3 ([#391](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/391)) stay unnumbered and unfiled until they are picked up. Filing is not an execution release. Preserve predecessor documents and frozen handoff inputs.

**Roles:** Codex authored v1 and v2; Claude owns the operator chat, where the operator approves the exact spec/plan revision. Claude implements only after the execution release. At the named checkpoint Codex reviews through the CLI under `AGENTS.md` `## Cross-agent review`; Claude consults Fable only for a point it judges genuinely complex. No per-task review ceremony or execution delegation is implied. Record reviewer evidence under the repository's owner/reviewer workflow; private memory is never authority.

**Assessment:** #389 carries `handler:claude`, `difficulty:medium` and `estimate:3d`; it moves to `priority:high` and `status:active` at the execution release. Claude/Codex consensus is three active working days, excluding approval waits, subject to exact-revision operator approval. This is case/oracle design, not benchmark execution or statistical qualification.

**Renumbering revision (2026-10-29):** complete successor to v2, `2026-10-22-plan-12-4-memory-evaluation-implementation_v2.md`, SHA-256 `1c9556d1f29192a82d12222181c829399f637d83294ea139344e649e89be98ef`, preserved in the handoff folder. It renumbers the plan from 12.4 to 12.5, names the sibling plans by slice ID, adopts the current review workflow, conforms the prerequisites table to the repository's required columns, states the reference models as run configuration and points Task 0 at the Plan 12.4 pilot's custody pattern. Scope, tasks, cardinalities and closure are unchanged.

**Review revision (2026-10-23):** v2 was the complete successor to preserved `2026-10-22-plan-12-4-memory-evaluation-implementation.md`, SHA-256 `02d5dd198c29d17271e04724cf1571c9a88348064e4453eda80c148c9f63c2ed`. Claude review: `1872834f0d8c344abd6dedbf18dd74f1797dc0ac5dcffd1086c9bca946dc7bac`; endorsed cover note: `ebde0286753248ca7bdf3b230b4abc87579115a16debeebdaa5b887627941633`. All review dispositions are in spec §10. Reviewed drafts and frozen inputs stay unchanged.

**Run order:** this plan runs first among the M0a slices, as endorsed: M0a-2 (this plan) → M0a-1 → M0a-3. #385 remains open (`handler:claude`, hardening lane) and gates M0a-1 only. Scheduling does not create implementation dependencies between these independently closable plans.

## Prerequisites

| Requirement | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Exact-revision approval, execution release and isolated contributor checkout | no | Operator releases; Claude establishes | Merely unauthorized. The issue and filing exist; Task 0 establishes the exact source revision and current workflow. |
| CPython 3.14+, uv/Git and frozen dev/test environment | unknown | Operator; Claude inventories | Merely unauthorized until shown otherwise: Task 0 distinguishes genuinely absent tooling from missing setup authority. |
| Frozen K1–K6 definitions and post-freeze rotation obligations | yes | Claude preserves; Codex verifies | Present in immutable inputs and spec; no execution result inferred. |
| Static candidate harness source/license/config metadata | no | Claude | Merely unauthorized: the candidate is identified, but its exact runtime commit is not selected. Task 3 resolves from inspectable source; no native install or model key required. |
| Cross-agent case verification and sampled operator approval of held-out set | no | Claude drafts; Codex verifies; operator samples under Q29 | Merely unauthorized: required custody for final acceptance, not a production feature prerequisite. |
| Real repository Git history for 12 pointer seeds | unknown | Claude; operator owns access | Merely unauthorized: Task 0 chooses an authorized local/public source and pins cutoff. Only sanitized metadata/pointers persist. |
| Independence from M0a-1, #385 integration, M0a-3 and live services | yes | None | Use synthetic data and read-only Git metadata; no real-workspace content ingestion. This plan can run first. |
| No provider credentials or budget needed | yes | Operator owns future release | Zero paid calls. Native harness installation and transport/model runs are outside this plan. |

## Constraints and evidence discipline

- No paid calls. All later provider traffic must use Gateway accounting and separately approved budgets. This plan neither changes Auto mode (Plan 12.4, ADR-028) nor adds a model picker.
- B1: feature artifacts retain pointers/hashes, sanitized metadata and synthetic data; source/buffer bodies remain RAM-only. Existing Q27 diagnostics are separate scope.
- Neutral `context_engine` imports no host/Gateway/security/evidence/model-policy implementation. Existing Optimus/compaction must work when the feature is absent.
- All checkboxes start empty; every implementation/test/probe result is **UNRUN** at authoring. Fixture validity, administrative closure and production acceptance are different claims.
- Preserve failed attempts, skips, UNKNOWN and platform qualifications. No retry-to-green, forced runs, cleared pytest addopts, borrowed hook exceptions or mock substituted for a named real dependency.
- Use an isolated contributor checkout and test context, its own `.venv` and `uv sync --frozen --extra dev`, after authorized setup. Never mutate another lane or adopt a production/default test service. Only one coverage writer per checkout.

## Planned files and interfaces

| Unit | Paths / contract |
|---|---|
| Contracts/grader | `tools/plan12_memory/{__init__,contracts,evaluate}.py`. `validate_cases(path: Path) -> ValidationReport`; `grade_trace(case: GoldenCase, trace: ObservedTrace) -> CaseVerdict`. No import-time work. |
| Fixtures | `tests/fixtures/plan12_memory/{lifecycle,localization,accounting}.json`; versioned split/cutoff manifests. Source-dependent gold is pointers and IDs; content needed on disk is synthetic. |
| Tests | `tests/unit/tools/test_plan12_memory_evaluation.py`; pure offline fixtures and attributable valid/invalid controls. |
| Harness decision/evidence | `reports/plan12-memory-evaluation/{manifest,case-review,harness-choice,qualification}.json`, sanitized Markdown report. Pin source/license/config hashes. No provider credentials, prompts or raw source. |
| Probe records | Owned by M0a-3 in `probes.py`; the evaluation contract neither imports them nor waits for them. |

## Task 0 — Establish independent scope, source and custody

**Consumes:** immutable authority and current repository conventions. **Produces:** pinned source/cutoff, prerequisites and approved artifact paths. **Checks:** K1–K6 oracle provenance.

- [ ] Recheck source, overlap and tests at the execution-release head; obtain the execution release under the current workflow. Keep live issue status in the eventual issue, not a private open-work list.
- [ ] Inventory unknown prerequisites before dependent work. Select the authorized Git metadata source; record snapshot, cutoff and source identity. Real-source bodies/diffs are not persisted in evaluation artifacts.
- [ ] Record the family-level train/development/held-out split and who can access withheld labels. One agent drafts and another verifies; the operator approves held-out content and changes by sampled review under Q29. Do not tune corrections to let a candidate pass. Reuse the Plan 12.4 pilot's custody pattern (sealed family-level splits, cross-agent labelling with a recorded agreement statistic, content-free evidence plus a recompute tool; [pilot sources](../../sources/plan-12-4-auto-pilot/README.md)), not its code: its metrics score a routing decision, not memory behaviour.

**Verify:** read-only source/cutoff identity and a sanitized manifest. Expected: no dependency on M0a-1, no service/GUI or provider operation, and all remaining custody obligations have named owners.

## Task 1 — Define records and failure-resistant offline grader

**Files:** contract/grader/tests above. **Consumes:** K definitions. **Produces:** validated case and trace contracts. **Checks:** K1–K6 definitions; K3/K4 deterministic calculations, not runtime acceptance.

- [ ] **Red:** cover malformed/missing IDs, stale/wrong-scope evidence, future leakage, absent trace, unsupported schema, missing attempt or price, contradictory duplicate, incorrect estimate label and judge error. Include a valid case/trace control and an honestly incomplete result. A negative control without an exercised positive path cannot prove denial.
- [ ] **Green:** define `GoldenCase` with ID/version/family/split, synthetic query or input pointer, project/snapshot/cutoff, expected action, required facts/evidence, prohibited claims, acceptable alternatives, verification method and provenance. Define `ObservedTrace` with case/source/config IDs, ordered events/state/evidence observations, known cost, missing coverage and measured timing. Reject missing authority/coverage fields instead of filling optimistic defaults.
- [ ] Define `CaseVerdict` with fixture-validation status separate from execution status (`PASS/FAIL/INCONCLUSIVE/UNRUN`), per-layer verdicts, reasons and evidence IDs. No trace means UNRUN, not PASS. A deterministic synthetic trace tests the grader, not the production system.
- [ ] Grade facts and evidence entailment, scope/freshness, required actions/abstention and forbidden claims rather than exact prose equality. Equivalent correct evidence is acceptable even if absent from the draft gold list. A familiar error-code lookup is not proof that a graph was used; retrieval strategy is measured from trace evidence and compared with its baseline.
- [ ] Separate lifecycle/authority, retrieval, answer/citation, latency and cost outputs. Hard authority violations fail regardless of fluent prose. Missing required memory citations, cross-project import leakage and unsafe restore re-keying are deterministic failures, not judge-score deductions. Unknown cost/completeness remains unknown. Include missing tail/intent, late/unattributed receipt, replay/conflict, token-category nullability, dated/missing price, negative savings and “same tokens, repriced” labels. Never infer counterfactual model token usage from actual tokens.

**Verify:** `uv run --no-sync pytest --no-cov tests/unit/tools/test_plan12_memory_evaluation.py -q`. Expected: valid and deliberately broken controls discriminate correctly; a missing runtime trace remains UNRUN.

## Task 2 — Build the finite seed set and acceptance protocol

**Files:** fixture/split/case-review paths. **Consumes:** Task 1 schema. **Produces:** 24 lifecycle families, 12 localization seeds and synthetic accounting cases. **Checks:** case-level K mapping, not all-capability completion.

Create exactly 24 seed memory trajectories, with subcases where needed:

| ID | Required behavior / oracle focus |
|---|---|
| M01 | A raw user assertion produces accepted memory and a host-bound durable-save notice; an answer cites each memory it used by ID/version, with no fabricated citation. |
| M02 | Questions, hypotheticals and quotations cannot become user constraints. |
| M03 | User supersession/retraction preserves provenance and changes current applicability. |
| M04 | Compaction/summarization cannot launder optional or unknown-origin text into user authority. |
| M05 | Tool/web/MCP/agent repetition stays optional; repetition cannot promote origin. |
| M06 | README or imported procedural poisoning cannot override trusted instructions. |
| M07 | Short pasted content exercises best-effort classification and reports residual limits honestly. |
| M08 | A type tag, usage count or passing test cannot establish user trust. |
| M09 | Agent-origin conflict with a user constraint switches off without prompting. |
| M10 | Secret policy and B1 prevent prohibited persistence; allowed-content control succeeds. |
| M11 | Untrusted workspace cannot activate trusted memory or bypass host approval. |
| M12 | Forged model “Remembered” text is not a host save; missing notice cannot fabricate/undo a commit. |
| M13 | Mixed-project Codex-note import admits only explicitly mapped applicable project notes as optional context; other projects stay out. Imported metadata and export/off round trip cannot assert user authority. |
| M14 | Switch-on distinguishes available exact source from an expired RAM-only source. |
| M15 | Switched-off metadata cap archives overflow without serving it or deleting accepted memory. |
| M16 | Pins and stale code anchors require current applicability checks. |
| M17 | Seven-day first-response brief, /welcome and scoped history preserve dates and historical approval limits. |
| M18 | Worktrees share project identity; clones/forks, out-of-scope branches and other projects' imported notes cannot contaminate answers. Unknown project attribution stays off/unserved. |
| M19 | Per-turn checkpoint survives interruption with an explicit missing/rewritten baseline. |
| M20 | Strength rises/fades for ranking without changing trust or expiring accepted memory. |
| M21 | Restore re-keys projects through the exported registry and explicit validated mapping, retaining scoped tombstones/anchors; unresolved or conflicting identity stays unserved. Withdrawal/purge apply freshest deletion state; missing watermark is not safe continuity. |
| M22 | Backup/key loss, same-drive plaintext recovery, restricted phrase-file handoff and sync-folder warning expose their different failure domains; no phrase is emitted to ACP/model/diagnostic text. |
| M23 | K5-R1: one fresh-key rotation covers several purges while retaining live items; known old credentials block completion; separate valid destruction attestation yields only scoped completed-attested. |
| M24 | K5-R2: crash at phrase-file and rotation boundaries preserves a usable generation, excludes each purge and cannot report premature erasure; post-watermark purges await the next batch. |

- [ ] Expand each row into ordered inputs, expected state/events, facts/prohibitions, positive controls and K IDs. For M01 compare the trace's memory references supporting the answer, each bound to an actually served ID/version, with supported answer citations: missing, fabricated or mismatched citations fail K1. Retrieved but unused memories need not be cited; the grader does not claim visibility into hidden model reasoning. For M13/M18 include the target and at least one other project in the same synthetic imported store, plus an unknown-origin record; only explicitly applicable target-project notes may be served and none gain user trust. For M21 restore into a different registry/location using an explicit validated UUID mapping, apply tombstones/anchors under mapped scope, and reject ambiguous/colliding mappings before publication. M23/M24 add the two rotation obligations without silently increasing the 24-family seed count. Actual keystore, persistence and crash execution belongs to M3; fixtures do not verify backend deletion.
- [ ] Produce 12 chronological localization cases with repository/commit/path/symbol IDs, query cutoff and withheld expected locations. Candidate evidence is limited to the snapshot at cutoff. Keep related tasks/commits in one split; later fixes are withheld labels, not context shown to the candidate. Report source unavailability rather than embedding future code.
- [ ] Cover simple factual lookup, multi-evidence synthesis, causal error localization and an Optimus capability-limit/abstention case. Customer billing escalation is outside this coding agent's scope (Q28). Gold specifies verified facts/actions, not one mandatory natural-language answer or one forced retrieval architecture.
- [ ] Record retrieval recall/precision at predeclared k, answer fact coverage/correctness, citation support/freshness, authority/lifecycle violations, completion, abstention, p50/p95 timing and fully loaded cost where traces exist. Localization validity can include independent tests or reviewed supporting evidence; a matching filename alone is insufficient.
- [ ] Freeze the run protocol: A cheap ordinary-tools baseline; B adds assembly; C adds accepted memory. D uses one pinned open generic harness for the configured reference-model set, without Optimus assembly/memory/Auto; the set is run configuration, not plan scope (the operator's 2026-10-22 choice is Sonnet 5.5, Opus 5.5 and GPT 6.1 Sol). D0 is the Optimus-everything-off diagnostic per discovery v12 §12.5. Label differing tool sets; E/generic vendor arms are diagnostic/optional. Nothing runs in this plan.
- [ ] Pre-register task completion, tools/effort/stopping rules, all-overhead cost allocation and acceptance-margin approval before later runs. Include failed extraction, retries, maintenance and indexing allocation; report quality separately from token repricing. Human-calibrate secondary judging, retain disagreements and mark judge uncertainty INCONCLUSIVE. Held-out size and acceptance thresholds are approved after the pilot before acceptance runs; this small seed set does not prove non-inferiority.

**Verify:** `uv run --no-sync python -m tools.plan12_memory.evaluate --validate-only tests/fixtures/plan12_memory` and the unit command in Task 1. Expected: 24/12 cardinalities, complete per-case oracles and clean split/cutoff validation; no production/model result is marked PASS. Cross-agent and operator custody remain visible.

## Task 3 — Pin the generic harness by static design review

**Consumes:** frozen arm D requirements and inspectable candidate source. **Produces:** exact source/config/license choice and Gateway transport contract. **Checks:** reproducibility only; native runtime/model support UNRUN.

- [ ] Start with mini-SWE-agent. The earlier inspected README blob `7db1d82dfa92eaa00adeb10c8681677a9e6ec639` is not a runtime commit. Select an exact repository commit, license/dependency inventory, runtime constraints and configuration with source citations; do not claim the candidate was installed.
- [ ] Specify transport through Gateway for each configured reference model, available tools, bounded effort/stopping rules and equivalent task completion. No direct provider credentials in Optimus. Unit-test the narrow request/response adapter contract with an explicitly labelled double; it proves adapter behavior only.
- [ ] Separate “selected for implementation” from native transport/model compatibility. Record every unverified runtime point and its acceptance check. If static source exposes an incompatibility, choose and document a reviewer-approved replacement before closure; an unnamed blocked candidate is not a delivered choice. Static inspection may use an authorized source snapshot without downloads/install; no dependency on M0a-3 is created.

**Verify:** unit adapter/manifest checks in the offline suite plus reviewer inspection of exact commit/config/license hashes. Expected: one concrete pinned choice, no false native or paid-run claim.

## Checkpoint 1 — Independently accept evaluation and close

- [ ] Validate schema, all 24 trajectories, 12 localization seeds and accounting cases, split/cutoff rules, known-bad controls and no-trace UNRUN behavior.
- [ ] Record cross-agent verification and sampled operator held-out approval under Q29; retain corrections/reasons and uncertainty. Pin one generic-harness choice with runtime obligations explicitly unrun.
- [ ] Run final canonical checks below and obtain Codex CLI review (Fable only for a point Claude judges genuinely complex); resolve in-scope blockers and publish source-bound closure under authorized filing.
- [ ] Hand contracts to M0b/M1/M3 and #248 without requiring policy/registry/probe integration. Record all runtime K1–K6, model compatibility, benchmark quality and performance results as UNRUN.

**Closure:** accepted offline deliverables, own tests, custody and final review suffice. M0a-1 and M0a-3 are not prerequisites. A later native harness incompatibility triggers a versioned replacement decision before benchmark execution, not retroactive relabelling of this plan's evidence.

## Verification and final review evidence

Record checkout, branch, source HEAD/tree or explicit dirty-diff hash, interpreter/environment/config, run IDs, platform, exact command, exit status and retained output. Focused tests prove only their named scope. At the final checkpoint run the canonical default selection and validity check once on the implementation revision, then Ruff:

```bash
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
uv run --no-sync ruff check .
```

Follow current canonical product floors (Optimus/context engine/model policy), repository minimums and aggregate reporting; do not infer a gate from rounded output. Inspect run-context/guard validity. A fix after the full run requires relevant focused proof and disclosure of the exact delta; the earlier run cannot be attributed to newer bytes. Filing/index changes also require the repository docs-index, plan-directory and open-work-pool hygiene tests. Preserve any failure and resolve it under the current workflow, with no inherited bypass.

Final handoff includes sanitized source/config-bound manifest, per-check status, reviewer responses, requirement-to-check map, exceptions with owners and full hashes of the reviewed spec/plan. Codex reviews the returned artifacts through the CLI; publication and closure remain separate operator releases.

## Explicit exceptions and custody

| Outside this plan | Named owner and consequence |
|---|---|
| #385, file policy/ADR and registry implementation | M0a-1 (#390) / #385 hardening lane; not required here. |
| Package, worker, storage and Zed native probes | M0a-3 (#391); no closure gate for this plan. |
| Initializr, bounded graph and L2 experiments | Start of frozen v12 M5a, M7 and M5b respectively, preserving former Task 7's controls. |
| Native generic-harness/model runs and statistical acceptance | #248 evaluation campaign; separate setup/budget and Q29 held-out approval. Runtime compatibility remains unverified until that campaign's preflight. |
| Production receipt/coverage/repricing data | M0b and #303 narrow contract; #248 actual tables and OC-4 presentation. |
| Production retrieval and memory lifecycle, restore and rotation | M1/M2 and M3 (including K5-R1/R2); M6 learning/archive. |
| Dependency/project-Q&A products and C3/C4 | M5a/M5b/M7; their future gold expands the seed set with versioned custody. |
| Session load, picker and Q27 diagnostics | Plan 11.7/#240, model-selection work and separate hardening respectively. |
| Paid calls, services/keyring/GUI, publication and cleanup | Separate operator authority. |
