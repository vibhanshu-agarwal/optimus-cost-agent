# ADR-013: Repair runner effect producers as Plan 12's first code step

**Status:** Accepted-with-open-items. **Decision date:** 2026-10-01. **Decider:** operator, evidenced by the verbatim selected option and cross-checked question-tool answer. **Publication:** Repository-form record; editable in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:** Completes the delivery prerequisite for [ADR-002](ADR-002-history-strategies-and-picker.md)'s exact effect-state requirement; relates to [ADR-001](ADR-001-context-engine-separate-product.md)'s authoritative host boundary. It does not supersede either record or change the effect vocabulary.

## Source and provenance

Source **S2**, indexed in the [decision log](README.md#rules-for-every-record): the operator's Claude Code session "PYTHON - [PLAN 12] Context Engine compaction", session `4162c45b-36f9-4cec-adb6-722ec3b28cb2`, exported on 2026-10-01 to `optimus-handoff\decisions-sources\2026-10-01-claude-session-context-engine-decisions-export.zip`; SHA-256 `8769D433CB869362305E91525273E8CA7A19EBC2807B1CA726F5DC9D4A81F5C2`. The archive is external raw provenance, never an operating, test or release dependency. The verbatim questions, options, selected labels and typed response reproduced below are the repository-visible decision evidence. Codex verified the archive checksum and the exact Q1–Q3 selections against the original question-tool records; Claude checked the export. Question/option wording is Claude's; selected labels and typed responses are the operator's. Agent relay summaries are context only.

**Initial question shown, verbatim:**

> Q1: No production code records whether a turn's file changes or tests actually happened, so every turn is stored as 'no effect'. How should that be fixed?

**Operator's typed response, verbatim:**

> How much effort is this fix?

**Scheduling question shown, verbatim:**

> Q1: How should the effect-state fix (small: about 100 lines of code plus tests) be scheduled?

**Operator selected, verbatim:**

> Fold into Plan 12

This was **not** Claude's recommended option. The “small” / “about 100 lines of code plus tests” language was Claude's code-reading estimate, not measured implementation effort or an operator requirement. No completed patch or elapsed-time proof supports that estimate here.

## Context and verified facts

On the source tree pinned to merge `83fafb9606fb81992508554aa302d3b62c603236`, runner READ/WRITE/TEST executors discard their operation control (`runner.py:822,849,875`), approved READ/WRITE/TEST calls omit it (`:706,723,727`), and `_commit_turn` records NONE (`acp/spec.py:1039`). Lifecycle registration/start/terminal APIs and effect calculation exist, but correct WRITE/TEST producer facts do not follow from their existence. Archived Plan 11.25 Task 6 Steps 3 and 8 mark producer instrumentation complete despite this discrepancy.

The pinned main has in-memory sessions and no session/load handler. Restarting the repaired process creates fresh conversation history. If durable restore ships first, its owning lane must handle provenance before treating old placeholder NONE records as authoritative; no unconditional historical migration is added here.

## Options and reasoning

| Exact option shown | Exact description shown |
|---|---|
| Separate item, sandbox route (Recommended) | A new runtime-hardening item, drafted by Codex and implemented by Claude. It is built in the sandbox, tagged, then copied to main with a PR. This is the usual hardening route and fixes both copies; it takes longer overall. The Context Engine waits for it before going live. |
| Separate item, straight to main | The same item, built directly on main with one review and one PR. It's faster, and the sandbox picks up the fix the next time it's synced with main. |
| Fold into Plan 12 | Fix it inside the Context Engine work as its first step. Fastest, but a runtime-hardening fix ends up in a feature PR. |

Claude recommended the sandbox-route option because it follows the usual hardening custody and repairs both copies. The operator chose Fold into Plan 12 instead. It puts the narrow runtime repair first within feature custody and leaves the sandbox unchanged until later sync. The option description's “Fastest” is Claude's comparative claim, conditional on early delivery; it is not an accepted timing guarantee or a selection of one combined PR. Waiting for the full engine, paid qualification and all live evidence would delay the fix. PR shape remains the operator's later decision.

**Decision, paraphrased from the actual selection:** include the narrow repair in Plan 12 as its first product-code task. It reaches main through Plan 12's authorized main-based PR or PRs; no direct main editing is authorized. Do not create a separate runtime-hardening item for this scope. Attached production activation requires reviewed real-boundary proof. Offline engine construction/testing may proceed before activation under the separately accepted scope and first-step ordering. The later Package A selection below releases only Tasks 0, 2 and 3 after docs-first filing; package-A PR shape remains undecided.

## Technical mechanisms agreed by Claude and Codex for scope review

- A TEST returning normally is an executed effectful operation even if its test exit is non-zero: execution terminal `succeeded`, test verdict independently failing. COMPLETE denotes completed effectful execution, not test correctness. A typed proven pre-producer denial is failed_no_effect; uncertain completion after possible WRITE/TEST start is failed_effect_unknown. READ remains non-effectful. No new enum.
- IDs combine host turn/run identity, phase and invocation/directive ordinals in per-call state. Repeated paths/commands and implicit pre-WRITE reads have distinct IDs; no shared AgentRunner counter or model-issued identity.
- Register known WRITE/TEST operations before execution. lifecycle.py must change: cancellation and denied starts suppress operations without recomputation today. Recompute in those paths or provide a locked fresh effect read at commit; transport teardown already recomputes. Completed WRITE followed by cancelled TEST must project PARTIAL, not a stale COMPLETE. Lease grant is the existing start boundary; already-started work is not promised to be killed or rolled back.

Claude agreed with all three technical choices in its version-4 review: TEST execution semantics, deterministic per-call IDs, and advance registration of the known WRITE/TEST set. They are architect/reviewer choices, not additional operator-selected defaults. The full [Plan 12.2 (reviewed source revision 5)](../superpowers/plans/2026-10-01-plan-12-2-context-engine-implementation.md) retains the technical contract; the later selection below authorizes only its Package A subset.

## Separately recorded execution and filing authority

S2 also records this later question and selection at `2026-10-01T06:09:37.747Z`:

**Question shown, verbatim:**

> What should I be authorized to implement now?

**Operator selected, verbatim:**

> Package A (Recommended)

**Selected description shown, verbatim:**

> Tasks 0, 2 and 3, in a fresh worktree from the latest main: set up and check main for changes since the plan was written; fix effect recording and cancellation (Task 2); then add the visible 80% warning, usage meter and history-order fix (Task 3). Codex reviews each task. No paid calls. It ends with a reviewed branch; whether that becomes its own PR is your call then.

**Filing question shown, verbatim:**

> When should the three new decision records (ADR-013–015) and the Plan 11.25 correction note go into the repository?

**Operator selected, verbatim:**

> Docs PR first (Recommended)

**Selected description shown, verbatim:**

> A small docs-only PR now, like PR #213: the three records, a hashed export of this session as their source (S2), the decision-index update, the Plan 12 backlog entry and the correction note. Your decisions are frozen in the repo before code starts. It costs one extra PR cycle.

This operational authority is separate from Q1's architecture decision. It authorizes Claude's Tasks 0, 2 and 3 only; Task 0 is read-only and Tasks 2/3 wait for the docs PR merge. Task 1 and Tasks 4–13, paid calls, service/settings changes, sandbox changes and package-A commit/push/PR/merge are not authorized by this selection. Codex remains architect/reviewer. The sole backlog records current execution and delivery gates. Raw S2 stays outside Git; its source entry and this sanitized record are filed. The spec and full plan are filed alongside the records so the backlog has its required plan link; filing the full plan does not authorize its remaining tasks.

## Consequences, custody and authority

Codex drafts and reviews; Claude reviews then implements the accepted scope; the operator separately accepts execution scope and delivery. The sole consolidated backlog retains Plan 12 custody. Sandbox synchronization, broader goal-loop cancellation, unrelated producer instrumentation and persistence remain separately owned. The PR description must disclose the hardening fix and the sandbox's retained gap. The [Plan 11.25 correction note](../superpowers/reviews/2026-10-01-plan-11-25-effect-instrumentation-correction.md) reports the discrepancy without modifying the archived plan or sealed evidence.

Q1 accepts scope placement and required behavior. Separately, the later source-backed selections authorize docs-first filing and Claude’s narrow Package A execution after its merge. Those selections do not authorize the full plan, paid calls or package-A delivery. Publication freezes this record on its first merge.
