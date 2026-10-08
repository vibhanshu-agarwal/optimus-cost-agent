# ADR-018 — Plan 12 CP4 measured policy and whole-turn availability

**Status:** Accepted-with-open-items. **Decision date:** 2026-10-04. **Verbatim provenance filed:** 2026-10-07 (ADR-011 source S4). **Decider:** Operator; wording drafted by Codex. ID allocated at local filing (see Record allocation below). The numeric policy, one finite repack and disclosed whole-turn/D7 limitation are accepted for the released offline scope. Remaining route qualification, genuine summary-quality evidence and real-editor Task 13 remain open; production activation and publication are separately held.

## Context

ADR-003 left numeric history/output policy for measurement. ADR-014 preserves the absent-engine source floor and all-session final request guard. CP4 C1/C2 corrections are accepted offline at `dea4624b118e99f989a4ab6d1482f281603d71d9`; measurements used synthetic ratio profiles and do not prove real route safety. A prompt-time record reservation does not limit the reply, so a later ordinary turn may be too large for whole-turn summarization.

The operator directed a simple acceptable approach with further optimization later. This record records accepted numeric completion within Plan 12.2; it neither replaces frozen ADR-003/014 nor selects the future percentage-trigger optimization.

## Accepted decision

Use the numeric table in Task 1 contracts complete v3 draft §9: absent source 524288 bytes; attached source 1048576; prompt-time record reservation 131072; transient serialized input 524288; history ceiling min(131072, 80% usable input), protected state first; engine maintenance text 131072 estimated tokens (host summary/wire framing extra); effective summary output 8192 and byte bound floor(S/r); compaction tail 32768; hybrid anchor/tail 16384/65536; implementer output reservation 32768; effective total request ceiling min(262144, verified route window); shared maintenance allowance 18; one finite repack after initial packing.

Only supported conservative profiles may supply r; invalid relationships refuse configuration. Token/byte equality is admitted. Complete input/output/framing and actual upstream cap semantics are checked on each provider attempt. Synthetic bounds and sampled tokenizer ratios cannot enable a route.

Retain whole-turn packing. Accept its disclosed availability limitation: some admitted histories/replies cannot be compacted under current estimator/bounds. Refuse before callback when preflight cannot pack an indivisible required turn or exceeds the call allowance. Recovery is a later explicit sliding selection or a new thread; sliding may omit all ordinary history. Never silently split, switch or discard inside compaction/hybrid. Protected host state remains exact.

## Consequences and evidence

Measurements support bounded fixtures, not a guarantee that every admitted source rebuild fits 18 calls or a latency guarantee. Boundary assertions must use accepted values after direct release. The named D7 exception is accepted because universal r=1 cannot admit the full floor plus material/output; conservative route-specific estimator/framing proof remains missing. Retain 524288-byte source and warning; overflow stays OPEN and dispatches no answer/plan. Exact tokenizer dependencies are deferred. Acceptance of this numeric decision grants no production attachment, route enabling, paid calls or publication. Within-turn splitting and packing/call-frequency optimization remain deferred with existing Plan 12 ownership.

## Acceptance provenance

Source S4 records the operator’s 2026-10-04 acceptance of the numeric set, one finite repack and disclosed whole-turn/D7 limitation. Codex independently verified the archived human message against the sealed proposed release and the verbatim quotation below on 2026-10-07. Preserve predecessor records and sealed measurements unchanged; acceptance of this decision does not close full CP4 or authorize paid/live work, activation or publication.

Filed 2026-10-07: the operator's exact words, the reviewed package identity and the transcript source are recorded under **Operator decision** below.


Record allocation: ADR-018 was allocated at local filing on 2026-10-05 from the then-current index, whose last record is ADR-017 on `main` `a929aab`; no branch or worktree holds ADR-018 or later. The concurred curated-tier draft (2026-10-02) is unfiled and reserves no number; it takes the next free number at its own filing. If it reaches `main` first, this unpublished record is renumbered before its first merge.



## Recorded D7 decision

Retain inclusive 524288-byte absent-engine canonical storage/admission and its separate storage warning. Full stored history need not fit a provider request. Once enforcement is active, an over-capacity complete request refuses readably with OPEN disposition; no rejected answer/planning request goes upstream. Apply the same final guard to absent-engine and attached full-history fallback. A smaller prompt or setup can change fit; history that cannot fit by itself cannot be repaired by shortening only the next prompt.

