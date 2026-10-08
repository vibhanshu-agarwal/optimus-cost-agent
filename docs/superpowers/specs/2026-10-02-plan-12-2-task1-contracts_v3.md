# Plan 12.2 Task 1 contracts

**Reviewed local filing candidate, 2026-10-04; observed clean CP4 candidate cf9bb9d.** This complete same-number successor preserves all original sections/tasks and historical acceptance separately. Its controlling offline disposition is review-disposition.md; Task 11/coverage/test composition/Task 12 are verified, while paid/live/activation remain held. Filing is assigned to Claude under the existing offline release. The D7 verbatim record still requires saved transcript provenance.

Historical first-contract/v2-plan acceptance, 2026-10-02, Asia/Calcutta. Codex architects; Claude implements. **Those historical editions were accepted by the operator on
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
| `ViewLimits` | Finite history/source/transient/maintenance bounds; required `summary_max_bytes` (at least 1, strictly below `transient_max_bytes`, derived as `floor(S / r)` from the verified byte-ratio profile, C2); host `estimate_history(text) -> int` with verified estimator ID, subadditive over any strings the engine concatenates |
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

## 3. Accepted strategy and summary-format mechanisms; numeric adoption proposed

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

Observed host RetryPolicy permits an initial call plus up to three retries. The enabled Gateway policy permits one primary plus at most one identical-payload resend on the same route only after definitely not-sent or HTTP 429. Timeout, 5xx and uncertain/unknown-usage failures are never resent under enforcement. The host must honor non-retryable errors. No alternative-model/same-role route recovery exists or is introduced; ADR-009 recovery remains deferred. Each physical attempt is separately counted and receipted.

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
V2 proposes the named ADR-014 exception: preserve inclusive 524288-byte source/admission and warning, while permitting readable OPEN refusal when complete full-history input plus output does not fit. Apply the same guard to attached full-history fallback; no source-floor reduction or capacity exemption. Record operator acceptance before claiming the exception. Conservative complete-request safety and equality/one-over behavior remain required. Exact per-route tokenizer dependencies are deferred; unknown/expanding normalization is ineligible.

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

## 6. D6 accepted mechanism; governed implementation remains held

The first contract accepted on 2026-10-02 selects **non-latching incomplete accounting with no automatic unknown-cost retry**. Its governed integration and final product-stop removal remain held at dea4624; this draft proposes their bounded release. Keep strict
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
their SHA-256 identities are in `package-a-docs-draft/intake.json`. This complete v3 filing candidate is accompanied by complete HLD v2.19, LLD v2.42, Guardrails v1.4 and Test Strategy v1.8 PDFs. They are review drafts and have not replaced authoritative predecessors.
Complete proposed successors use the next versions only after rechecking actual latest predecessors.
Preserve all unrelated content and do not edit published bytes. Accepted Task 1 text is the input to
that full-document succession, not a substitute publication or a claim that it has happened.

Apply these exact replacement requirements to all spend-stop rules, retaining separate security limits:

| Successor | Required replacement language / proof |
|---|---|
| Architecture | Product dispatch is controlled by trusted role/route policy, request capacity, cancellation, permissions and finite work bounds. Actual cost produces alerts/incomplete-accounting notices; no product dollar stop. Context Engine receives only sanitized immutable data and injected maintenance; host owns authority and ledger. |
| LLD | Final Gateway validates complete request and output cap per actual attempt. True incomplete finish never becomes an approved executable artifact. Stage receipts are exactly-once ledger inputs; unknown cost is explicit, known subtotal survives and no automatic unknown-cost retry or session latch is introduced. |
| Guardrails | Remove runtime dollar-stop/remaining-budget predicates after accounting/D6; retain configured finite count/time/failure controls, authorization/trust/capacity constraints and independent evaluation ceilings. Historical approvals never grant new execution. |
| Test Strategy | Pin storage-floor admission and final request capacity with the disclosed D7 exception, exact protected state, stale/cancelled checkpoints, finish truncation, full-set picker, per-turn captured config and exactly-once/incomplete costs. One checkpoint full run plus explicit post-run fix delta; marked live tiers remain separately reported. |

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
| CP4, Tasks 12–13 | Measured finite source/reserve/transient/concurrency limits, enabled-route capacity/safety proof and named D7 exception, bounded paid summary receipts and real ACP/Zed/service evidence under separately granted authority |

