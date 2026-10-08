# Plan 12.2 offline review and remaining closure proposal

2026-10-04. Codex architect/reviewer; candidate cf9bb9d73ac6c8c3be508966245e0db7cdaaa503.

**Observed offline candidate, 2026-10-04:** cf9bb9d (clean local CP4 branch). V1 capacity text/meter, V3 remaining-allowance preflight, Task 11 product/evaluation separation, named trusted test composition, tracked-source coverage gate and Task 12 boundaries pass offline verification. Windows: 6830 passed, 39 skipped, 111 deselected; WSL: 6641 passed, 228 skipped, 111 deselected; both exits 0. Production ENFORCEMENT_ACTIVE=False, trusted_snapshot() returns None, and the shipped claude-haiku-4.5 default are unchanged. Luna remains ineligible, Qwen remains unqualified, and paid qualification/real editor Task 13 remain UNRUN. See review-disposition.md and evidence-verification.json. This source review is not production activation or full CP4 closure.

## 1. Simplest accepted technical approach

Retain whole-turn compaction/hybrid, exact protected state and readable OPEN refusal. Defer within-turn splitting, adaptive packing, tokenizer-platform expansion, semantic pins and new loop mechanisms. One shared 18-callback allowance and one finite repack are adopted for the released offline tests. A large reply can produce an indivisible unsummarizable turn: prompt-time reservation is not a reply cap. At <=524288 projected source bytes, any unavailable view may use full-history fallback only if its complete request fits; above the floor, refuse. Recovery can use a later explicit sliding choice or new thread; settings/history changes can change fit.

| Setting | Recommendation | Meaning and evidence boundary |
|---|---:|---|
| Absent-engine source | 524288 UTF-8 bytes, inclusive | Preserve existing floor and its 80% storage warning. Not a model token window. |
| Attached canonical source | 1048576 UTF-8 bytes, inclusive | Measured candidate; applies only with explicitly approved attachment. |
| Prompt-time record reservation | 131072 bytes | Admission reservation, not a hard reply/turn cap. A large reply can create an oversized turn. |
| Engine `source_max_bytes` | 1048576 | Matches attached source class. |
| Engine transient serialized input | 524288 bytes | Includes maintenance header, separators and prior summary; not a whole-process memory budget. |
| Cheap/ultra-cheap history allowance | `min(131072, floor(0.8 * usable_input))` tokens | Further reduced by complete-request packing after exact protected state. A history ceiling, not a delayed summary trigger. |
| ViewLimits.maintenance_input_tokens | 131072 estimated tokens | Engine-assembled text only: ordinary turns, separators and prior-summary header. The host adds summary-prompt framing (989 bytes at this baseline) and wire/framing overhead; the complete request plus output must separately fit the enabled Gateway guard. |
| Summary output and maintenance reserve | 8192 tokens | Use effective cap `S = min(parameter cap, verified maintenance cap)`; reserve output once. |
| Summary maximum UTF-8 bytes | `floor(S / r)` | Exact arithmetic for a supported verified byte-ratio profile. Required integer >=1 and < transient bound; invalid relationships refuse configuration. |
| Cold maintenance calls | At most 18 | Shared per-turn allowance, including any repack. Fixture measurements were 1–14; conditional fixture bounds 17/9/5/9 at ratios 1/0.5/0.25/0.2. No universal summarizability or latency promise. |
| Compaction exact tail | 32768 tokens | Whole turns; ordinary tail plus summary <=40960 before protected facts. |
| Hybrid first-turn anchor / tail | 16384 / 65536 tokens | Whole turns, deduplicated overlap; ordinary head/tail/summary <=90112 before protected facts. |
| Implementer output reserve | 32768 tokens | Must fit actual route output maximum and verified upstream/reasoning semantics. |
| Effective request ceiling | `min(262144, verified route window)` | Final complete-input estimate + enforced output reserve <= ceiling; equality allowed. |
| `max_repacks` | 1 after initial packing | New architect recommendation. Same captured history and shared 18-call allowance; test finite exhaustion before release. |

Keep StrategyParameters and its checkpoint digest unchanged across the turn. Pass ViewLimits.maintenance_calls_remaining = max(0, 18 - callbacks_already_consumed) for initial preparation and each repack; this execution-state field is outside summary identity. The engine preflights the complete chunk plan against min(parameters.max_maintenance_calls, remaining) before any callback. Zero remaining permits a valid zero-call reused/sliding view and refuses a plan needing calls. Reuse still requires matching source, coverage, estimator and token/byte bounds. Retain the host defensive counter and allowance classification; repack checkpoints remain unpublished.

## 2. Verified offline completion

