# Optimus decision log (ADRs)

**Why this exists.** On 2026-09-30 the operator said:

> "Importantly, I hope this context can be saved in some way - often my requirements gets lost or
> oversimplified losing the original context and reasoning. Architectural decisions should not be binary
> - must be supported by proper reasoning and tradeoff analysis"

Three recent examples show the problem. Agents set each of these values, and each was later treated as if
the operator had required it:

- the $0.05 per-turn budget;
- the "100K inside 128K" headroom;
- the 3-planning-turn cap.

Meanwhile a real operator requirement, "curbing unnecessary agent loops", survived only as one line in a
brainstorm diary.

**Where this log lives.** Here, in the repository, as the operator required on 2026-09-30: "These should be
in the repo and agreed by both you and Codex". Every agent reads the same versioned copy, and every change
goes through review. Earlier drafts in the operator's handoff folder (outside the repository) are superseded
by this folder.

## Rules for every record

1. **Keep the operator's words verbatim,** with the date and a shared source. A paraphrase is labelled as
   a paraphrase, with its source. An agent's private memory or paraphrase is never a verbatim source.
   - **Source S1.** Unless a record says otherwise, operator quotes dated 2026-09-30 come from the
     operator's messages in the Claude Code session "PYTHON - [PLAN 12] Context Engine compaction".
     - Its transcript export is kept outside the repository in the operator's handoff folder, at
       `optimus-handoff\decisions-sources\2026-09-30-claude-session-context-engine-compaction-export-4.zip`.
     - Its SHA-256 is `E3BCB3F6A9F0C706FF3E0BC46BE791490D871017D753ADB3B34BA44F33DC8A0F`.
     - This fourth export supersedes three earlier ones, which predate the operator's later messages:
       `...-export.zip` (SHA-256 `87CB74E5…`), `...-export-2.zip` (`1BC23372…`) and `...-export-3.zip`
       (`063BC3AF…`).
     - Quotes given after an export was taken need a fresh export, which is recorded the same way.
   - **Source S2.** Operator selections dated 2026-10-01 come from a later export of the same
     Claude Code session, `4162c45b-36f9-4cec-adb6-722ec3b28cb2`.
     - External raw transcript archive: `optimus-handoff\decisions-sources\2026-10-01-claude-session-context-engine-decisions-export.zip`.
     - SHA-256: `8769D433CB869362305E91525273E8CA7A19EBC2807B1CA726F5DC9D4A81F5C2`.
     - Covers Q1’s typed effort question and later Fold into Plan 12 selection; Q2’s guard/floor
       clarification; Q3’s removal-after-accounting sequence; and the later Package A and Docs PR first
       selections (`2026-10-01T06:09:37.747Z`). ADR-013–015 reproduce the decision evidence in tracked
       text. Codex verified the archive checksum and the scope/filing question-tool answers; Claude
       checked the exported selections. Raw S2 is archival provenance, not an operating/test/release input.
     - S1 remains the cited provenance for the frozen 2026-09-30 records; S2 adds later selections.
   - **Source S3.** Fresh Package A/cadence export, session `4162c45b-36f9-4cec-adb6-722ec3b28cb2`,
     taken on 2026-10-02 (Asia/Calcutta): `optimus-handoff\decisions-sources\2026-10-02-claude-session-context-engine-package-a-export.zip`.
     - SHA-256 `9B89272060555D1542B14F25C37807F21C5763222D0A93CF2C1ECC791D642A66`.
     - Covers the post-S2 local-commit selection, Task 3's narrow exception, standing checkpoint
       cadence and Package A PR then CP1 selections. Operator text/tool-result selections were
       checked directly inside the archive. Original UTC times are retained; the cadence/next-step
       answers on October 1 UTC occurred on October 2 in the operator's timezone.
     - S1/S2 remain the provenance of their frozen records. S3 is external archival provenance,
       not a build/test/runtime input; no raw transcript is added to the repository.
2. **Label the decider.** Each record says who decided: the operator, an agent (Claude or Codex), or an
   agent proposal still awaiting the operator. A value an agent chose must never read as an operator
   requirement.
3. **No binary decisions.** Every record lists the options considered, with their pros and cons, and the
   trade-off reasoning.