Focused TDD/checks and local commits run between checkpoints; only the full-suite hook may be skipped.
At each checkpoint: one scheduled full suite with coverage, Fable 5.1 review, focused fixes, one
consolidated Codex review. Identify exactly which commit the suite tested and the later fix delta;
retain failures/skip/unrun evidence. No reviewer back-and-forth or per-task review before that gate.
An unresolved safety/integration failure cannot be declared green; handle it at that same checkpoint.
Operator decides package publication/merge and any paid/live envelope. Do not reuse ADR-017 as a
future four-line or general coverage waiver. No code or external actions are authorized by this draft.


## 9. CP4 offline numeric adoption and remaining closure evidence

### Numeric recommendation: Recommended values and disclosed limitation

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

These values do not enable any route or establish a conservative estimator. Summary byte limits derive from the selected verified profile, never a bytes/4 assumption. Section 4 proposes the named D7 exception to full-floor provider fit. Both actual request paths still require conservative complete-request safety and equality/one-over refusal evidence with maximum permitted material and one output reserve.

Accept this availability limitation: compaction/hybrid refuse if a required indivisible ordinary turn cannot fit maintenance, or the complete chunk plan exceeds the allowance. At projected source <=524288 bytes, any unavailable view (including oversized turn, missing summarizer or protected-state overflow) may use full-history fallback if the final request fits. Above that floor it refuses. Refusal persists only while relevant history, estimator and bounds remain unchanged. The user can choose sliding for a later turn or start a new thread; sliding may omit all ordinary history when even the newest turn does not fit. Protected authority remains exact. No automatic strategy change or within-turn splitting is introduced. The accepted reason-specific C1 messages remain verbatim; unavailable summarizers do not suggest a paid retry.



### D7 / free inspection: D7 disposition and free route/configuration inspection

**Architect recommendation for recorded operator acceptance:** retain inclusive 524288-byte absent-engine canonical storage/admission and its warning, but accept the named ADR-014 exception that full stored history need not fit a provider request. A complete conservative request that exceeds capacity gets the accepted readable OPEN capacity refusal, without answer/planning dispatch. Apply this to both absent-engine and attached full-history fallback; compaction/sliding may create a smaller eligible view. Do not lower the source cap, exempt any request from the guard or pretend the exception is already accepted.

Arithmetic is already decisive for the current byte-ratio mechanism. Agent usable input is 229376 (262144 minus 32768 output). Measured maximum planning material is 43795 bytes. At r=1, even before any additional overhead, no more than 185581 history/prompt bytes fit (35.40% of 524288). Full-floor admission would need r<=0.4038; that is incompatible with universal byte-fallback safety. Inspect normalization and framing to prove a route-specific profile; even r=1 is not automatically safe. Its extra overhead further reduces the bound. This is a request-capacity exception, not a replacement storage limit.

Use only verified conservative r=1 test profiles for this simple release. A nominal 32768-token exact tail then admits at most roughly 32768 UTF-8 bytes, an 8192-token summary has summary_max_bytes=8192, and the engine maintenance cap approximates a 131072-byte budget, less estimator overhead. English/code ordinarily use several bytes per real token: this gives substantially less usable history than exact counting would. Do not claim a fixed turns count or universal four-times ratio. Exact per-route tokenizer counting and dependencies remain deferred; no new reader or lockfile change is proposed now.

Allow at most **40 public HTTP GETs including redirects, four candidate tokenizer configurations, 64 MiB per asset, 256 MiB total, 30 minutes network and 30 minutes JSON/config inspection**. There is no counting step: tokenizers/tiktoken/sentencepiece/transformers are absent in the CP4 venv and installation is outside scope. No inference, credentials, private payload, weights, repository execution, remote code, package installation or sample-based safety proof.