V1 capacity outcomes/request meter, V3 preflight/reuse, Task 11 optional evaluation cap with no product dollar stop or remaining-dollar prompt, tracked-source coverage enforcement, source-owned trusted test composition, finite-repack and actual HostMaintenance-wrapped Gateway boundary tests pass. Final Windows and WSL gates are recorded against the exact clean candidate. Limits and wheel evidence were produced at cc6959b; cf9bb9d changes only tools/tests, with no src/pyproject/lock delta. They are carried source-scope evidence, not a claim the wheel was built at cf9bb9d.

Until the profiles lane lands, the hook entry is unchanged and keeps pyproject fail_under=80 (an Optimus-only interim floor). Only CI switches to --run-full-suite. The profiles lane later moves the hook to commit with no coverage gate.

Use coverage.py/pytest-cov precision 0 comparison; print measured and compared values. The final measured required rows exceed 80% unrounded on both systems. The aggregate and Evidence Handoff rows remain informational. Existing failed/no-op/stopped runs remain non-passing.

## 3. D7 capacity disclosure and provenance

Retain inclusive 524288-byte absent-engine storage/admission and its separately labelled 80% storage notice. Once enforcement is active, complete-request overflow refuses with OPEN disposition and zero upstream attempts for the rejected request. Request usage and its once-per-session 80% warning refer to complete request capacity, not storage; a local Gateway dispatch reading does not prove provider delivery. Only INPUT_EXCEEDS_CAPACITY gets capacity text; unknown CAPACITY_REFUSED stays generic. Earlier planning/maintenance can still incur cost.

At r=1, 262144 - 32768 = 229376 usable input; maximum planning material at cf9bb9d is 43795 bytes, leaving at most 185581 history/prompt bytes before other overhead (35.40% of storage). Earlier 43819/185557/35.39% readings stay historical. This is not a universal cutoff. The sealed return reports human acceptance in the offline release; recording the exact D7 words under ADR-011 still needs the saved session export. The architect does not invent that quotation.

## 4. Remaining route and paid/live prerequisites

The public inspection returned incomplete estimator evidence. Luna stays ineligible; Qwen stays unqualified and has no qualifying existing active coding role. The pinned qualification candidate is openai/gpt-6-luna on openai/fast, reasoning none, literal quantization unknown. Synthetic r=1 proofs do not establish this real route. No package install, tokenizer execution or speculative eligibility promotion is included. Preserve the original free-inspection bounds: 40 public GETs including redirects, four candidate configs, 64 MiB/asset, 256 MiB total, 30 minutes network plus 30 minutes JSON inspection. These limits are historical release boundaries, not a fresh authorization or instructions to retry rejected origins.

Paid proposal stays held: one Luna candidate, two logical fixture requests, at most four physical attempts, US$0.05, 30 minutes, complete input <=8192 verified tokens and output <=1200 tokens. No alternative route/model or rerun-until-pass. A passing receipt establishes only its fixture/route/format/validator key, not 8192-token production summary quality. New attached-profile inputs/hash require review and matching trusted approval. Missing tokenizer/route proof blocks dependent calls even if a spending ceiling is later approved.

Task 13 stays held: US$0.50, at most 24 physical upstream attempts, one attended 60-minute session, real acpx/Optimus/Gateway/TimeSeries Redis/Zed in the named synthetic workspace. Combined proposal is US$0.55/28 attempts. Use separate absent-engine/small sessions and one reused seeded attached session, restoring compaction before maintenance/fault/cancellation cases. Label synthetic seeding and simulated faults honestly. Operator remains at Zed for prompts/mode changes/exact scratch-artifact approvals. Back up settings bytes/hash, edit only the named agent_servers command to the approved profile, and restore/verify on every exit while preserving unrelated concurrent edits. No paid/live execution is authorized by this document.

## 5. Documentation closure and full CP4 verdict

Codex supplies these corrected complete sources, four rebuilt PDFs and updated migration map. Claude files and verifies under the existing offline local-filing release, preserving frozen predecessors and correcting roadmap/backlog/plan acceptance references and the cancellation diagnostic note. Allocate decision IDs from the then-current index; placeholders do not reserve ADR-018. Insert the actual saved D7 decision at filing; do not call a placeholder a recorded approval.

This packet removes the source/PDF ownership ambiguity. It is a complete reviewed local filing candidate, not an accepted/publication or activation assertion. Documentation filing does not itself clear CP4: route/estimator proof, genuine summary qualification and real-editor Task 13 remain required passing claims or need a separately recorded operator disposition. Push, PR, merge, production activation, shipped Haiku-default removal and sandbox synchronization remain held. No new code batch or full-suite rerun is requested for these documentation corrections.
