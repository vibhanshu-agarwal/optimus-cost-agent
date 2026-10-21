# Plan 12.2 ordinary compaction shipping contract

**Filed candidate, 2026-10-18. The implementation it governs ships to `main` with the Plan 12.2 delivery PR. Its acceptance and the closure gate below are tracked in [#237](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/237).**

- Wording: Codex's architecture text (#237 comment 6250318148; draft SHA-256 `15e96a3e35c6662ad119b899736653852f46829bb4ab814d051bfff18f0631ed`).
- Filing: Claude, on the Plan 12.2 shipping branch, after checking the text against the implementation.
- Scope: a scoped successor to the [Task 1 contracts](2026-10-02-plan-12-2-task1-contracts_v3.md) and the [Context Engine design](2026-10-01-plan-12-2-context-engine-design_v3.md). Their unaffected requirements and the frozen ADRs remain in force.
- Controlling records: the decision record [ADR-023](../../decisions/ADR-023-plan12-shipped-empirical-admission-and-default-planner.md) and the governed [shipping amendment](../../sources/plan-12-2-ordinary-shipping/architecture-amendment.md) for the HLD, LLD, Guardrails, evidence and roadmap views.

## Authority and evidence boundary

The direct human approved the offline implementation scope and policy changes of closure plan v3, SHA-256 `06a114f95565e6da10bc2c8833e84e3f81741122852813828cfb583ef99a35db`. Codex relayed that approval in #237 comment 6249169293, after Claude's exact concurrence 6247502930. It authorizes the integrated offline delivery batch, not live execution or shipment.

This contract rests on Claude's facts sheet for the shipping candidate (v1, SHA-256 `047d56bf667ab9181e26b60bfaeee2ed179af687cd1972b362414c086ef9da99`, at local candidate `6bd09e782cabdd7586c9c616cbae3b785bacab8b`, corrected by its later revision). Codex inspected the relevant composition, approval and failure paths read-only. That candidate was not finally reviewed or live-qualified; the current review, acceptance and live-proof status are tracked in [#237](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/237). The combined return binds the implementation and evidence map to the final HEAD and tree, with every retained failure, in a separate immutable evidence manifest. No provisional test claim becomes final acceptance through this document.

## Ordinary composition and supported path

An ordinary ACP launch is one without a test profile or Stage C flag. It:
- composes the packaged trusted registry;
- binds planning and answer requests;
- attaches the existing Context Engine with Gateway-backed maintenance;
- uses no scenario, fault control, seed or Stage C ledger.

The attachment's no-op ledger callback does not replace the per-turn receipt sink. Every maintenance attempt must reach session settlement, including failures, unknown-cost loss and cancellation. Cancellation publishes no derived checkpoint or answer, and keeps the attempts and costs already incurred.

**Planner selection.**
- The ordinary planner is the first eligible medium model, otherwise the first eligible easy model. Today that is `anthropic/claude-haiku-5.5`, which stays in its easy tier and also serves as summarizer.
- An explicitly configured planner must be an eligible implementer in the trusted registry; otherwise startup refuses with `AGENT_MODEL_INVALID` and migration guidance.
- This grants no other model and reassigns no tier. The assessment-v1.1 summary receipt keeps its exact original quality scope.

**Transport and adopted Gateways.**
- The default newline-delimited JSON transport is the supported ACP transport for this shipping path.
- `--framed` refuses at startup, before any service or provider dispatch, because that transport lacks route binding. It must not silently send unbound requests.
- Ordinary adopted-Gateway and no-auto-start behaviour remains available. An unenforced Gateway refuses with `BINDING_UNSUPPORTED`, and one bound to another registry with `REGISTRY_HASH_MISMATCH`, before provider dispatch, for both answers and summaries.

## Explicit empirical admission exception

The human approved implementing one shipped empirical exception: Haiku 5.5 at the exact effective registry hash `06e637845f5f7cea2b4a22d23407c59efc9741d7848b06ee5f4c3d2284f3f07d`.

**What the exception does and does not establish.**
- The estimator stays `verified: false`. Its estimate (UTF-8 bytes, plus 16 tokens per message and 256 fixed tokens) is an empirical policy, not a demonstrated universal token upper bound.
- Normalization, framing and token expansion remain uncertainties.
- The Anthropic provider-family slug does not establish the exact backend variant or region.
- Equality with the attached profile's hash establishes semantic policy identity. It does not establish YAML byte identity, shared approval authority or ordinary execution proof.

**What it keeps.**
- Complete admission of the actual request and full output; disabled provider fallback; the provider, usage and reply checks; receipt-first accounting; and the permanent experimental route stop.
- A final Gateway check that uses the same estimator is not independent validation, and a check made after billing cannot prove a universal pre-call bound. Successful examples and window margin do not remove these qualifications.
- A changed snapshot or model falls outside this exception: it must meet ordinary eligibility or receive a separately authorized successor.

**Shared route stop.** Answers and summaries share Haiku's route, so a stopped experimental route can block both for the rest of the Gateway launch. Diagnosis and a deliberate manual restart follow; automatic retry-to-green is prohibited. A restart grants no execution or spending authority. Product spending remains alerts-only, without an enforced dollar ceiling.

## Shared numeric and history contract

Ordinary composition and Stage C import one shipped numeric policy:

| Value | Setting |
|---|---|
| Source | 1,048,576 bytes |
| Record reservation | 131,072 bytes |
| Transient | 524,288 bytes |
| Maintenance input | 131,072 tokens |
| Summary output | 8,192 tokens |
| Anchor | 16,384 tokens |
| Compaction tail | 32,768 tokens |
| Hybrid tail | 65,536 tokens |
| Maintenance calls | at most 18 per turn |
| Repacks | 1 |
| History allowance | `min(131072, floor(0.8 * usable))` |
| Initial strategy | `compaction` |

**History rules.**
- Compaction keeps the newest whole turns that fit `min(32768, available)` and summarizes the older covered prefix. It does not wait for the whole history allowance.
- Canonical history and the exact protected outcome, effect and approval facts remain authoritative.
- Summaries remain inert: they cannot grant permission or choose files or skills. They publish only under the existing revision, parameter and cancellation checks.
- With no eligible summarizer the engine is absent; the existing full-history admission and refusal, and the unavailable-maintenance fallback, remain guarded. A fallback does not bypass a stopped route or complete-request admission.

## Approval and migration contract

**Approvals.**
- Host launch approvals and Gateway manifests each bind the trusted registry literal independently.
- Changed security inputs require genuine personal re-approval; signatures are never migrated.
- Named test-profile launches also bind `_test_profile=<name>`, so ordinary and profile approvals cannot authorize each other even when their registry hashes match.
- Old profile and Stage C approvals also require re-approval under the changed security inputs. The original envelope and seal bytes stay unchanged; an unchanged envelope does not preserve approval for a changed launch.

**Wording and probes.**
- Gateway refusal wording describes the refused request's charge. It must not assert a zero total for a whole turn that may already contain charged work.
- Gateway ownership must be identified before shutdown. Never tell the user to stop every listener on a port, or another lane's service.
- The strict configuration preflight is still a real, possibly billed model probe; binding does not make it offline.

## Ordinary proof and closure gates

**Fixture.** The fixture correction in #237 comment 6249598217 replaces the historical 80 KiB notes with two 24 KiB notes/OK turns followed by the factual question. The approved plan and the failed 80 KiB evidence stay unchanged.

**Offline evidence.** Pinned real-acpx/inert-double evidence must show that:
- all three prompts keep one host and one runtime session, without `session/load`;
- the first notes are summarized and excluded from the exact tail, and the second notes stay exact;
- the answer receives the resulting summary view, with no raw first-notes leakage.

Constant fake summary and answer content proves the plumbing only. Factual retention of TANGERINE-47 needs the separately released real check.

**Driver checks.**
- Before the next prompt, the evidence-side driver checks each actual sanitized complete record, including the answer and its rendering. Each must fit the effective exact tail.
- Before prompt 3, the pair must exceed that tail while fitting the maintenance, history and source limits.
- An oversized-answer regression must prove stop-before-next-prompt.
- A violated prerequisite stops the check, keeping attempts, costs and shutdown evidence, with no retry, reseed or exploratory live work.

**Schedule and money.**
- The future schedule stays at most 18 maintenance calls in total plus three answers: 21 logical / 42 physical attempts with the existing safe resends.
- Engineering basis: `3 * 0.196608 + 18 * 0.086647 = 2.149470 USD`. 2.20 USD is a planning allowance. Neither is an enforced ceiling.
- Recompute against the final wrappers and prices before a separate live release. That release must accept the alerts-only residual or require a separately verified external control.
- No Stage C ledger, window or approval is reused.

**Offline completion.** Required:
- exact-candidate full-product checks with independent coverage floors;
- Windows and WSL evidence;
- marked-tier accounting;
- effect and cancellation evidence;
- one Fable 5.1 review and its fixes;
- then the consolidated Codex review.

**Later ordinary live proof.** Needs:
- a fresh exact-candidate release, availability and genuine approvals;
- an announced and acquired named exclusive hold (10-minute target, at most 30 without extension);
- custody, shutdown, a final CLEAR and a seal on every outcome.

A blocked hold announcement fails the gate.

**Closure.**
- Plan 12.2 is not DONE until the ordinary proof and the separately authorized shipment and merge checks are accepted with the requirement/evidence/residual map.
- Legacy live-harness incompatibilities must be named explicitly as unsupported or UNRUN where applicable; they are not green tests or evidence of ordinary use. Keep their owner and next action in the current work register, without filing external follow-ups under this offline authority.
- The umbrella Plan 12 and other deferred mechanisms do not close automatically.
- r9 stays CLOSED / NOT ACCEPTED. The separately accepted 14-case-plus-technical-A6 composite keeps its missing-hold deviation and all original qualifications and seals.
