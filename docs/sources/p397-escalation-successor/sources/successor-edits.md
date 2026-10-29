## Covers

### H1 — HLD v2.23

```markdown
# Optimus - Architecture (HLD)

**Version 2.23 — Auto escalation and host/Gateway timing, 2026-10-29; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-Architecture-v2.22.pdf; SHA-256 139fc9d25f659f7fbda14c3a1e28c78757dcca288458373b9c3675ecd77f124b. Retain the predecessor unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-Architecture-v2.18.pdf (SHA-256 0f8725765fecc9a93045fd26630457dfe7112508df164a3ec5bcc55dbc976807). This complete successor retains the predecessor's carried bodies and source corrections except for the changes identified below. Page keys remain those of the native baseline.

**What this edition changes.** It describes ADR-029's single recovery escalation in interactive Auto planning: its trigger, configured target, bounds, notice, records, check-in and approved application on the moved-to model (§14.8). It also states the host/Gateway timing boundary: a 60-second upstream attempt, a 120-second upstream-dispatch budget and a 135-second default host wait, with the processing and cancellation limitations (§14.9). These additions describe main `5977155c2bce9728156ee5898ff9e17d0ae08750`, PR #437 merged 2026-10-29T16:12:49Z, with parents `2b183c8baeb881c26121341f5825e7c212a6e5fa` and PR head `0d68dfebee35ad61fcc8f87c61838185131e8e34`.

**Inspected production facts at 5977155.** Interactive Auto planning can move once to the trusted registry's escalation role's first routable model after a recovery nudge has not helped. A target already current, unavailable or smaller in usable input supplies no step. A grant changes the active model, route and target limits while preserving captured history, authority and incurred receipts; the turn's approved application uses the moved-to model. Fixed-model and headless callers gain no escalation. Gateway dispatch checks and worker deadlines bound upstream waits, with at most 32 outstanding attempt workers. The dispatch budget is not an end-to-end deadline on the Gateway's own processing.

**Provenance and controlling Plan 12.2 amendment.** Unchanged baseline statements retain `91fd64ac78025efe1076bddb106ff89e6adb2030` provenance; localized EDIT and its execution-path corrections retain `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac`; the predecessor's original registry, production-construction and Auto statements retain `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`. This is not a full current-state refresh. The 2026-10-18 amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, remains controlling for unrefreshed Plan 12.2 material, including source/compaction policy, profiles, maintenance and historical evidence. Guardrails is unchanged. ADR-024 governs interactive detection, one nudge and the Continue/Stop check-in; ADR-029 extends that recovery with one Auto escalation. Retained interim limits and legacy goal-loop descriptions do not override those decisions.

**Evidence stays attached to its source.** Section 15 distinguishes source inspection, unit composition, reported Windows suites, Linux PR CI at test merge ref `a53b6888`, scripted acpx/Zed escalation and real-model Zed cases. A real model stuck enough to escalate remains owed in #397; scripted evidence stands in. Z2's lost billed reply and its absence of a rerun remain disclosed. No historical receipt is promoted to a run on `5977155`.

**Authority.** Codex's architecture wording; local filing by Claude under the operator's 2026-10-29 answer, verbatim, "Yes, all four", to Claude's post-merge-follow-up question, whose fourth item commissioned this successor with Codex writing and Claude checking/building. Publication to main requires the operator's separate approval. `SKIP=check-added-large-files` has not been approved for these PDFs. The filing label describes this document, not whether the pinned product feature is enabled. This document grants no additional implementation, service-change, paid-call, hook-bypass or publication authority. No product suite or live call was run to author this text.
```

### L1 — LLD v2.46

```markdown
# Optimus - Low-Level Design

**Version 2.46 — Auto escalation and host/Gateway timing, 2026-10-29; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-LLD-v2.45.pdf; SHA-256 d65bd0033ce1a3331802ca726a86ff955333fa491f6a77c87807a2f80a7563d8. Retain the predecessor unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-LLD-v2.41.pdf (SHA-256 69400fd474eb30711fcc9a061243d6a4d2e35d39d7794d4aa69f5ff51b98109b). This complete successor retains the predecessor's carried bodies and source corrections except for the changes identified below. Page keys remain those of the native baseline.

**What this edition changes.** It specifies ADR-029's interactive Auto escalation: entry and trigger, the escalation-role graph, one move per turn, binder/attachment changes, notice and records, subsequent check-in and application on the moved-to model (§13.11). It adds the shared host/Gateway timing constants, request-scoped dispatch admission, attempt deadlines, outstanding-worker cap, failure facts and delivery limitations (§13.12). These additions describe main `5977155c2bce9728156ee5898ff9e17d0ae08750`, PR #437 merged 2026-10-29T16:12:49Z, with parents `2b183c8baeb881c26121341f5825e7c212a6e5fa` and PR head `0d68dfebee35ad61fcc8f87c61838185131e8e34`.

**Inspected production facts at 5977155.** `AutoRouter.escalation_target` supplies the configured role's first eligible unstopped model, subject to current-model and usable-input checks. The adapter prepares the move before publishing it, records notice delivery and honors halt. The planning loop permits one grant per turn, preserves the recovery episode and grants the target Continue's default three steps and fresh 30 minutes. Application receives the active moved-to model and binder. Earlier receipts and dispatch readings keep their attribution. The shared timing defaults are 60 seconds per upstream attempt, 120 seconds for upstream dispatch per host request and 135 seconds for the host wait. Attempt deadlines bound the wait; abandoned workers can survive uninterruptible setup and retain one of 32 slots until they exit.

**Provenance and controlling Plan 12.2 amendment.** Unchanged baseline statements retain `91fd64ac78025efe1076bddb106ff89e6adb2030` provenance; §4B and localized EDIT corrections retain `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac`; original registry, production-construction and Auto contracts retain `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`. This is not a full current-state refresh. The 2026-10-18 amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, remains controlling for unrefreshed Plan 12.2 material, including compaction, numeric policy, profiles, maintenance and historical evidence. Guardrails is unchanged. ADR-024 governs interactive detection, one nudge and the Continue/Stop check-in; ADR-029 supplies its single Auto escalation extension. Retained numerical limits and legacy goal-loop descriptions do not override those decisions.

**Evidence stays attached to its source.** Section 14 separates inspected contracts and test sources from reported execution. Windows full-suite failures and later focused deltas remain visible; Linux PR CI tested `a53b6888`, not the actual main merge. Scripted acpx/Zed escalation does not satisfy the real-model struggle-to-escalation criterion still owed in #397. Real-model Z3 demonstrates a 51-second known-cost reply, followed by model refusal; it is not an escalation success or a Z2 rerun. Prompt in-flight cancellation and an end-to-end Gateway-processing deadline remain owed.

**Authority.** Codex's architecture wording; local filing by Claude under the operator's 2026-10-29 answer, verbatim, "Yes, all four", to Claude's post-merge-follow-up question, whose fourth item commissioned this successor with Codex writing and Claude checking/building. Publication to main requires the operator's separate approval. `SKIP=check-added-large-files` has not been approved for these PDFs. The filing label describes this document, not whether the pinned product feature is enabled. This document grants no additional implementation, service-change, paid-call, hook-bypass or publication authority. No product suite or live call was run to author this text.
```

## Edits

### H2 — hld/4

OLD:
```text
that model remains fixed for the turn (§14.7). Automatic struggle escalation during a turn remains deferred under #397.
```

NEW:
```text
that model remains bound except for ADR-029's single recovery escalation in interactive Auto planning (§14.8). The moved-to model also serves that turn's approved application. Fixed-model and headless launches do not gain escalation.
```

### H3 — hld/6

OLD:
```text
ADR-024 governs current interactive loop control.
```

NEW:
```text
ADR-024 governs interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds one escalation in interactive Auto planning (§14.8).
```

