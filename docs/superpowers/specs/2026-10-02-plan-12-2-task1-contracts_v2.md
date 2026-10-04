# Plan 12.2 Task 1 contracts

**Version 2, 2026-10-04.** A complete successor of the accepted first edition, which is archived unchanged. It incorporates only the CP4 corrections C1–C3 from Codex's final corrections note `2026-10-04-plan12-final-corrections-and-release-draft.md`, released by the operator on 2026-10-04 for offline implementation, in sections 2, 3 and 5. The accepted contracts are otherwise unchanged.

2026-10-02, Asia/Calcutta. Codex architects; Claude implements. **Accepted by the operator on
2026-10-02** ("Accept (Recommended)"), together with the complete v2 implementation plan. The
mechanisms below are architect proposals the operator accepted; the text keeps that provenance.
Numeric, paid and governed-document activation gates stay as stated. It refines the filed
revision-5 design rather than reopening accepted model roles, the floor, three strategies or the
alerts-only requirement.

The operator selected Package A PR then CP1. Package A publication and this contract review can
proceed independently. Accepting this contract and the complete implementation-plan successor
permits the agreed offline scope to proceed through CP1–CP3 without per-task reviews; CP4's paid,
service and real-client actions retain their own authority. No new review checkpoint is added for
each task, interface or local commit. This single acceptance decision is required before CP1.

## 1. Boundaries and responsibilities

| Owner / files | Contract |
|---|---|
| `src/context_engine/contracts.py` | Frozen neutral scalar/tuple records and synchronous injected callback; forbidden host/Gateway/security/evidence imports |
| `context_engine/selection.py`, `summary.py`, `checkpoints.py`, `engine.py` | Complete-turn partition, bounded inert summaries, revision proof and pure strategy orchestration |
| `src/optimus_model_policy/{registry,validation,capacity}.py`, `defaults.yaml` | Neutral typed YAML snapshot, structural roles, route evidence and exact capacity predicate |
| `src/optimus_gateway/model_policy.py` and current provider request adapters | Trusted approved snapshot; final packed request/route/output checks; actual attempt identities/finish statuses |
| `src/optimus/context/{adapter,assembly,maintenance}.py` | Canonical snapshots, exact selection, sanitizer, host notices/cancellation and injected model calls |
| `src/optimus/acp/session_config.py` | One full-set snapshot; setters/capture/resync under one session lock |
| `src/optimus/usage/{turn_settlement,cost_alerts}.py` | Exactly-once projection over the existing usage ledger; no second spend authority |

Use the filed plan's existing integration files; no generic plugin framework, persistence or service
split. CP1 owns transport/policy, CP2 engine tooling, CP3 host integration/accounting. Interfaces may
be refined internally by Claude while preserving these externally visible invariants. Material
policy or owner/scope changes return to the operator at the existing checkpoint, not an extra review.

## 2. Neutral engine data and view contract

Keep the filed API names/signatures. Types are immutable; validation happens before engine work.

| Type | Required fields / rules |
|---|---|
| `HistoryRevision` | Opaque `session_key`, committed `generation`, `last_committed_seq`, sanitized canonical `digest`; sequence strictly increasing |
| `OrdinaryTurn` | `seq`, `user_prompt`, `plan_text`, `completion_text`; only complete committed ordinary turns |
| `ProtectedTurnState` | `seq`, exact `outcome`, exact `effect_state`, tuple of host-issued approval facts; exactly one per committed turn |
| `HistorySnapshot` | Revision plus tuples of ordinary turns/protected state with equal complete ID sets; no provisional current prompt |
| `StrategyParameters` | Anchor/tail allocations, summary output bound, finite maintenance-call count, prompt/format version and digest |
| `ViewLimits` | Finite history/source/transient/maintenance bounds; required `summary_max_bytes` (at least 1, strictly below `transient_max_bytes`, derived as `floor(S / r)` from the verified byte-ratio profile, C2); host `estimate_history(text) -> int` with verified estimator ID, subadditive over complete strings supplied to the engine |
| `MaintenanceRequest` | Complete sanitized `input_text`, host-computed covered IDs, max output, prompt/format version; model cannot supply trusted coverage metadata |
| `MaintenanceResult` | Bounded optional summary text, attempt IDs, status and true finish/truncation status; monetary receipts remain host-owned |
| `SummaryCheckpoint` | Current revision and digest, covered turn IDs plus per-turn source digests, strategy/parameter/format identity, sanitized inert summary |
| `PreparedView` | Exact head/tail IDs, candidate checkpoint, all protected facts, covered/omitted manifest, availability/reason; partitions cannot overlap |

