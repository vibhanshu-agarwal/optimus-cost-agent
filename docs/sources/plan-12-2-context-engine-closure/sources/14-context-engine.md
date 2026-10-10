# 14. Optional Context Engine and Plan 12 migration

## 14.1 Product boundaries

`context_engine` is an optional, extractable in-process Python package. It receives immutable sanitized ordinary turns, exact host-issued execution/approval projections, strategy parameters, limits, revision identity and an injected maintenance callback. It owns derived views and checkpoints only. It imports no Optimus host, Gateway, security, evidence-handoff, workspace, Redis or provider implementation.

Optimus owns canonical storage, current prompt, exact authority, turn lifecycle, current workspace resolution, policy capture, model-facing assembly and notices. `optimus_model_policy` is neutral shared policy code; host and Gateway independently consume the trusted immutable snapshot. The Gateway alone performs approved upstream calls and enforces final request capacity for each actual attempt. Existing ledger/telemetry owners account for every attempt.

The local Gateway, shared-secret boundary, independent client-MCP trust controls, public tool dependencies and OTel/OTLP topology remain as specified in earlier sections. Plan 12 adds no Gateway MCP broker, provider key in CORE or generalized plugin platform.

## 14.2 Canonical source and selected views

Without the engine, retain full canonical history and inclusive 524,288-byte admission, its 80% storage warning, and the already accepted history-order/display exceptions. An attached engine may use the released offline 1,048,576-byte source class; production attachment still requires its own activation. Source size is distinct from provider request capacity and the context meter. A prompt-time 131,072-byte record reservation is not a cap on the eventual reply or entire turn.

Compaction is the default. It retains a newest whole-turn exact tail and summarizes earlier ordinary history. Hybrid optionally retains the first complete turn as an exact anchor, uses a larger exact tail and summarizes the middle; deduplicate overlapping head/tail turns. Sliding takes the newest complete turns that fit, makes zero summary calls and does not skip an oversized newest turn to recover older ordinary history. All three retain exact protected state. Derived omission never deletes canonical history.

The proposed cheap/ultra-cheap history allowance is the smaller of 131,072 tokens and 80% of usable input, further constrained by final packing after protected state. It is a ceiling on history sent, not a threshold that delays summarization. The released offline summary cap is 8,192 tokens; compaction tail is 32,768 tokens, hybrid anchor 16,384 tokens and hybrid tail 65,536 tokens. Thus compaction's ordinary tail plus summary is at most 40,960 tokens; hybrid's head, tail and summary at most 90,112, before exact protected facts and other material. These are adopted offline test values; production defaults and route activation remain held.

Whole-turn summarization remains the simplest accepted design direction. If an indivisible older turn cannot fit maintenance, report the reason and the filed recovery choices; do not split it, silently switch strategies or discard ordinary text inside compaction/hybrid. Sliding can omit even all ordinary history when its newest turn does not fit. Any unavailable view at <=524288 projected source bytes may use full-history fallback when its complete final request fits, including an oversized turn or missing summarizer. Above that floor it refuses readably with OPEN disposition. Availability depends on the actual history, estimator and bounds. Within-turn splitting and delayed-trigger/call-frequency optimization remain deferred.

## 14.3 Authority, selection and continuity

Model-authored history and generated summaries are inert. A claim that a change ran, a test passed or an approval exists cannot create host authority. Preserve every committed turn's exact outcome/effect projection and host-issued approval facts, independently of ordinary history selection. Historical approval describes an earlier decision and grants no fresh execution.

Exact retained earlier plans/replies may supply ordinary file/skill selection hints. Resolve file references against the current eligible workspace and assemble current bounded content. A resolved path does not verify an old diagnosis. Generated summary text does not directly select files or skills. A reference appearing only in omitted history may be unavailable to selection; do not claim full-history retrieval after compaction.

Model changes preserve canonical conversation and the strategy-defined view. They do not trigger a paid whole-chat factual audit. Use existing targeted freshness checks for selected file data and controlled edit targets. Preserve approval/version checks; no background watcher, durable claim database, semantic pinning or repository-wide rescan is introduced. These controls do not eliminate races with unrelated external writers.

## 14.4 Capacity and policy

Every final model request uses `effective_total = min(262144, verified_route_window)`, `usable_input = effective_total - verified_output_reserve`, and a complete-input estimate that includes messages, templates, workspace/tool/evidence material and framing. Admit equality; count the actual enforced output cap once, including verified reasoning semantics. Recompute at the final Gateway boundary for every actual provider attempt. A pre-call refusal dispatches no upstream attempt for that rejected request and remains readable/recoverable; earlier maintenance attempts can still have receipts.

D7's proposed named exception retains inclusive 524288-byte canonical storage/admission and its warning, but does not guarantee that full history fits a provider request. Both absent-engine and attached full-history fallback still undergo the final complete-request guard; overflow gives the accepted readable OPEN refusal without answer/planning dispatch. Do not lower the source cap or exempt capacity. The release implements this disclosed exception offline; its verbatim D7 record still needs saved transcript provenance at filing. Exact per-route tokenizers remain deferred; route-specific byte-ratio safety requires normalization/pre-tokenization/framing proof and cannot be inferred from samples. Unknown/expanding behavior remains ineligible.


The curated registry retains explicit role assignments, supported capabilities, exact endpoints, provenance and cheapest-per-token ordering among eligible assignments. Crossed prices need the accepted blend contract; no hidden scoring replaces policy. Contributor routes keep their filed disclosure. Haiku is excluded from the curated migration target. This does not claim active enforcement or a shipped-default change; normal bootstrap remains inactive until separately released. Auto classification, reviewer/depth behavior, savings-report surfaces and ADR-009's future recovery mechanism are not activated by this migration.

## 14.5 Costs and execution

The normative product policy after the accepted D6/governed migration has no dollar-stop predicate, hidden summary reserve, positive-dollar constructor requirement, remaining-dollar planner prompt or infinite sentinel. It keeps actual provider-reported costs, exactly-once settlement, notices and explicitly configured alerts. Missing cost remains unknown, never zero; keep known subtotals and incomplete-accounting attribution. Do not automatically retry an uncertain attempt or freeze the session. A later intentional request still uses normal capacity, trust and authorization controls.

Finite work controls remain: current defaults of three Agent planning rounds, 30 minutes and two repeated failures, single-call Chat, bounded maintenance and explicit repacks. Goal loops retain their own finite count/time/failure controls. Independently authorized evaluation/test budgets remain real monetary ceilings. Product dollar stops and remaining-dollar prompts are removed on the reviewed cf9bb9d branch. Independently capped evaluation remains capped. This branch result does not claim main is merged or production context enforcement is active.

## 14.6 Evidence and release

Implementation checkpoints, measured coverage and exact acceptance/provenance are recorded in the companion closure records. Architecture targets do not promote historical evidence to changed code or establish current gate enforcement.

Complete product activation requires accepted measured policy, supported route/estimator/output facts, an exact qualified summary receipt, production-base effect/cancellation proof, trusted launch composition, finite repack behavior and real-client evidence. There is still no production constructor of ContextAttachment; the reviewed named test composition supplies it only within its approved test process. Task 13 may use a separately approved ephemeral test composition through explicitly implemented and reviewed process-scoped dependency injection; that proves the named test configuration, not production bootstrap activation. No publication or merge follows from draft acceptance.


Once enforcement is active, capacity-specific text is selected only for INPUT_EXCEEDS_CAPACITY. The 80% request warning uses complete request size, while the separate storage notice preserves the source floor. A local Gateway dispatch reading is not proof of upstream delivery.