### H4 — hld/8

OLD:
```text
ADR-024 governs current interactive loop control, which is outside this scoped refresh.
```

NEW:
```text
ADR-024 governs interactive detection, one nudge and the Continue/Stop check-in; ADR-029 extends that recovery with one Auto escalation (§14.8). Other Plan 12.3 details remain outside this scoped refresh.
```

### H5 — hld/8

OLD:
```text
Auto's confidence and availability route-ups occur before planning/answer dispatch; they do not implement ADR-009's deferred struggle-escalation rung (#397).
```

NEW:
```text
Auto's confidence and availability route-ups remain pre-dispatch selection. At `5977155`, ADR-029's distinct struggle-escalation rung is implemented: an interactive Auto turn may move once after its recovery nudge, before the Continue/Stop check-in. The Gateway timing boundary is specified in §14.9.
```

### H6 — hld-14-context-engine.md

OLD:
```text
ADR-024 controls interactive loop behavior; retained interim limits and legacy goal-loop descriptions are not current overrides.
```

NEW:
```text
ADR-024 controls interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds the single Auto escalation described in §14.8. Escalation and the host/Gateway timing contract (§14.9) are refreshed at main `5977155c2bce9728156ee5898ff9e17d0ae08750` (2026-10-29). Retained interim limits and legacy goal-loop descriptions are not current overrides; this is not a full Plan 12.3 refresh.
```

### H7 — hld-14-context-engine.md

OLD:
```text
Auto's pre-dispatch route-ups do not implement automatic struggle escalation (#397).
```

NEW:
```text
Auto's pre-dispatch route-ups are distinct from ADR-029's single recovery escalation, implemented at `5977155` (§14.8).
```

### H8 — hld-14-context-engine.md

OLD:
```text
The final reviewer step, savings report, automatic struggle escalation and package publication retain separate ownership and are not delivered by Auto.
```

NEW:
```text
The final reviewer step, savings report and package publication retain separate ownership. ADR-029's single Auto escalation is implemented at `5977155`; its scripted escalation evidence and the real-model criterion still owed in #397 are distinguished in §15.
```

### H9 — hld-14-context-engine.md

OLD:
```text
The chosen planning/answer model, route and context limits remain bound for the turn and its approved application.
```

NEW:
```text
The chosen planning/answer model, route and context limits remain bound except for ADR-029's one recovery move (§14.8). After a grant, subsequent planning and that turn's approved application use the moved-to model and route; applying the plan does not classify it again.
```

### H10 — hld-14-context-engine.md

OLD:
```text
The escalation role's assignment does not activate ADR-009 rung 2.
```

NEW:
```text
At `5977155`, the escalation role supplies ADR-029's rung-2 target in interactive Auto planning. These shipped assignments do not guarantee a stronger available step for every tier.
```

### H11 — hld-14-context-engine.md

OLD:
```text
A different judge mechanism has separate ownership (#426); automatic struggle escalation remains #397.
```

NEW:
```text
A different judge mechanism has separate ownership (#426). ADR-029 accepts ADR-009 rung 2 as scoped in §14.8; #397 retains the evidence and documentation follow-ups.
```

### H12 — hld-14-context-engine.md

OLD:
```text
§15 distinguishes source inspection, offline tests, pilot evidence and the three reported live slices.
```

NEW:
```text
§15 distinguishes source inspection, offline tests, pilot evidence and the three reported live slices.

## 14.8 One recovery escalation in interactive Auto planning

**At main `5977155` (ADR-029).** ADR-024 supplies the recovery episode: detection, one corrective nudge and the Continue/Stop check-in. In an interactive Auto session, a second detection, an allowance ending without a plan or refusal after the nudge, or a REFUSE settled after the nudge may grant one move before that check-in. A first refusal outside an episode remains a refusal; a plan produced after the nudge goes directly to the check-in. Reaching the planning limit without a detection does not itself trigger escalation.

The graph has one possible edge from the current implementer to the trusted registry's `escalation` role's first routable model. That role undergoes implementer eligibility checks. Later entries substitute for stopped earlier entries; they are not further rungs. No step exists if no target is routable, the current model is already the target, or the target has less usable input. The check-in reports when no stronger eligible model was available. Fixed-model launches, headless callers and `OPTIMUS_LOOP_RECOVERY=headless` retain their existing behavior.

A grant permits at most one move per episode and per turn. It gives the target Continue's allowance: three planning steps and a fresh 30 minutes by default. The episode remains open and proceeds to its check-in unless a halt or typed failure ends the run. The detector restarts for the target; later Continue episodes cannot grant another move in the same turn. Nothing runs while the user answers the check-in. Continue grants planning work or presents a waiting plan for its separate exact approval; it never approves a change.

Before switching, the host attempts a live notice identifying the move, its cause and the registry's input/output prices per million tokens, including the former prices. Delivery is recorded and does not gate the move; a halt wins. Contributor disclosure remains mandatory per request. Model identity, routing and target limits move together; captured history, strategy parameters, summarizer, maintenance/repack allowances and earlier receipts remain. The approved application uses the moved-to model. The initial `auto_routing` record stays the classifier's selection; `loop_recovery` records the escalation decision and, on a grant, `from_model`, `to_model` and `notice_delivered`. Each request keeps the route that sent it and its actual cost or explicit unknown.

The target is configuration, not a hard-coded model or a promise of task success. Escalation bypasses no approval, guard, disclosure, capacity or accounting check. Contracts and executable checks are in LLD §13.11; §15 qualifies their reported evidence.

## 14.9 Host/Gateway timing boundary

At `5977155`, the shared defaults are a 60-second upstream-attempt timeout, a 120-second upstream-dispatch budget per host request, and a 135-second host wait (`MAX_ROUTE_ATTEMPTS` × 60 seconds, plus 15 seconds of processing slack). This budget is time, not a product dollar stop. The Gateway starts a request-scoped deadline and checks that a complete attempt timeout still fits before every dispatch, including after a retry backoff. The two-attempt completion ceiling is a maximum, not an entitlement to a second attempt; the decisions route still makes at most one attempt without resend.

Each production upstream attempt is waited for through a worker-thread deadline. The Gateway abandons it at expiry, shuts down an available socket and refuses a late connection before request bytes leave. Uninterruptible setup may leave a worker running after the waiter returns; a 32-slot process-wide cap bounds outstanding workers, and a slot is held until its worker exits. `attempt_deadline`, `attempt_capacity` and `request_budget` distinguish the failures. The attempt's delivery classification remains separate: uncertain delivery/cost is never silently converted to zero or automatically resent under the enforced completion policy.

The 120-second budget controls upstream dispatch; it is not an end-to-end deadline on request reading, Stage C storage, logging or reply writing. Those operations have no whole-request deadline from this mechanism and can consume the host's slack. The 135-second default depends on responsive Gateway processing and storage. A shorter positive finite `--gateway-timeout-seconds` is allowed with a warning and can lose a billed reply; planning then retains its unknown-cost stop. A departed host's broken/reset reply socket produces a sanitized `reply_undeliverable` record. Prompt cancellation of an in-flight Gateway call and an end-to-end Gateway-processing deadline remain owed in #397. LLD §13.12 specifies the transport details.
```

### H13 — hld-15-capability-status.md

OLD:
```text
Other rows retain their stated historical pins and have not been generally reverified at `bf440cb`.
```

NEW:
```text
Other rows retain their stated historical pins and have not been generally reverified at `bf440cb`. Escalation and host/Gateway timing statements expressly updated in this edition describe main `5977155c2bce9728156ee5898ff9e17d0ae08750` (2026-10-29); they do not re-pin the retained Auto, EDIT or baseline evidence.
```

### H14 — hld-15-capability-status.md

OLD:
```text
ADR-024 governs current interactive loop control; the retained loop rows and numerical limits are historical.
```