`ContextEngine.prepare_view(snapshot, *, strategy, parameters, limits, checkpoint, maintenance,
cancelled) -> PreparedView`; `MaintenanceCallback.__call__(MaintenanceRequest) -> MaintenanceResult`
is synchronous and invoked off the ACP event loop. Cancellation is host supplied. Engine writes no
workspace, store, ledger or ACP UI. Malformed snapshot/unknown IDs are validation failures; healthy
but unfit/failed maintenance returns an unavailable view with a typed reason. A callback status
`unavailable` or `unsupported` is the reason `maintenance unavailable`, not a failure (C1). Pack
complete turns against both the token and the UTF-8 byte limit of a maintenance input, reserving a
later rolling summary at `summary_max_bytes` and the effective token cap; enforce both bounds on
fresh and reused summaries; preflight the whole plan and call allowance; check each assembled input
again before its callback (C2, design spec v2 section 6.2).

Choose **append-only prefix validation** for checkpoint reuse: verify every covered source digest,
identical strategy/parameter/format identity and the covered prefix relationship, then re-key the
candidate to the captured current revision. Never reuse by session ID alone. Publication is an
atomic compare against current revision and parameter digest, via the filed
`publish_checkpoint(candidate, *, current_revision, current_parameters_digest, cancelled) -> bool`.
If cancelled/stale, discard the derived candidate; settle all actual attempts regardless.

Allocate current prompt/instructions/exact facts/required evidence/output first. Every protected
record remains exact, including omitted ordinary turns. If required facts cannot fit, recoverably
refuse. No model text is parsed into permission, exact host state, file/skill hints or executable plan.

## 3. Strategy and summary-format decisions proposed for acceptance

Compaction remains default. Hybrid pins only the first complete turn if its ordinary content fits
the anchor allocation and retains a larger exact tail; deduplicate head/tail. Sliding keeps the
newest consecutive complete turns that fit, makes zero maintenance calls and cannot skip an
oversized newest turn to retain unrelated older ones. Canonical history is never replaced/evicted.
D1/D2 numeric targets, source/transient bounds and concurrency policies remain CP4 measurements;
the per-tier history value is a ceiling on the history allocation, not the point at which compaction
begins: compaction summarizes history outside its exact-tail allocation (C3);
offline tests inject explicit finite fixture policies and never promote them to deployment defaults.

Choose **host-wrapped bounded plain text** for summary format `context-summary-v1`, avoiding an
unnecessary provider-native JSON capability requirement. Host owns ordered sections for task
context, constraints/changes, decisions, work/evidence, unresolved matters and source chronology.
Section bodies are untrusted text. Host wrapper carries coverage/version/digests, not model output.
Empty, malformed or truncated result is unavailable; sanitize before rendering and enforce byte/token
bounds after sanitization. Do not execute directives printed inside any ordinary/summary block.

Accept the filed `calculator-constraints-v1` fixture: Decimal/public calculate API, no eval/network,
negative inputs, initial HALF_UP superseded by late HALF_EVEN with 2.345 -> 2.34 and 2.355 -> 2.36.
Both the early constraints and correction must lie inside summarized ranges, not hidden in exact
head/tail. Include denied approval and hostile ordinary/tool text; host protected state stays exact.
Require every fact, supersession and no invented effect/approval. Also require the two-step incremental
variant, including correction of an already summarized constraint. Mutation/negative controls must
demonstrate omitted fact, stale correction, invented approval and truncation are rejected.

Qualification receipts bind exact model ID, endpoint, reasoning/route settings, formatter/validator,
fixture/prompt/source digests, request IDs and result date. No receipt means not eligible for the
summarizer role. Changing a qualification key invalidates eligibility. CP2 builds tooling with fakes;
CP4 performs any separately authorized paid qualification. No general coding/equivalence test is added.
Paid envelope remains at most two initial fixture requests per candidate, with measured input/output,
dollar and total provider-attempt ceilings presented before calls; no rerun-until-pass.

