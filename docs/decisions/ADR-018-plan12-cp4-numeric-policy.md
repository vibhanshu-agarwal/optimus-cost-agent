# ADR-018 — Plan 12 CP4 measured policy and whole-turn availability

**Status:** Filing candidate; verbatim operator acceptance record pending. **Date:** 2026-10-04. ID allocated at local filing (see Record allocation below). Codex drafts; Claude reviews; offline implementation release is reported in the sealed return; the verbatim D7 operator record and governed filing remain pending.

## Context

ADR-003 left numeric history/output policy for measurement. ADR-014 preserves the absent-engine source floor and all-session final request guard. CP4 C1/C2 corrections are accepted offline at `dea4624b118e99f989a4ab6d1482f281603d71d9`; measurements used synthetic ratio profiles and do not prove real route safety. A prompt-time record reservation does not limit the reply, so a later ordinary turn may be too large for whole-turn summarization.

The operator directed a simple acceptable approach with further optimization later. This record proposes numeric completion within Plan 12.2; it neither replaces frozen ADR-003/014 nor selects the future percentage-trigger optimization.

## Proposed decision

Use the numeric table in Task 1 contracts complete v3 draft §9: absent source 524288 bytes; attached source 1048576; prompt-time record reservation 131072; transient serialized input 524288; history ceiling min(131072, 80% usable input), protected state first; engine maintenance text 131072 estimated tokens (host summary/wire framing extra); effective summary output 8192 and byte bound floor(S/r); compaction tail 32768; hybrid anchor/tail 16384/65536; implementer output reservation 32768; effective total request ceiling min(262144, verified route window); shared maintenance allowance 18; one finite repack after initial packing.

Only supported conservative profiles may supply r; invalid relationships refuse configuration. Token/byte equality is admitted. Complete input/output/framing and actual upstream cap semantics are checked on each provider attempt. Synthetic bounds and sampled tokenizer ratios cannot enable a route.

Retain whole-turn packing. Accept its disclosed availability limitation: some admitted histories/replies cannot be compacted under current estimator/bounds. Refuse before callback when preflight cannot pack an indivisible required turn or exceeds the call allowance. Recovery is a later explicit sliding selection or a new thread; sliding may omit all ordinary history. Never silently split, switch or discard inside compaction/hybrid. Protected host state remains exact.

## Consequences and evidence

Measurements support bounded fixtures, not a guarantee that every admitted source rebuild fits 18 calls or a latency guarantee. Boundary assertions must use accepted values after direct release. The named D7 exception is proposed because universal r=1 cannot admit the full floor plus material/output; conservative route-specific estimator/framing proof remains missing. Retain 524288-byte source and warning; overflow stays OPEN and dispatches no answer/plan. Exact tokenizer dependencies are deferred. No production attachment, route enabling, paid calls or publication follows from this record's draft status. Within-turn splitting and packing/call-frequency optimization remain deferred with existing Plan 12 ownership.

## Acceptance provenance

Claude records the 2026-10-04 human offline release as accepting the numeric set and D7 disclosure. This architect review does not supply the missing saved transcript or invent the operator’s exact words. On acceptance, file the operator's exact disposition, reviewed package identity and any narrower scope in this record. Preserve predecessor records and sealed measurements unchanged; update only current index links and the authoritative tracking venue according to actual Plan 11.29 cutover under separate filing authority.


Record allocation: ADR-018 was allocated at local filing on 2026-10-05 from the then-current index, whose last record is ADR-017 on `main` `a929aab`; no branch or worktree holds ADR-018 or later. The concurred curated-tier draft (2026-10-02) is unfiled and reserves no number; it takes the next free number at its own filing. If it reaches `main` first, this unpublished record is renumbered before its first merge.



## D7 decision to record

Retain inclusive 524288-byte absent-engine canonical storage/admission and its separate storage warning. Full stored history need not fit a provider request. Once enforcement is active, an over-capacity complete request refuses readably with OPEN disposition; no rejected answer/planning request goes upstream. Apply the same final guard to absent-engine and attached full-history fallback. A smaller prompt or setup can change fit; history that cannot fit by itself cannot be repaired by shortening only the next prompt.

At cf9bb9d, r=1 Agent usable input is 229376; maximum planning material is 43795 bytes, leaving at most 185581 history/prompt bytes before additional overhead (35.40% of storage). Earlier dea4624 measurements remain historical.

**Operator decision:** PENDING saved session export under ADR-011. Insert the exact operator words, date, transcript reference and reviewed package identity during authorized filing. Do not treat this placeholder as an approval quotation.

Keep StrategyParameters and its checkpoint digest unchanged across the turn. Pass ViewLimits.maintenance_calls_remaining = max(0, 18 - callbacks_already_consumed) for initial preparation and each repack; this execution-state field is outside summary identity. The engine preflights the complete chunk plan against min(parameters.max_maintenance_calls, remaining) before any callback. Zero remaining permits a valid zero-call reused/sliding view and refuses a plan needing calls. Reuse still requires matching source, coverage, estimator and token/byte bounds. Retain the host defensive counter and allowance classification; repack checkpoints remain unpublished.

**Observed offline candidate, 2026-10-04:** cf9bb9d (clean local CP4 branch). V1 capacity text/meter, V3 remaining-allowance preflight, Task 11 product/evaluation separation, named trusted test composition, tracked-source coverage gate and Task 12 boundaries pass offline verification. Windows: 6830 passed, 39 skipped, 111 deselected; WSL: 6641 passed, 228 skipped, 111 deselected; both exits 0. Production ENFORCEMENT_ACTIVE=False, trusted_snapshot() returns None, and the shipped claude-haiku-4.5 default are unchanged. Luna remains ineligible, Qwen remains unqualified, and paid qualification/real editor Task 13 remain UNRUN. See review-disposition.md and evidence-verification.json. This source review is not production activation or full CP4 closure.