NEW:
```text
ADR-024 governs interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds one Auto escalation (§14.8). The retained loop rows and numerical limits are historical.
```

### H15 — hld-15-capability-status.md

OLD:
```text
| Automatic struggle escalation (ADR-009 rung 2) | Not implemented by Auto; pre-dispatch confidence/availability route-ups are distinct | No delivery evidence claimed here | Deferred under #397 |
```

NEW:
```text
| Automatic struggle escalation (ADR-009 rung 2, §14.8) | Implemented at `5977155` as scoped by ADR-029; one move per interactive Auto turn to the escalation role's first routable model | Unit and unit composition tests; reported suites, scripted acpx/Zed escalation and separate real-model Zed cases below. A real model stuck enough to escalate remains owed in #397 | Available in interactive Auto planning under its approved composition; fixed-model/headless callers unchanged |
| Host/Gateway timing (§14.9) | Shared 60 s attempt timeout, 120 s upstream-dispatch budget, 135 s default host wait; worker deadlines and 32-slot cap at `5977155` | Real-socket/unit regressions, reported revert checks and Z3's 51 s known-cost reply; see evidence below | Production defaults; responsive Gateway processing/storage required. No whole-request Gateway-processing deadline or prompt in-flight cancellation claim |
```

### H16 — hld-15-capability-status.md

OLD:
```text
**Auto evidence.** Source inspection for the refreshed statements is at main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`.
```

NEW:
```text
**#397 escalation and timing evidence.** Source inspection for these additions is at main `5977155c2bce9728156ee5898ff9e17d0ae08750`, PR #437's merge on 2026-10-29. The repository-visible record is `docs/sources/p397-escalation/validation-record.md`; ADR-029 records the accepted decision and remaining real-model criterion. The record's earlier CI entry remains a dated pre-merge obligation, not a claim that the later CI was unrun.

The record reports Windows full suites with coverage at `a358d58`, then `ca66625` (10,417 passed, 52 skipped, 106 deselected, 0 failed), then `07e7ed2` (10,462 passed, 52 skipped, 106 deselected, 2 failed). The two last-run failures were inventory checks, fixed in `6ca4bee`; retry-report fixes `bfee317` and `5630fe9` also followed that full suite. Those deltas had focused checks only, including 852 passed and 22 deselected for the last retry-report fix; no later Windows full suite is inferred. The record preserves the first timing revert check's surviving late-handshake gap and the added check that caught it, all five #432 revert parts, and the later five-part retry-report check.

PR #437 guardrails run 40903870999 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40903870999), job `clean-environment-recheck`, passed on Linux/Python 3.14.10 at test merge ref `a53b6888708dcfb7c36ac27349ac187f66fdadb0`, combining PR head `0d68dfebee35ad61fcc8f87c61838185131e8e34` with main `2b183c8baeb881c26121341f5825e7c212a6e5fa`: 10,208 passed, 309 skipped, 106 deselected, 1 warning, 0 failed. Required product floors and full-run coverage validity passed. Run `20261029T154119-3004-c688fb` reported active default selection, COMPLETE records and unsupported Linux native/parent/guard capability; this is not Windows parity. Main-push guardrails run 40909335091 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40909335091) subsequently completed successfully on Linux/Python 3.14.10 at actual merge `5977155c2bce9728156ee5898ff9e17d0ae08750`: 10,208 passed, 309 skipped, 106 deselected, 1 warning, 0 failed. Required coverage floors passed: Optimus 89.7079%, Context Engine 95.9243% and model policy 94.4251%; full-run coverage validity passed. Its run `20261029T161355-2787-7329e8` recorded active default selection, clean source before/after, COMPLETE records and unsupported Linux native/parent/guard capability. Work status page run 40909335032 at the same merge also succeeded. These are separate main-push results, not a relabelling of PR CI or Windows evidence.

Scripted live evidence at `ca66625` used the plan r6 S1 exception, not a real model struggling: independent acpx A1′ escalated once and stopped at the check-in; real Zed U2 stopped, U5 cancelled at the check-in, U4 had no stronger target, and U3 continued before separate plan approval. The record preserves the stub lifetime expiry and second attempt for the remaining Zed chain. Unit sources exercise triggers, graph eligibility, target limits, halt/notice handling, one move, receipts, the meter and approved application. The configured-server test in `tests/unit/acp/test_auto_escalation_end_to_end.py` replaces network/provider dependencies and remains unit composition evidence, despite its file name.

Real-model Zed evidence is separate: U1/Z1 at `3272ce0` completed; Z2 at that head routed up for low confidence but lost a billed reply to the former 30-second host timeout and stopped with unknown cost. Z2 was not rerun. Z3 at `07e7ed2` received a 51-second reply with known cost, then the model refused the task. Known paid spend is reported as USD 0.0587, including Z2's lost reply. These cases do not satisfy the real-model struggle-to-escalation criterion (plan r6 S3), still owed in #397. Prompt cancellation during an in-flight Gateway call and an end-to-end Gateway-processing deadline also remain owed there. The documentation follow-up closes only after the separately authorized successor PR merges; this text does not declare #397 closed.

**Original Auto evidence.** Source inspection for the original registry/construction/Auto statements is at main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`.
```

### L2 — lld/10

OLD:
```text
An escalation assignment does not activate struggle escalation.
```

NEW:
```text
At `5977155`, the escalation role's first routable model is ADR-029's one recovery target for interactive Auto planning (§13.11); it is subject to implementer eligibility.
```

### L3 — lld/11

OLD:
```text
Automatic struggle escalation remains deferred under #397.
```

NEW:
```text
At `5977155`, ADR-029 permits one mid-turn recovery escalation in interactive Auto planning (§13.11); approved application uses the moved-to model. This is the bounded exception to Auto's turn binding.
```

### L4 — lld/14

OLD:
```text
ADR-024 governs current interactive loop control.
```

NEW:
```text
ADR-024 governs interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds one escalation in interactive Auto planning (§13.11).
```

### L5 — lld/16

OLD:
```text
ADR-024 governs interactive loop recovery.
```

NEW:
```text
ADR-024 governs interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds one escalation in interactive Auto planning (§13.11). Neither changes the approval boundary.
```

### L6 — lld/17

OLD:
```text
H and `AutoRouter` binding one eligible model per Auto turn (§13.10).
```

NEW:
```text
H and `AutoRouter` initially binding one eligible model per Auto turn (§13.10), with ADR-029's single interactive recovery move (§13.11).
```

### L7 — lld/17

OLD:
```text
ADR-024 controls interactive loop behavior.
```

NEW:
```text
ADR-024 controls interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds the single Auto recovery move (§13.11).
```

### L8 — lld/18

OLD:
```text
ADR-024 governs interactive loop control.
```

NEW:
```text
ADR-024 governs interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds one Auto recovery escalation (§13.11).
```

### L9 — lld-13-context-integration.md

OLD:
```text
The new §13.10 specifies Auto. ADR-024 controls interactive loop behavior; retained interim limits and legacy goal-loop descriptions do not override it.
```

NEW:
```text
Section 13.10 specifies Auto's original routing at that pin. Sections 13.11–13.12 add escalation and host/Gateway timing at main `5977155c2bce9728156ee5898ff9e17d0ae08750` (2026-10-29). ADR-024 controls interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds the single Auto escalation. Retained interim limits and legacy goal-loop descriptions do not override those decisions; this is not a full Plan 12.3 refresh.
```

### L10 — lld-13-context-integration.md

OLD:
```text
Approved application reuses it and the exact artifact hash; it neither summarizes again nor reselects a model.
```

NEW:
```text
Approved application reuses it and the exact artifact hash; it neither summarizes again nor reselects a model. ADR-029's recovery move occurs during interactive Auto planning, before that application: it updates the active model, binder and target limits while preserving the captured admission as historical identity (§13.11). Application uses the model and binder the turn moved to.
```