Fetch official route metadata and publisher-owned tokenizer/configuration JSON: model type, normalizer (including expansion), pre-tokenizer, byte fallback, postprocessor/special-token additions and chat/wire framing. Record provenance, hashes, license and an explicit safety argument; a family label or missing behavior is not proof. Verify exact endpoint slugs, quantization, supported cap/reasoning/finish semantics, window >=262144 and maximum output >= each role reserve; current eligibility rejects lower-window routes. If public data need authentication, stop that retrieval. At most three redirects within approved official origins. Existing role exclusions and disclosures remain; no model substitution.

Put verified facts into a reviewed, non-fixture **test-only override**, never packaged defaults. Prove host/Gateway equality and complete-request capacity boundaries with the actual format. Metadata supports documented finish-contract verification; live qualification records actual finish behavior. Return ineligible/unknown rows if proof cannot be obtained within this bound. This inspection verifies eligibility, not the already disproved full-floor guarantee, and does not enable production routes.



## 10. Mandatory trusted Plan 12 test composition — proposed interface

Review edition 2, 2026-10-04. This is a concrete implementation contract for Claude after direct offline release, not executable code or an activation record. Baseline dea4624: ENFORCEMENT_ACTIVE=False, trusted_snapshot() returns None, normal default claude-haiku resolves to claude-haiku-4.5, and AcpServer._serve_ndjson does not pass a context attachment or route/alert policies to AcpDuplexAdapter. Gateway enforcement requires config.model_policy. Adapter-level injection alone is insufficient.

### 10.1 Entry and trust

Add one option --plan12-test-profile <approved-profile> to the actual trusted launch/entrypoint path used by acpx. A profile is bounded reviewed local input, carrying exact non-fixture registry/configuration/qualification identities. Do not treat a path or caller-supplied hash as trust. Independently compose/validate the effective snapshot in host and Gateway, bind its canonical hash in the approved HMAC launch record and authenticated child manifest, and retain existing scope/workspace/keyring/credential protections. Unknown hash, absent approval, mismatch, tampering or fixture=True makes zero upstream calls. A profile change requires a matching new approval/manifest, not reuse of an old hash.

Use explicit process-scoped dependency injection through the actual server construction and _serve_ndjson adapter creation. Supply host RoutePolicy, context attachment where appropriate, receipt sink and optional explicitly configured alert policies; supply GatewayModelPolicy in the real Gateway process. Select an exact eligible model as this test-process default. Do not flip the packaged ENFORCEMENT_ACTIVE constant, monkeypatch globals, add a hidden environment enablement flag, edit shipped model defaults or bypass the real child process. Absence of the option preserves normal held production composition.

### 10.2 Two bounded profiles

| Profile | Preconditions and allowed claim |
|---|---|
| A — qualification / absent-engine | Exact public route/window/output/estimator/finish/pricing facts verified; approved non-fixture test override; candidate already eligible in an existing active role. Gateway eligibility is the union of existing active roles, so no new role grant or fabricated summary receipt is needed. Invoke the separately capped evaluator without claiming production SUMMARIZER eligibility. Absent-engine/unavailable behavior may be exercised; maintenance quality remains unqualified. |
| B — attached maintenance | Profile A facts plus the genuine passing fixture/route/format/validator receipt. Construct the attachment with compaction default, accepted limits, summary callback/route and one finite repack. New effective hash must match its own approval/child manifest. Attached Task 13 maintenance requires B; A cannot stand in for it. |

Production SUMMARIZER eligibility remains withheld until its actual receipt passes. Test override facts do not publish packaged registry changes. Host/Gateway hash equality, exact model selection and enabled final guards are necessary evidence, not inferred from a successful raw HTTP call.

### 10.3 Offline acceptance cases before paid/live use

