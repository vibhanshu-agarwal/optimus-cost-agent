# ADR-044: User memory requires an explicit user action; automatic extraction captures off metadata

**Status:** Proposed; operator acceptance pending.

**Date:** 2026-11-18.

**Decider:** Operator. Recommended by Claude and Codex in principle; Claude's concurrence with the complete mechanism below remains required before the operator is asked.

**Author:** Codex. Claude implements and may place the approved author text in the repository; placement does not establish acceptance or implementation authority.

**Work:** Plan 12.11, issue [#490](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/490), under #235. Work status, owner and next gate remain in the issue.

## Context and provenance

[ADR-031](ADR-031-project-memory-and-evidence.md), Decision, records the operator policy as “Automatic memory, with no review queue.” The [whole-feature design v4](../superpowers/specs/2026-10-22-plan12-memory-design_v4.md), sections 1, 4 and 9, carries automatic memory without user review, immediate admission of supported user statements, automatic retractions and rejection of a review queue. This is the recorded prior policy, not a newly verified quotation from its original transcript. Its original provenance is Source S10 in the decision index.

CP2 reviews 6-9 demonstrated that lexical forms, source spans and current target matches do not establish the meaning or authority of a user mutation. Reported failures included attributed statements, indirect questions, conditional changes and reversed withdrawal wording. Source hashes establish which words were inspected; they do not establish what those words authorize.

Operator-approved Plan 12.11 v3, SHA-256 `f8071e83e5bad3236881aca7f5f3dd29adcabe9ba4e2af4da7f5598464a9c643`, establishes D9: automatic user-origin admissions, updates and natural-language withdrawals remain off. Task 4 requires an authority mechanism and explicit disposition of any conflict before dependent implementation.

Claude authored the round-107 gate-1 brief, 2026-11-18, quoting the CP3 task's operator process rules: “No queue, no silent authority change.” and “Claude implements and never writes the plan.” The brief requests a recommendation and proposed records; it is not itself operator acceptance of this product change.

The quoted brief and resulting review must be retained on #490 by the owner under the applicable write authority. Private review-kit paths are archival provenance, never operating or test dependencies.

## Options considered

| Option | Assessment |
|---|---|
| A. Explicit user commands; automatic user extraction remains off | Recommended. Reuses planned host commands and makes the authorized operation and content explicit. Requires user effort and changes the automatic-user-memory requirement. |
| B. One-shot permission for every extracted candidate | Not selected. Can establish authority with exact binding, but interrupts the user, depends on client support and changes the accepted no-review UX. No implementation release follows from this assessment. |
| C. Standing auto-remember consent | Rejected. Earlier approval cannot authorize a later candidate's meaning, content, target or version; it retains the CP2 defect. |
| D. Retain D9 without replacing the product requirement | Safe fallback. Leaves final user-admission scope unresolved and prevents the dependent completion claim. |

## Proposed decision

For user-origin memory, replace automatic admission, automatic updates and automatic natural-language withdrawals with automatic off-metadata capture plus explicit user-authorized commands. Agent-derived lessons remain automatic and optional under the existing Gate.

This deliberately partially supersedes ADR-031's automatic-memory policy and design v4 sections 1 and 4, only for user-origin activation and mutation. It preserves the prohibition on a review queue. It neither defers the replaced requirement to #491 nor claims to have delivered automatic user admission.

### Authority mechanism

1. Commands are recognized before inference/classification, only on the host's bound inbound user-command channel. Model responses, tools, documents, quotations, attachments, notices and stored command text cannot invoke or answer them. This relies on the existing trusted-host/client boundary; it does not protect against a party already holding equivalent host credentials.

2. `/remember <statement>` requests a new memory containing the complete bounded statement supplied by the user. It cannot infer a target, overwrite an existing item or select a semantic subset. Unsupported representation, unresolved conflict or failed checks refuses or remains off with an explicit reason.

3. `/memory edit <id>@<version> <statement>` changes only the addressed item/version. `/forget <id>@<version>` and `/memory forget <id>@<version>` withdraw only that item/version. The host binds project, scope, session/request identity, operation, complete content, target and expected version. A bare mutable ID is insufficient for these mutations. An authenticated structured equivalent must carry the same binding.

4. `/memory switch-on <off-id>@<version>` binds the immutable off record and its host-established origin, source locator, source revision/digest and deterministic extraction identity. The host obtains the exact permitted source again and repeats all checks with zero inference. For user-origin material, the action authorizes a new memory of one complete, unambiguous source statement, preserving its conditions and qualifications. It never executes an inferred update, withdrawal or model-selected target. Ambiguous selection, missing context, unsupported representation, unavailable/altered source or unestablished origin refuses; the user may instead supply `/remember`, `/memory edit` or `/forget`.

5. A scanned title or model-selected span is insufficient to establish that switch-on content is complete. Source selection must be mechanically established from the exact source, without semantic paraphrase or omission of contextual qualifications. Missing RAM-only source remains unavailable; diagnostics are never a replacement.

6. Switch-on or edit never promotes agent-derived or imported material to user-authored trust. A new explicit `/remember` statement is a separate user action with its own source, scans and provenance; it cannot relabel another item's origin.

7. Automatic extraction, compaction and restart/reconnect remain subject to D9 permanently under this decision. No consent setting, bypass flag or stored prior action enables future automatic user mutations.

8. The checked host action still passes the Gate, injection/secret/B1/source-overlap checks, trust/scope validation, current authoritative state, fenced lease, expected-version and durable commit controls. Recheck bindings at commit. Wrong session/project, stale version or moved source refuses without retargeting.

9. Retries reconcile the same action identity and content; they do not authorize another mutation or bind to a newer target. Replayed requests append nothing. A new user action is required for a changed operation, content or target. Durability reconciliation is distinct from authorization.

10. User acceptance is not a saved result. Only the ordinary confirmed durable outcome supports Remembered/Updated/Forgotten notices. Unconfirmed persistence, projection delay, refusal and off outcomes retain distinct truthful states.

11. Every command, including switch-on, uses zero inference. Off records retain only permitted pointer/origin/source/scanned-display metadata, never candidate payload. `/memory` lists them as off with source availability. There is no pending-approval collection, unsolicited prompt, reminder, accept-all operation or turn-blocking wait. Existing durable notice delivery is not an approval queue.

12. Purge retains its separate, version-bound one-shot permission ceremony and deletion contract. This decision does not weaken purge, restore or sync-consent requirements.

## Consequences and limits

Users must explicitly save, activate, edit or withdraw their memories. Ordinary conversation still produces off metadata where eligible, but cannot silently change active user memory. Source loss can make switch-on unavailable; off records do not promise that activation will remain possible.

Automatic extraction still incurs its actual inference/accounting cost. Claims and UI must say “automatic capture with explicit user activation,” rather than imply automatic user admission. Agent lessons remain automatic and optional; memory never grants execution authority.

No new authority database, review service, model write tool, provider credential or inference-based command interpreter is introduced. Reuse the existing host, Gate, store and delivery machinery.

## Verification and adoption

Plan 12.11 v4 contains the command, source-binding, refusal, real-store, real-client and revert checks. D9 remains until those interfaces are approved and verified, and remains on automatic paths afterward.

Before dependent implementation:
- Claude and Codex agree to this complete mechanism.
- The operator explicitly accepts this product change and the complete Plan 12.11 v4.
- The owner records the acceptance and exact source reference on #490 and updates the mutable decision index.

Do not edit ADR-031 or design v4. They remain frozen historical authorities; this record supplies the narrow disposition. ADR-042's topology and durability requirements remain unchanged.

Outstanding matters are operator acceptance, exact-byte plan adoption and implementation/qualification. They are not implicitly accepted by filing this Proposed record.

Acceptance of this decision grants no implementation, service, credential, paid-call, publication, commit or merge authority beyond separately recorded releases.