### L11 — lld/19

OLD:
```text
No alternative-model recovery is added.
```

NEW:
```text
This resend policy adds no alternative-model recovery. ADR-029's single later recovery move is a separate interactive Auto planning action (§13.11), not a resend of an uncertain or failed provider attempt. The per-request timing budget is specified in §13.12.
```

### L12 — lld/20

OLD:
```text
No alternative-model recovery is added.
```

NEW:
```text
This resend policy adds no alternative-model recovery. ADR-029's single later recovery move is a separate interactive Auto planning action (§13.11), not a resend of an uncertain or failed provider attempt. The per-request timing budget is specified in §13.12.
```

### L13 — lld/36

OLD:
```text
No alternative-model recovery is added.
```

NEW:
```text
This resend policy adds no alternative-model recovery. ADR-029's single later recovery move is a separate interactive Auto planning action (§13.11), not a resend of an uncertain or failed provider attempt. The per-request timing budget is specified in §13.12.
```

### L14 — lld-13-context-integration.md

OLD:
```text
No alternative-model recovery is added.
```

NEW:
```text
This resend policy adds no alternative-model recovery. ADR-029's single later recovery move is a separate interactive Auto planning action (§13.11), not a resend of an uncertain or failed provider attempt. The per-request timing budget is specified in §13.12.
```

### L15 — lld-13-context-integration.md

OLD:
```text
The adapter captures the chosen route binder and rebinds the attached turn's limits before planning/answer work. The selected planning/answer model remains fixed through that turn and approved application; applying an old plan does not classify it again. The summarizer remains the separately eligible summarizer, not whichever implementer H selected (`src/optimus/acp/auto_composition.py:303–362`; `src/optimus/acp/spec.py:1844–1851`; `tests/unit/acp/test_auto_turn_routing.py:174`).
```

NEW:
```text
The adapter captures the chosen route binder and rebinds the attached turn's limits before planning/answer work. At `5977155`, the selected planning/answer model remains bound except for ADR-029's one interactive recovery move (§13.11). Subsequent planning and approved application use the moved-to model and binder; applying an old plan does not classify it again. Maintenance retains its separately selected summarizer (`src/optimus/acp/spec.py:2040–2047`, `:1812–1836`, `:2667–2729`; `src/optimus/acp/auto_composition.py:348–382`).
```

### L16 — lld-13-context-integration.md

OLD:
```text
These confidence/availability route-ups happen before planning/answer dispatch. They do not switch models mid-turn or implement ADR-009 struggle escalation. The configured escalation role remains distinct; rung 2 is owned by #397.
```

NEW:
```text
These confidence/availability route-ups remain pre-dispatch selection. ADR-029's distinct rung 2 is implemented at `5977155`: one mid-turn recovery move to the escalation role's first routable model in interactive Auto planning (§13.11). The classifier is not rerun for that move.
```

### L17 — lld-13-context-integration.md

OLD:
```text
Round 2 remains under #395; neither Auto's shipment nor these successor documents declare the whole plan complete.
```