At cf9bb9d, r=1 Agent usable input is 229376; maximum planning material is 43795 bytes, leaving at most 185581 history/prompt bytes before additional overhead (35.40% of storage). Earlier dea4624 measurements remain historical.

**Operator decision (verbatim, ADR-011 source S4).** The operator sent this message on 2026-10-04 at 16:56:55 IST (`2026-10-04T11:26:55.284Z`). It is record `b34978ea-d159-41c0-bee3-ad74a26a5bb2`, line 57140 of the S4 transcript.

- **Who wrote the words.** Codex drafted them as proposed release text: the "Offline and free release" block of `plan12-closure-release-supplement/release-text.md`, SHA-256 `404354cf4bc576a3a60f94e1455a6a2b18238b997d08de5ef0202921e0ec1844`.
- **Who decided.** The operator sent that block unchanged as their own release.

Its first two paragraphs are the acceptance this record files. The message's own quote markers are shown here as a block quote.

> Claude, I accept Codex's Plan 12.2 closure V2 package as corrected by the Plan 12 closure release supplement dated 2026-10-04, the recommended numeric set, one finite repack and the disclosed whole-turn availability limitation. Where they differ, the supplement controls.
>
> I accept the named D7 request-capacity exception under ADR-014: inclusive 524288-byte absent-engine storage/admission remains, but it does not guarantee all stored history fits a model request. With r=1 and the measured maximum Agent planning material, history/prompt capacity is at most 185557 bytes before further overhead, 35.39% of that storage allowance. This is an envelope-specific upper bound; accumulated history can prevent further requests until a new thread or an available smaller engine view is used. Exact counting is deferred and would not guarantee universal full-floor fit. Implement the capacity-specific absent-engine refusals and request-capacity meter/80% warning; preserve a separately labelled 80% storage notice. Keep production enforcement inactive.

- **The rest of the message.** It authorizes bounded local offline completion and the free inspection, and keeps paid, live, activation and publication work held. This record does not restate it.
- **Reviewed package identity.**
  - The V2 package is Codex's `plan12-closure-draft-v2`: 111 payloads sealed by a `SHA256SUMS.txt` whose own SHA-256 is `3fbe8c57223b215ba2b07fe27fa534d4b561d2ae31aa07b334eaf6187e8291d8`.
  - The supplement is `plan12-closure-release-supplement`: 6 payloads sealed by a `SHA256SUMS.txt` whose own SHA-256 is `0fc6844f8c4c1642a5673844bc8ab26c1b61331d22577cd65478d019af3c2e80`. Its review disposition has SHA-256 `7e3487d88fdaae584dfee1e283e20eccaaf185decb1d0edea4b1b96cbb39ba3e`.
  - Both packages verified against their seals on 2026-10-07.
- **Two measurements.** The quoted 185557 bytes (35.39%) is the dea4624 measurement in force at the decision. The 185581 bytes (35.40%) at cf9bb9d, above, is the later re-measurement. Neither replaces the other.

Keep StrategyParameters and its checkpoint digest unchanged across the turn. Pass ViewLimits.maintenance_calls_remaining = max(0, 18 - callbacks_already_consumed) for initial preparation and each repack; this execution-state field is outside summary identity. The engine preflights the complete chunk plan against min(parameters.max_maintenance_calls, remaining) before any callback. Zero remaining permits a valid zero-call reused/sliding view and refuses a plan needing calls. Reuse still requires matching source, coverage, estimator and token/byte bounds. Retain the host defensive counter and allowance classification; repack checkpoints remain unpublished.

**Observed offline candidate, 2026-10-04:** cf9bb9d (clean local CP4 branch). V1 capacity text/meter, V3 remaining-allowance preflight, Task 11 product/evaluation separation, named trusted test composition, tracked-source coverage gate and Task 12 boundaries pass offline verification. Windows: 6830 passed, 39 skipped, 111 deselected; WSL: 6641 passed, 228 skipped, 111 deselected; both exits 0. Production ENFORCEMENT_ACTIVE=False, trusted_snapshot() returns None, and the shipped claude-haiku-4.5 default are unchanged. Luna remains ineligible, Qwen remains unqualified, and paid qualification/real editor Task 13 remain UNRUN. See review-disposition.md and evidence-verification.json. This source review is not production activation or full CP4 closure.
