# Plan 12.2 shipped empirical admission and default-planner successor

**Status:** Accepted-with-open-items. The policy is accepted for the approved offline implementation, which ships with the Plan 12.2 delivery merge; the ordinary-launch proof for the shipped candidate is tracked in #237. **Date:** 2026-10-18 (Asia/Calcutta). **Deciders:** the operator (the policy, by the direct answer quoted below); drafted by Codex; filed by Claude. Identifier allocated from the decisions index at filing: 023 (the index ended at ADR-022 at candidate `3f38d097612e0d2562c9283e31d1bdeeca1dd5e2`). No frozen predecessor is edited.

**Disposition:** policy accepted for the approved offline implementation; publication and merge are by the separately authorized Plan 12.2 delivery PR, and live execution remains separately gated. Implementation and proof status belong to the dated review and #237, not a retrospective expansion of this decision.

## Direct authority

In Codex chat `01a102cf-53c7-7cb1-b470-0f0f4efcbb0e` (source S9 in the [decisions index](README.md)), the operator instructed:

> Keep coordinating with Claude until you agree on one concise plan to ship usable compaction and declare Plan 12.2 DONE. Bring that plan back for my approval; no implementation or live run yet.

The agreed plan was v3, SHA-256 `06a114f95565e6da10bc2c8833e84e3f81741122852813828cfb583ef99a35db`; Claude's concurrence is #237 comment 6247502930. Codex's concrete approval question was:

> Do you approve the plan's offline implementation scope and policy changes? Live execution, publication/merge, cleanup and sandbox sync remain separately gated.

The operator's direct answer was:

> Approved

The controlling authority is that direct question/answer in this Codex chat. Comment 6249169293 relays it to Claude and binds the plan; it is coordination evidence, not a new human approval. This record preserves the scope of the answer and does not invent a precise human-message timestamp or an exported transcript hash. The decisions index registers that direct-chat provenance as source S9 and lists the relay separately, as coordination evidence. No raw private transcript is a build/runtime dependency.

## Decision and reason

Ship one explicitly qualified empirical admission exception for `anthropic/claude-haiku-5.5`, bound to effective registry hash `06e637845f5f7cea2b4a22d23407c59efc9741d7848b06ee5f4c3d2284f3f07d`. Reuse the accepted assessment-v1.1 summary receipt only within its recorded model/route/prompt/fixture/validator scope. Keep the estimator's `verified: false` value and provider-family limitation visible. Passing calls, window margin, the final Gateway's same-estimator recheck and post-billed checks do not prove a universal pre-call token bound, exact backend variant or region.

Use the first eligible medium model as default planner, otherwise the first eligible easy model. Today Haiku 5.5 is the easy fallback and the summarizer. Its tier is unchanged. This is an explicit successor to the medium-only default requirement, not a claim that a medium model was qualified or that all registry models are usable. Configured ineligible/unregistered planners refuse with migration guidance.

The reason is to deliver usable ordinary compaction with the existing scoped quality evidence while disclosing the unverified admission assumptions. The alternative is to keep ordinary activation blocked until verified estimation/exact-route evidence exists. The operator approved the former policy for implementation. This does not silently inherit the earlier test-only exception or retroactively change its authority.

## Controls and consequences

Host and Gateway independently compose the trusted policy and bind complete requests/output caps. Retain disabled provider fallback, provider/usage/reply checks, receipt-first settlement, finite maintenance/repack limits and launch-scoped permanent route stop. Changed snapshot/model values do not inherit this exception. Genuine personal reapproval is required for changed security inputs; ordinary and named-profile approval identities remain distinct even with equal policy hashes.

Haiku serves answers and summaries on the same experimental route. One refused or unverifiable reply can stop both for that Gateway launch. Diagnosis/manual restart is the documented recovery, with no automatic retry-to-green or authority renewal. Product spending remains alerts-only, without an enforced dollar ceiling. A later live release must explicitly address that residual or require separately verified external control.

This partially supersedes the verified-only admission and medium-only/default/activation portions of the earlier Context Engine/model-registry contracts and relevant ADR-003/004/006 integration claims. It does not supersede the other role assignments, capacity/storage distinctions, unknown-cost semantics, effect/cancellation obligations or frozen provenance. The ordinary shipping contract dated 2026-10-18 specifies implementation details. It does not declare Plan 12.2 DONE; ordinary proof and separately authorized shipment remain required. Plan 12 umbrella deferrals retain their owners.