NEW:
```text
Round 2 remains under #395; neither Auto's shipment nor these successor documents declare the whole plan complete.

## 13.11 ADR-029: one mid-turn Auto recovery move

### 13.11.1 Entry, trigger and graph

At `5977155`, the adapter supplies `recovery_escalation` only when interactive recovery is enabled and the turn has an Auto decision (`src/optimus/acp/spec.py:1658–1665`). Fixed-model launches and headless callers gain no move; `OPTIMUS_LOOP_RECOVERY=headless` retains the existing hard caps. This extends ADR-024's recovery episode only as ADR-029 scopes it.

After an episode's nudge, a second detection, an allowance ending without a plan or refusal, or a settled REFUSE can request a `PlanningEscalation`. A grant sets aside that refusal; without a grant, the refusal remains for the check-in. A first refusal outside an episode is terminal, a final plan after the nudge goes directly to the check-in, and an exhausted allowance without a detection has no escalation edge (`src/optimus/agent/planning_loop.py:1415–1447`, `:1461–1484`; `tests/unit/agent/test_planning_loop_escalation.py:96–174`, `:240–290`).

`AutoRouter.escalation_target(current_model_id)` selects the first eligible unstopped model of `Role.ESCALATION`. An empty role, all-stopped role, current model equal to that first routable target, or target with less usable input yields no target; it does not skip that target to invent another rung. Later role entries substitute for stopped earlier ones. `escalation` is an implementer role, with native-tool, planning-grammar, route, capacity and reserve checks. Launch constructs its route policies and attachments in advance (`src/optimus/acp/auto_composition.py:311–322`, `:348–382`; `src/optimus_model_policy/registry.py:98–123`; `src/optimus_model_policy/validation.py:67–78`, `:110–150`).

### 13.11.2 Grant, attachment and accounting

The bridge prepares the target binder, attachment and notice before publishing the switch. It checks halt before selection and again after the notice; preparation failure returns `failed` without publishing a move. An absent target returns `no_target`. The notice is attempted with confirmed flushing under the existing bounded notice wait; failure is recorded as undelivered and does not gate the move. The line names the cause, target and configured input/output prices per million tokens, with the previous prices. It is an informational cost alert, not a spend limit or approval. Contributor disclosure remains required per request (`src/optimus/acp/auto_composition.py:175–186`; `src/optimus/acp/spec.py:2667–2729`).

A grant publishes the target binder and `escalated_model`. `turn_model` then resolves to that model while `auto_decision` remains the initial classifier routing. The new binder adopts all earlier dispatch readings, each with its original capacity; the meter still chooses the largest input, smaller capacity on a tie. `AttachedTurn.escalate_attachment` changes model, request estimator, usable input and target history limits together. It preserves captured history, admission identity, strategy parameters/checkpoint identity, summarizer, maintenance allowance, repack count and earlier readings. Existing final fit/repack and Gateway admission still apply; a usable-input comparison alone does not establish that a particular request fits (`src/optimus/acp/spec.py:424–434`, `:2719–2727`; `src/optimus/gateway/route_binding.py:161–176`; `src/optimus/context/assembly.py:510–522`; `tests/unit/acp/test_auto_escalation.py:218–238`).

`AgentRunner` replaces its active model/route scope before later request reports are made; earlier receipts retain their original routes. The final plan names the producing model, and the adapter passes the moved-to model and binder into the separately approved application. No classification or extra maintenance is performed merely to apply the stored plan (`src/optimus/agent/runner.py:644–704`; `src/optimus/acp/spec.py:1812–1836`; `tests/unit/acp/test_auto_escalation.py:321–347`).

### 13.11.3 Bounds, check-in and records

The planning loop marks the episode's move tried even on a refusal. A grant disables further escalation for the turn, resets the detector and carries an explanation to the target's first request. The episode stays open. The target gets `continue_grant_steps` and a fresh wall-clock allowance: three steps and 30 minutes by default. A later Continue starts a new episode on the moved-to model but cannot enable another switch. A halt or typed failure remains terminal (`src/optimus/agent/planning_loop.py:187–206`, `:1206–1245`, `:1415–1489`).

The subsequent Continue/Stop check-in identifies the move, or says `Auto had no stronger eligible model to try.` when appropriate. Nothing is dispatched while it is pending. Continue grants only planning work; if a final plan is waiting, Continue presents it for its own exact approval. Stop ends the turn with its cause or retains a pending refusal. The one-move bound adds no WRITE/TEST authority (`src/optimus/agent/planning_loop.py:1517–1542`; `tests/unit/acp/test_auto_escalation_end_to_end.py:49–118`, `:121–148`).

The content-free `loop_recovery` event adds `record="escalation"`, the signal, planning step and decision (`granted`, `no_target`, `failed` or `halted`). A grant adds `from_model`, `to_model` and `notice_delivered`. It carries no path, tool arguments or reply text. The initial `auto_routing` projection is not rewritten, and neither event owns a second debit. Actual attempts retain ordinary receipt-first settlement with explicit unknown costs (`src/optimus/agent/planning_loop.py:1461–1478`, `:1544–1568`; `src/optimus/telemetry/events.py:540–568`; `tests/unit/agent/test_planning_loop_escalation.py:213–231`).

## 13.12 Host/Gateway timing contract

### 13.12.1 Shared clocks and dispatch admission

At `5977155`, `UPSTREAM_ATTEMPT_TIMEOUT_SECONDS = 60.0`, `GATEWAY_REQUEST_BUDGET_SECONDS = MAX_ROUTE_ATTEMPTS * 60.0 = 120.0`, and `HOST_GATEWAY_TIMEOUT_SECONDS = 135.0`. `GatewayClient` uses the host constant by default. The CLI accepts a positive finite `--gateway-timeout-seconds` override for this process and warns below that default. A shorter wait can abandon a billed reply and leave planning stopped as `PLANNING_GATEWAY_COST_UNKNOWN`; it changes no resend or accounting rule (`src/optimus_model_policy/binding.py:219–237`; `src/optimus/gateway/client.py:24–41`, `:124–133`; `src/optimus/acp/__main__.py:303–320`, `:968–971`).

The server calls `begin_request_budget` before handling an accepted route and clears its thread-local deadline in `finally`. `request_budget_admits(seconds)` requires the whole proposed wait to fit before the monotonic request deadline. Completion and decision handlers check immediately before upstream dispatch. Completion recovery must also fit its delay plus an entire attempt, with admission rechecked at dispatch after backoff. Tool-provider retries use the same budget; a failed retry candidate whose backoff consumes the remaining time leaves the previous attempt as the final failure. Retry observers run only after the retry dispatch, so reporting cannot delay it beyond the last budget check (`src/optimus_gateway/server.py:108–123`; `src/optimus_gateway/upstream_client.py:48–66`, `:278–334`; `src/optimus_gateway/responses.py:178–218`; `src/optimus_gateway/decisions.py:86–103`; `src/optimus_gateway/tool_provider_http.py:65–73`, `:102–119`).

The enforced completion limit stays one primary attempt plus at most one identical-payload recovery attempt on the same route, only after definitely not sent or rejected HTTP 429. Uncertain delivery, 5xx or unknown accounting is not resent. The decisions route remains one attempt with no resend. A budget permits fewer attempts than the numerical maximum; it creates no entitlement to a retry.

### 13.12.2 Attempt deadline and failure facts

`AttemptDeadline.run` executes upstream I/O on a daemon worker and waits no longer than that attempt's timeout. This bounds the wait through name lookup, multi-address connect, proxy tunnel, TLS, send and response reads, including a peer that keeps dripping bytes. At expiry it abandons the attempt, shuts down an available socket and rejects a connection completed later before any request byte leaves. The raw socket is handed over before tunnel/TLS work. Setup that cannot be interrupted can leave the worker alive; one of 32 process-wide slots remains held until that worker actually exits. A full pool refuses new work immediately (`src/optimus_gateway/upstream_client.py:76–174`).

Production completions, decisions and tool-provider HTTP calls use that deadline machinery. The watched opener connects their sockets to it. Enforced model/decision expiry is `not_sent` if no connection was accepted, otherwise `uncertain`; worker-capacity refusal starts nothing. Structured failure kinds are `attempt_deadline`, `attempt_capacity` and `request_budget`; delivery outcome remains separately attributable (`src/optimus_gateway/upstream_client.py:370–385`, `:439–448`, `:492–500`; `src/optimus_gateway/tool_provider_http.py:113–119`; `src/optimus_gateway/responses.py:188–194`).

### 13.12.3 Delivery limitation and evidence

The dispatch budget starts before request-body handling, so Gateway processing can consume time and leave less room for dispatch. It does not impose an end-to-end deadline on request reading, Stage C ledger work, logging or reply writing. The host's additional 15 seconds is slack, not proof of delivery through stalled storage/processing. These controls bound waits and outstanding attempts; they do not promise immediate termination of every abandoned worker or prompt cancellation of an in-flight host call. Both prompt in-flight cancellation and a Gateway-processing deadline remain owed in #397.

When reply writing encounters `BrokenPipeError`, `ConnectionAbortedError` or `ConnectionResetError`, the server closes the connection and emits sanitized `reply_undeliverable` with known route and status, after its ordinary outcome log; it does not turn the lost reply into a fresh model attempt (`src/optimus_gateway/server.py:210–228`). Tests in `tests/unit/optimus_gateway/test_upstream_retry.py`, `test_responses.py`, `test_decisions.py` and `test_server.py` cover the budget, deadline, late connection, cap and lost-reply paths. Section 14 distinguishes this inspected test coverage from reported execution, live evidence and remaining obligations.
```

### L18 — lld-14-capability-status.md

OLD:
```text
Other contracts retain their historical pins and have not been generally reverified at `bf440cb`.
```

NEW:
```text
Other contracts retain their historical pins and have not been generally reverified at `bf440cb`. Escalation and host/Gateway timing statements expressly updated in this edition describe main `5977155c2bce9728156ee5898ff9e17d0ae08750` (2026-10-29); they do not re-pin the original Auto, EDIT or baseline evidence.
```

### L19 — lld-14-capability-status.md

OLD:
```text
ADR-024 governs current interactive loop control; retained loop types and numerical bounds are historical.
```

NEW:
```text
ADR-024 governs interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds one Auto recovery escalation (§13.11). Retained loop types and numerical bounds are historical.
```

### L20 — lld-14-capability-status.md

OLD:
```text
Active in approved Auto launches; planning/answer model fixed per turn
```

NEW:
```text
Active in approved Auto launches; initial planning/answer binding with ADR-029's single interactive recovery exception (§13.11)
```

### L21 — lld-14-capability-status.md

OLD:
```text
Auto's shipped judge; no struggle-escalation implementation
```

NEW:
```text
Auto's shipped judge; pre-dispatch selection is distinct from ADR-029's recovery move (§13.11)
```

### L22 — lld-14-capability-status.md

OLD:
```text
| `optimus-trust run-gateway --auto` (§13.10.1) | CLI flag; durable workspace approval must bind registry and composition | Launch CLI unit tests | Supported for a manually managed Auto Gateway |
```

NEW:
```text
| `optimus-trust run-gateway --auto` (§13.10.1) | CLI flag; durable workspace approval must bind registry and composition | Launch CLI unit tests | Supported for a manually managed Auto Gateway |
| ADR-029 escalation (§13.11) | `escalation_target`, interactive callback, one grant per turn, binder/attachment switch and moved-to approved application at `5977155` | Unit and unit composition tests; reported suites and scripted acpx/Zed cases below. Real-model struggle-to-escalation criterion still owed in #397 | Interactive Auto planning under its approved composition; fixed-model/headless unchanged |
| Host/Gateway timing (§13.12) | Shared 60 s attempt, 120 s upstream-dispatch budget, 135 s default host wait; `AttemptDeadline`, 32 outstanding worker slots and dispatch checks at `5977155` | Unit/real-socket regressions, reported revert checks and Z3 known-cost reply; evidence below | Production defaults; no end-to-end Gateway-processing deadline or prompt in-flight cancellation claim |
```

### L23 — lld-14-capability-status.md

OLD:
```text
**Auto evidence.** The refreshed implementation statements use main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`.
```

NEW:
```text
**#397 escalation and timing evidence.** Source inspection for these additions is at main `5977155c2bce9728156ee5898ff9e17d0ae08750`, PR #437's merge on 2026-10-29. The repository-visible record is `docs/sources/p397-escalation/validation-record.md`; ADR-029 records the accepted decision and remaining real-model criterion. The record's earlier CI entry remains a dated pre-merge obligation, not a claim that the later CI was unrun.