4. **Status** is one of Proposed, Accepted, Accepted-with-open-items, Deferred or Superseded.
5. **A record never changes once it has merged. A change is a new record.**
   - **Where this came from.** The operator assumed, on 2026-09-30: "I am assuming ADR will not change
     once written, we only have a new one that supersedes it?" Claude and Codex agreed to make that the
     rule.
   - **One publication-freeze rule:**
     - **Before its first merge to `main`,** a record is an unpublished draft. It may be revised during
       review, including when it records an operator decision that is already accepted.
     - **On first merge, every record is frozen byte for byte,** including records whose decision status is
       Proposed.
     - **After that,** corrections, completions, acceptance and supersession all use a **new** record that
       names what it affects ("Completes ADR-00N item X", "Accepts ADR-00N", "Corrects ADR-00N",
       "Supersedes ADR-00N").
     - The mutable index records the effective decision status and preserves links to unchanged
       predecessors.
   - Freezing defines when bytes stop changing. It does **not** turn a Proposed mechanism into an accepted
     decision.
   - The first batch (ADR-001 to 012) was revised in review before its first merge, after Codex's reviews
     on 2026-09-30.
   - **A fully superseded record moves unchanged to `archive/`** beside this folder's records, following
     the repository convention in `docs/README.md`.
     - This index, the only mutable part of the log, keeps its row, **links to its archived location** so
       the published link still resolves, and marks it "Superseded by ADR-0NN".
     - Its line in `docs/README.md` is removed, as the docs-index test requires.
     - Tools find documents by file name (`tools/doc_paths.py`), but a Markdown link in another document
       that points at the old path will not follow the move in a browser. Link to a record through this
       index where practical.
   - **The index Status column is mutable and shows the effective state,** for example
     "Accepted-with-open-items; item 1 completed by ADR-013". A frozen file keeps the status it had when
     it merged.
6. **Read before proposing.** Any agent working in an area reads the relevant records first and does not
   re-derive or contradict an Accepted one. If new evidence conflicts, raise it explicitly with the
   operator.
7. **Keep evidence separate from interpretation.** Facts carry their source: a file and line, a commit, a
   URL and date. Interpretations are labelled as such. Survey findings are stated as what the surveyed
   sources show, never as universal claims.
8. **State the authority boundary.** Keep these apart:
   - an operator's acceptance of a requirement or policy;
   - a proposed mechanism, default or number;
   - authority to implement, commit, publish, merge or make paid calls.

   A record accepted "with open items" may accept the requirement while its mechanism stays proposed.
   **No record commissions implementation** on its own.
9. **Work lives in the backlog, not here.** The consolidated deferred-followups backlog remains the sole
   live registry for work, owners, statuses and next gates. Filing a record does not close an existing
   owner or authorize implementation or paid calls.

## Index