Verify the real entrypoint/subprocess receives the profile and passes dependencies into AcpDuplexAdapter; verify Gateway config.model_policy is present. Prove positive approved non-fixture composition and negative absent/mismatched/stale/tampered/fixture approval; protect secrets from outputs. Prove equality/one-over complete input plus output, enforced upstream cap/finish semantics, host non-retryable propagation and maximum two physical attempts after not-sent/429 only. Profile A cannot invoke attached production maintenance; B cannot reuse a changed qualification key. Verify default model in the test process is eligible, while shipped defaults remain held.

Retain exact source/profile/launch/approval/manifest identities and sanitized verdicts. Fable and consolidated Codex review the offline composition before any conditional paid/live release. Production bootstrap enforcement, production attachment and shipped Haiku-default removal remain separately visible rollout requirements. This package contains no implementation and grants no service or inference authority.


Coverage implementation follows Test Strategy v1.8 §8A and the migration map: full-suite data only, independent required floors, no aggregate gate, commit profile retained. Quality ceiling $0.05/four attempts; editor $0.50/24 attempts, 28 total. All approvals remain absent.


## Offline closure status and controlling corrections

**Observed offline candidate, 2026-10-04:** cf9bb9d (clean local CP4 branch). V1 capacity text/meter, V3 remaining-allowance preflight, Task 11 product/evaluation separation, named trusted test composition, tracked-source coverage gate and Task 12 boundaries pass offline verification. Windows: 6830 passed, 39 skipped, 111 deselected; WSL: 6641 passed, 228 skipped, 111 deselected; both exits 0. Production ENFORCEMENT_ACTIVE=False, trusted_snapshot() returns None, and the shipped claude-haiku-4.5 default are unchanged. Luna remains ineligible, Qwen remains unqualified, and paid qualification/real editor Task 13 remain UNRUN. See review-disposition.md and evidence-verification.json. This source review is not production activation or full CP4 closure.

Keep StrategyParameters and its checkpoint digest unchanged across the turn. Pass ViewLimits.maintenance_calls_remaining = max(0, 18 - callbacks_already_consumed) for initial preparation and each repack; this execution-state field is outside summary identity. The engine preflights the complete chunk plan against min(parameters.max_maintenance_calls, remaining) before any callback. Zero remaining permits a valid zero-call reused/sliding view and refuses a plan needing calls. Reuse still requires matching source, coverage, estimator and token/byte bounds. Retain the host defensive counter and allowance classification; repack checkpoints remain unpublished.

Until the profiles lane lands, the hook entry is unchanged and keeps pyproject fail_under=80 (an Optimus-only interim floor). Only CI switches to --run-full-suite. The profiles lane later moves the hook to commit with no coverage gate.

Coverage uses coverage.py/pytest-cov fail-under semantics at configured precision 0: 79.5% compares as 80% and 79.0% fails. Report both measured and compared values. Independent package floors remain required; aggregate cannot substitute.

Task 12 additionally verifies the actual HostMaintenance-wrapped complete input, including the summary prompt and wire/framing, plus one output reserve through the enabled in-process Gateway: equality admitted, one-over refused with zero upstream calls. Synthetic estimator evidence does not enable a real route.

Qualification is Luna-only on the pinned openai/fast route, reasoning none, literal quantization unknown; None is not that literal. There is no new Qwen active-role grant, no model substitution and no fabricated receipt. The present real profile remains ineligible because estimator/route proof is incomplete.

For any later authorized Zed run, back up the exact settings bytes, record a sanitized identity/hash, change only the named agent_servers command to the approved profile, and restore/verify the original on every exit. Preserve concurrent unrelated edits rather than blindly overwriting them.

D7 remeasurement at cf9bb9d: 229376 usable input - 43795 bytes of maximum planning material = at most 185581 history/prompt bytes at r=1 before other overhead (35.40% of 524288). The earlier 43819/185557/35.39% reading belongs to dea4624 and remains in sealed evidence. These are conditional upper bounds, not universal request cutoffs. The implemented numeric set follows the reported human offline release; the new ADR must not invent its verbatim D7 decision. ADR-011 transcript provenance is still needed at filing.