The record reports Windows full suites with coverage at `a358d58`, then `ca66625` (10,417 passed, 52 skipped, 106 deselected, 0 failed), then `07e7ed2` (10,462 passed, 52 skipped, 106 deselected, 2 failed). The two last-run failures were inventory checks, fixed in `6ca4bee`; retry-report fixes `bfee317` and `5630fe9` also followed that full suite. Those deltas had focused checks only, including 852 passed and 22 deselected for the last retry-report fix; no later Windows full suite is inferred. The record preserves the first timing revert check's surviving late-handshake gap and the added check that caught it, all five #432 revert parts, and the later five-part retry-report check.

PR #437 guardrails run 40903870999 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40903870999), job `clean-environment-recheck`, passed on Linux/Python 3.14.10 at test merge ref `a53b6888708dcfb7c36ac27349ac187f66fdadb0`, combining PR head `0d68dfebee35ad61fcc8f87c61838185131e8e34` with main `2b183c8baeb881c26121341f5825e7c212a6e5fa`: 10,208 passed, 309 skipped, 106 deselected, 1 warning, 0 failed. Required product floors and full-run coverage validity passed. Run `20261029T154119-3004-c688fb` reported active default selection, COMPLETE records and unsupported Linux native/parent/guard capability; this is not Windows parity. Main-push guardrails run 40909335091 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40909335091) subsequently completed successfully on Linux/Python 3.14.10 at actual merge `5977155c2bce9728156ee5898ff9e17d0ae08750`: 10,208 passed, 309 skipped, 106 deselected, 1 warning, 0 failed. Required coverage floors passed: Optimus 89.7079%, Context Engine 95.9243% and model policy 94.4251%; full-run coverage validity passed. Its run `20261029T161355-2787-7329e8` recorded active default selection, clean source before/after, COMPLETE records and unsupported Linux native/parent/guard capability. Work status page run 40909335032 at the same merge also succeeded. These are separate main-push results, not a relabelling of PR CI or Windows evidence.

Scripted live evidence at `ca66625` used the plan r6 S1 exception, not a real model struggling: independent acpx A1′ escalated once and stopped at the check-in; real Zed U2 stopped, U5 cancelled at the check-in, U4 had no stronger target, and U3 continued before separate plan approval. The record preserves the stub lifetime expiry and second attempt for the remaining Zed chain. Unit sources exercise triggers, graph eligibility, target limits, halt/notice handling, one move, receipts, the meter and approved application. The configured-server test in `tests/unit/acp/test_auto_escalation_end_to_end.py` replaces network/provider dependencies and remains unit composition evidence, despite its file name.

Real-model Zed evidence is separate: U1/Z1 at `3272ce0` completed; Z2 at that head routed up for low confidence but lost a billed reply to the former 30-second host timeout and stopped with unknown cost. Z2 was not rerun. Z3 at `07e7ed2` received a 51-second reply with known cost, then the model refused the task. Known paid spend is reported as USD 0.0587, including Z2's lost reply. These cases do not satisfy the real-model struggle-to-escalation criterion (plan r6 S3), still owed in #397. Prompt cancellation during an in-flight Gateway call and an end-to-end Gateway-processing deadline also remain owed there. The documentation follow-up closes only after the separately authorized successor PR merges; this text does not declare #397 closed.

**Original Auto evidence.** The original registry/construction/Auto implementation statements use main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`.
```

### L24 — lld-14-capability-status.md

OLD:
```text
Reviewer behavior, savings reporting and automatic struggle escalation retain their separate owners.
```

NEW:
```text
Reviewer behavior and savings reporting retain their separate owners. ADR-029's bounded Auto escalation is implemented at `5977155`; its evidence limitations and #397 follow-ups are recorded above.
```

## docs/README.md

### D1 / H1 — HLD index row

OLD:
```text
| [Architecture (HLD) v2.22](Optimus-Cost-Agent-Architecture-v2.22.pdf) | High-level design; opt-in Auto mode and its enforced-registry prerequisites at `bf440cb` (2026-10-27). Carried baseline and EDIT statements retain their earlier pins. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) still controls unrefreshed Plan 12.2 material; ADR-024 governs interactive loop control |
```

NEW:
```text
| [Architecture (HLD) v2.23](Optimus-Cost-Agent-Architecture-v2.23.pdf) | High-level design; ADR-029's single interactive Auto escalation and the host/Gateway timing boundary at `5977155` (2026-10-29), extending v2.22's Auto/registry scope. Carried statements keep their pins. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) controls unrefreshed Plan 12.2 material; ADR-024 supplies detection, one nudge and the check-in, extended by ADR-029's one Auto move |
```

### D2 / L1 — LLD index row

OLD:
```text
| [LLD v2.45](Optimus-Cost-Agent-LLD-v2.45.pdf) | Low-level design; Auto composition, H, decisions, routing/binding, stops, settlement and visibility (§13.10), with registry/construction corrections at `bf440cb` (2026-10-27). Prior baseline/EDIT pins remain. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) controls unrefreshed material; ADR-024 governs interactive loop control |
```

NEW:
```text
| [LLD v2.46](Optimus-Cost-Agent-LLD-v2.46.pdf) | Low-level design; ADR-029's trigger, graph, one-move bound, notices/records, attachment/binder switch and approved application (§13.11), plus the host/Gateway timing contract (§13.12), at `5977155` (2026-10-29). Prior pins remain. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) controls unrefreshed material; ADR-024's recovery is extended by ADR-029's single Auto escalation |
```

### D3 — Amendment scope in the index

OLD:
```text
| [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) | Filed 2026-10-18 Plan 12.2 statements and historical evidence. HLD v2.22 / LLD v2.45 refresh registry, production-construction and Auto statements; this amendment remains controlling for their unrefreshed Plan 12.2 material and retains its Guardrails/evidence/roadmap scope. The frozen amendment and 2026-10-15 correction sources stay unchanged |
```

NEW:
```text
| [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) | Filed 2026-10-18 Plan 12.2 statements and historical evidence. HLD v2.23 / LLD v2.46 retain v2.22/v2.45's registry, production-construction and Auto refresh, adding ADR-029 escalation and host/Gateway timing. This amendment remains controlling for unrefreshed Plan 12.2 material and retains its Guardrails/evidence/roadmap scope. The frozen amendment and 2026-10-15 correction sources stay unchanged |
```

### D4 — Successor sources and predecessor provenance

OLD:
```text
| [Plan 12.4 Auto-mode successor sources](sources/plan-12-4-auto-mode/) | Codex's replacement text, assembled baseline-keyed sources and filing validation for HLD v2.22 and LLD v2.45; scoped to Auto and its registry prerequisites at `bf440cb` |
```

NEW:
```text
| [#397 escalation successor sources](sources/p397-escalation-successor/) | Codex's replacement text, assembled baseline-keyed sources and filing validation for HLD v2.23 and LLD v2.46; ADR-029 escalation and host/Gateway timing at `5977155` |
| [Plan 12.4 Auto-mode successor sources](sources/plan-12-4-auto-mode/) | Preserved predecessor text, baseline-keyed sources and validation for HLD v2.22 and LLD v2.45 at `bf440cb`; inputs to the #397 successor |
```

### R1 — root README.md documentation table: HLD

OLD:
```text
| [docs/Optimus-Cost-Agent-Architecture-v2.22.pdf](docs/Optimus-Cost-Agent-Architecture-v2.22.pdf) | High-level design; scoped Auto/registry successor at `bf440cb` |
```

NEW:
```text
| [docs/Optimus-Cost-Agent-Architecture-v2.23.pdf](docs/Optimus-Cost-Agent-Architecture-v2.23.pdf) | High-level design; scoped Auto-escalation and host/Gateway timing successor at `5977155` |
```

