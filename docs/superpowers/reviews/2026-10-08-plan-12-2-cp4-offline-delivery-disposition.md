# Plan 12.2 CP4 offline delivery disposition (addendum)

Recorded 2026-10-08 (Asia/Calcutta). Claude files this record; Codex is architect and reviewer.

This addendum records an operator decision. It adds to the [2026-10-04 CP4 offline review disposition](2026-10-04-plan-12-2-cp4-offline-review-disposition.md) and does not change it. It is not a second work pool: the consolidated backlog owns current status.

## Operator decision

**Where it was given:** the Claude Code session `4162c45b-36f9-4cec-adb6-722ec3b28cb2`.

- **When:** 2026-10-08 at 21:11:06 IST (`2026-10-08T15:41:06.488Z`).
- **Record:** `91060d43-735d-4d0f-8cb6-17a956181c6d`.
- **The message:** it relays Codex's note that the operator's approval was still pending, then ends "[Vibhanshu] Approved".
- **Who wrote what:** Codex worded the approved text, with Claude's concurrence. The operator decided.

> I accept the completed offline implementation and documentation through `2068366`. Defer Luna route/estimator qualification, the genuine summary-quality receipt and real-editor Task 13 as named, UNRUN obligations under existing Plan 12.2 ownership. Record offline delivery as complete with live qualification deferred. Preserve safety gates and sealed evidence; commission no further model investigation.
>
> Production enforcement, attached production use and Haiku-default removal require their applicable real evidence and separate activation authority. This disposition grants no full CP4 pass, paid/live execution, push, PR or merge.

**Source.** The session transcript is the source. No export of it is registered for this record. If a decision record later quotes these words, register a session export first, as ADR-011 requires and as was done for source S4.

## How the decision was reached

Full CP4 was blocked at its first dependency, an eligible summarizer route:
- The summary-quality receipt needs verified route facts.
- The context-engine part of Task 13 needs that receipt.

Codex compared three options:
- **A:** a fallback model search, inspection and qualification batch;
- **B:** accept the offline delivery and defer the live items;
- **C:** wait for OpenAI to publish a Luna tokenizer mapping.

Codex recommended B as the simplest. Claude concurred.

**No qualified summarizer is needed for safe operation.** [ADR-006](../../decisions/ADR-006-summarizer-model.md) specifies the non-latching fallback when no eligible summarizer exists: full history if it fits the floor, otherwise a recoverable refusal. The offline candidate implements both, verified at `cf9bb9d`.

**Claude's addition, with Codex's wording.** Offline acceptance remains evidence for the offline checks. It cannot substitute for the real evidence that activation requires.

## What this records

| Item | State |
|---|---|
| Offline implementation and documentation through `2068366` | Accepted. Offline delivery is complete |
| Luna route/estimator qualification | Deferred, UNRUN. Luna is ineligible: the tokenizer, framing and finish-semantics gaps are identified. The 2026-10-04 free inspection is complete and its time window is closed |
| Genuine summary-quality receipt | Deferred, UNRUN. It needs an eligible route |
| Real-editor Task 13 | Deferred, UNRUN. Its absent-engine cases may run before summary qualification, once their own route, service and execution prerequisites are met |

The three deferred items stay under existing Plan 12.2 ownership. No further model investigation is commissioned.

## Boundaries

- **This is not a full CP4 pass and not a waiver.**
- **The safety gates are unchanged:**
  - production `ENFORCEMENT_ACTIVE` is `False`;
  - `trusted_snapshot()` returns `None`;
  - the shipped `claude-haiku-4.5` default is unchanged;
  - the attached test profile admits no model without a genuine receipt.
- **Activation needs more than this record.** Production enforcement, attached production use and Haiku-default removal each require their applicable real evidence and separate activation authority.
- **History is preserved.** Sealed evidence and historical records are unchanged.
- **No authority is granted.** The decision grants no paid or live execution, push, PR or merge.

## Branch at the decision

`agent/claude/plan12-context-engine-cp4`, local only, on `main` `a929aab`:

| Commit | Content |
|---|---|
| `cf9bb9d` | Offline code candidate |
| `5ee081e` | Documentation filing |
| `9f70fab` | D7 record from source S4 |
| `2068366` | Plan v4 correction; ADR-018 Accepted-with-open-items |