## 4. Registry, trust and final request transport (CP1)

Retain YAML. Use a custom SafeLoader that rejects all anchors/aliases/merge keys, duplicate keys at
every depth, non-string keys and custom/unsafe tags; quoted scalar characters do not count as syntax.
Reject unknown typed fields, duplicate/ambiguous IDs and non-finite/negative numbers. Typed override
maps combine by declared key; lists replace. Hash canonical validated effective data; retain input-byte
hashes separately. Do not merge untrusted YAML into approval objects or embed executable config.

Registry fields include schema/policy version; effective ceiling; per-role output reserves; measured
strategy/source/temporary bounds; model identity/origin/tier/explicit role assignments; approved endpoint
and quantization allow-sets; capability/reasoning/output mappings; route-estimator evidence; prices and
data-use facts; summary receipt references; alerts settings. All optional constraints default inactive
unless accepted: no new ADR-010 country/provider restriction.

Retain the exact ADR-004 role lists. Tier membership/disabled origin inventory grants no role.
Implementer assignments conservatively require documented native tool support plus compatibility
with Optimus's text planning grammar; those are distinct checks. Summarizers need bounded text and
qualified format, not native JSON schema. Reviewer role capability is dormant until its future artifact
contract is accepted. Classifier is dormant under proposed ADR-007. No Auto behavior is silently created.

Use eligible-role price dominance ordering; crossed prices require an explicitly accepted blend,
never a hidden task score. Free Task 4 checks verify actual IDs/endpoints/prices/capabilities; this
contract is not a claim those public facts have been refreshed. Contradictions are reported, not
silently substituted. Keep unverified routes unavailable and test transport offline with named fixtures.

Trusted launch composition supplies the effective snapshot to host and Gateway. A caller-supplied
hash is not authority. Draft a versioned Plan 9.96 approval successor storing a bounded schema/version
and effective hash, not the entire registry; keyring/trusted composition provides the validated object.
Unknown hashes/aliases/routes or no trusted snapshot means zero upstream calls. No arbitrary model
pass-through. Preserve launch scope/workspace binding and frozen predecessor approval bytes.

Provider enforcement uses an explicit endpoint allow-set and required parameters, not preference-only
ordering. Every provider attempt has its own capacity check and receipt identity. Proposal: **one
primary attempt plus at most one recovery attempt per host model request**, from explicit approved
same-role alternatives, only after a known eligible transport/provider failure and explicit request
fallback permission. Fixed-model selection has fallback permission false by default. No struggle
escalation, cross-role model substitution, opaque unrestricted provider retry or unknown-cost recovery.
The number 2 is an architect-proposed finite retry bound, not an earlier operator requirement.

Contributor disclosure precedes every new Contributor payload/route, including maintenance/fallback.
Use the exact filed warning. Bind disclosure authorization to payload digest and approved route;
identical bounded transport retry can reuse disclosure, but each attempt is billed separately.
No per-turn grouping or new consent dialog. Standard-only max reasoning is excluded on Contributor.

Capacity contract, recomputed by the Gateway after final packing:

`effective_total = min(262144, verified_route_window)`;
`usable_input = effective_total - output_reserve`;
`complete_input_estimate <= usable_input` (equality admitted);
`0 < output_reserve <= verified_route_max_output`.

Count output reserve once, enforce it through the verified upstream parameter and include reasoning
semantics. Count messages/templates/files/tools/framing in final input, not caller-supplied token data.
Use a validated route tokenizer/estimator and smallest allowed endpoint capacities. No invented 128K
fallback or bytes/4 safety estimate. Preserve the 524288-byte source floor independently.
Every enabled absent-engine route must admit representative full-floor English/code histories plus
its permitted evidence/framing/output reserve, and separately pass adversarial Unicode safety tests.
Unresolved route/floor conflict returns to the operator before release, not an undercounting workaround.