### R2 — root README.md documentation table: LLD

OLD:
```text
| [docs/Optimus-Cost-Agent-LLD-v2.45.pdf](docs/Optimus-Cost-Agent-LLD-v2.45.pdf) | Low-level design; Auto composition and routing contracts at `bf440cb` |
```

NEW:
```text
| [docs/Optimus-Cost-Agent-LLD-v2.46.pdf](docs/Optimus-Cost-Agent-LLD-v2.46.pdf) | Low-level design; one Auto recovery move and host/Gateway timing contracts at `5977155` |
```

## Author notes

- **r2 (2026-10-29, follow-up 1):** Reviewed r1's staged assembly, both tools, both README changes, bundle README/validation record, page maps, manifest, four contact sheets and two enlarged evidence pages; independently matched all 57 ordered normalized source/page groups (including 18 native carries) and the draft/repeat/filing PDF hashes. Updated only the two main-push CI paragraphs and their author note with verified completed results; all OLD blocks, covers and build strings are unchanged. R2 still requires Claude's fresh assembly/build/render checks and artifact hashes.

- **D1 ruling: (a).** Cover #397 as merged: ADR-029's single escalation, the ADR-024 recovery it extends as far as rung 2 requires, the changed host/Gateway timing boundary and the documentation indexes. Merely removing “deferred” would leave unconditional turn-binding statements and the changed transport boundary misleading. A full Plan 12.3 integration, ADR-030 approval storage and #434's ordering/lifecycle/queue contract are outside this successor. No unpublished mechanism from the other lane is incorporated.

- **Authority and source of the instruction.** The operator's 2026-10-29 answer supplied in this authoring request is, verbatim, “Yes, all four”, answering Claude's “Go ahead with the post-merge follow-ups?” Fourth item, verbatim: “The HLD v2.23 / LLD v2.46 successor PR: Codex writes the edits and I check and build them. It covers escalation, the host/Gateway timing contract and `docs/README.md` rows 17–18. #397 closes after it merges.” This commissions the wording and Claude's local assembly/check/build. It does not establish separate publication/merge approval or `SKIP=check-added-large-files` approval. The predecessor's PDF exemption is not carried forward. No issue, label, plan checkbox, ADR or review log was changed by this read-only authoring pass.

- **Checkout identity.** Inspected `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p397`, branch `agent/claude/p397-design-docs`, HEAD `5977155c2bce9728156ee5898ff9e17d0ae08750`. Git independently confirmed parents `2b183c8baeb881c26121341f5825e7c212a6e5fa` and `0d68dfebee35ad61fcc8f87c61838185131e8e34`, and the 2026-10-29T16:12:49Z merge time. Initial and final status showed no changes. Git warned that the user's global ignore file was inaccessible; it was not changed. The supplied checkout was used without creating a branch or worktree.

- **Predecessor and custody.** Read `docs/sources/plan-12-4-auto-mode/README.md:3–36`, `validation-record.md:7–59`, both cover sources, `sources/successor-edits.md:1–805`, the complete baseline-keyed `page-updates.json` and all four appended sources. SHA-256 checks independently matched both current predecessor PDFs and both archived native baselines to the cover identities. The current predecessor PDFs have not yet been moved by this pass; Claude must move v2.22/v2.45 to `docs/archive/` unchanged during authorized filing. Preserve the predecessor source bundle.

- **Mechanical checks.** There are 44 OLD/NEW blocks: 38 document-body blocks and six README blocks. Every OLD was checked for exactly one literal occurrence in its predecessor source, and the complete sequential replacement check also passed in memory. All 53 new file:line ranges were checked for existing files and valid line bounds; their substantive support was inspected as described below. No source files were assembled or written. Claude must repeat uniqueness checks against the filed text and retain the assembled-source, PDF-text, page-map and rendering checks.

- **Page-key inventory.** In `docs/sources/plan-12-4-auto-mode/sources/page-updates.json`, the changed HLD keys are `4` (line 4), `6` (line 5) and `8` (line 7). Changed LLD keys are `20` (line 19), `36` (line 23), `10` (line 26), `11` (line 27), `14` (line 29), `17` (line 30), `18` (line 31), `19` (line 32) and `16` (line 34). These are native-baseline keys, not v2.22/v2.45 rendered page numbers. Native-only pages receive no invented source or replacement block: the adjacent replaced lifecycle/strategy pages and appended contracts qualify their inherited model/loop descriptions.

- **Additional stale statements corrected.** Besides Claude's inventory, `lld/17` and the LLD capability row stated one fixed model per turn. The resend descriptions in `lld/19`, `lld/20`, `lld/36` and §13.4 said no alternative-model recovery was added; their qualification now distinguishes the unchanged provider resend policy from the later planning-level escalation. The modified §13.10.3 paragraph uses current binding/application references rather than retaining its now-misleading old line offsets. Other original Auto citations retain their `bf440cb` provenance; this is not a wholesale line-number refresh.

- **Appended-source anchors.** Relevant predecessor statements were inspected at `sources/hld-14-context-engine.md:3`, `:44–77`; `sources/hld-15-capability-status.md:5–7`, `:37–50`; `sources/lld-13-context-integration.md:3`, `:50–70`, `:139–175`; and `sources/lld-14-capability-status.md:5–7`, `:37–62`, all relative to `docs/sources/plan-12-4-auto-mode/`. The new sections are HLD §14.8–§14.9 and LLD §13.11–§13.12. Original Auto and EDIT evidence remains intact and explicitly identified as original evidence.

- **Decision authority checked.** `docs/decisions/README.md:24–27`, `:253–257`, `:269–291` establishes provenance, issue custody and the effective ADR relationships. `docs/decisions/ADR-007-auto-mode-tier-routing.md:68–77` supplies the original binding and anticipated escalation exception. `docs/decisions/ADR-024-accepts-adr-009-loop-control-phase-1-scope.md:7–11`, `:24–47`, `:49–57` supplies Phase 1's accepted recovery and authority boundaries. `docs/decisions/ADR-029-accepts-adr-009-rung-2-one-escalation.md:7–21`, `:23–79`, `:81–121` supplies the accepted automatic choice, graph, triggers, bounds, disclosure, evidence and remaining obligations. Frozen ADR-007, ADR-024, ADR-028 and ADR-029 are not edited. ADR-028's earlier absence-of-escalation statement is historical; its effective relationship is qualified by ADR-029 and the mutable decision index.

- **Controlling amendment.** `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md:3–21`, `:23–37` supplies the continuing scope and evidence qualifications. The successor does not re-author its compaction/numeric policy, profiles, maintenance, Guardrails or historical evidence. Nor does it promote the amendment's dated work-status wording into a new current-status claim.

- **Graph and configuration.** `src/optimus/acp/auto_composition.py:175–186`, `:276–322`, `:348–382` establishes initial routing, the role-based target, current-model/usable-input checks, price notice and prebuilt routes/attachments. `src/optimus_model_policy/registry.py:98–123` includes escalation in `IMPLEMENTER_ROLES`; `src/optimus_model_policy/validation.py:67–78`, `:110–150` establishes the relevant eligibility checks. Models remain configuration. Retained shipped-model examples are explicitly configuration at their original pin; no new mechanism is defined by a named model.

- **Trigger and bounds.** `src/optimus/agent/planning_loop.py:187–206`, `:1086–1098`, `:1206–1245`, `:1393–1489`, `:1517–1568` establishes interactive entry, default allowances, trigger ordering, refusal/plan treatment, one successful switch per turn, later Continue behavior, check-in text and records. The graph is not a sequence of increasingly expensive models, and “stronger” describes the configured escalation role rather than a measured quality guarantee.