| ADR | Title | Status | Decider | Date |
|---|---|---|---|---|
| [001](ADR-001-context-engine-separate-product.md) | The Context Engine is a separate, loosely coupled product; the Optimus floor stays | Accepted | Operator; details agreed by Claude and Codex | 2026-09-28 to 09-30 |
| [002](ADR-002-history-strategies-and-picker.md) | History strategies (compaction default, hybrid, sliding window) and the IDE picker | Accepted; effect-repair placement clarified by [ADR-013](ADR-013-plan12-effect-producer-repair.md); offline repair evidence accepted in Package A; main publication/live gates remain | Operator; definitions agreed by Claude and Codex | 2026-09-29 to 09-30 |
| [003](ADR-003-context-ceiling-and-history-limits.md) | Context ceiling of about 256K for all models; history may exceed 512 KiB while the engine is attached; Haiku removed | Accepted-with-open-items; D7 interpretation completed by [ADR-014](ADR-014-all-session-request-guard-floor-clarification.md); measurement obligations remain | Operator | 2026-09-30 |
| [004](ADR-004-curated-model-registry.md) | Curated model registry (YAML), tiers, origin rule, per-token selection among eligible models | Accepted-with-open-items | Operator; mechanism proposed by Claude, reviewed by Codex | 2026-09-30 |
| [005](ADR-005-cost-alerts-not-limits.md) | Cost policy: alerts and warnings, not limits | Accepted; sequencing completed by [ADR-015](ADR-015-cost-stop-removal-sequencing.md); runtime migration still owed | Operator | 2026-09-30 |
| [006](ADR-006-summarizer-model.md) | The summarizer comes from the ultra-cheap tier | Accepted-with-open-items | Operator | 2026-09-30 |
| [007](ADR-007-auto-mode-tier-routing.md) | Auto mode: classify each request into a tier | Proposed | Operator direction; design by Claude, awaiting Codex | 2026-09-30 |
| [008](ADR-008-final-review-step-and-modes.md) | A final review step, with Standard and Thorough modes | Proposed | Operator idea; design pending | 2026-09-30 |
| [009](ADR-009-loop-control-without-stopping-the-user.md) | Loop control that is never open-ended and never silently stops the user | Proposed; interim cost-removal dependency clarified by [ADR-015](ADR-015-cost-stop-removal-sequencing.md), without accepting the mechanism | Operator requirement; architecture by Claude, awaiting Codex | 2026-09-30 |
| [010](ADR-010-data-handling-for-chinese-model-routes.md) | Data handling on Chinese-model routes: no restriction now | Deferred | Operator | 2026-09-30 |
| [011](ADR-011-how-decisions-are-recorded.md) | How decisions are recorded | Accepted | Operator (requirement and repository home); mechanism agreed by Claude and Codex | 2026-09-30 |
| [012](ADR-012-cost-savings-report.md) | A cost-savings report is a Plan 12 feature | Accepted-with-open-items (requirement accepted; design proposed) | Operator; design by Claude, awaiting Codex | 2026-09-30 |
| [013](ADR-013-plan12-effect-producer-repair.md) | Effect/cancellation repair as Plan 12’s first code step; completes [ADR-002](ADR-002-history-strategies-and-picker.md) delivery prerequisite, relates to [ADR-001](ADR-001-context-engine-separate-product.md) | Accepted-with-open-items; Package A offline repair accepted; main publication/live gates remain | Operator; narrow mechanisms agreed by Claude/Codex | 2026-10-01 |
| [014](ADR-014-all-session-request-guard-floor-clarification.md) | All-session request guard and unchanged source floor; completes [ADR-003](ADR-003-context-ceiling-and-history-limits.md) D7 interpretation | Accepted-with-open-items; full-floor/estimator evidence owed | Operator | 2026-10-01 |
| [015](ADR-015-cost-stop-removal-sequencing.md) | Cost-stop removal after accounting/D6; completes [ADR-005](ADR-005-cost-alerts-not-limits.md) sequencing, clarifies [ADR-009](ADR-009-loop-control-without-stopping-the-user.md) dependency | Accepted-with-open-items; D6 and migration owed | Operator | 2026-10-01 |
| [016](ADR-016-checkpoint-review-cadence.md) | At most four checkpoint reviews; Fable then Codex; local focused-test commits and Package A publication | Accepted | Operator | 2026-10-02 |
| [017](ADR-017-package-a-coverage-exception.md) | Exact four-statement coverage residual at 38a465f | Accepted; terminal result remains NOT MET | Operator | 2026-10-01 |

**Package A delivery:** [local accepted implementation and evidence](../superpowers/reviews/2026-10-02-plan-12-2-package-a-delivery.md);
the sole backlog records current publication/next gates. The frozen ADR-013 repair decision and
Plan 11.25 correction remain unchanged; the repair exists on the Package A branch, not yet main.

**Evidence in the repository:** [industry practice and model catalog, 2026-09-30](2026-09-30-industry-context-cost-and-model-evidence.md).
It holds the survey of how eight coding agents handle context and spend, the OpenRouter catalog snapshot
of the tier models, and their sources.

**Related filed contract:** [Plan 12.2 design](../superpowers/specs/2026-10-01-plan-12-2-context-engine-design_v2.md) (v2), [implementation plan](../superpowers/plans/2026-10-01-plan-12-2-context-engine-implementation_v3.md) (v3; earlier editions are archived), [Task 1 contracts](../superpowers/specs/2026-10-02-plan-12-2-task1-contracts_v2.md) (v2) and [Plan 11.25 correction note](../superpowers/reviews/2026-10-01-plan-11-25-effect-instrumentation-correction.md). The predecessors are only partially completed/clarified, so ADR-001–012 remain current and unchanged; none moves to archive.

**Working papers outside the repository** (the operator's handoff folder,
`optimus-handoff\plan-12-discovery\`). They are kept for provenance only; the records above are
authoritative.

- `2026-09-30-claude-review-context-engine-direction.md`, `...-claude-reply-2-...` and
  `...-claude-reply-3-...`, with Codex's replies under `Documents\Codex\2026-09-30\...\outputs\`:
  rounds 1–3 of the Context Engine direction.
- `2026-09-30-claude-four-decisions-pros-cons.md`.
- `2026-09-30-claude-model-registry-and-cost-alerts-input.md`.