Propagate true provider finish status. A WRITE-bearing answer is usable only when the verified route
reports a complete successful finish; length-limit/missing/unknown status fails before parse/store/
approval/execution, even if its prefix parses. Chat incomplete output is visibly incomplete. Preserve
all usage receipts. Final numeric reserves/estimators require CP4 evidence; fixture values do not activate.

## 5. Host integration and ACP (CP3)

Capture revision, mode/strategy/parameters, registry/model/route and request identity before any
interleaving await. Setters affect later turns; never hold the config lock across calls/permissions.
Use current prompt, exact selection text and history envelope separately. Summary text never selects
files/skills. Bind stored plan and admitted context digest; application reuses the admitted request,
not a newly summarized view. Absent-engine behavior preserves the Package A floor baseline.

Attached storage class persists through an engine fault. Pure projected-floor fallback includes
canonical history plus provisional current prompt: <=524288 uses full history with a strategy-not-applied
notice; >524288 refuses recoverably with zero answer/planning dispatch and keeps the thread OPEN.
Repeated faults never latch CAP_CLOSED. Required authority overflow is a recoverable capacity refusal.
Each such refusal uses the filed reason-specific message and common ending, the fallback notice and
the planning/Chat capacity texts use their filed wording (C1, design spec v2 section 10).

Full-set `configOptions` publication uses option id/context setter configId as the pinned schema
requires. Strategy picker only when configured attached; a health fault does not remove it. Preserve
mode/model options on every update. One revision/resync state prevents old flush clearing new pending
state. Sliding description and first-admitted-turn notice use filed exact text and actual delivery.
Meter uses largest actually dispatched planning/answer input with that request's usable capacity;
ties choose smaller capacity. Summaries affect costs, not ring; no fabricated reading on no-dispatch refusal.

## 6. D6 proposed disposition: unknown cost, alerts and cost-stop removal

Accept **non-latching incomplete accounting with no automatic unknown-cost retry**. Keep strict
Gateway usage validation: missing/invalid cost does not become a valid zero-cost ProviderUsage.
Record the attempt as unknown, preserve any known subtotal before and after it, warn that totals
are incomplete, and retain the model/route/request correlation. A failed maintenance result is
unavailable; an unverified final result is not promoted to a complete successful candidate.
Unknown accounting never silently imposes a session-wide paid-maintenance suspension. A later
intentional request may proceed under normal approved capacity/authorization/finite attempt rules.
Do not redispatch an uncertain attempt just to obtain a known cost. No dollars cap is renamed.

`StageReceipt` includes session/turn/stage/attempt and optional Gateway request IDs; requested/resolved
model/provider; revision/strategy/registry; Decimal reported cost or explicit unknown; token/cache
metadata and timestamp. `TurnCostSummary` has known subtotal, unknown attempt IDs, receipt IDs and
completeness. `CostScopeSummary` adds scope/day/timezone and reconciliation state. `AlertPolicy`
defines scope/thresholds; `CostNotice` is keyed by scope/threshold crossing identity.
`record_attempt(receipt) -> None`, `settle_turn(turn_id) -> TurnCostSummary`, and
`evaluate_alerts(summary, policy) -> tuple[CostNotice, ...]` adapt the existing ledger.

Duplicate identical receipt is idempotent; divergent duplicate is an integrity error. Every actual
provider attempt counts once, including failed/cancelled/stale/discarded summaries. Settlement is
independent of conversation commit. Approved-plan application does not debit old planning again.
Version stored plan records to preserve cost completeness and receipt references; old missing fields
are unverified, not complete. A proven zero-upstream preflight refusal is not an invented billed attempt.
Retain known-subtotal accumulation after unknown receipts. Prevent duplicate agent_run debit through
the existing P11.26-CAND-2 schema boundary rather than a parallel telemetry/ledger owner.

Alerts use explicit operator-configured increasing USD thresholds; no numerical amounts are invented
here. Per-turn/session supported first. Daily alerts require configured IANA day/timezone identity and
a reconciled durable ledger; no process-local daily totals. Emit once at each actual crossing. Absent
daily prerequisites make that scope unavailable, not a fake zero or product dispatch stop.
Retain P9.85-FU-3 ownership for alerts and P11.26-CAND-2 for telemetry completion.