- **Host switch and application.** `src/optimus/acp/spec.py:424–434`, `:1658–1665`, `:1812–1836`, `:2040–2047`, `:2667–2729` establishes the interactive Auto seam, original versus active model, initial binding, halt/notice handling, preparation-before-publication and moved-to approved application. `src/optimus/agent/runner.py:644–704` establishes the active reporting scope and producing model. `src/optimus/context/assembly.py:510–522` establishes target limits and preserved captured state; `src/optimus/gateway/route_binding.py:161–176` establishes adopted meter readings. A target's equal-or-larger usable input is not proof that a particular request fits under a different estimator.

- **Records and executable escalation checks.** `src/optimus/telemetry/events.py:540–568` and `src/optimus/agent/planning_loop.py:1544–1568` establish the content-free event fields. Inspected checks include `tests/unit/agent/test_planning_loop_escalation.py:96–174`, `:213–231`, `:240–290`; `tests/unit/acp/test_auto_escalation.py:28–65`, `:218–238`, `:262–290`, `:321–347`; and `tests/unit/acp/test_auto_escalation_end_to_end.py:1–8`, `:49–148`. The last file explicitly identifies itself as offline unit composition evidence, not independent live acceptance. These tests were inspected, not executed here.

- **Timing constants and host boundary.** `src/optimus_model_policy/binding.py:219–237` establishes 2 attempts, 60 seconds, 120 seconds and 135 seconds, including processing outside the dispatch guarantee. `src/optimus/gateway/client.py:24–41`, `:74–101`, `:124–133` establishes the default and transport wait. `src/optimus/acp/__main__.py:303–320`, `:370–376`, `:968–971` establishes validation, CLI override and short-wait warning. `README.md:590–598` supplies the operator-facing limitation. The host timeout is not represented as a new end-to-end wall-clock interrupt.

- **Gateway dispatch and deadline boundary.** `src/optimus_gateway/server.py:108–130`, `:210–228` establishes budget lifecycle, request handling and undeliverable replies. `src/optimus_gateway/upstream_client.py:48–66`, `:76–174`, `:278–334`, `:370–385`, `:439–448`, `:492–500` establishes dispatch admission, worker deadlines/cap, retry-report order and delivery classifications. `src/optimus_gateway/responses.py:178–218` and `src/optimus_gateway/decisions.py:86–103` establish dispatch-time checks and unchanged route-specific resend behavior. `src/optimus_gateway/tool_provider_http.py:65–73`, `:102–119` establishes tool-provider participation. Processing can consume budget time without being bounded by that budget; this distinction is explicit in the new text.

- **Executable timing checks identified.** `tests/unit/optimus_gateway/test_upstream_retry.py:358–374`, `:385–505`, `:561–787` identifies shared-default, budget/backoff/observer, dripping-response, late-connect/TLS, DNS/proxy, worker-cap and tool-adapter checks. `tests/unit/optimus_gateway/test_decisions.py:287–295` identifies decision budget refusal; `tests/unit/optimus_gateway/test_server.py:756–834` identifies per-request budgeting and sanitized undeliverable replies. These sources identify executable checks, not new passing runs by this author.

- **#432 ruling.** Searched all baseline-keyed bodies, appended sources and extracted current-PDF text for detector evidence, novelty, fingerprints and unchanged/returned-result claims. Neither edition states the detector's returned-range novelty predicate. Therefore no detector-behavior replacement is needed under D1(a); #432 appears only in the reported #397 evidence. Independently checked `src/optimus/agent/planning_loop.py:238–241`, `:331–350`, `:2010` and `src/optimus/loops/signals.py:47–94`: novelty uses returned coverage, while request identity remains distinct. This avoids importing the full Plan 12.3 detector specification merely because its correction shares PR #437.

- **Evidence record checked.** `docs/sources/p397-escalation/validation-record.md:19–47` supplies heads, full-suite failures and focused deltas; `:49–59` preserves revert checks and the initial surviving gap; `:61–85` supplies scripted versus real-model cases, identities and Z2/Z3 qualifications; `:87–91` supplies USD 0.0587 spend; `:93–116` supplies review dispositions and remaining obligations. `docs/decisions/ADR-029-accepts-adr-009-rung-2-one-escalation.md:81–110` independently retains the scripted-evidence exception and real-model criterion. No external raw evidence was opened, rerun or resealed.

- **GitHub evidence checked read-only.** PR #437 metadata independently matched the code pin and parents. Its guardrails run 40903870999 and job 123553196294 supplied checkout ref `a53b6888708dcfb7c36ac27349ac187f66fdadb0`, Linux/Python identity, exact pytest counts, clean before/after source, active default selection, COMPLETE records, unsupported native/parent/guard capabilities, required product-floor passes and successful full-run coverage validation. Follow-up 1 independently verified main-push guardrails run 40909335091, job 123572690704, completed successfully at actual merge `5977155`; its log records 10,208 passed, 309 skipped, 106 deselected, 1 warning, required product-floor passes and full-run coverage validity. Main run `20261029T161355-2787-7329e8` had clean source before/after, active default selection, COMPLETE records and unsupported Linux native/parent/guard capability. Work status page run 40909335032 also succeeded at that merge. These results are separately attributed from PR CI. #397 was open and labelled `handler:claude` when inspected. No GitHub write occurred.

- **Indexes and existing README narrative.** `docs/README.md:17–24` supplies the edition/amendment/source rows; `:29–30` already indexes the separate #433/#397 evidence bundles. `README.md:259–285`, `:590–598`, `:709–729` already describes recovery, escalation and timing, so its product narrative is unchanged. Its documentation-table rows at `README.md:1057–1058` are replaced. The new source index row applies when Claude files `docs/sources/p397-escalation-successor/` with its sources, tools, README and validation record; it is not a claim that those artifacts were created by this pass.

- **Filing and rendering handoff.** Preserve baseline keys and native carried bodies. Adapt the predecessor assembler/build driver to the new bundle and editions without retaining its hard-coded block count. The rendered NEW text uses plain repository paths and label (URL) citations, avoiding the predecessor renderer's unsupported Markdown-link behavior. Index links remain Markdown because they are repository indexes. Claude must establish ordered rendered-text fidelity, native carry equivalence, predecessor coverage, label/footer presence, deterministic builds, every-page layout and fresh PDF hashes. PDF hook-exemption approval remains pending.

- **Intentionally unchanged and unrun.** No full Plan 12.2 amendment fold-in, full Plan 12.3 refresh, ADR-030 storage text, #434 draft contract, Guardrails rebuild, new model qualification, product execution or live call was performed. Historical baseline/EDIT/Auto evidence retains its pins. No content under `plan12-4-auto\task6\sealed` was read.

## Build strings

- Page-header `LABEL`: `LOCAL FILING - NOT ACTIVATED`
- Footer: `Auto escalation and Gateway timing | 2026-10-29`
- HLD PDF `/Title`: `Optimus - Architecture (HLD) v2.23 - Auto escalation and Gateway timing (local filing - not activated)`
- LLD PDF `/Title`: `Optimus - Low-Level Design v2.46 - Auto escalation and Gateway timing (local filing - not activated)`
- HLD PDF `/Subject`: `Scoped ADR-029 Auto-escalation and host/Gateway timing successor at main 5977155c2bce9728156ee5898ff9e17d0ae08750; mixed historical provenance and controlling unrefreshed Plan 12.2 amendment preserved. Local filing; publication requires separate operator approval.`
- LLD PDF `/Subject`: `One interactive Auto recovery move, binding/application, records and host/Gateway timing contracts at main 5977155c2bce9728156ee5898ff9e17d0ae08750; prior evidence pins and remaining obligations preserved. Local filing; publication requires separate operator approval.`

Not run: source assembly, PDF build/rendering, product tests or new live calls.  
Risk: Claude must verify the filed artifacts; real-model escalation evidence, processing/cancellation limitations and PDF hook-exemption approval remain outstanding.