After this D6 disposition, accounting proof and governing successor acceptance, Task 11 removes all
product monetary stops/positive-dollar construction requirements/remaining-dollar prompt semantics.
Retain configured planning count (current default 3), wall clock (30 minutes), repeated-failure count
(2), single-call Chat and safety/capacity/cancellation controls. No infinity/large sentinel. Independently
authorized test/evaluation dollar/call ceilings remain. ADR-009's new loop/check-in design is not selected.
Amount/day configuration and CP4 deployment measurements gate activation, not offline implementation.

## 7. Governed successor language and publication workflow

The verified current predecessors are HLD v2.18, LLD v2.41, Guardrails v1.3 and Test Strategy v1.7;
their SHA-256 identities are in `package-a-docs-draft/intake.json`. This draft changes no PDF.
Complete proposed successors use the next versions only after rechecking actual latest predecessors.
Preserve all unrelated content and do not edit published bytes. Accepted Task 1 text is the input to
that full-document succession, not a substitute publication or a claim that it has happened.

Apply these exact replacement requirements to all spend-stop rules, retaining separate security limits:

| Successor | Required replacement language / proof |
|---|---|
| Architecture | Product dispatch is controlled by trusted role/route policy, request capacity, cancellation, permissions and finite work bounds. Actual cost produces alerts/incomplete-accounting notices; no product dollar stop. Context Engine receives only sanitized immutable data and injected maintenance; host owns authority and ledger. |
| LLD | Final Gateway validates complete request and output cap per actual attempt. True incomplete finish never becomes an approved executable artifact. Stage receipts are exactly-once ledger inputs; unknown cost is explicit, known subtotal survives and no automatic unknown-cost retry or session latch is introduced. |
| Guardrails | Remove runtime dollar-stop/remaining-budget predicates after accounting/D6; retain configured finite count/time/failure controls, authorization/trust/capacity constraints and independent evaluation ceilings. Historical approvals never grant new execution. |
| Test Strategy | Pin full-floor capacity, exact protected state, stale/cancelled checkpoints, finish truncation, full-set picker, per-turn captured config and exactly-once/incomplete costs. One checkpoint full run plus explicit post-run fix delta; marked live tiers remain separately reported. |

Codex drafts complete successor sources and a requirement-by-requirement migration map during the
CP3 policy migration; Claude reviews as part of the same checkpoint; operator approves publication.
Allocate actual record IDs from the then-current decision index, completing ADR-004/005/006 and
recording the accepted mechanisms without editing predecessors. No new per-task review gate.
If those governed successors or alerts configuration remain unaccepted, hold only activation of the
dependent cost/registry behavior, not unrelated offline engine work. The complete `_v2` implementation
draft accompanies this contract; it retains all tasks and replaces obsolete per-task custody text.

## 8. Checkpoint evidence and handoff

| Checkpoint | Combined review evidence |
|---|---|
| CP1, Tasks 4–5 | YAML/role/route trust; packaged defaults; final capacity equality, finish truncation and per-attempt telemetry/disclosure controls; explicit unverified-route holds |
| CP2, Tasks 6–8 | Forbidden imports/extraction, exact facts/selection isolation, strategy discriminator, zero sliding calls, prefix/stale/cancel publication, fake summary qualification controls; zero paid calls |
| CP3, Tasks 9–11 | Pure fallback/recovery, stored-view binding, full picker capture/resync, meter truth, exactly-once/unknown costs and separated product/evaluation policy; unresolved activation holds explicit |
| CP4, Tasks 12–13 | Measured finite source/reserve/transient/concurrency limits, enabled-route full-floor proof, bounded paid summary receipts and real ACP/Zed/service evidence under separately granted authority |

Focused TDD/checks and local commits run between checkpoints; only the full-suite hook may be skipped.
At each checkpoint: one scheduled full suite with coverage, Fable 5.1 review, focused fixes, one
consolidated Codex review. Identify exactly which commit the suite tested and the later fix delta;
retain failures/skip/unrun evidence. No reviewer back-and-forth or per-task review before that gate.
An unresolved safety/integration failure cannot be declared green; handle it at that same checkpoint.
Operator decides package publication/merge and any paid/live envelope. Do not reuse ADR-017 as a
future four-line or general coverage waiver. No code or external actions are authorized by this draft.
